"""Content-free safety contracts for the external Pi overload baseline."""

from __future__ import annotations

import math
import os
import re
import stat
import tempfile
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.services.chat_external_pi_shadow import (
    ExternalPiShadowProjection,
    ExternalPiShadowRequest,
    ExternalPiWorkerStatus,
)
from deploy.external_pi_slot_lifecycle import resolve_external_pi_slot

CONFIRMATION = "RUN_EXTERNAL_PI_SHADOW_BASELINE"
PROFILE = "single-worker-overload-baseline"
EXPECTED_USERS = 100
EXPECTED_SPAWN_RATE = 100.0
EXPECTED_MAXIMUM_SESSIONS = 8
NO_QUEUE_MAX_MS = 5_000
MAX_REPORT_DURATION_MS = 60_000
MAX_REPORT_COUNTER = 1_000_000
ALLOWED_SLOT_ENDPOINTS = {
    "blue": "http://127.0.0.1:8766",
    "green": "http://127.0.0.1:8767",
}

APP_ROOT = Path("/srv/paperswithcode")
REPORT_ROOT = Path("/var/lib/paperswithcode/staging")
SOURCE_ROOT = Path(__file__).resolve().parents[2]
TOKEN_KEY = "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN"
_IMMUTABLE_RELEASE = re.compile(r"^[0-9a-f]{12}-staging$")


class RunRefused(RuntimeError):
    """The requested baseline does not satisfy the fail-closed safety contract."""


@dataclass(frozen=True, slots=True)
class ExternalPiBaselineConfig:
    profile: str
    users: int
    spawn_rate: float
    slot: str
    worker_url: str
    worker_id: str
    release_id: str
    release: Path
    runtime: Path
    prompt_path: Path
    prompt: str = field(repr=False)
    report_path: Path
    token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class BaselineObservation:
    classification: Literal["compatible", "capacity", "error"]
    latency_ms: int

    def __post_init__(self):
        if (
            type(self.latency_ms) is not int
            or not 0 <= self.latency_ms <= MAX_REPORT_DURATION_MS
        ):
            raise ValueError(
                "external Pi baseline latency is outside bounded report range"
            )


class ExternalPiBaselineReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    profile: str
    expected_users: int = Field(ge=EXPECTED_USERS, le=EXPECTED_USERS)
    release_id: str
    worker_id: str
    instance_id: str
    worker_generation: int = Field(ge=1, le=MAX_REPORT_COUNTER)
    maximum_sessions: int = Field(
        ge=EXPECTED_MAXIMUM_SESSIONS, le=EXPECTED_MAXIMUM_SESSIONS
    )
    observations: int = Field(ge=0, le=EXPECTED_USERS)
    compatible: int = Field(ge=0, le=EXPECTED_USERS)
    capacity: int = Field(ge=0, le=EXPECTED_USERS)
    error: int = Field(ge=0, le=EXPECTED_USERS)
    latency_p50_ms: int = Field(ge=0, le=MAX_REPORT_DURATION_MS)
    latency_p95_ms: int = Field(ge=0, le=MAX_REPORT_DURATION_MS)
    latency_p99_ms: int = Field(ge=0, le=MAX_REPORT_DURATION_MS)
    capacity_max_ms: int = Field(ge=0, le=MAX_REPORT_DURATION_MS)
    shadow_requests_delta: int = Field(ge=-MAX_REPORT_COUNTER, le=MAX_REPORT_COUNTER)
    model_calls: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    tool_calls: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    provider_calls: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    modal_calls: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    billing_events: int = Field(ge=0, le=MAX_REPORT_COUNTER)
    provider_credentials_present: bool
    modal_credentials_present: bool
    registered_tool_count: int = Field(ge=0, le=128)
    safety_passed: bool
    capacity_target_passed: bool


@dataclass(slots=True)
class ExternalPiBaselineTracker:
    """Bounded in-memory storage for classification and integer latency only."""

    _observations: list[BaselineObservation] = field(default_factory=list, repr=False)

    def record(self, observation: BaselineObservation) -> None:
        if len(self._observations) >= EXPECTED_USERS:
            raise RunRefused("external Pi baseline accepts exactly 100 observations")
        self._observations.append(observation)

    @property
    def observations(self) -> tuple[BaselineObservation, ...]:
        return tuple(self._observations)


def _required(environ: Mapping[str, str], key: str) -> str:
    value = environ.get(key)
    if value is None or not value:
        raise RunRefused(f"external Pi baseline requires {key}")
    return value


def _protected_token(path: Path) -> str:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise RunRefused("external Pi baseline token file is not protected") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise RunRefused("external Pi baseline token file is not protected")
    entries: list[tuple[str, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise RunRefused("external Pi baseline token file is not protected") from exc
    for line in lines:
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key != TOKEN_KEY or not value:
            raise RunRefused("external Pi baseline token file has unexpected entries")
        entries.append((key, value))
    if len(entries) != 1:
        raise RunRefused(
            "external Pi baseline token file must contain exactly one token"
        )
    return entries[0][1]


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _resolve_external_pi_baseline_topology(slot: str, worker_url: str):
    if slot not in ALLOWED_SLOT_ENDPOINTS or worker_url != ALLOWED_SLOT_ENDPOINTS[slot]:
        raise RunRefused(
            "external Pi baseline requires the active staging worker endpoint"
        )
    staging_root = APP_ROOT / "environments/staging"
    current_link = staging_root / "current"
    active_link = staging_root / "active"
    expected_active = staging_root / "slots" / slot
    try:
        current = current_link.resolve(strict=True)
        active = active_link.resolve(strict=True)
        expected_active = expected_active.resolve(strict=True)
        active_release = (active_link / "release").resolve(strict=True)
        expected_active_release = (expected_active / "release").resolve(strict=True)
    except OSError as exc:
        raise RunRefused(
            "external Pi baseline requires the exact active immutable staging release"
        ) from exc
    if (
        not current_link.is_symlink()
        or not active_link.is_symlink()
        or not _IMMUTABLE_RELEASE.fullmatch(current.name)
        or current.parent != APP_ROOT / "releases"
        or active != expected_active
        or active_release != current
        or expected_active_release != current
        or SOURCE_ROOT.resolve() != current
    ):
        raise RunRefused(
            "external Pi baseline requires the exact active immutable staging release"
        )
    try:
        resolved = resolve_external_pi_slot("staging", slot)
    except (OSError, ValueError) as exc:
        raise RunRefused(
            "external Pi baseline could not resolve the active staging slot"
        ) from exc
    if (
        resolved.release.resolve() != current
        or resolved.release_id != current.name
        or resolved.slot != slot
        or resolved.worker_id != f"staging-{slot}"
        or worker_url != f"http://127.0.0.1:{resolved.port}"
        or resolved.prompt.parent.parent != resolved.runtime
    ):
        raise RunRefused(
            "external Pi baseline requires the exact active immutable staging release"
        )
    return resolved


def validate_external_pi_baseline_topology(config: ExternalPiBaselineConfig) -> None:
    """Revalidate that the run remains bound to its exact active staging slot."""

    try:
        resolved = _resolve_external_pi_baseline_topology(
            config.slot, config.worker_url
        )
    except RunRefused:
        raise RunRefused(
            "external Pi baseline requires the exact active immutable staging topology"
        ) from None
    if (
        resolved.release != config.release
        or resolved.release_id != config.release_id
        or resolved.worker_id != config.worker_id
        or resolved.runtime != config.runtime
        or resolved.prompt != config.prompt_path
    ):
        raise RunRefused(
            "external Pi baseline requires the exact active immutable staging topology"
        )


def load_external_pi_baseline_config(
    environ: Mapping[str, str],
) -> ExternalPiBaselineConfig:
    """Load an exact active-slot, staging-only baseline configuration."""

    if environ.get("PWC_EXTERNAL_PI_BASELINE_CONFIRM") != CONFIRMATION:
        raise RunRefused("external Pi baseline confirmation is required")
    if environ.get("PWC_EXTERNAL_PI_BASELINE_PROFILE") != PROFILE:
        raise RunRefused("external Pi baseline profile is invalid")
    try:
        users = int(_required(environ, "PWC_EXTERNAL_PI_BASELINE_USERS"))
        spawn_rate = float(_required(environ, "PWC_EXTERNAL_PI_BASELINE_SPAWN_RATE"))
    except ValueError as exc:
        raise RunRefused(
            "external Pi baseline requires exactly 100 users at spawn rate 100.0"
        ) from exc
    if users != EXPECTED_USERS or spawn_rate != EXPECTED_SPAWN_RATE:
        raise RunRefused(
            "external Pi baseline requires exactly 100 users at spawn rate 100.0"
        )

    slot = _required(environ, "PWC_EXTERNAL_PI_BASELINE_SLOT")
    worker_url = _required(environ, "PWC_EXTERNAL_PI_BASELINE_WORKER_URL")
    resolved = _resolve_external_pi_baseline_topology(slot, worker_url)
    try:
        prompt = resolved.prompt.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RunRefused(
            "external Pi baseline canonical runtime prompt is unavailable"
        ) from exc

    report_path = Path(_required(environ, "PWC_EXTERNAL_PI_BASELINE_REPORT"))
    try:
        report_parent = report_path.parent.resolve(strict=True)
        report_root = REPORT_ROOT.resolve(strict=True)
    except OSError as exc:
        raise RunRefused(
            "external Pi baseline report must be retained under staging"
        ) from exc
    if not report_path.is_absolute() or not _path_within(report_parent, report_root):
        raise RunRefused("external Pi baseline report must be retained under staging")
    token = _protected_token(
        Path(_required(environ, "PWC_EXTERNAL_PI_BASELINE_TOKEN_FILE"))
    )
    return ExternalPiBaselineConfig(
        profile=PROFILE,
        users=users,
        spawn_rate=spawn_rate,
        slot=slot,
        worker_url=worker_url,
        worker_id=resolved.worker_id,
        release_id=resolved.release_id,
        release=resolved.release,
        runtime=resolved.runtime,
        prompt_path=resolved.prompt,
        prompt=prompt,
        report_path=report_path,
        token=token,
    )


def build_external_pi_baseline_request(
    ordinal: int, prompt: str
) -> ExternalPiShadowRequest:
    """Build one maximum-cardinality native transcript without user content."""

    if type(ordinal) is not int or not 0 <= ordinal < EXPECTED_USERS:
        raise ValueError("external Pi baseline ordinal is out of range")
    chat_session_id = uuid.uuid4()
    agent_session_id = uuid.uuid4()
    entry_ids = [str(uuid.uuid4()) for _ in range(1_999)]
    entries: list[dict[str, object]] = [
        {"type": "session", "id": str(agent_session_id), "version": 3}
    ]
    entries.extend(
        {
            "type": "message",
            "id": entry_id,
            "parentId": None if index == 0 else entry_ids[index - 1],
        }
        for index, entry_id in enumerate(entry_ids)
    )
    return ExternalPiShadowRequest(
        request_id=str(uuid.uuid4()),
        chat_session_id=chat_session_id,
        agent_session_id=agent_session_id,
        current_leaf_id=entry_ids[-1],
        prompt=prompt,
        tool_names=(),
        transcript_entries=tuple(entries),
    )


def classify_external_pi_baseline_response(
    *,
    request: ExternalPiShadowRequest,
    status_code: int | None,
    payload: object,
    latency_ms: int,
) -> BaselineObservation:
    """Reduce a worker response to a fixed-cardinality, content-free outcome."""

    classification: Literal["compatible", "capacity", "error"] = "error"
    if status_code == 503 and payload == {"code": "shadow_capacity"}:
        classification = "capacity"
    elif status_code == 200:
        try:
            projection = ExternalPiShadowProjection.model_validate(payload)
        except ValidationError:
            pass
        else:
            if projection.compatible_with(request):
                classification = "compatible"
    return BaselineObservation(classification=classification, latency_ms=latency_ms)


def _nearest_rank(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered)) - 1]


def _forbidden_counters_are_zero(status: ExternalPiWorkerStatus) -> bool:
    counters = status.operation_counters
    return (
        counters.model_calls == 0
        and counters.tool_calls == 0
        and counters.provider_calls == 0
        and counters.modal_calls == 0
        and counters.billing_events == 0
    )


def _safe_capabilities(status: ExternalPiWorkerStatus) -> bool:
    evidence = status.capability_evidence
    return (
        not evidence.provider_credentials_present
        and not evidence.modal_credentials_present
        and evidence.registered_tool_count == 0
    )


def _status_has_bounded_report_values(status: ExternalPiWorkerStatus) -> bool:
    counters = status.operation_counters
    return (
        status.worker_generation is not None
        and status.worker_generation <= MAX_REPORT_COUNTER
        and all(
            value <= MAX_REPORT_COUNTER
            for value in (
                counters.shadow_requests,
                counters.model_calls,
                counters.tool_calls,
                counters.provider_calls,
                counters.modal_calls,
                counters.billing_events,
            )
        )
    )


def _publish_external_pi_baseline_report(
    report: ExternalPiBaselineReport, path: Path
) -> None:
    try:
        root = REPORT_ROOT.resolve(strict=True)
        parent = path.parent.resolve(strict=True)
    except OSError as exc:
        raise RunRefused(
            "external Pi baseline report directory is unavailable"
        ) from exc
    if not path.is_absolute() or not _path_within(parent, root):
        raise RunRefused("external Pi baseline report must be retained under staging")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=parent
    )
    temporary = Path(temporary_name)
    try:
        os.chmod(temporary, 0o600)
        payload = report.model_dump_json(indent=2).encode() + b"\n"
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def finalize_external_pi_baseline(
    *,
    config: ExternalPiBaselineConfig,
    before: ExternalPiWorkerStatus,
    after: ExternalPiWorkerStatus,
    tracker: ExternalPiBaselineTracker,
) -> ExternalPiBaselineReport:
    """Validate worker invariants and atomically retain the content-free report."""

    observations = tracker.observations
    if len(observations) != EXPECTED_USERS:
        raise RunRefused("external Pi baseline requires exactly 100 observations")
    if not _status_has_bounded_report_values(
        before
    ) or not _status_has_bounded_report_values(after):
        raise RunRefused("external Pi baseline worker exceeded bounded report values")
    compatible = sum(item.classification == "compatible" for item in observations)
    capacity = sum(item.classification == "capacity" for item in observations)
    errors = sum(item.classification == "error" for item in observations)
    latencies = [item.latency_ms for item in observations]
    capacity_latencies = [
        item.latency_ms for item in observations if item.classification == "capacity"
    ]
    before_counts = before.operation_counters
    after_counts = after.operation_counters
    shadow_delta = after_counts.shadow_requests - before_counts.shadow_requests
    unchanged_identity = (
        before.protocol == after.protocol == "external-pi-v1"
        and before.state == after.state == "ready"
        and before.release_id == after.release_id == config.release_id
        and before.worker_id == after.worker_id == config.worker_id
        and before.instance_id == after.instance_id
        and before.worker_generation is not None
        and before.worker_generation == after.worker_generation
        and before.maximum_sessions
        == after.maximum_sessions
        == EXPECTED_MAXIMUM_SESSIONS
    )
    safety_passed = (
        compatible > 0
        and compatible + capacity == EXPECTED_USERS
        and errors == 0
        and (not capacity_latencies or max(capacity_latencies) <= NO_QUEUE_MAX_MS)
        and unchanged_identity
        and after.active_sessions == 0
        and _safe_capabilities(before)
        and _safe_capabilities(after)
        and _forbidden_counters_are_zero(before)
        and _forbidden_counters_are_zero(after)
        and shadow_delta == EXPECTED_USERS
    )
    report = ExternalPiBaselineReport(
        profile=PROFILE,
        expected_users=EXPECTED_USERS,
        release_id=config.release_id,
        worker_id=config.worker_id,
        instance_id=str(before.instance_id),
        worker_generation=before.worker_generation or 1,
        maximum_sessions=after.maximum_sessions,
        observations=len(observations),
        compatible=compatible,
        capacity=capacity,
        error=errors,
        latency_p50_ms=_nearest_rank(latencies, 0.50),
        latency_p95_ms=_nearest_rank(latencies, 0.95),
        latency_p99_ms=_nearest_rank(latencies, 0.99),
        capacity_max_ms=max(capacity_latencies, default=0),
        shadow_requests_delta=shadow_delta,
        model_calls=after_counts.model_calls,
        tool_calls=after_counts.tool_calls,
        provider_calls=after_counts.provider_calls,
        modal_calls=after_counts.modal_calls,
        billing_events=after_counts.billing_events,
        provider_credentials_present=after.capability_evidence.provider_credentials_present,
        modal_credentials_present=after.capability_evidence.modal_credentials_present,
        registered_tool_count=after.capability_evidence.registered_tool_count,
        safety_passed=safety_passed,
        capacity_target_passed=safety_passed and compatible == EXPECTED_USERS,
    )
    _publish_external_pi_baseline_report(report, config.report_path)
    return report
