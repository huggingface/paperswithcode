"""Dependency-free contracts shared by the staging chat load-test adapter."""

from __future__ import annotations

import json
import math
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

STAGING_ORIGIN = "https://staging.paperswithcode.co"
STAGING_RUNTIME_ENV_PATH = Path("/etc/paperswithcode/staging.env")
CONFIRMATION = "RUN_BOUNDED_STAGING_CHAT_LOAD"
MAX_CHECKPOINT_USERS = 2
MAX_PROMPT_CHARS = 1024
MAX_OUTPUT_CHARS = 64 * 1024
MAX_PROTECTED_ENV_BYTES = 1024 * 1024
QUALIFIED_PROVIDER_MODELS = {
    "gpt-5.6-luna@openai": "PWC_CHAT_OPENAI_DAILY_BUDGET_USD",
}
SAFE_CLI_COMMAND = "pwc paper info 1706.03762"


class RunRefused(ValueError):
    """The operator configuration does not satisfy the staging safety gate."""


@dataclass(frozen=True)
class LoadProfile:
    name: str
    users: int
    spawn_rate: float
    cohort: str
    metric_label: str
    same_account: bool = False
    executable: bool = True


@dataclass(frozen=True)
class RunConfig:
    host: str
    profile: LoadProfile
    synthetic_cookies: tuple[str, ...]
    max_users: int
    max_spend_usd: float
    protected_spend_cap_usd: float | None
    initial_model: str | None
    max_prompt_chars: int
    max_output_chars: int


PROFILES = {
    "bridge-smoke": LoadProfile(
        "bridge-smoke", 2, 2.0, "durable-bridge", "bridge_smoke"
    ),
    "steady-10": LoadProfile("steady-10", 10, 1.0, "stream", "steady_10"),
    "steady-25": LoadProfile("steady-25", 25, 2.0, "stream", "steady_25"),
    "steady-50": LoadProfile("steady-50", 50, 5.0, "stream", "steady_50"),
    "steady-100": LoadProfile("steady-100", 100, 10.0, "stream", "steady_100"),
    "burst": LoadProfile("burst", 25, 25.0, "stream", "burst"),
    "same-account-contention": LoadProfile(
        "same-account-contention",
        2,
        2.0,
        "stream",
        "same_account_contention",
        same_account=True,
    ),
    "reconnect": LoadProfile("reconnect", 2, 1.0, "reconnect", "reconnect"),
    "safe-cli": LoadProfile("safe-cli", 2, 1.0, "stream", "safe_cli"),
    "general-bash": LoadProfile("general-bash", 2, 1.0, "stream", "general_bash"),
    "overload": LoadProfile("overload", 3, 3.0, "stream", "overload"),
    "connection-only": LoadProfile(
        "connection-only",
        2,
        1.0,
        "sse-connection",
        "connection_only",
        executable=False,
    ),
    "availability-connectivity": LoadProfile(
        "availability-connectivity", 2, 1.0, "availability", "availability_connectivity"
    ),
}

_PROMPTS = {
    "safe-cli": (
        "Run exactly this read-only command exactly once: "
        f"`{SAFE_CLI_COMMAND}`. Do not run any other command."
    ),
    "general-bash": "Run `printf loadtest-ready` once, then report only the exit code.",
    "reconnect": "Reply with READY only. Do not call tools.",
    "same-account-contention": "Reply with READY only. Do not call tools.",
    "overload": "Reply with READY only. Do not call tools.",
    "stream": "Reply with READY only. Do not call tools.",
}


def _required(environment: Mapping[str, str], name: str, description: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise RunRefused(f"explicit {description} is required")
    return value


def _positive_int(raw: str, description: str, *, maximum: int) -> int:
    try:
        value = int(raw)
    except ValueError as error:
        raise RunRefused(f"{description} must be an integer") from error
    if not 1 <= value <= maximum:
        raise RunRefused(f"{description} must be between 1 and {maximum}")
    return value


@dataclass(frozen=True)
class ProtectedBudget:
    key: str
    usd: Decimal


def read_authoritative_budget(
    path: Path,
    *,
    expected_path: Path,
    expected_owner_uid: int,
    required_key: str,
) -> ProtectedBudget:
    """Read one nonsecret budget from an exact, protected runtime env file."""

    if path != expected_path:
        raise RunRefused("budget must use the exact protected staging runtime path")
    try:
        before = path.lstat()
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
    except OSError as error:
        raise RunRefused("authoritative staging budget file is unavailable") from error
    try:
        opened = os.fstat(descriptor)
        secure_metadata = (
            stat.S_ISREG(before.st_mode)
            and stat.S_ISREG(opened.st_mode)
            and (before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino)
            and opened.st_uid == expected_owner_uid
            and opened.st_mode & 0o022 == 0
        )
        if not secure_metadata:
            raise RunRefused("protected staging runtime file metadata is invalid")
        total_bytes = 0
        pending = bytearray()
        values: list[str] = []
        while True:
            chunk = os.read(descriptor, 4096)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_PROTECTED_ENV_BYTES:
                raise RunRefused("protected staging runtime file is too large")
            pending.extend(chunk)
            while b"\n" in pending:
                raw_line, _, remainder = pending.partition(b"\n")
                pending = bytearray(remainder)
                _collect_budget_value(raw_line, required_key, values)
        if pending:
            _collect_budget_value(bytes(pending), required_key, values)
    except OSError as error:
        raise RunRefused("authoritative staging budget file is unreadable") from error
    finally:
        os.close(descriptor)
    if len(values) != 1:
        raise RunRefused("protected daily budget key must occur exactly once")
    try:
        budget = Decimal(values[0])
    except InvalidOperation as error:
        raise RunRefused(
            "protected daily budget must be finite and positive"
        ) from error
    if not budget.is_finite() or budget <= 0:
        raise RunRefused("protected daily budget must be finite and positive")
    return ProtectedBudget(required_key, budget)


def _collect_budget_value(
    raw_line: bytes, required_key: str, values: list[str]
) -> None:
    try:
        line = raw_line.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise RunRefused("protected staging runtime file is invalid") from error
    if not line or line.startswith("#") or "=" not in line:
        return
    name, value = line.split("=", 1)
    if name.strip() == required_key:
        values.append(value.strip())


def load_run_config(
    environment: Mapping[str, str],
    *,
    budget_path: Path | None = None,
    expected_budget_path: Path | None = None,
    expected_budget_owner_uid: int = 0,
) -> RunConfig:
    """Validate the complete fail-closed operator envelope from environment."""

    host = _required(environment, "PWC_LOADTEST_HOST", "host")
    if host != STAGING_ORIGIN:
        raise RunRefused(f"host must be the exact staging origin {STAGING_ORIGIN}")
    confirmation = _required(environment, "PWC_LOADTEST_CONFIRM", "confirmation")
    if confirmation != CONFIRMATION:
        raise RunRefused(f"confirmation must equal {CONFIRMATION}")
    profile_name = _required(environment, "PWC_LOADTEST_PROFILE", "profile selection")
    try:
        profile = PROFILES[profile_name]
    except KeyError as error:
        raise RunRefused("profile selection is not recognized") from error
    if not profile.executable or profile.users > MAX_CHECKPOINT_USERS:
        raise RunRefused(
            f"profile {profile.name} is definition-only at this checkpoint"
        )

    raw_cookies = _required(
        environment,
        "PWC_LOADTEST_SYNTHETIC_COOKIES",
        "dedicated synthetic session cookies",
    )
    try:
        cookies = json.loads(raw_cookies)
    except json.JSONDecodeError as error:
        raise RunRefused("synthetic session cookies must be a JSON array") from error
    if (
        not isinstance(cookies, list)
        or not cookies
        or not all(isinstance(cookie, str) and cookie.strip() for cookie in cookies)
    ):
        raise RunRefused("dedicated synthetic session cookies are required")
    synthetic_cookies = tuple(cookie.strip() for cookie in cookies)
    required_cookies = 1 if profile.same_account else profile.users
    if len(synthetic_cookies) < required_cookies:
        raise RunRefused(
            f"profile requires at least {required_cookies} synthetic session cookies"
        )
    if not profile.same_account and len(set(synthetic_cookies)) < required_cookies:
        raise RunRefused(
            f"profile requires at least {required_cookies} distinct synthetic session cookies"
        )

    max_users = _positive_int(
        _required(environment, "PWC_LOADTEST_MAX_USERS", "user envelope"),
        "user envelope",
        maximum=MAX_CHECKPOINT_USERS,
    )
    if max_users < profile.users:
        raise RunRefused("user envelope is below the selected profile")
    raw_spend = _required(environment, "PWC_LOADTEST_MAX_SPEND_USD", "spend envelope")
    try:
        max_spend_usd = float(raw_spend)
    except ValueError as error:
        raise RunRefused("spend envelope must be numeric") from error
    if not math.isfinite(max_spend_usd):
        raise RunRefused("spend envelope must be finite")
    if max_spend_usd < 0 or max_spend_usd > 10:
        raise RunRefused("spend envelope must be between 0 and 10 USD")
    protected_spend_cap_usd: float | None = None
    initial_model: str | None = None
    if profile.cohort in {"durable-bridge", "availability", "sse-connection"}:
        if max_spend_usd != 0:
            raise RunRefused("model-free profiles require a zero spend envelope")
        if environment.get("PWC_LOADTEST_MODEL", "").strip():
            raise RunRefused("model-free profile cannot select a model")
    else:
        if max_spend_usd <= 0:
            raise RunRefused("stream profiles require a positive spend envelope")
        initial_model = _required(
            environment, "PWC_LOADTEST_MODEL", "reviewed provider model"
        )
        try:
            required_budget_key = QUALIFIED_PROVIDER_MODELS[initial_model]
        except KeyError as error:
            raise RunRefused(
                "provider model is not supported by this checkpoint"
            ) from error
        if budget_path is None or expected_budget_path is None:
            raise RunRefused("authoritative staging budget file is required")
        protected_budget = read_authoritative_budget(
            budget_path,
            expected_path=expected_budget_path,
            expected_owner_uid=expected_budget_owner_uid,
            required_key=required_budget_key,
        )
        declared_spend = Decimal(raw_spend)
        if protected_budget.usd != declared_spend:
            raise RunRefused(
                "protected daily spend cap does not match declared envelope"
            )
        protected_spend_cap_usd = float(protected_budget.usd)

    max_prompt_chars = _positive_int(
        _required(environment, "PWC_LOADTEST_MAX_PROMPT_CHARS", "prompt bound"),
        "prompt bound",
        maximum=MAX_PROMPT_CHARS,
    )
    max_output_chars = _positive_int(
        _required(environment, "PWC_LOADTEST_MAX_OUTPUT_CHARS", "output bound"),
        "output bound",
        maximum=MAX_OUTPUT_CHARS,
    )
    return RunConfig(
        host=host,
        profile=profile,
        synthetic_cookies=synthetic_cookies,
        max_users=max_users,
        max_spend_usd=max_spend_usd,
        protected_spend_cap_usd=protected_spend_cap_usd,
        initial_model=initial_model,
        max_prompt_chars=max_prompt_chars,
        max_output_chars=max_output_chars,
    )


def build_turn_request(
    profile: LoadProfile,
    *,
    client_message_id: str,
    max_prompt_chars: int,
    initial_model: str | None = None,
) -> dict[str, object]:
    """Build one bounded synthetic turn for executable future profiles."""

    if profile.cohort in {"durable-bridge", "availability", "sse-connection"}:
        raise RunRefused("profile does not admit chat turns")
    if initial_model not in QUALIFIED_PROVIDER_MODELS:
        raise RunRefused("provider model is not supported by this checkpoint")
    prompt = _PROMPTS.get(profile.name, _PROMPTS["stream"])
    if len(prompt) > max_prompt_chars:
        raise RunRefused("profile prompt fixture exceeds the configured prompt bound")
    return {
        "message": prompt,
        "session_id": None,
        "client_message_id": client_message_id,
        "web_search_enabled": False,
        "reasoning_effort": "low",
        "initial_model": initial_model,
    }


class SSEParseError(ValueError):
    """A bounded, content-free SSE protocol failure."""


class SSEParser:
    """Incrementally parse JSON objects from SSE ``data`` fields."""

    def __init__(self, *, max_event_bytes: int = 128 * 1024) -> None:
        if max_event_bytes < 1:
            raise ValueError("max_event_bytes must be positive")
        self._maximum = max_event_bytes
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[dict[str, Any]]:
        self._buffer.extend(chunk)
        events: list[dict[str, Any]] = []
        while True:
            normalized = bytes(self._buffer).replace(b"\r\n", b"\n")
            separator = normalized.find(b"\n\n")
            if separator < 0:
                if len(self._buffer) > self._maximum:
                    raise SSEParseError(f"SSE event exceeds {self._maximum} bytes")
                return events
            raw = normalized[:separator]
            consumed = self._consumed_bytes(separator + 2)
            del self._buffer[:consumed]
            if len(raw) > self._maximum:
                raise SSEParseError(f"SSE event exceeds {self._maximum} bytes")
            parsed = self._parse_frame(raw)
            if parsed is not None:
                events.append(parsed)

    def close(self) -> list[dict[str, Any]]:
        if not self._buffer:
            return []
        normalized = bytes(self._buffer).replace(b"\r\n", b"\n")
        self._buffer.clear()
        if len(normalized) > self._maximum:
            raise SSEParseError(f"SSE event exceeds {self._maximum} bytes")
        parsed = self._parse_frame(normalized)
        return [] if parsed is None else [parsed]

    def _consumed_bytes(self, normalized_length: int) -> int:
        consumed = 0
        normalized = 0
        data = self._buffer
        while consumed < len(data) and normalized < normalized_length:
            if (
                data[consumed] == 13
                and consumed + 1 < len(data)
                and data[consumed + 1] == 10
            ):
                consumed += 2
            else:
                consumed += 1
            normalized += 1
        return consumed

    @staticmethod
    def _parse_frame(raw: bytes) -> dict[str, Any] | None:
        data_lines = []
        for line in raw.split(b"\n"):
            if not line.startswith(b"data:"):
                continue
            value = line[5:]
            if value.startswith(b" "):
                value = value[1:]
            data_lines.append(value)
        data = b"\n".join(data_lines)
        if not data or data == b"[DONE]":
            return None
        try:
            event = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SSEParseError("SSE data is not valid JSON") from error
        if not isinstance(event, dict):
            raise SSEParseError("SSE data must be a JSON object")
        return event


def classify_event(event: Mapping[str, Any]) -> str:
    """Return a fixed-cardinality metric label for a parsed public event."""

    event_type = event.get("type")
    if event_type == "stream_start":
        return "admission"
    if event_type == "done":
        return "terminal"
    if event_type == "error":
        code = event.get("code")
        if code == "account_busy":
            return "account_busy"
        if code in {"chat_overload", "chat_capacity"}:
            return "overload"
        return "stream_error"
    return "event"


def classify_refusal(payload: object) -> str:
    """Classify an HTTP error body without using its unbounded message text."""

    if not isinstance(payload, Mapping):
        return "stream_error"
    detail = payload.get("detail")
    if not isinstance(detail, Mapping):
        return "stream_error"
    code = detail.get("code")
    if code == "account_busy":
        return "account_busy"
    if code in {"chat_overload", "chat_capacity"}:
        return "overload"
    return "stream_error"


def classify_refusal_bytes(data: bytes, *, max_bytes: int = 4096) -> str:
    """Parse a bounded HTTP refusal body into a fixed-cardinality label."""

    if len(data) > max_bytes:
        return "stream_error"
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "stream_error"
    return classify_refusal(payload)


@dataclass(frozen=True)
class Metric:
    name: str
    elapsed_ms: int
    success: bool


def validate_runtime_shape(
    profile: LoadProfile, *, users: int | None, spawn_rate: float | None
) -> None:
    """Require Locust's effective shape to exactly match the named profile."""

    if users != profile.users:
        raise RunRefused(f"Locust users must equal profile size {profile.users}")
    if spawn_rate is None or not math.isclose(
        spawn_rate, profile.spawn_rate, rel_tol=0, abs_tol=1e-9
    ):
        raise RunRefused(
            f"Locust spawn rate must equal profile rate {profile.spawn_rate}"
        )


class ProfileObservationTracker:
    """Verify profile-specific behavior with fixed-cardinality metrics."""

    def __init__(self, profile: LoadProfile) -> None:
        self._safe_cli = profile.name == "safe-cli"
        self._observed = False
        self._invalid_tool = False
        self._observed_ids: set[str] = set()
        self._finished = False

    def observe(self, event: Mapping[str, Any], *, elapsed_ms: int) -> list[Metric]:
        if not self._safe_cli or self._finished:
            return []
        event_type = event.get("type")
        arguments = event.get("args", event.get("input"))
        if event_type in {"tool_call", "tool_call_arguments_done"}:
            event_id = event.get("id")
            identity = (
                event_id if isinstance(event_id, str) else f"anonymous-{id(event)}"
            )
            if identity not in self._observed_ids:
                self._observed_ids.add(identity)
                exact = (
                    event.get("name") == "Bash"
                    and isinstance(arguments, Mapping)
                    and arguments.get("command") == SAFE_CLI_COMMAND
                )
                if exact and not self._observed:
                    self._observed = True
                    return [Metric("chat.safe_cli_command", elapsed_ms, True)]
                self._invalid_tool = True
        if event_type in {"done", "error"}:
            self._finished = True
            metrics: list[Metric] = []
            if not self._observed:
                metrics.append(Metric("chat.safe_cli_command", elapsed_ms, False))
            metrics.append(
                Metric(
                    "chat.safe_cli_contract",
                    elapsed_ms,
                    self._observed and not self._invalid_tool and event_type == "done",
                )
            )
            return metrics
        return []


class StreamMetricTracker:
    """Derive explicit milestones; never infer terminal time from HTTP timing."""

    def __init__(
        self,
        *,
        first_event_name: str = "chat.first_event",
        record_admission: bool = True,
    ) -> None:
        self._saw_event = False
        self._first_event_name = first_event_name
        self._record_admission = record_admission

    def observe(self, event: Mapping[str, Any], *, elapsed_ms: int) -> list[Metric]:
        metrics: list[Metric] = []
        if not self._saw_event:
            self._saw_event = True
            metrics.append(Metric(self._first_event_name, elapsed_ms, True))
        classification = classify_event(event)
        if classification == "admission" and self._record_admission:
            metrics.append(Metric("chat.admission", elapsed_ms, True))
        elif classification == "terminal":
            metrics.append(Metric("chat.terminal", elapsed_ms, True))
        elif classification in {"stream_error", "account_busy", "overload"}:
            metrics.append(Metric(f"chat.{classification}", elapsed_ms, False))
        return metrics


@dataclass(frozen=True)
class StreamBatch:
    events: list[dict[str, Any]]
    metrics: list[Metric]


class BoundedSSEStream:
    """Apply identical parsing, output, and terminal rules to an SSE stream."""

    def __init__(self, *, max_output_chars: int, replay: bool = False) -> None:
        self._parser = SSEParser(max_event_bytes=max(4096, max_output_chars * 2))
        self._tracker = StreamMetricTracker(
            first_event_name="chat.first_replay" if replay else "chat.first_event",
            record_admission=not replay,
        )
        self._maximum_output = max_output_chars
        self._output_chars = 0
        self._finished = False
        self._successful_terminal = False

    @property
    def finished(self) -> bool:
        return self._finished

    @property
    def successful_terminal(self) -> bool:
        return self._successful_terminal

    def feed(self, chunk: bytes, *, elapsed_ms: int) -> StreamBatch:
        if self._finished:
            raise SSEParseError("SSE event arrived after terminal event")
        return self._observe(self._parser.feed(chunk), elapsed_ms=elapsed_ms)

    def close(self, *, elapsed_ms: int) -> StreamBatch:
        if self._finished:
            return StreamBatch([], [])
        return self._observe(self._parser.close(), elapsed_ms=elapsed_ms)

    def _observe(self, events: list[dict[str, Any]], *, elapsed_ms: int) -> StreamBatch:
        metrics: list[Metric] = []
        for event in events:
            metrics.extend(self._tracker.observe(event, elapsed_ms=elapsed_ms))
            event_type = event.get("type")
            if event_type in {"answer_delta", "reasoning_delta"}:
                text = event.get("text")
                self._output_chars += len(text) if isinstance(text, str) else 0
                if self._output_chars > self._maximum_output:
                    raise SSEParseError("stream output exceeded configured bound")
            if event_type in {"done", "error"}:
                self._finished = True
                self._successful_terminal = event_type == "done"
                break
        return StreamBatch(events, metrics)
