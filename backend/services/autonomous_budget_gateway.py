"""Ephemeral metering gateway that enforces a Codex run budget per API call."""

from __future__ import annotations

import json
import secrets
import threading
from dataclasses import dataclass
from decimal import Decimal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections.abc import Callable
from typing import Protocol
from urllib.parse import urlparse

import httpx


class PricingPolicy(Protocol):
    input_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal
    output_usd_per_million: Decimal


@dataclass(frozen=True, slots=True)
class GatewayUsage:
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


class GatewayConfigurationError(RuntimeError):
    pass


class AutonomousBudgetGateway:
    """Proxy Responses API calls while reserving their maximum possible cost."""

    _MAX_REQUEST_BYTES = 10_000_000
    _MAX_RESPONSE_BYTES = 20_000_000
    _INPUT_TOKEN_OVERHEAD = 4096
    _MAX_OUTPUT_TOKENS_PER_CALL = 32_768
    _ALLOWED_REQUEST_FIELDS = frozenset(
        {
            "include",
            "input",
            "instructions",
            "max_output_tokens",
            "max_tool_calls",
            "metadata",
            "model",
            "parallel_tool_calls",
            "prompt_cache_key",
            "prompt_cache_retention",
            "reasoning",
            "safety_identifier",
            "service_tier",
            "store",
            "stream",
            "temperature",
            "text",
            "tool_choice",
            "tools",
            "top_p",
            "truncation",
            "user",
        }
    )

    def __init__(
        self,
        *,
        upstream_base_url: str,
        upstream_api_key: str,
        local_api_key: str,
        expected_model: str,
        expected_reasoning_effort: str,
        budget_usd: Decimal,
        pricing: PricingPolicy,
        usage_recorder: Callable[[GatewayUsage, Decimal], None] | None = None,
        allow_insecure_upstream: bool = False,
    ) -> None:
        parsed = urlparse(upstream_base_url)
        if (
            parsed.scheme
            not in ({"http", "https"} if allow_insecure_upstream else {"https"})
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or not upstream_api_key
            or not local_api_key
            or not expected_model
            or expected_reasoning_effort not in {"medium", "high"}
            or not budget_usd.is_finite()
            or budget_usd <= 0
            or any(
                not rate.is_finite() or rate < 0
                for rate in (
                    pricing.input_usd_per_million,
                    pricing.cached_input_usd_per_million,
                    pricing.output_usd_per_million,
                )
            )
            or pricing.input_usd_per_million <= 0
            or pricing.output_usd_per_million <= 0
            or pricing.cached_input_usd_per_million > pricing.input_usd_per_million
        ):
            raise GatewayConfigurationError("Invalid autonomous budget gateway")
        self.upstream_base_url = upstream_base_url.rstrip("/")
        self.upstream_api_key = upstream_api_key
        self.local_api_key = local_api_key
        self.expected_model = expected_model
        self.expected_reasoning_effort = expected_reasoning_effort
        self.budget_usd = budget_usd
        self.pricing = pricing
        self.usage_recorder = usage_recorder
        self._lock = threading.Lock()
        self._spent = Decimal("0")
        self._reserved = Decimal("0")
        self._input_tokens = 0
        self._output_tokens = 0
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @classmethod
    def create(
        cls,
        *,
        upstream_base_url: str,
        upstream_api_key: str,
        expected_model: str,
        expected_reasoning_effort: str,
        budget_usd: Decimal,
        pricing: PricingPolicy,
        usage_recorder: Callable[[GatewayUsage, Decimal], None] | None = None,
    ) -> AutonomousBudgetGateway:
        return cls(
            upstream_base_url=upstream_base_url,
            upstream_api_key=upstream_api_key,
            local_api_key=secrets.token_urlsafe(32),
            expected_model=expected_model,
            expected_reasoning_effort=expected_reasoning_effort,
            budget_usd=budget_usd,
            pricing=pricing,
            usage_recorder=usage_recorder,
        )

    def start(self) -> tuple[str, str]:
        if self._server is not None:
            raise RuntimeError("Autonomous budget gateway already started")
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                gateway._handle(self)

            def log_message(self, _format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="pwc-autonomous-budget-gateway",
            daemon=True,
        )
        self._thread.start()
        host, port = self._server.server_address
        return f"http://{host}:{port}/v1", self.local_api_key

    def close(self) -> GatewayUsage:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None
        return self.usage()

    def usage(self) -> GatewayUsage:
        with self._lock:
            return GatewayUsage(self._input_tokens, self._output_tokens, self._spent)

    def _handle(self, handler: BaseHTTPRequestHandler) -> None:
        if (
            handler.path.rstrip("/") not in {"/v1/responses", "/responses"}
            or handler.headers.get("Authorization") != f"Bearer {self.local_api_key}"
        ):
            self._error(handler, HTTPStatus.FORBIDDEN, "request_not_allowed")
            return
        try:
            length = int(handler.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= self._MAX_REQUEST_BYTES:
            self._error(
                handler, HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request_too_large"
            )
            return
        body = handler.rfile.read(length)
        try:
            value = json.loads(body)
            encoded, reserved_cost = self._reserve_request(value, len(body))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._error(handler, HTTPStatus.BAD_REQUEST, "invalid_request")
            return
        if encoded is None:
            self._error(handler, HTTPStatus.TOO_MANY_REQUESTS, "budget_exhausted")
            return
        response_body = bytearray()
        try:
            with httpx.Client(
                timeout=120, follow_redirects=False, trust_env=False
            ) as client:
                with client.stream(
                    "POST",
                    f"{self.upstream_base_url}/responses",
                    headers={
                        "Authorization": f"Bearer {self.upstream_api_key}",
                        "Content-Type": "application/json",
                    },
                    content=encoded,
                ) as response:
                    handler.send_response(response.status_code)
                    handler.send_header(
                        "Content-Type",
                        response.headers.get("Content-Type", "application/json"),
                    )
                    handler.end_headers()
                    for chunk in response.iter_bytes():
                        if len(response_body) + len(chunk) > self._MAX_RESPONSE_BYTES:
                            raise RuntimeError("upstream response too large")
                        response_body.extend(chunk)
                        handler.wfile.write(chunk)
                        handler.wfile.flush()
        except (httpx.HTTPError, OSError, RuntimeError):
            self._settle(reserved_cost, None)
            return
        self._settle(reserved_cost, self._extract_usage(bytes(response_body)))

    def _reserve_request(
        self, value: object, body_bytes: int
    ) -> tuple[bytes | None, Decimal]:
        if not isinstance(value, dict):
            raise ValueError("invalid request")
        self._validate_request_scope(value)
        requested_output = value.get(
            "max_output_tokens", self._MAX_OUTPUT_TOKENS_PER_CALL
        )
        if (
            isinstance(requested_output, bool)
            or not isinstance(requested_output, int)
            or requested_output <= 0
        ):
            raise ValueError("invalid output limit")
        input_bound = body_bytes + self._INPUT_TOKEN_OVERHEAD
        input_cost = (
            Decimal(input_bound)
            * self.pricing.input_usd_per_million
            / Decimal(1_000_000)
        )
        with self._lock:
            remaining = self.budget_usd - self._spent - self._reserved - input_cost
            if remaining <= 0:
                return None, Decimal("0")
            affordable_output = int(
                remaining * Decimal(1_000_000) / self.pricing.output_usd_per_million
            )
            output_limit = min(
                requested_output,
                affordable_output,
                self._MAX_OUTPUT_TOKENS_PER_CALL,
            )
            if output_limit <= 0:
                return None, Decimal("0")
            value["max_output_tokens"] = output_limit
            reserved_cost = input_cost + (
                Decimal(output_limit)
                * self.pricing.output_usd_per_million
                / Decimal(1_000_000)
            )
            self._reserved += reserved_cost
            snapshot = GatewayUsage(
                self._input_tokens, self._output_tokens, self._spent
            )
            upper_bound = self._spent + self._reserved
        self._record(snapshot, upper_bound)
        return json.dumps(value, separators=(",", ":")).encode(), reserved_cost

    def _validate_request_scope(self, value: dict[str, object]) -> None:
        if (
            not set(value) <= self._ALLOWED_REQUEST_FIELDS
            or value.get("model") != self.expected_model
            or value.get("background") not in {None, False}
            or value.get("service_tier") not in {None, "default"}
        ):
            raise ValueError("request exceeds reserved scope")
        reasoning = value.get("reasoning")
        if (
            not isinstance(reasoning, dict)
            or reasoning.get("effort") != self.expected_reasoning_effort
        ):
            raise ValueError("request exceeds reserved scope")
        tools = value.get("tools", [])
        if not isinstance(tools, list) or any(
            not isinstance(tool, dict)
            or tool.get("type") not in {"function", "custom", "local_shell"}
            for tool in tools
        ):
            raise ValueError("request exceeds reserved scope")
        stack = [value.get("input")]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                item_type = item.get("type")
                if (
                    item_type in {"input_file", "input_image"}
                    or isinstance(item_type, str)
                    and "reference" in item_type
                    or any(key in item for key in ("file_data", "file_id", "image_url"))
                ):
                    raise ValueError("request exceeds reserved scope")
                stack.extend(item.values())
        value["store"] = False

    def _settle(
        self, reserved_cost: Decimal, usage: tuple[int, int, int] | None
    ) -> None:
        with self._lock:
            self._reserved -= reserved_cost
            if usage is None:
                self._spent += reserved_cost
            else:
                input_tokens, cached_input_tokens, output_tokens = usage
                actual = (
                    Decimal(input_tokens - cached_input_tokens)
                    * self.pricing.input_usd_per_million
                    + Decimal(cached_input_tokens)
                    * self.pricing.cached_input_usd_per_million
                    + Decimal(output_tokens) * self.pricing.output_usd_per_million
                ) / Decimal(1_000_000)
                self._spent += min(actual, reserved_cost)
                if actual > reserved_cost:
                    self._spent = self.budget_usd
                self._input_tokens += input_tokens
                self._output_tokens += output_tokens
            snapshot = GatewayUsage(
                self._input_tokens, self._output_tokens, self._spent
            )
            upper_bound = self._spent + self._reserved
        self._record(snapshot, upper_bound)

    def _record(self, usage: GatewayUsage, upper_bound: Decimal) -> None:
        if self.usage_recorder is not None:
            self.usage_recorder(usage, upper_bound)

    @staticmethod
    def _extract_usage(body: bytes) -> tuple[int, int, int] | None:
        candidates: list[dict[str, object]] = []
        for line in body.decode("utf-8", errors="replace").splitlines():
            line = line.removeprefix("data: ").strip()
            if not line or line == "[DONE]":
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                usage = value.get("usage")
                response = value.get("response")
                if isinstance(usage, dict):
                    candidates.append(usage)
                if isinstance(response, dict) and isinstance(
                    response.get("usage"), dict
                ):
                    candidates.append(response["usage"])
        if not candidates:
            try:
                value = json.loads(body)
            except json.JSONDecodeError:
                return None
            if isinstance(value, dict) and isinstance(value.get("usage"), dict):
                candidates.append(value["usage"])
        if not candidates:
            return None
        usage = candidates[-1]
        values = []
        for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
            token_count = usage.get(key, 0)
            if (
                isinstance(token_count, bool)
                or not isinstance(token_count, int)
                or token_count < 0
            ):
                return None
            values.append(token_count)
        if values[1] > values[0]:
            return None
        return values[0], values[1], values[2]

    @staticmethod
    def _error(handler: BaseHTTPRequestHandler, status: HTTPStatus, code: str) -> None:
        body = json.dumps({"error": {"code": code}}).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
