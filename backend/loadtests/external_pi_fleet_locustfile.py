"""Thin direct-loopback Locust adapter for external Pi fleet qualification."""

from __future__ import annotations

import itertools
import time
import uuid
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Literal, Protocol
from datetime import UTC, datetime

import gevent
from gevent.event import Event
from gevent.lock import Semaphore
from gevent.monkey import MonkeyPatchWarning

with warnings.catch_warnings():
    warnings.simplefilter("ignore", MonkeyPatchWarning)
    from locust import HttpUser, User, between, events, task
    from locust.env import Environment
    from locust.exception import StopUser
    from locust.runners import LocalRunner

from requests.exceptions import RequestException

from backend.loadtests.external_pi_fleet_core import (
    EXPECTED_USERS,
    DurableTurnObservation,
    DurableWorkload,
    FleetReplica,
    FleetRunRefused,
    aggregate_durable_profile,
    build_external_pi_fleet_request,
    classify_external_pi_fleet_response,
    route_ordinal,
    resolve_durable_profile,
    modal_lifecycle_delta,
    ModalLifecycleSnapshot,
    ModalRateEvidence,
    DurableQualificationEvidence,
)
from backend.services.durable_external_qualification_contract import (
    DURABLE_QUALIFICATION_RUN_TIMEOUT_SECONDS,
)
from backend.loadtests.external_pi_shadow_core import BaselineObservation


@dataclass(frozen=True, slots=True)
class FleetRoundConfig:
    replicas: tuple[FleetReplica, ...]
    expected_users: int
    prompt: str = field(repr=False)
    token: str = field(repr=False)
    barrier_deadline: float
    abort_requested: Callable[[], bool] = field(repr=False)


@dataclass(frozen=True, slots=True)
class FleetRoundResult:
    observations: tuple[BaselineObservation, ...]
    protocol_errors: int
    transport_errors: int


@dataclass(frozen=True, slots=True)
class DurableUserSpec:
    ordinal: int
    workload: DurableWorkload
    arrival_delay_ms: Literal[0] = 0
    application_queue: Literal[False] = False


@dataclass(frozen=True, slots=True)
class DurableRunResources:
    peak_memory_bytes: int
    minimum_host_mem_available_bytes: int
    peak_cpu_percent: float
    peak_active_backend_turns: int
    peak_active_external_workers: int
    peak_active_sandboxes: int


@dataclass(frozen=True, slots=True)
class DurableProfileMeasurement:
    profile_name: str
    observations: tuple[DurableTurnObservation, ...]
    resources: DurableRunResources
    window_started_at: datetime
    qualification_scope_id: uuid.UUID


class DurableStreamTransport(Protocol):
    def open_durable_stream(self, spec: DurableUserSpec) -> Mapping[str, object]: ...


class ModalLifecycleEvidenceSource(Protocol):
    def snapshot(self, profile_name: str) -> ModalLifecycleSnapshot: ...


class DurableQualificationEvidenceSource(Protocol):
    def collect(self, scope_id: uuid.UUID) -> DurableQualificationEvidence: ...


@dataclass(frozen=True, slots=True)
class DurableRunConfig:
    profile_name: str
    specs: tuple[DurableUserSpec, ...]
    transport: DurableStreamTransport = field(repr=False)
    barrier_deadline: float


def build_durable_user_specs(profile_name: str) -> tuple[DurableUserSpec, ...]:
    """Build one immediate, deterministic user assignment without queue state."""
    profile = resolve_durable_profile(profile_name)
    return tuple(
        DurableUserSpec(ordinal=ordinal, workload=workload)
        for ordinal, workload in enumerate(profile.workloads)
    )


def build_durable_observation(**evidence) -> DurableTurnObservation:
    """Normalize stream evidence without reflecting rejected values."""
    allowed = {
        "workload",
        "outcome",
        "admission_ms",
        "reconnect_ready_ms",
        "ttft_ms",
        "completion_ms",
        "reconnects",
        "reconnect_successes",
        "model_starts",
        "operation_start_ids",
        "queued_states",
        "stale_mutations",
        "duplicate_turns",
        "terminal_cause",
        "failure_code",
    }
    legacy_evidence = {"operation_start_ids", "queued_states", "stale_mutations"}
    fields = set(evidence)
    if fields != allowed and fields != allowed - legacy_evidence:
        raise FleetRunRefused("durable observation fields are invalid")
    operation_ids = evidence.pop("operation_start_ids", ())
    if (
        not isinstance(operation_ids, (tuple, list))
        or len(operation_ids) > 1_000
        or any(
            not isinstance(identity, str)
            or not identity
            or len(identity) > 64
            or any(
                not (character.islower() or character.isdigit() or character == "-")
                for character in identity
            )
            for identity in operation_ids
        )
    ):
        raise FleetRunRefused("durable operation identity evidence is invalid")
    normalized = dict(evidence)
    normalized.setdefault("queued_states", 0)
    normalized.setdefault("stale_mutations", 0)
    normalized["operation_start_count"] = len(set(operation_ids))
    normalized["duplicate_operation_start_count"] = len(operation_ids) - len(
        set(operation_ids)
    )
    try:
        return DurableTurnObservation.model_validate(normalized)
    except ValueError:
        raise FleetRunRefused("durable observation evidence is invalid") from None


_ordinals = itertools.count()
_config: FleetRoundConfig | None = None
_observations: list[BaselineObservation] = []
_protocol_errors = 0
_transport_errors = 0
_arrival_gate = Event()
_arrival_lock = Semaphore()
_barrier_arrivals = 0
_barrier_failure: str | None = None
_durable_config: DurableRunConfig | None = None
_durable_ordinals = itertools.count()
_durable_observations: list[DurableTurnObservation] = []
_durable_gate = Event()
_durable_lock = Semaphore()
_durable_barrier_arrivals = 0
_durable_failure: str | None = None


def configure_fleet_round(
    *,
    replicas: tuple[FleetReplica, ...],
    prompt: str,
    token: str,
    expected_users: int = EXPECTED_USERS,
    barrier_timeout_seconds: float = 5.0,
    abort_requested: Callable[[], bool] = lambda: False,
) -> None:
    """Set one bounded in-process round without serializing protected inputs."""
    global _arrival_gate, _arrival_lock, _barrier_arrivals, _barrier_failure
    global _config, _durable_config, _ordinals, _observations
    global _protocol_errors, _transport_errors
    route_ordinal(0, replicas)
    if type(expected_users) is not int or not 1 <= expected_users <= EXPECTED_USERS:
        raise FleetRunRefused("external Pi fleet expected users are invalid")
    if not prompt or not token:
        raise FleetRunRefused("external Pi fleet round inputs are incomplete")
    if not 0 < barrier_timeout_seconds <= 10:
        raise FleetRunRefused("external Pi fleet concurrency barrier is not bounded")
    _config = FleetRoundConfig(
        replicas=replicas,
        expected_users=expected_users,
        prompt=prompt,
        token=token,
        barrier_deadline=time.monotonic() + barrier_timeout_seconds,
        abort_requested=abort_requested,
    )
    _durable_config = None
    _ordinals = itertools.count()
    _observations = []
    _protocol_errors = 0
    _transport_errors = 0
    _arrival_gate = Event()
    _arrival_lock = Semaphore()
    _barrier_arrivals = 0
    _barrier_failure = None


def fleet_round_result() -> FleetRoundResult:
    return FleetRoundResult(
        observations=tuple(_observations),
        protocol_errors=_protocol_errors,
        transport_errors=_transport_errors,
    )


def run_local_fleet_round(
    *,
    replicas: tuple[FleetReplica, ...],
    prompt: str,
    token: str,
    expected_users: int = EXPECTED_USERS,
    timeout_seconds: float = 30.0,
    abort_requested: Callable[[], bool] = lambda: False,
    monotonic: Callable[[], float] = time.monotonic,
    barrier_timeout_seconds: float = 5.0,
) -> FleetRoundResult:
    """Run one exact bounded profile in one process and return its evidence."""
    if not 0 < timeout_seconds <= 60:
        raise FleetRunRefused("external Pi fleet Locust timeout is not bounded")
    if barrier_timeout_seconds > timeout_seconds:
        raise FleetRunRefused("external Pi fleet concurrency barrier exceeds timeout")
    configure_fleet_round(
        replicas=replicas,
        prompt=prompt,
        token=token,
        expected_users=expected_users,
        barrier_timeout_seconds=barrier_timeout_seconds,
        abort_requested=abort_requested,
    )
    environment = Environment(
        user_classes=[ExternalPiFleetUser],
        host=None,
        parsed_options=SimpleNamespace(
            num_users=expected_users, spawn_rate=float(expected_users)
        ),
    )
    runner = environment.create_local_runner()
    _validate_runner(environment)
    deadline = monotonic() + timeout_seconds
    try:
        runner.start(user_count=expected_users, spawn_rate=float(expected_users))
        while monotonic() < deadline:
            if _barrier_failure is not None:
                raise FleetRunRefused(_barrier_failure)
            if abort_requested():
                _fail_barrier("external Pi fleet concurrency barrier aborted")
                raise FleetRunRefused("external Pi fleet round aborted by safety guard")
            if runner.user_count == 0 and len(_observations) == expected_users:
                break
            gevent.sleep(0.05)
        else:
            _fail_barrier("external Pi fleet round timed out")
    finally:
        _arrival_gate.set()
        runner.quit()
    if _barrier_failure is not None:
        raise FleetRunRefused(_barrier_failure)
    result = fleet_round_result()
    if len(result.observations) != expected_users:
        raise FleetRunRefused(
            "external Pi fleet Locust round requires the exact expected observations"
        )
    return result


def configure_durable_profile(
    *,
    profile_name: str,
    transport: DurableStreamTransport,
    barrier_timeout_seconds: float = 5.0,
) -> None:
    """Configure one executable immediate durable profile in one process."""
    global _config, _durable_config, _durable_ordinals, _durable_observations
    global _durable_gate, _durable_lock, _durable_barrier_arrivals, _durable_failure
    if not 0 < barrier_timeout_seconds <= 10:
        raise FleetRunRefused("durable concurrency barrier is not bounded")
    specs = build_durable_user_specs(profile_name)
    _config = None
    _durable_config = DurableRunConfig(
        profile_name=profile_name,
        specs=specs,
        transport=transport,
        barrier_deadline=time.monotonic() + barrier_timeout_seconds,
    )
    _durable_ordinals = itertools.count()
    _durable_observations = []
    _durable_gate = Event()
    _durable_lock = Semaphore()
    _durable_barrier_arrivals = 0
    _durable_failure = None


def run_local_durable_profile(
    *,
    profile_name: str,
    transport: DurableStreamTransport,
    resources: DurableRunResources,
    lifecycle_source: ModalLifecycleEvidenceSource,
    modal_rate: ModalRateEvidence,
    timeout_seconds: float = DURABLE_QUALIFICATION_RUN_TIMEOUT_SECONDS,
    barrier_timeout_seconds: float = 5.0,
    monotonic: Callable[[], float] = time.monotonic,
):
    """Execute the exact Locust profile through an injected durable transport."""
    lifecycle_before = lifecycle_source.snapshot(profile_name)
    observations = _run_durable_observations(
        profile_name=profile_name,
        transport=transport,
        timeout_seconds=timeout_seconds,
        barrier_timeout_seconds=barrier_timeout_seconds,
        monotonic=monotonic,
    )
    lifecycle_after = lifecycle_source.snapshot(profile_name)
    profile = resolve_durable_profile(profile_name)
    return aggregate_durable_profile(
        profile=profile,
        observations=observations,
        peak_memory_bytes=resources.peak_memory_bytes,
        minimum_host_mem_available_bytes=resources.minimum_host_mem_available_bytes,
        peak_cpu_percent=resources.peak_cpu_percent,
        peak_active_backend_turns=resources.peak_active_backend_turns,
        peak_active_external_workers=resources.peak_active_external_workers,
        peak_active_sandboxes=resources.peak_active_sandboxes,
        modal_lifecycle=modal_lifecycle_delta(lifecycle_before, lifecycle_after),
        modal_rate=modal_rate,
    )


def _run_durable_observations(
    *,
    profile_name: str,
    transport: DurableStreamTransport,
    timeout_seconds: float,
    barrier_timeout_seconds: float,
    monotonic: Callable[[], float] = time.monotonic,
) -> tuple[DurableTurnObservation, ...]:
    if not 0 < timeout_seconds <= 120:
        raise FleetRunRefused("durable Locust timeout is not bounded")
    if barrier_timeout_seconds > timeout_seconds:
        raise FleetRunRefused("durable concurrency barrier exceeds timeout")
    configure_durable_profile(
        profile_name=profile_name,
        transport=transport,
        barrier_timeout_seconds=barrier_timeout_seconds,
    )
    config = _durable_config
    assert config is not None
    expected_users = len(config.specs)
    environment = Environment(
        user_classes=[DurableExternalTurnUser],
        host=None,
        parsed_options=SimpleNamespace(
            num_users=expected_users,
            spawn_rate=float(expected_users),
        ),
    )
    runner = environment.create_local_runner()
    _validate_durable_runner(environment)
    deadline = monotonic() + timeout_seconds
    try:
        runner.start(user_count=expected_users, spawn_rate=float(expected_users))
        while monotonic() < deadline:
            if _durable_failure is not None:
                raise FleetRunRefused(_durable_failure)
            if runner.user_count == 0 and len(_durable_observations) == expected_users:
                break
            gevent.sleep(0.01)
        else:
            _fail_durable_barrier("durable Locust profile timed out")
    finally:
        _durable_gate.set()
        runner.quit()
    if _durable_failure is not None:
        raise FleetRunRefused(_durable_failure)
    if len(_durable_observations) != expected_users:
        raise FleetRunRefused("durable Locust profile evidence is incomplete")
    return tuple(_durable_observations)


def finalize_live_durable_profile(
    measurement: DurableProfileMeasurement,
    *,
    evidence_source: DurableQualificationEvidenceSource | None = None,
    qualification_evidence: DurableQualificationEvidence | None = None,
    modal_rate: ModalRateEvidence,
):
    profile = resolve_durable_profile(measurement.profile_name)
    if (evidence_source is None) == (qualification_evidence is None):
        raise FleetRunRefused("exactly one durable evidence input is required")
    evidence = qualification_evidence or evidence_source.collect(
        measurement.qualification_scope_id
    )
    resources = measurement.resources
    return aggregate_durable_profile(
        profile=profile,
        observations=measurement.observations,
        peak_memory_bytes=resources.peak_memory_bytes,
        minimum_host_mem_available_bytes=resources.minimum_host_mem_available_bytes,
        peak_cpu_percent=resources.peak_cpu_percent,
        peak_active_backend_turns=resources.peak_active_backend_turns,
        peak_active_external_workers=resources.peak_active_external_workers,
        peak_active_sandboxes=resources.peak_active_sandboxes,
        qualification_evidence=evidence,
        modal_rate=modal_rate,
    )


def run_live_durable_profile(
    *,
    profile_name: str,
    transport_config,
    resources: DurableRunResources,
    qualification_scope_id: uuid.UUID,
    timeout_seconds: float = DURABLE_QUALIFICATION_RUN_TIMEOUT_SECONDS,
    barrier_timeout_seconds: float = 5.0,
):
    """Guarded constructor: live evidence can only use the real chat transport."""
    from backend.loadtests.durable_chat_transport import create_live_durable_transport

    started_at = datetime.now(UTC)
    start_sampling = getattr(resources, "start", None)
    stop_sampling = getattr(resources, "stop", None)
    sampling = callable(start_sampling) and callable(stop_sampling)
    if sampling:
        start_sampling()
    try:
        observations = _run_durable_observations(
            profile_name=profile_name,
            transport=create_live_durable_transport(
                transport_config, qualification_scope_id
            ),
            timeout_seconds=timeout_seconds,
            barrier_timeout_seconds=barrier_timeout_seconds,
        )
    finally:
        if sampling:
            resources = stop_sampling()
    if not isinstance(resources, DurableRunResources):
        raise FleetRunRefused("durable resource evidence is invalid")
    return DurableProfileMeasurement(
        profile_name=profile_name,
        observations=observations,
        resources=resources,
        window_started_at=started_at,
        qualification_scope_id=qualification_scope_id,
    )


def _fail_durable_barrier(reason: str) -> None:
    global _durable_failure
    with _durable_lock:
        if _durable_failure is None:
            _durable_failure = reason
        _durable_gate.set()


def _await_durable_barrier(config: DurableRunConfig) -> bool:
    global _durable_barrier_arrivals, _durable_failure
    expected_users = len(config.specs)
    with _durable_lock:
        if _durable_failure is not None:
            return False
        _durable_barrier_arrivals += 1
        if _durable_barrier_arrivals == expected_users:
            if time.monotonic() >= config.barrier_deadline:
                _durable_failure = "durable concurrency barrier timed out"
            _durable_gate.set()
    while not _durable_gate.wait(timeout=0.01):
        if time.monotonic() >= config.barrier_deadline:
            _fail_durable_barrier("durable concurrency barrier timed out")
    return _durable_failure is None


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1_000))


def _fail_barrier(reason: str) -> None:
    global _barrier_failure
    with _arrival_lock:
        if _barrier_failure is None:
            _barrier_failure = reason
        _arrival_gate.set()


def _await_concurrency_barrier(config: FleetRoundConfig) -> bool:
    global _barrier_arrivals, _barrier_failure
    with _arrival_lock:
        if _barrier_failure is not None:
            return False
        _barrier_arrivals += 1
        if _barrier_arrivals == config.expected_users:
            if config.abort_requested():
                _barrier_failure = "external Pi fleet concurrency barrier aborted"
                _arrival_gate.set()
            elif time.monotonic() >= config.barrier_deadline:
                _barrier_failure = "external Pi fleet concurrency barrier timed out"
                _arrival_gate.set()
            else:
                _arrival_gate.set()
    while not _arrival_gate.wait(timeout=0.01):
        if config.abort_requested():
            _fail_barrier("external Pi fleet concurrency barrier aborted")
        elif time.monotonic() >= config.barrier_deadline:
            _fail_barrier("external Pi fleet concurrency barrier timed out")
    return _barrier_failure is None and not config.abort_requested()


@events.test_start.add_listener
def _start(environment, **_kwargs) -> None:
    if _durable_config is not None:
        _validate_durable_runner(environment)
    else:
        _validate_runner(environment)


def _validate_runner(environment: Environment) -> None:
    """Reject an unsafe runner synchronously before Locust starts users."""
    if not isinstance(environment.runner, LocalRunner):
        raise FleetRunRefused("external Pi fleet requires one local Locust runner")
    if _config is None:
        raise FleetRunRefused("external Pi fleet round is not configured")
    options = environment.parsed_options
    if getattr(options, "num_users", None) != _config.expected_users or getattr(
        options, "spawn_rate", None
    ) != float(_config.expected_users):
        raise FleetRunRefused(
            "external Pi fleet requires the exact configured users and spawn rate"
        )
    if environment.host is not None:
        raise FleetRunRefused("external Pi fleet must not accept a Locust host")


def _validate_durable_runner(environment: Environment) -> None:
    if not isinstance(environment.runner, LocalRunner):
        raise FleetRunRefused("durable profile requires one local Locust runner")
    config = _durable_config
    if config is None:
        raise FleetRunRefused("durable profile is not configured")
    expected_users = len(config.specs)
    options = environment.parsed_options
    if getattr(options, "num_users", None) != expected_users or getattr(
        options, "spawn_rate", None
    ) != float(expected_users):
        raise FleetRunRefused(
            "durable profile requires exact users and immediate spawn rate"
        )
    if environment.host is not None:
        raise FleetRunRefused("durable profile must not accept a Locust host")


class DurableExternalTurnUser(User):
    wait_time = between(0, 0)

    @task
    def run_once(self) -> None:
        if getattr(self, "_durable_stream_started", False):
            raise StopUser()
        self._durable_stream_started = True
        config = _durable_config
        if config is None or not _await_durable_barrier(config):
            raise StopUser()
        ordinal = next(_durable_ordinals)
        if ordinal >= len(config.specs):
            _fail_durable_barrier("durable profile produced an extra user")
            raise StopUser()
        try:
            raw = config.transport.open_durable_stream(config.specs[ordinal])
            if not isinstance(raw, Mapping):
                raise FleetRunRefused("durable transport evidence is invalid")
            observation = build_durable_observation(**dict(raw))
        except BaseException:
            _fail_durable_barrier("durable transport failed")
            raise StopUser() from None
        _durable_observations.append(observation)
        raise StopUser()


class ExternalPiFleetUser(HttpUser):
    host = "http://127.0.0.1"
    wait_time = between(0, 0)

    def on_start(self) -> None:
        self.client.trust_env = False
        self.client.proxies.clear()

    @task
    def run_once(self) -> None:
        global _protocol_errors, _transport_errors
        if getattr(self, "_fleet_request_started", False):
            raise StopUser()
        self._fleet_request_started = True
        config = _config
        if config is None:
            raise StopUser()
        if not _await_concurrency_barrier(config):
            raise StopUser()
        ordinal = next(_ordinals)
        if ordinal >= config.expected_users:
            raise StopUser()
        replica = route_ordinal(
            ordinal, config.replicas, expected_users=config.expected_users
        )
        request = build_external_pi_fleet_request(ordinal, config.prompt)
        started = time.perf_counter()
        observation = BaselineObservation("error", 0)
        try:
            with self.client.post(
                f"{replica.worker_url}/v1/shadow",
                headers={"Authorization": f"Bearer {config.token}"},
                json=request.wire_payload(),
                name="external_pi.error",
                catch_response=True,
                timeout=10.0,
                allow_redirects=False,
            ) as response:
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
                observation = classify_external_pi_fleet_response(
                    request=request,
                    status_code=response.status_code,
                    payload=payload,
                    latency_ms=_elapsed_ms(started),
                )
                response.request_meta["name"] = (
                    f"external_pi.{observation.classification}"
                )
                if observation.classification == "error":
                    _protocol_errors += 1
                    response.failure("external_pi.error")
                else:
                    response.success()
        except RequestException:
            _transport_errors += 1
            observation = BaselineObservation("error", _elapsed_ms(started))
        _observations.append(observation)
        raise StopUser()
