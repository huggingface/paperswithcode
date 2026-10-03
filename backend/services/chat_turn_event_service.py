"""Immutable typed chat-turn events and lifecycle transitions.

Raw adapters normalize into this contract once. Compatibility serializers
retain exact wire shape at tracing, projection, and public output boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Final, TypeAlias, ClassVar


class _Unset:
    pass


UNSET: Final = _Unset()
JsonValue: TypeAlias = str | int | float | bool | None | list[Any] | dict[str, Any]
FrozenJson: TypeAlias = str | int | float | bool | None | tuple[Any, ...]
FrozenExtras: TypeAlias = tuple[tuple[str, FrozenJson], ...]


def _freeze(value: JsonValue | FrozenJson) -> FrozenJson:
    if isinstance(value, tuple):
        return value
    if isinstance(value, dict):
        return ("dict", tuple((key, _freeze(item)) for key, item in value.items()))
    if isinstance(value, list):
        return ("list", tuple(_freeze(item) for item in value))
    return value


def _thaw(value: FrozenJson) -> JsonValue:
    if isinstance(value, tuple) and len(value) == 2 and value[0] == "dict":
        return {str(key): _thaw(item) for key, item in value[1]}
    if isinstance(value, tuple) and len(value) == 2 and value[0] == "list":
        return [_thaw(item) for item in value[1]]
    return value


def _extras(event: dict[str, Any], *known: str) -> FrozenExtras:
    return tuple(
        (key, _freeze(value))
        for key, value in event.items()
        if key != "type" and key not in known
    )


def _legacy(
    event_type: str,
    extras: FrozenExtras,
    field_order: tuple[str, ...] = (),
    **fields: JsonValue | FrozenJson | _Unset,
) -> dict[str, Any]:
    if any(key == "type" for key, _value in extras):
        raise ValueError("Legacy extras cannot override an event type")
    values = {"type": event_type, **{key: _thaw(value) for key, value in extras}}
    for key, value in fields.items():
        if value is not UNSET:
            values[key] = _thaw(value)
    if field_order:
        return {key: values[key] for key in field_order if key in values}
    return values


class TerminalOutcome(StrEnum):
    SUCCESS = "success"
    MAX_TURNS = "max_turns"
    TOOL_LIMIT = "tool_limit"
    SCOPE_BLOCKED = "scope_blocked"
    STOPPED = "stopped"


class InterruptionReason(StrEnum):
    CLIENT_DISCONNECT = "client_disconnect"
    STREAM_CLOSED = "stream_closed"
    STREAM_CANCELLED = "stream_cancelled"
    WORKER_CANCELLED = "worker_cancelled"


class TurnTerminalState(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    COMPLETED_DEGRADED = "completed_degraded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class TurnFinalizationState(StrEnum):
    RUNNING = "running"
    AWAITING_PRODUCERS = "awaiting_producers"
    FINALIZED = "finalized"


class PersistedTurnStatus(StrEnum):
    COMPLETE = "complete"
    ERROR = "error"
    INTERRUPTED = "interrupted"


class ArtifactEventType(StrEnum):
    START = "artifact_start"
    READY = "artifact_ready"
    ERROR = "artifact_error"


@dataclass(frozen=True)
class ResearchFinishedEvent:
    event_type: ClassVar[str] = "_research_finished"
    extras: FrozenExtras = ()
    field_order: tuple[str, ...] = ()

    def to_legacy(self) -> dict[str, Any]:
        return _legacy("_research_finished", self.extras, self.field_order)


@dataclass(frozen=True)
class TitleEvent:
    event_type: ClassVar[str] = "session_title_done"
    title: str | None | _Unset = UNSET
    extras: FrozenExtras = ()
    field_order: tuple[str, ...] = ()

    def to_legacy(self) -> dict[str, Any]:
        return _legacy(
            "session_title_done", self.extras, self.field_order, title=self.title
        )


@dataclass(frozen=True)
class TitleFinishedEvent:
    event_type: ClassVar[str] = "_title_finished"
    extras: FrozenExtras = ()
    field_order: tuple[str, ...] = ()

    def to_legacy(self) -> dict[str, Any]:
        return _legacy("_title_finished", self.extras, self.field_order)


@dataclass(frozen=True)
class PersistenceEvent:
    event_type: ClassVar[str] = "_sdk_session"
    session_id: str | None | _Unset = UNSET
    extras: FrozenExtras = ()
    field_order: tuple[str, ...] = ()

    def to_legacy(self) -> dict[str, Any]:
        return _legacy(
            "_sdk_session", self.extras, self.field_order, session_id=self.session_id
        )


@dataclass(frozen=True)
class MirrorFailureEvent:
    event_type: ClassVar[str] = "_mirror_error"
    key: FrozenJson | _Unset = UNSET
    error: str | None | _Unset = UNSET
    terminal: FrozenJson | _Unset = UNSET
    result_available: bool | None | _Unset = UNSET
    extras: FrozenExtras = ()
    field_order: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.key is not UNSET:
            object.__setattr__(self, "key", _freeze(self.key))
        if self.terminal is not UNSET:
            object.__setattr__(self, "terminal", _freeze(self.terminal))

    def completed_result(self) -> TerminalOutcome | None:
        terminal = _thaw(self.terminal) if self.terminal is not UNSET else None
        if self.result_available is not True or not isinstance(terminal, dict):
            return None
        if terminal.get("type") != "done":
            return None
        try:
            return TerminalOutcome(terminal.get("finish_reason", "success"))
        except (TypeError, ValueError):
            return None

    def to_legacy(self) -> dict[str, Any]:
        return _legacy(
            "_mirror_error",
            self.extras,
            self.field_order,
            key=self.key,
            error=self.error,
            terminal=self.terminal,
            result_available=self.result_available,
        )


@dataclass(frozen=True)
class TelemetryEvent:
    event_type: ClassVar[str] = "_execution_telemetry"
    maximum_tool_rounds: int | None | _Unset = UNSET
    maximum_tool_calls: int | None | _Unset = UNSET
    tool_rounds_executed: int | None | _Unset = UNSET
    tool_calls_allowed: int | None | _Unset = UNSET
    execution_limit_reached: bool | None | _Unset = UNSET
    finalizer_attempted: bool | None | _Unset = UNSET
    finalizer_outcome: str | None | _Unset = UNSET
    extras: FrozenExtras = ()
    field_order: tuple[str, ...] = ()

    def to_legacy(self) -> dict[str, Any]:
        return _legacy(
            "_execution_telemetry",
            self.extras,
            self.field_order,
            maximum_tool_rounds=self.maximum_tool_rounds,
            maximum_tool_calls=self.maximum_tool_calls,
            tool_rounds_executed=self.tool_rounds_executed,
            tool_calls_allowed=self.tool_calls_allowed,
            execution_limit_reached=self.execution_limit_reached,
            finalizer_attempted=self.finalizer_attempted,
            finalizer_outcome=self.finalizer_outcome,
        )


@dataclass(frozen=True)
class LatencyEvent:
    event_type: ClassVar[str] = "_latency"
    extras: FrozenExtras = ()
    field_order: tuple[str, ...] = ()

    phase: str | None | _Unset = UNSET
    elapsed_ms: int | None | _Unset = UNSET
    acquisition_outcome: str | None | _Unset = UNSET
    first_semantic_event_class: str | None | _Unset = UNSET
    pool_miss_reason: str | None | _Unset = UNSET
    session_reuse_cohort: str | None | _Unset = UNSET
    failure_stage: str | None | _Unset = UNSET
    failure_class: str | None | _Unset = UNSET
    attempt_kind: str | None | _Unset = UNSET

    def to_legacy(self) -> dict[str, Any]:
        return _legacy(
            "_latency",
            self.extras,
            self.field_order,
            phase=self.phase,
            elapsed_ms=self.elapsed_ms,
            acquisition_outcome=self.acquisition_outcome,
            first_semantic_event_class=self.first_semantic_event_class,
            pool_miss_reason=self.pool_miss_reason,
            session_reuse_cohort=self.session_reuse_cohort,
            failure_stage=self.failure_stage,
            failure_class=self.failure_class,
            attempt_kind=self.attempt_kind,
        )


@dataclass(frozen=True)
class McpReadinessEvent:
    event_type: ClassVar[str] = "_mcp_readiness"
    extras: FrozenExtras = ()
    field_order: tuple[str, ...] = ()

    ready: bool | None | _Unset = UNSET
    failure_class: str | None | _Unset = UNSET
    enabled_provider_ids: FrozenJson | None | _Unset = UNSET
    registration_latency_ms: int | None | _Unset = UNSET
    registered_tool_names: FrozenJson | None | _Unset = UNSET
    egress_policy_digest: str | None | _Unset = UNSET

    def __post_init__(self) -> None:
        for name in ("enabled_provider_ids", "registered_tool_names"):
            value = getattr(self, name)
            if value is not UNSET:
                object.__setattr__(self, name, _freeze(value))

    def to_legacy(self) -> dict[str, Any]:
        return _legacy(
            "_mcp_readiness",
            self.extras,
            self.field_order,
            ready=self.ready,
            failure_class=self.failure_class,
            enabled_provider_ids=self.enabled_provider_ids,
            registration_latency_ms=self.registration_latency_ms,
            registered_tool_names=self.registered_tool_names,
            egress_policy_digest=self.egress_policy_digest,
        )


@dataclass(frozen=True)
class UsageEvent:
    event_type: ClassVar[str] = "usage"
    usage: FrozenJson | _Unset = UNSET
    model_usage: FrozenJson | _Unset = UNSET
    total_cost_usd: float | None | _Unset = UNSET
    provider_requests: int | None | _Unset = UNSET
    phase: str | None | _Unset = UNSET
    extras: FrozenExtras = ()
    field_order: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.usage is not UNSET:
            object.__setattr__(self, "usage", _freeze(self.usage))
        if self.model_usage is not UNSET:
            object.__setattr__(self, "model_usage", _freeze(self.model_usage))

    def to_legacy(self) -> dict[str, Any]:
        return _legacy(
            "usage",
            self.extras,
            self.field_order,
            usage=self.usage,
            model_usage=self.model_usage,
            total_cost_usd=self.total_cost_usd,
            provider_requests=self.provider_requests,
            phase=self.phase,
        )


@dataclass(frozen=True)
class ArtifactEvent:
    kind: ArtifactEventType
    publication_id: str | None | _Unset = UNSET
    identifier: str | None | _Unset = UNSET
    title: str | None | _Unset = UNSET
    code: str | None | _Unset = UNSET
    message: str | None | _Unset = UNSET
    artifact_id: str | None | _Unset = UNSET
    version_id: str | None | _Unset = UNSET
    version: int | None | _Unset = UNSET
    gate_status: str | None | _Unset = UNSET
    total_bytes: int | None | _Unset = UNSET
    extras: FrozenExtras = ()
    field_order: tuple[str, ...] = ()

    def to_legacy(self) -> dict[str, Any]:
        return _legacy(
            self.kind.value,
            self.extras,
            self.field_order,
            publication_id=self.publication_id,
            identifier=self.identifier,
            title=self.title,
            code=self.code,
            message=self.message,
            artifact_id=self.artifact_id,
            version_id=self.version_id,
            version=self.version,
            gate_status=self.gate_status,
            total_bytes=self.total_bytes,
        )


@dataclass(frozen=True)
class CompletionEvent:
    event_type: ClassVar[str] = "done"
    outcome: TerminalOutcome | None = None
    finish_reason_present: bool = True
    raw_finish_reason: str | None | _Unset = UNSET
    followups: FrozenJson | _Unset = UNSET
    citations: FrozenJson | _Unset = UNSET
    extras: FrozenExtras = ()
    field_order: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.followups is not UNSET:
            object.__setattr__(self, "followups", _freeze(self.followups))
        if self.citations is not UNSET:
            object.__setattr__(self, "citations", _freeze(self.citations))

    def finish_reason(self, default="success"):
        value = self.raw_finish_reason
        if value is UNSET and self.finish_reason_present and self.outcome:
            value = self.outcome.value
        return event_value(value, default)

    def effective_outcome(self) -> TerminalOutcome:
        """Interpret exactly the finish reason that the compatibility wire exposes."""
        try:
            return TerminalOutcome(self.finish_reason())
        except (TypeError, ValueError):
            return TerminalOutcome.SUCCESS

    def to_legacy(self) -> dict[str, Any]:
        finish_reason: JsonValue | _Unset = self.raw_finish_reason
        if finish_reason is UNSET and self.finish_reason_present and self.outcome:
            finish_reason = self.outcome.value
        return _legacy(
            "done",
            self.extras,
            self.field_order,
            followups=self.followups,
            citations=self.citations,
            finish_reason=finish_reason,
        )


@dataclass(frozen=True)
class FailureEvent:
    event_type: ClassVar[str] = "error"
    code: str | None | _Unset = UNSET
    message: str | None | _Unset = UNSET
    interruption: InterruptionReason | None = None
    extras: FrozenExtras = ()
    field_order: tuple[str, ...] = ()

    def to_legacy(self) -> dict[str, Any]:
        if self.interruption is not None:
            raise ValueError("Interrupted turns have no public error frame")
        return _legacy(
            "error", self.extras, self.field_order, code=self.code, message=self.message
        )


@dataclass(frozen=True)
class CancellationEvent:
    event_type: ClassVar[str] = "_cancelled"
    reason: InterruptionReason = InterruptionReason.WORKER_CANCELLED
    extras: FrozenExtras = ()
    field_order: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.reason is not InterruptionReason.WORKER_CANCELLED:
            raise ValueError("Cancellation events represent worker cancellation")

    def to_legacy(self) -> dict[str, Any]:
        return _legacy("_cancelled", self.extras, self.field_order)


@dataclass(frozen=True)
class ToolEvent:
    """Tool lifecycle fields used internally; provider payload stays lossless."""

    event_type: str
    id: str | None | _Unset = UNSET
    took_ms: int | None | _Unset = UNSET
    extras: FrozenExtras = ()
    field_order: tuple[str, ...] = ()

    def to_legacy(self) -> dict[str, Any]:
        return _legacy(
            self.event_type,
            self.extras,
            self.field_order,
            id=self.id,
            took_ms=self.took_ms,
        )


@dataclass(frozen=True)
class LegacyPassthroughEvent:
    event_type: str
    extras: FrozenExtras = ()
    field_order: tuple[str, ...] = ()

    def to_legacy(self) -> dict[str, Any]:
        return _legacy(self.event_type, self.extras, self.field_order)


ChatTurnEvent: TypeAlias = (
    ResearchFinishedEvent
    | TitleEvent
    | TitleFinishedEvent
    | PersistenceEvent
    | MirrorFailureEvent
    | TelemetryEvent
    | LatencyEvent
    | McpReadinessEvent
    | UsageEvent
    | ArtifactEvent
    | CompletionEvent
    | FailureEvent
    | CancellationEvent
    | LegacyPassthroughEvent
    | ToolEvent
)


def event_kind(event: ChatTurnEvent) -> str:
    return event.kind.value if isinstance(event, ArtifactEvent) else event.event_type


def event_value(value, default=None):
    """Read an optional frozen field without materializing an entire event."""
    return default if value is UNSET else _thaw(value)


def event_extra(event: ChatTurnEvent, key: str, default=None):
    return next((_thaw(value) for name, value in event.extras if name == key), default)


def update_event(event: ChatTurnEvent, **changes) -> ChatTurnEvent:
    """Enrich immutable fields while retaining wire insertion order."""
    updated = replace(event, **changes)
    order = event.field_order
    if order:
        for key, value in changes.items():
            if isinstance(updated, CompletionEvent) and key in {
                "outcome",
                "raw_finish_reason",
                "finish_reason_present",
            }:
                key, value = "finish_reason", updated.finish_reason(UNSET)
            if key not in order and value is not UNSET:
                order += (key,)
        updated = replace(updated, field_order=order)
    return updated


def from_legacy_event(event: dict[str, Any]) -> ChatTurnEvent:
    """Convert one legacy frame while preserving field presence exactly."""

    event_type = event.get("type")
    if not isinstance(event_type, str):
        raise ValueError("Chat-turn event type must be a string")
    field_order = tuple(event)

    def value(key: str) -> JsonValue | _Unset:
        return event[key] if key in event else UNSET

    if event_type in {
        "tool_call",
        "tool_call_start",
        "tool_call_arguments_delta",
        "tool_call_arguments_done",
        "tool_result",
    }:
        return ToolEvent(
            event_type,
            value("id"),
            value("took_ms"),
            _extras(event, "id", "took_ms"),
            field_order,
        )
    if event_type == "_research_finished":
        return ResearchFinishedEvent(_extras(event), field_order)
    if event_type == "session_title_done":
        return TitleEvent(value("title"), _extras(event, "title"), field_order)
    if event_type == "_title_finished":
        return TitleFinishedEvent(_extras(event), field_order)
    if event_type == "_sdk_session":
        return PersistenceEvent(
            value("session_id"), _extras(event, "session_id"), field_order
        )
    if event_type == "_mirror_error":
        known = "key", "error", "terminal", "result_available"
        return MirrorFailureEvent(
            *(value(key) for key in known), _extras(event, *known), field_order
        )
    if event_type == "_execution_telemetry":
        known = (
            "maximum_tool_rounds",
            "maximum_tool_calls",
            "tool_rounds_executed",
            "tool_calls_allowed",
            "execution_limit_reached",
            "finalizer_attempted",
            "finalizer_outcome",
        )
        return TelemetryEvent(
            *(value(key) for key in known), _extras(event, *known), field_order
        )
    if event_type == "_latency":
        known = (
            "phase",
            "elapsed_ms",
            "acquisition_outcome",
            "first_semantic_event_class",
            "pool_miss_reason",
            "session_reuse_cohort",
            "failure_stage",
            "failure_class",
            "attempt_kind",
        )
        return LatencyEvent(
            extras=_extras(event, *known),
            field_order=field_order,
            **{key: value(key) for key in known},
        )
    if event_type == "_mcp_readiness":
        known = (
            "ready",
            "failure_class",
            "enabled_provider_ids",
            "registration_latency_ms",
            "registered_tool_names",
            "egress_policy_digest",
        )
        return McpReadinessEvent(
            extras=_extras(event, *known),
            field_order=field_order,
            **{key: value(key) for key in known},
        )
    if event_type == "usage":
        known = "usage", "model_usage", "total_cost_usd", "provider_requests", "phase"
        return UsageEvent(
            *(value(key) for key in known), _extras(event, *known), field_order
        )
    try:
        artifact_kind = ArtifactEventType(event_type)
    except ValueError:
        artifact_kind = None
    if artifact_kind is not None:
        known = (
            "publication_id",
            "identifier",
            "title",
            "code",
            "message",
            "artifact_id",
            "version_id",
            "version",
            "gate_status",
            "total_bytes",
        )
        return ArtifactEvent(
            artifact_kind,
            *(value(key) for key in known),
            _extras(event, *known),
            field_order,
        )
    if event_type == "done":
        raw_reason = value("finish_reason")
        try:
            outcome = None if raw_reason is UNSET else TerminalOutcome(raw_reason)
        except (TypeError, ValueError):
            outcome = None
        return CompletionEvent(
            outcome,
            raw_reason is not UNSET,
            raw_reason,
            value("followups"),
            value("citations"),
            _extras(event, "finish_reason", "followups", "citations"),
            field_order,
        )
    if event_type == "error":
        return FailureEvent(
            value("code"),
            value("message"),
            None,
            _extras(event, "code", "message"),
            field_order,
        )
    if event_type == "_cancelled":
        return CancellationEvent(extras=_extras(event), field_order=field_order)
    return LegacyPassthroughEvent(event_type, _extras(event), field_order)


@dataclass(frozen=True)
class PersistenceOutcome:
    status: PersistedTurnStatus
    finish_reason: TerminalOutcome | None = None
    error_code: str | None = None
    transcript_degraded: bool = False


@dataclass(frozen=True)
class ChatTurnLifecycle:
    """Terminal and producer-finalization state for one chat turn."""

    title_requested: bool = False
    research_finished: bool = False
    title_finished: bool = False
    terminal: TurnTerminalState = TurnTerminalState.ACTIVE
    outcome: TerminalOutcome | None = None
    interruption: InterruptionReason | None = None
    failure_code: str | None = None

    @property
    def finalization(self) -> TurnFinalizationState:
        if self.terminal is TurnTerminalState.ACTIVE:
            return TurnFinalizationState.RUNNING
        if self.research_finished and (not self.title_requested or self.title_finished):
            return TurnFinalizationState.FINALIZED
        return TurnFinalizationState.AWAITING_PRODUCERS

    def transition(self, event: ChatTurnEvent) -> "ChatTurnLifecycle":
        if isinstance(event, ResearchFinishedEvent):
            if self.research_finished:
                raise ValueError("Research already finished")
            return replace(self, research_finished=True)
        if isinstance(event, TitleFinishedEvent):
            if not self.title_requested or self.title_finished:
                raise ValueError("Title is not awaiting completion")
            return replace(self, title_finished=True)
        if self.terminal is not TurnTerminalState.ACTIVE:
            raise ValueError("Cannot add a second terminal chat-turn event")
        if isinstance(event, CompletionEvent):
            outcome = event.effective_outcome()
            terminal = (
                TurnTerminalState.INTERRUPTED
                if outcome is TerminalOutcome.STOPPED
                else TurnTerminalState.COMPLETED
            )
            return replace(self, terminal=terminal, outcome=outcome)
        if isinstance(event, MirrorFailureEvent):
            outcome = event.completed_result()
            if outcome is not None:
                return replace(
                    self,
                    terminal=TurnTerminalState.COMPLETED_DEGRADED,
                    outcome=outcome,
                )
            return replace(
                self,
                terminal=TurnTerminalState.FAILED,
                failure_code="transcript_mirror_error",
            )
        if isinstance(event, (FailureEvent, CancellationEvent)):
            interruption = (
                event.interruption if isinstance(event, FailureEvent) else event.reason
            )
            return replace(
                self,
                terminal=(
                    TurnTerminalState.INTERRUPTED
                    if interruption is not None
                    else TurnTerminalState.FAILED
                ),
                interruption=interruption,
                failure_code=(
                    event.code
                    if isinstance(event, FailureEvent) and event.code is not UNSET
                    else "interrupted"
                    if interruption
                    else "provider_error"
                ),
            )
        return self

    def persistence_outcome(self) -> PersistenceOutcome:
        if self.terminal is TurnTerminalState.COMPLETED:
            assert self.outcome is not None
            return PersistenceOutcome(PersistedTurnStatus.COMPLETE, self.outcome)
        if self.terminal is TurnTerminalState.COMPLETED_DEGRADED:
            assert self.outcome is not None
            return PersistenceOutcome(
                PersistedTurnStatus.COMPLETE, self.outcome, transcript_degraded=True
            )
        if self.terminal is TurnTerminalState.INTERRUPTED:
            return PersistenceOutcome(
                PersistedTurnStatus.INTERRUPTED,
                error_code=self.failure_code or "interrupted",
            )
        if self.terminal is TurnTerminalState.FAILED:
            return PersistenceOutcome(
                PersistedTurnStatus.ERROR,
                error_code=self.failure_code or "provider_error",
            )
        raise ValueError("Active chat turns do not have a persisted outcome")
