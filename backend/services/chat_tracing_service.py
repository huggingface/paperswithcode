"""Langfuse tracing for the trusted side of sandboxed chat turns."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from langfuse import Langfuse, propagate_attributes
from langfuse.api.core.api_error import ApiError
from pydantic import ValidationError

from backend.config import Settings, get_settings
from backend.services.autonomous_cron_probe import FindingState, HealthFinding

logger = logging.getLogger(__name__)

SAFE_OBSERVATION_FIELDS = "core,basic,time,metrics"
MAX_OBSERVATION_PAGES = 10
PROVIDER_OUTCOMES = frozenset(
    {
        "provider_error",
        "provider_invalid_request",
        "provider_rate_limit",
        "provider_timeout",
        "provider_unavailable",
        "openai_unavailable",
        "openrouter_unavailable",
        "auth_error",
        "billing_error",
    }
)
AUTH_OUTCOMES = frozenset(
    {
        "openrouter_byok_credential_invalid",
        "provider_auth",
        "provider_authentication_error",
        "provider_unauthorized",
    }
)
BILLING_OUTCOMES = frozenset(
    {
        "hf_inference_billing_exhausted",
        "openrouter_byok_billing_error",
        "openrouter_monthly_budget_exhausted",
        "provider_billing",
        "provider_payment_required",
    }
)


@dataclass(frozen=True, slots=True)
class SafeProviderObservation:
    """Content-free projection of one Langfuse provider request."""

    outcome: str
    ttft_ms: int | None
    duration_ms: int | None


@dataclass(frozen=True, slots=True)
class SafeProviderObservationPage:
    observations: tuple[SafeProviderObservation, ...]
    complete: bool


@dataclass(frozen=True, slots=True)
class SafeChatTurnObservation:
    """Content-free projection of one end-to-end chat turn."""

    outcome: str
    ttft_ms: int | None
    duration_ms: int | None


@dataclass(frozen=True, slots=True)
class SafeChatTurnObservationPage:
    observations: tuple[SafeChatTurnObservation, ...]
    complete: bool


@dataclass(frozen=True, slots=True)
class IncidentTraceContentQuery:
    trace_id: str
    window_start: datetime
    window_end: datetime


_TRACE_CONTENT_PERMIT_TOKEN = object()
_ACTIVE_TRACE_CONTENT_PERMITS: dict[str, datetime] = {}
TRACE_CONTENT_PERMIT_LIFETIME = timedelta(minutes=5)
TRACE_CONTENT_AUDIT_FILENAME = "chat-incident-trace-access-audit.jsonl"


@dataclass(frozen=True, slots=True, init=False)
class IncidentTraceContentPermit:
    incident_signature: str
    query: IncidentTraceContentQuery
    audited_at: datetime
    nonce: str

    def __init__(
        self,
        incident_signature: str,
        query: IncidentTraceContentQuery,
        audited_at: datetime,
        nonce: str,
        *,
        _authorization: object | None = None,
    ) -> None:
        if _authorization is not _TRACE_CONTENT_PERMIT_TOKEN:
            raise PermissionError("use the authorization helper to create a permit")
        object.__setattr__(self, "incident_signature", incident_signature)
        object.__setattr__(self, "query", query)
        object.__setattr__(self, "audited_at", audited_at)
        object.__setattr__(self, "nonce", nonce)


def authorize_incident_trace_content_access(
    *,
    finding: HealthFinding,
    actor: str,
    run_id: uuid.UUID,
    query: IncidentTraceContentQuery,
    now: datetime | None = None,
) -> IncidentTraceContentPermit:
    """Authorize exceptional trace I/O access only after a durable redacted audit."""

    settings = get_settings()
    if finding.state != FindingState.DEGRADED:
        raise PermissionError("a degraded aggregate finding is required")
    if not settings.chat_langfuse_trace_content_access_enabled:
        raise PermissionError("telemetry retention must be disabled")
    if re.fullmatch(r"operator:[A-Za-z0-9._-]{1,200}", actor) is None:
        raise PermissionError("a named operator actor is required")
    if re.fullmatch(r"[0-9a-f]{32}", query.trace_id) is None:
        raise PermissionError("a bounded trace query is required")
    if (
        query.window_start.tzinfo is None
        or query.window_end.tzinfo is None
        or query.window_end <= query.window_start
        or query.window_end - query.window_start > timedelta(hours=1)
    ):
        raise PermissionError("a bounded trace query is required")
    signature = finding.evidence.get("incident_signature")
    if not isinstance(signature, str) or not signature.startswith("chat:"):
        raise PermissionError("a stable incident signature is required")
    finding_start = datetime.fromisoformat(str(finding.evidence["window_start"]))
    finding_end = datetime.fromisoformat(str(finding.evidence["window_end"]))
    if query.window_start < finding_start or query.window_end > finding_end:
        raise PermissionError("trace query exceeds the incident window")
    accessed_at = (now or datetime.now(UTC)).astimezone(UTC)
    record: dict[str, object] = {
        "actor": actor,
        "accessed_at": accessed_at.isoformat(),
        "incident_signature": signature,
        "query": {
            "trace_id": query.trace_id,
            "window_start": query.window_start.isoformat(),
            "window_end": query.window_end.isoformat(),
        },
        "run_id": str(run_id),
    }
    append_incident_trace_access_audit(settings, record)
    nonce = uuid.uuid4().hex
    _ACTIVE_TRACE_CONTENT_PERMITS[nonce] = accessed_at + TRACE_CONTENT_PERMIT_LIFETIME
    return IncidentTraceContentPermit(
        signature,
        query,
        accessed_at,
        nonce,
        _authorization=_TRACE_CONTENT_PERMIT_TOKEN,
    )


def fetch_incident_trace_content(
    permit: IncidentTraceContentPermit,
    *,
    now: datetime | None = None,
) -> Any:
    """Fetch one authorized trace without persisting or projecting its content."""

    settings = get_settings()
    if not settings.chat_langfuse_trace_content_access_enabled:
        raise PermissionError("trace content access is disabled")
    expires_at = _ACTIVE_TRACE_CONTENT_PERMITS.pop(permit.nonce, None)
    if expires_at is None:
        raise PermissionError("trace content permit is single-use")
    accessed_at = (now or datetime.now(UTC)).astimezone(UTC)
    if accessed_at > expires_at:
        raise PermissionError("trace content permit has expired")
    client = configured_chat_client(settings)
    if client is None:
        raise RuntimeError("chat Langfuse client is unavailable")
    trace = client.api.trace.get(
        permit.query.trace_id,
        fields="core,io,observations",
    )
    timestamp = trace.timestamp
    if timestamp.tzinfo is None:
        raise PermissionError("trace timestamp is not timezone-aware")
    observed_at = timestamp.astimezone(UTC)
    if (
        trace.id != permit.query.trace_id
        or trace.environment != settings.environment
        or observed_at < permit.query.window_start
        or observed_at > permit.query.window_end
    ):
        raise PermissionError("trace content exceeds the authorized query")
    return trace


def append_incident_trace_access_audit(
    settings: Settings,
    record: dict[str, object],
) -> None:
    """Append and fsync one private content-free authorization record."""

    directory = Path(settings.cron_log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / TRACE_CONTENT_AUDIT_FILENAME
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    payload = (json.dumps(record, sort_keys=True) + "\n").encode()
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        if os.write(descriptor, payload) != len(payload):
            raise OSError("incident trace audit append was incomplete")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@lru_cache(maxsize=4)
def _client(
    environment: str,
    release: str,
    public_key: str,
    secret_key: str,
    base_url: str,
) -> Langfuse:
    return Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        base_url=base_url,
        environment=environment,
        release=release,
    )


def _configured_client(settings: Settings) -> Langfuse | None:
    if not settings.chat_langfuse_enabled:
        return None
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")
    base_url = os.environ.get("LANGFUSE_BASE_URL", "")
    if not public_key or not secret_key or not base_url:
        logger.warning(
            "chat Langfuse tracing disabled because credentials are incomplete"
        )
        return None
    return _client(
        settings.environment,
        settings.release_id,
        public_key,
        secret_key,
        base_url,
    )


def configured_chat_client(settings: Settings) -> Langfuse | None:
    """Return the server-owned Langfuse client used by chat integrations."""

    return _configured_client(settings)


def _safe_provider_outcome(level: object, status_message: object) -> str:
    value = status_message if isinstance(status_message, str) else ""
    if value in AUTH_OUTCOMES:
        return "auth_error"
    if value in BILLING_OUTCOMES:
        return "billing_error"
    if value in PROVIDER_OUTCOMES:
        if "auth" in value:
            return "auth_error"
        if "billing" in value:
            return "billing_error"
        return "provider_error"
    normalized_level = str(getattr(level, "value", level)).upper()
    return "provider_error" if normalized_level == "ERROR" else "success"


def _safe_turn_outcome(level: object, status_message: object) -> str:
    value = status_message if isinstance(status_message, str) else ""
    if value in AUTH_OUTCOMES:
        return "auth_error"
    if value in BILLING_OUTCOMES:
        return "billing_error"
    if value in PROVIDER_OUTCOMES:
        return "provider_error"
    normalized_level = str(getattr(level, "value", level)).upper()
    if normalized_level == "ERROR":
        return "error"
    if normalized_level == "WARNING" or value in {"interrupted", "stopped"}:
        return "interrupted"
    return "success"


def _milliseconds(value: object) -> int | None:
    if not isinstance(value, (int, float)) or value < 0:
        return None
    return round(float(value) * 1000)


def fetch_provider_request_observations(
    settings: Settings,
    window_start: datetime,
    window_end: datetime,
) -> SafeProviderObservationPage | None:
    """Fetch only content-free Langfuse fields for one bounded probe window."""

    client = configured_chat_client(settings)
    if client is None:
        return None
    cursor: str | None = None
    observations: list[SafeProviderObservation] = []
    try:
        for _page_number in range(MAX_OBSERVATION_PAGES):
            page = client.api.observations.get_many(
                fields=SAFE_OBSERVATION_FIELDS,
                limit=1000,
                cursor=cursor,
                name="provider-request",
                environment=settings.environment,
                from_start_time=window_start,
                to_start_time=window_end,
            )
            observations.extend(
                SafeProviderObservation(
                    outcome=_safe_provider_outcome(row.level, row.status_message),
                    ttft_ms=_milliseconds(row.time_to_first_token),
                    duration_ms=_milliseconds(row.latency),
                )
                for row in page.data
                if row.end_time is not None
            )
            cursor = page.meta.cursor
            if cursor is None:
                return SafeProviderObservationPage(tuple(observations), complete=True)
    except (ApiError, httpx.HTTPError, TypeError, ValueError, ValidationError):
        logger.exception("content-free chat aggregate query failed")
        return None
    return SafeProviderObservationPage(tuple(observations), complete=False)


def fetch_chat_turn_observations(
    settings: Settings,
    window_start: datetime,
    window_end: datetime,
) -> SafeChatTurnObservationPage | None:
    """Fetch sanitized end-to-end turn outcomes without Langfuse I/O fields."""

    client = configured_chat_client(settings)
    if client is None:
        return None
    cursor: str | None = None
    observations: list[SafeChatTurnObservation] = []
    try:
        for _page_number in range(MAX_OBSERVATION_PAGES):
            page = client.api.observations.get_many(
                fields=SAFE_OBSERVATION_FIELDS,
                limit=1000,
                cursor=cursor,
                name="generate-research-response",
                environment=settings.environment,
                from_start_time=window_start,
                to_start_time=window_end,
            )
            for row in page.data:
                if row.end_time is None:
                    continue
                observations.append(
                    SafeChatTurnObservation(
                        outcome=_safe_turn_outcome(row.level, row.status_message),
                        ttft_ms=_milliseconds(row.time_to_first_token),
                        duration_ms=_milliseconds(row.latency),
                    )
                )
            cursor = page.meta.cursor
            if cursor is None:
                return SafeChatTurnObservationPage(tuple(observations), complete=True)
    except (ApiError, httpx.HTTPError, TypeError, ValueError, ValidationError):
        logger.exception("content-free chat turn aggregate query failed")
        return None
    return SafeChatTurnObservationPage(tuple(observations), complete=False)


def _usage_details(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    aliases = {
        "input": ("input_tokens", "inputTokens"),
        "output": ("output_tokens", "outputTokens"),
        "cache_read_input": (
            "cache_read_input_tokens",
            "cacheReadInputTokens",
        ),
        "cache_creation_input": (
            "cache_creation_input_tokens",
            "cacheCreationInputTokens",
        ),
    }
    details: dict[str, int] = {}
    for target, sources in aliases.items():
        count = next(
            (
                candidate
                for source in sources
                if isinstance((candidate := value.get(source)), int) and candidate >= 0
            ),
            None,
        )
        if count is not None:
            details[target] = count
    return details


class ChatTurnTrace:
    """Best-effort observation lifecycle for one research-chat turn."""

    def __init__(
        self,
        root: Any,
        *,
        prompt: str,
        model: str,
        execution_backend: str,
        reasoning_effort: str = "high",
        display_prompt: str | None = None,
        content_free: bool = False,
    ) -> None:
        self.root = root
        self.content_free = content_free
        self.prompt = "" if content_free else prompt
        self.display_prompt = "" if content_free else display_prompt or prompt
        self.execution_backend = execution_backend
        generation_metadata = {
            "aggregation": "agent-run",
            "ttft_semantics": "first-worker-delta",
            "reasoning_effort": reasoning_effort,
        }
        if content_free:
            generation_metadata["content_policy"] = "content-free"
        generation_fields: dict[str, Any] = {
            "name": "generate-research-response",
            "as_type": "generation",
            "model": model,
            "metadata": generation_metadata,
        }
        if not content_free:
            generation_fields["input"] = [{"role": "user", "content": prompt}]
        self.generation = root.start_observation(**generation_fields)
        self.title_generation: Any | None = None
        self.tools: dict[str, Any] = {}
        self.sandbox_acquisition: Any | None = None
        self.capability_installation: Any | None = None
        self.model_dispatch: Any | None = None
        self.first_worker_delta_recorded = False
        self.usage: dict[str, int] = {}
        self.usage_by_phase: dict[str, dict[str, int]] = {}
        self.cost: dict[str, float] = {}
        self.answer = ""
        self.answer_present = False
        self.status = "interrupted"
        self.terminal_code: str | None = None
        self.interruption_reason: str | None = None
        self.warm_assignment_metadata: dict[str, object] = {}
        self.closed = False

    @property
    def trace_id(self) -> str:
        return self.root.trace_id

    def start_title(self, model: str) -> None:
        if getattr(self, "content_free", False):
            return
        if self.title_generation is None:
            self.title_generation = self.root.start_observation(
                name="generate-session-title",
                as_type="generation",
                input=[{"role": "user", "content": self.display_prompt}],
                model=model,
            )

    def finish_title(self, title: str, *, fallback: bool) -> None:
        if self.title_generation is None:
            return
        self.title_generation.update(
            output=title,
            level="WARNING" if fallback else "DEFAULT",
            status_message="deterministic fallback used" if fallback else None,
        ).end()
        self.title_generation = None

    def record_usage(self, event: dict[str, Any]) -> None:
        details = _usage_details(event.get("usage"))
        for key, value in details.items():
            self.usage[key] = self.usage.get(key, 0) + value
        phase = str(event.get("phase") or "research")
        phase_usage = self.usage_by_phase.setdefault(phase, {})
        for key, value in details.items():
            phase_usage[key] = phase_usage.get(key, 0) + value
        cost = event.get("total_cost_usd")
        if isinstance(cost, (int, float)) and cost >= 0:
            self.cost["total"] = self.cost.get("total", 0.0) + float(cost)
        self.generation.update(metadata={"usage_by_phase": self.usage_by_phase})

    def record_citation_metrics(self, metrics: dict[str, int | float]) -> None:
        self.generation.update(metadata={"citation_format": metrics})

    def record_event(self, kind: str, event: dict[str, Any]) -> None:
        """Advance operational spans from sanitized worker lifecycle events."""

        if kind == "sandbox_start" and self.sandbox_acquisition is None:
            self.sandbox_acquisition = self.root.start_observation(
                name="acquire-sandbox",
                as_type="span",
                metadata={"execution_backend": self.execution_backend},
            )
            return
        if kind == "sandbox_ready":
            self._finish_sandbox_acquisition(event)
            if self.capability_installation is None:
                self.capability_installation = self.root.start_observation(
                    name="install-sandbox-capability",
                    as_type="span",
                )
            return
        if kind == "workspace_ready":
            self._finish_model_dispatch()
            return
        if kind in {"reasoning_delta", "tool_call", "tool_call_start", "answer_delta"}:
            self._record_first_worker_delta()
            return
        if kind == "_execution_telemetry":
            self.generation.update(
                metadata={
                    "aggregation": "agent-run",
                    "execution_policy": event,
                }
            )
            return
        if kind != "_latency":
            return

        phase = str(event.get("phase") or "")
        if phase in {"sandbox_acquisition_ms", "sandbox_acquisition_started"}:
            self._finish_sandbox_acquisition(event)
        elif phase in {"capability_install_ms", "broker_capability_installed"}:
            self._finish_capability_installation(event)
        elif phase in {"sdk_dispatch_ms", "sdk_query_dispatched"}:
            self._finish_model_dispatch(event)
        elif phase == "first_worker_delta":
            self._record_first_worker_delta()
        elif phase == "assignment_fallback":
            self.warm_assignment_metadata = {
                "warm_assignment_failure_stage": event.get("failure_stage"),
                "warm_assignment_failure_class": event.get("failure_class"),
                "warm_assignment_attempt_kind": event.get("attempt_kind"),
                "warm_assignment_retry_overhead_ms": event.get("elapsed_ms"),
            }

    def record_guardrail(
        self,
        decision: Any,
        *,
        buffered_events: int,
        buffered_bytes: int,
        cancellation_result: str,
        wasted_usage: dict[str, int] | None = None,
        wasted_cost: float | None = None,
    ) -> None:
        records = list(getattr(decision, "attempt_records", ()))
        for index, attempt in enumerate(records, start=1):
            validated = getattr(attempt, "decision", None) in {"allow", "block"}
            output = None
            if validated:
                output = {
                    "reason": getattr(attempt, "reason", None),
                    "decision": getattr(attempt, "decision", None),
                }
            metadata = {
                "attempt": index,
                "provider": getattr(attempt, "provider", None),
                "latency_ms": getattr(attempt, "latency_ms", None),
                "outcome": getattr(attempt, "outcome", None),
                "retry": index > 1,
                "fail_open": bool(getattr(decision, "fail_open", False)),
                "buffered_events": buffered_events,
                "buffered_bytes": buffered_bytes,
                "cancellation_result": cancellation_result,
                "wasted_main_usage": wasted_usage,
                "wasted_main_cost_usd": wasted_cost,
            }
            observation = self.root.start_observation(
                name="research-scope-guardrail",
                as_type="generation",
                model=getattr(attempt, "model", None),
                metadata=metadata,
            )
            observation.update(
                output=output,
                usage_details={
                    key: value
                    for key, value in {
                        "input": getattr(attempt, "usage_input_tokens", None),
                        "output": getattr(attempt, "usage_output_tokens", None),
                    }.items()
                    if isinstance(value, int)
                }
                or None,
                level="DEFAULT" if validated else "WARNING",
                status_message=str(getattr(attempt, "outcome", "unknown")),
            ).end()

    def _finish_sandbox_acquisition(self, event: dict[str, Any]) -> None:
        if self.sandbox_acquisition is None:
            return
        self.sandbox_acquisition.update(
            output={
                "acquisition_outcome": event.get("acquisition_outcome"),
                "elapsed_ms": event.get("elapsed_ms"),
            }
        ).end()
        self.sandbox_acquisition = None

    def _finish_capability_installation(self, event: dict[str, Any]) -> None:
        if self.capability_installation is not None:
            self.capability_installation.update(
                output={"elapsed_ms": event.get("elapsed_ms")}
            ).end()
            self.capability_installation = None
        if self.model_dispatch is None:
            self.model_dispatch = self.root.start_observation(
                name="dispatch-model-request",
                as_type="span",
            )

    def _finish_model_dispatch(self, event: dict[str, Any] | None = None) -> None:
        if self.model_dispatch is None:
            return
        self.model_dispatch.update(
            output={"elapsed_ms": (event or {}).get("elapsed_ms")}
        ).end()
        self.model_dispatch = None

    def _record_first_worker_delta(self) -> None:
        if self.first_worker_delta_recorded:
            return
        self.first_worker_delta_recorded = True
        self.generation.update(completion_start_time=datetime.now(UTC))

    def start_tool(self, event: dict[str, Any]) -> None:
        tool_id = str(event.get("id") or "")
        if not tool_id or tool_id in self.tools:
            return
        names = {
            "search_papers": "search-papers",
            "Bash": "run-bash-command",
            "Read": "read-file",
            "Grep": "search-files",
            "WebFetch": "fetch-web-page",
        }
        tool_name = str(event.get("name") or "tool")
        observation_type = "retriever" if tool_name == "search_papers" else "tool"
        fields: dict[str, Any] = {
            "name": names.get(tool_name, "use-tool"),
            "as_type": observation_type,
            "metadata": (
                {"content_policy": "content-free"}
                if getattr(self, "content_free", False)
                else {"tool_name": tool_name}
            ),
        }
        if not getattr(self, "content_free", False):
            fields["input"] = event.get("args") or {}
        self.tools[tool_id] = self.root.start_observation(**fields)

    def finish_tool(self, event: dict[str, Any]) -> None:
        tool = self.tools.pop(str(event.get("id") or ""), None)
        if tool is None:
            return
        status = str(event.get("status") or "success")
        fields: dict[str, Any] = {
            "metadata": {"duration_ms": event.get("took_ms", 0)},
            "level": "ERROR" if status == "error" else "DEFAULT",
            "status_message": status,
        }
        if not getattr(self, "content_free", False):
            output = event.get("results")
            if output is None:
                output = event.get("content") or []
            fields["output"] = output
        tool.update(**fields).end()

    def finish(
        self,
        answer: str,
        status: str,
        *,
        terminal_code: str | None = None,
        interruption_reason: str | None = None,
    ) -> None:
        self.answer_present = bool(answer.strip())
        self.answer = "" if getattr(self, "content_free", False) else answer
        self.status = status
        if terminal_code is not None:
            self.terminal_code = terminal_code
        if interruption_reason is not None:
            self.interruption_reason = interruption_reason

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.status == "success" and not self.answer_present:
            self.status = "error"
            self.terminal_code = "empty_assistant_response"
        level = (
            "ERROR"
            if self.status == "error"
            else "WARNING"
            if self.status in {"interrupted", "stopped"}
            else "DEFAULT"
        )
        for observation in (
            self.sandbox_acquisition,
            self.capability_installation,
            self.model_dispatch,
        ):
            if observation is not None:
                observation.update(
                    level="WARNING", status_message="turn ended before phase completed"
                ).end()
        self.sandbox_acquisition = None
        self.capability_installation = None
        self.model_dispatch = None
        for tool in self.tools.values():
            tool.update(
                level="WARNING", status_message="turn ended before tool result"
            ).end()
        self.tools.clear()
        if self.title_generation is not None:
            self.title_generation.update(
                level="WARNING", status_message="title generation did not finish"
            ).end()
            self.title_generation = None
        terminal_metadata = {"terminal_status": self.status}
        if self.terminal_code:
            terminal_metadata["terminal_code"] = self.terminal_code
        if self.interruption_reason:
            terminal_metadata["interruption_reason"] = self.interruption_reason
        terminal_metadata = {**self.warm_assignment_metadata, **terminal_metadata}
        if getattr(self, "content_free", False):
            terminal_metadata["content_policy"] = "content-free"
        status_message = self.terminal_code or self.interruption_reason or self.status
        generation_fields: dict[str, Any] = {
            "usage_details": self.usage or None,
            "cost_details": self.cost or None,
            "level": level,
            "status_message": status_message,
            "metadata": terminal_metadata,
        }
        root_fields: dict[str, Any] = {
            "level": level,
            "status_message": status_message,
            "metadata": terminal_metadata,
        }
        if not getattr(self, "content_free", False):
            output = [{"role": "assistant", "content": self.answer}]
            generation_fields["output"] = output
            root_fields["output"] = output
        self.generation.update(**generation_fields).end()
        self.root.update(**root_fields).end()


class NullChatTurnTrace:
    trace_id = ""

    def start_title(self, _model: str) -> None:
        return

    def finish_title(self, _title: str, *, fallback: bool) -> None:
        del fallback

    def record_usage(self, _event: dict[str, Any]) -> None:
        return

    def record_citation_metrics(self, _metrics: dict[str, int | float]) -> None:
        return

    def record_event(self, _kind: str, _event: dict[str, Any]) -> None:
        return

    def record_guardrail(self, _decision: Any, **_metadata: Any) -> None:
        return

    def start_tool(self, _event: dict[str, Any]) -> None:
        return

    def finish_tool(self, _event: dict[str, Any]) -> None:
        return

    def finish(
        self,
        _answer: str,
        _status: str,
        *,
        terminal_code: str | None = None,
        interruption_reason: str | None = None,
    ) -> None:
        del terminal_code, interruption_reason

    def close(self) -> None:
        return


class ProviderRequestTrace:
    """Content-free Langfuse generation for one gateway provider request."""

    def __init__(
        self,
        observation: Any,
        *,
        started: datetime,
        metadata: dict[str, Any],
    ) -> None:
        self.observation = observation
        self.started = started
        self.metadata = metadata
        self.first_byte_ms: int | None = None
        self.closed = False

    def first_byte(self, elapsed_ms: int) -> None:
        if self.first_byte_ms is not None:
            return
        self.first_byte_ms = elapsed_ms
        try:
            self.observation.update(
                completion_start_time=datetime.now(UTC),
                metadata={**self.metadata, "ttft_ms": elapsed_ms},
            )
        except Exception:
            logger.exception("chat provider-request TTFT tracing failed")

    def finish(
        self,
        *,
        usage: Any,
        status_code: int | None,
        error_code: str | None = None,
        tool_call_returned: bool | None = None,
    ) -> None:
        if self.closed:
            return
        self.closed = True
        usage_details = {
            key: value
            for key, value in {
                "input": getattr(usage, "prompt_tokens", None),
                "output": getattr(usage, "completion_tokens", None),
                "cache_read_input": getattr(usage, "cache_read_tokens", None),
                "cache_creation_input": getattr(usage, "cache_creation_tokens", None),
                "reasoning": getattr(usage, "reasoning_tokens", None),
            }.items()
            if isinstance(value, int)
        }
        cost = getattr(usage, "cost_microusd", None)
        metadata = {
            **self.metadata,
            "duration_ms": round(
                (datetime.now(UTC) - self.started).total_seconds() * 1000
            ),
            "ttft_ms": self.first_byte_ms,
            "http_status": status_code,
            "generation_id": getattr(usage, "generation_id", None),
            "upstream_provider": getattr(usage, "provider", None),
            "actual_service_tier": getattr(usage, "service_tier", None),
            "accounting_state": (
                "reconciled" if isinstance(cost, int) else "cost_unknown"
            ),
            "provider_outcome": getattr(usage, "outcome", None),
            "provider_error_classification": error_code,
            "tool_call_count": getattr(usage, "tool_call_count", None),
        }
        if tool_call_returned is not None:
            metadata["tool_call_returned"] = tool_call_returned
        cancelled = error_code == "openai_stream_cancelled"
        try:
            self.observation.update(
                usage_details=usage_details or None,
                cost_details=(
                    {"total": cost / 1_000_000} if isinstance(cost, int) else None
                ),
                metadata=metadata,
                level=(
                    "WARNING"
                    if cancelled
                    else "ERROR"
                    if error_code or (status_code or 500) >= 400
                    else "DEFAULT"
                ),
                status_message=(
                    error_code or (str(status_code) if status_code else None)
                ),
            ).end()
        except Exception:
            logger.exception("chat provider-request Langfuse finalization failed")


class NullProviderRequestTrace:
    def first_byte(self, _elapsed_ms: int) -> None:
        return

    def finish(
        self,
        *,
        usage: Any,
        status_code: int | None,
        error_code: str | None = None,
        tool_call_returned: bool | None = None,
    ) -> None:
        del usage, status_code, error_code, tool_call_returned


def start_provider_request_trace(
    *,
    settings: Settings,
    trace_id: str | None,
    turn_id: str,
    call_sequence: int,
    model: str,
    provider_mode: str,
    reasoning_effort: str,
    public_model_id: str | None = None,
    routing_policy: str = "throughput",
    service_tier: str | None = None,
    accounting_call_id: str | None = None,
    reserved_microusd: int | None = None,
    offered_tool_count: int | None = None,
    offered_tool_names: list[str] | None = None,
    offered_tool_digest: str | None = None,
    mcp_provider_states: dict[str, str] | None = None,
) -> ProviderRequestTrace | NullProviderRequestTrace:
    if not trace_id:
        return NullProviderRequestTrace()
    try:
        client = _configured_client(settings)
        if client is None:
            return NullProviderRequestTrace()
        started = datetime.now(UTC)
        metadata = {
            "aggregation": "provider-request",
            "turn_id": turn_id,
            "model_round": call_sequence,
            "provider_mode": provider_mode,
            "reasoning_effort": reasoning_effort,
            "routing_policy": routing_policy,
        }
        if public_model_id is not None:
            metadata["public_model_id"] = public_model_id
        if service_tier is not None:
            metadata["service_tier"] = service_tier
        if accounting_call_id is not None:
            metadata["accounting_call_id"] = accounting_call_id
        if reserved_microusd is not None:
            metadata["reserved_microusd"] = reserved_microusd
        if offered_tool_count is not None:
            metadata["offered_tool_count"] = offered_tool_count
        if offered_tool_names is not None:
            metadata["offered_tool_names"] = offered_tool_names
        if offered_tool_digest is not None:
            metadata["offered_tool_digest"] = offered_tool_digest
        if mcp_provider_states is not None:
            metadata["mcp_provider_states"] = mcp_provider_states
        observation = client.start_observation(
            trace_context={"trace_id": trace_id},
            name="provider-request",
            as_type="generation",
            model=model,
            metadata=metadata,
        )
        return ProviderRequestTrace(observation, started=started, metadata=metadata)
    except Exception:
        logger.exception("chat provider-request Langfuse initialization failed")
        return NullProviderRequestTrace()


@contextmanager
def trace_chat_turn(
    *,
    settings: Settings,
    request_id: str,
    session_id: str,
    user_id: str,
    prompt: str,
    model: str,
    execution_backend: str,
    is_replacement: bool,
    display_prompt: str | None = None,
    reasoning_effort: str = "high",
    content_free: bool = False,
) -> Iterator[ChatTurnTrace | NullChatTurnTrace]:
    """Create one trace per turn and one Langfuse session per conversation."""

    try:
        client = _configured_client(settings)
    except Exception:
        logger.exception("chat Langfuse client initialization failed")
        client = None
    if client is None:
        yield NullChatTurnTrace()
        return
    pseudonymous_user = hashlib.sha256(user_id.encode()).hexdigest()
    trace_id = client.create_trace_id(seed=request_id)
    trace: ChatTurnTrace | None = None
    try:
        propagation_metadata = {
            "request_id": request_id,
            "execution_backend": execution_backend,
            "is_replacement": str(is_replacement).lower(),
            "reasoning_effort": reasoning_effort,
        }
        if content_free:
            propagation_metadata["content_policy"] = "content-free"
        with propagate_attributes(
            user_id=pseudonymous_user,
            session_id=session_id,
            metadata=propagation_metadata,
            version=settings.release_id,
            tags=[
                "chat",
                "research-assistant",
                execution_backend,
                *(["content-free"] if content_free else []),
            ],
            trace_name="answer-research-question",
            environment=settings.environment,
        ):
            root_fields: dict[str, Any] = {
                "trace_context": {"trace_id": trace_id},
                "name": "answer-research-question",
                "as_type": "agent",
                "metadata": {
                    "request_id": request_id,
                    **({"content_policy": "content-free"} if content_free else {}),
                },
            }
            if not content_free:
                root_fields["input"] = [{"role": "user", "content": prompt}]
            root = client.start_observation(**root_fields)
            trace = ChatTurnTrace(
                root,
                prompt=prompt,
                display_prompt=display_prompt or prompt,
                model=model,
                execution_backend=execution_backend,
                reasoning_effort=reasoning_effort,
                content_free=content_free,
            )
            try:
                yield trace
            except BaseException as exc:
                if isinstance(exc, Exception):
                    trace.finish(trace.answer, "error")
                elif trace.status == "interrupted":
                    trace.finish(trace.answer, "interrupted")
                raise
            finally:
                try:
                    trace.close()
                except Exception:
                    logger.exception(
                        "chat Langfuse trace finalization failed request_id=%s",
                        request_id,
                    )
                logger.info(
                    "chat Langfuse trace complete request_id=%s trace_id=%s",
                    request_id,
                    trace.trace_id,
                )
    except BaseException:
        if trace is None:
            logger.exception("chat Langfuse trace initialization failed")
            yield NullChatTurnTrace()
            return
        raise
