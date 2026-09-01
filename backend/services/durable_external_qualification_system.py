"""Read-only host and database probes for durable staging qualification."""

from __future__ import annotations

import json
import grp
import os
import re
import stat
import subprocess
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values

from backend.loadtests.external_pi_fleet_core import (
    DurableQualificationProfile,
    HostResourceSnapshot,
)
from backend.services.durable_external_qualification import (
    MODAL_RATE_EVIDENCE_PATH,
    CleanupProof,
    DurableResourceSample,
    ImmutableFlagSnapshot,
    QualificationEnvironment,
    QualificationRefused,
    ScopedCleanupState,
    StagingQualificationPrerequisites,
    WholeWindowResourceSampler,
)


class SystemDurableQualificationControlPlane:
    """Read-only host adapter for one exact active staging qualification."""

    _FLAG_FIELDS = {
        "external_pi_admission": "chat_external_pi_admission_enabled",
    }

    _REQUIRED_RUNTIME_FLAGS = (
        "chat_sandbox_executor_enabled",
        "chat_remote_workspace_tools_enabled",
        "chat_remote_bash_enabled",
        "chat_remote_read_enabled",
        "chat_lazy_workspace_enabled",
    )

    def __init__(
        self,
        *,
        release_id: str,
        settings: object,
        app_root: Path = Path("/srv/paperswithcode"),
        environ: Mapping[str, str] = os.environ,
        mem_total: Callable[[], int],
        prerequisites: Callable[[], StagingQualificationPrerequisites],
        resource_preflight: Callable[
            [DurableQualificationProfile], HostResourceSnapshot
        ],
        sampler_factory: Callable[[DurableQualificationProfile], object],
        cleanup_probe: Callable[[], ScopedCleanupState],
        modal_rate_path: Path,
    ) -> None:
        self.release_id = release_id
        self.settings = settings
        self.app_root = app_root
        self.environ = environ
        self._mem_total = mem_total
        self._prerequisites = prerequisites
        self._resource_preflight = resource_preflight
        self._sampler_factory = sampler_factory
        self._cleanup_probe = cleanup_probe
        self.modal_rate_path = modal_rate_path
        self.qualification_scope_id: uuid.UUID | None = None
        self.scope_attempted = False

    def mark_scope_attempted(self) -> None:
        if self.scope_attempted:
            raise QualificationRefused("qualification_scope_invalid")
        self.scope_attempted = True

    def bind_scope(self, scope_id: uuid.UUID) -> None:
        if (
            not isinstance(scope_id, uuid.UUID)
            or self.qualification_scope_id is not None
        ):
            raise QualificationRefused("qualification_scope_invalid")
        self.scope_attempted = True
        self.qualification_scope_id = scope_id

    def _resolve_current(self, environment: str) -> str:
        current = self.app_root / "environments" / environment / "current"
        if not current.is_symlink():
            raise QualificationRefused("exact_staging_release_required")
        try:
            release = current.resolve(strict=True)
        except OSError:
            raise QualificationRefused("exact_staging_release_required") from None
        if release.parent != self.app_root / "releases":
            raise QualificationRefused("exact_staging_release_required")
        suffix = "staging" if environment == "staging" else "production"
        if re.fullmatch(rf"[0-9a-f]{{12}}-{suffix}", release.name) is None:
            raise QualificationRefused("exact_staging_release_required")
        return release.name

    def environment(self) -> QualificationEnvironment:
        staging_release = self._resolve_current("staging")
        production_release = self._resolve_current("production")
        if (
            getattr(self.settings, "environment", None) != "staging"
            or getattr(self.settings, "release_id", None) != self.release_id
            or self.environ.get("PWC_RELEASE_ID") != self.release_id
            or staging_release != self.release_id
            or production_release == staging_release
            or production_release.partition("-")[0] == staging_release.partition("-")[0]
        ):
            raise QualificationRefused("exact_staging_release_required")
        flags = self.snapshot_flags()
        return QualificationEnvironment(
            name="staging",
            target_release=self.release_id,
            staging_release=staging_release,
            production_release=production_release,
            host_mem_total_bytes=self._mem_total(),
            public_external_admission_flags=tuple(flags.values()),
        )

    def snapshot_flags(self) -> Mapping[str, bool]:
        result: dict[str, bool] = {}
        for name, field_name in self._FLAG_FIELDS.items():
            value = getattr(self.settings, field_name, None)
            if type(value) is bool:
                result[name] = value
            else:
                raise QualificationRefused(
                    "public_external_admission_flags_are_invalid"
                )
        return result

    def resource_snapshot(
        self, profile: DurableQualificationProfile
    ) -> HostResourceSnapshot:
        value = self._resource_preflight(profile)
        if not isinstance(value, HostResourceSnapshot):
            raise QualificationRefused("resource_preflight_invalid")
        return value

    def run_resources(self, profile: DurableQualificationProfile) -> object:
        return self._sampler_factory(profile)

    def setup_profile(self, profile: DurableQualificationProfile) -> None:
        self.environment()
        if profile.name != "32-functional-turns":
            raise QualificationRefused("binding_profile_order_required")
        evidence = self._prerequisites()
        configured_workers = configured_worker_ids(self.settings)
        evidence_workers = (
            tuple(worker_id for worker_id in evidence.worker_id.split(",") if worker_id)
            if isinstance(evidence, StagingQualificationPrerequisites)
            else ()
        )
        if not isinstance(evidence, StagingQualificationPrerequisites):
            raise QualificationRefused("staging_prerequisite_missing")
        if (
            not evidence.migrations_ready
            or not evidence.runtime_ready
            or evidence.worker_environment != "staging"
            or evidence.worker_id != evidence.configured_worker_id
            or configured_workers != evidence_workers
            or evidence.worker_release_id != self.release_id
            or evidence.worker_state != "ready"
            or evidence.worker_contract_version != "external-pi-v1"
            or evidence.maximum_sessions < 32
            or evidence.active_sessions != 0
            or getattr(self.settings, "chat_new_session_pi_percentage", None) != 100
            or not all(
                getattr(self.settings, field, None) is True
                for field in self._REQUIRED_RUNTIME_FLAGS
            )
        ):
            raise QualificationRefused("staging_prerequisite_missing")

    def restore_flags(self, flags: Mapping[str, bool]) -> Mapping[str, bool]:
        self.environment()
        expected = ImmutableFlagSnapshot.capture(flags)
        current = ImmutableFlagSnapshot.capture(self.snapshot_flags())
        if current != expected:
            raise QualificationRefused("public_external_admission_flags_drifted")
        return current.as_dict()

    def cleanup_transient_workers(self) -> CleanupProof:
        state = self._cleanup_probe()
        if not isinstance(state, ScopedCleanupState):
            raise QualificationRefused("cleanup_failed")
        proof = CleanupProof(
            exact_workers_drained=state.exact_workers_drained,
            transient_workers_removed=state.transient_workers == 0,
            listeners_gone=state.listeners == 0,
            status_files_gone=state.status_files == 0,
            processes_gone=state.processes == 0,
            final_active_backend_turns=state.active_backend_turns,
            final_active_external_workers=state.active_external_workers,
            final_active_sandboxes=state.active_sandboxes,
        )
        self.qualification_scope_id = None
        return proof

    def protected_runtime_evidence(
        self, _profile: DurableQualificationProfile
    ) -> Mapping[str, str]:
        try:
            metadata = self.modal_rate_path.stat()
            if (
                not self.modal_rate_path.is_file()
                or metadata.st_uid != 0
                or metadata.st_mode & 0o777 != 0o600
                or metadata.st_size > 4_096
            ):
                raise OSError
            payload = json.loads(self.modal_rate_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise QualificationRefused(
                "protected_modal_rate_evidence_invalid"
            ) from None
        expected_keys = {
            "PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND",
            "PWC_MODAL_EXECUTOR_RATE_SOURCE_ID",
            "PWC_RELEASE_ID",
        }
        try:
            rate = int(payload.get("PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND", ""))
        except (AttributeError, TypeError, ValueError):
            rate = 0
        if (
            not isinstance(payload, dict)
            or set(payload) != expected_keys
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in payload.items()
            )
            or payload["PWC_RELEASE_ID"] != self.release_id
            or payload["PWC_MODAL_EXECUTOR_RATE_SOURCE_ID"] != "modal-staging-price-v1"
            or not 1 <= rate <= 1_000_000
        ):
            raise QualificationRefused("protected_modal_rate_evidence_invalid")
        return payload


def configured_worker_ids(settings: object) -> tuple[str, ...]:
    endpoints = getattr(settings, "chat_external_pi_worker_endpoints", ())
    if not isinstance(endpoints, (tuple, list)):
        return ()
    result = []
    for endpoint in endpoints:
        worker_id = (
            endpoint.get("worker_id")
            if isinstance(endpoint, Mapping)
            else getattr(endpoint, "worker_id", None)
        )
        if not isinstance(worker_id, str) or not worker_id:
            return ()
        result.append(worker_id)
    if result:
        return tuple(result)
    worker_id = getattr(settings, "chat_external_pi_worker_id", "")
    worker_url = getattr(settings, "chat_external_pi_worker_url", "")
    worker_token = getattr(settings, "chat_external_pi_worker_token", "")
    if (
        isinstance(worker_id, str)
        and worker_id
        and isinstance(worker_url, str)
        and worker_url
        and isinstance(worker_token, str)
        and len(worker_token) >= 32
    ):
        return (worker_id,)
    return ()


def load_protected_staging_settings(
    path: Path = Path("/etc/paperswithcode/staging.env"),
):
    """Load staging credentials from one root-owned file, without ambient env."""
    from backend.config import Settings

    try:
        metadata = path.lstat()
        staging_gid = grp.getgrnam("pwc-staging").gr_gid
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != staging_gid
            or stat.S_IMODE(metadata.st_mode) != 0o640
            or metadata.st_size > 256 * 1024
        ):
            raise OSError
        raw = dotenv_values(path)
    except (KeyError, OSError, UnicodeError):
        raise QualificationRefused("protected_staging_settings_invalid") from None
    values = {
        key.removeprefix("PWC_").lower(): value
        for key, value in raw.items()
        if key.startswith("PWC_")
        and value is not None
        and key.removeprefix("PWC_").lower() in Settings.model_fields
    }
    try:
        settings = Settings.model_validate(values)
    except ValueError:
        raise QualificationRefused("protected_staging_settings_invalid") from None
    if (
        settings.environment != "staging"
        or len(settings.admin_api_token) < 32
        or len(settings.jwt_secret) < 32
    ):
        raise QualificationRefused("protected_staging_settings_invalid")
    return settings


def bind_active_staging_worker(
    settings: object, *, app_root: Path = Path("/srv/paperswithcode")
):
    """Bind protected settings to the exact active staging loopback worker."""
    active = app_root / "environments/staging/active"
    try:
        resolved = active.resolve(strict=True)
    except OSError:
        raise QualificationRefused("active_staging_worker_required") from None
    slot = resolved.name
    expected = app_root / f"environments/staging/slots/{slot}"
    token = getattr(settings, "chat_external_pi_worker_token", "")
    if (
        not active.is_symlink()
        or slot not in {"blue", "green"}
        or resolved != expected.resolve(strict=True)
        or getattr(settings, "environment", "") != "staging"
        or getattr(settings, "chat_external_pi_worker_endpoints", ())
        or getattr(settings, "chat_external_pi_worker_id", "")
        or getattr(settings, "chat_external_pi_worker_url", "")
        or not isinstance(token, str)
        or len(token) < 32
    ):
        raise QualificationRefused("active_staging_worker_required")
    from deploy.external_pi_slot_topology import external_pi_endpoints

    endpoints = json.loads(external_pi_endpoints("staging", slot, token))
    return settings.model_copy(
        update={
            "chat_external_pi_worker_id": "",
            "chat_external_pi_worker_url": "",
            "chat_external_pi_worker_token": "",
            "chat_external_pi_worker_endpoints": endpoints,
            "chat_external_pi_worker_contract_version": "external-pi-v1",
            "chat_external_pi_worker_max_sessions": 8,
        }
    )


def _proc_memory_value(name: str) -> int:
    prefix = f"{name}:"
    for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
        if line.startswith(prefix):
            fields = line.split()
            if len(fields) == 3 and fields[2] == "kB":
                return int(fields[1]) * 1024
    raise QualificationRefused("host_memory_evidence_unavailable")


def _systemctl_memory(unit: str) -> int:
    result = subprocess.run(
        ["systemctl", "show", "--property=MemoryCurrent", unit],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise QualificationRefused("process_memory_evidence_unavailable")
    _, separator, raw = result.stdout.strip().partition("=")
    try:
        value = int(raw) if separator else 0
    except ValueError:
        value = 0
    if value <= 0:
        raise QualificationRefused("process_memory_evidence_unavailable")
    return value


class _SystemResourceEvidence:
    def __init__(self, control_plane: SystemDurableQualificationControlPlane) -> None:
        self.control_plane = control_plane
        self._cpu: tuple[int, int] | None = None

    @staticmethod
    def _cpu_counters() -> tuple[int, int]:
        fields = Path("/proc/stat").read_text(encoding="ascii").splitlines()[0].split()
        if not fields or fields[0] != "cpu" or len(fields) < 6:
            raise QualificationRefused("host_cpu_evidence_unavailable")
        counters = tuple(int(value) for value in fields[1:])
        return sum(counters), counters[3] + counters[4]

    def _cpu_percent(self) -> float:
        current = self._cpu_counters()
        previous = self._cpu
        self._cpu = current
        if previous is None:
            return 0.0
        total = current[0] - previous[0]
        idle = current[1] - previous[1]
        if total <= 0:
            raise QualificationRefused("host_cpu_evidence_unavailable")
        return max(0.0, min(100.0, (total - idle) * 100 / total))

    def _scope_counts(
        self, *, include_terminal_reservations: bool = False
    ) -> tuple[int, int, int]:
        scope_id = self.control_plane.qualification_scope_id
        if scope_id is None:
            raise QualificationRefused("qualification_scope_invalid")
        worker_ids = configured_worker_ids(self.control_plane.settings)
        if not 1 <= len(worker_ids) <= 4:
            raise QualificationRefused("staging_prerequisite_missing")
        from sqlalchemy import text

        from backend.database.connection import db_manager

        with db_manager.session_local() as db:
            if include_terminal_reservations:
                turn_count_sql = """
                    SELECT count(*)
                    FROM chat_external_worker_reservations AS reservation
                    JOIN chat_turn_latency AS latency
                      ON latency.turn_id = reservation.turn_id
                    WHERE latency.qualification_scope_id = :scope_id
                      AND reservation.worker_id = ANY(CAST(:worker_ids AS text[]))
                      AND reservation.release_id = :release_id
                      AND reservation.expires_at > now()
                """
            else:
                turn_count_sql = """
                    SELECT count(*)
                    FROM chat_turn_latency
                    WHERE qualification_scope_id = :scope_id
                      AND terminal_status = 'running'
                """
            active_turns = int(
                db.execute(
                    text(turn_count_sql),
                    {
                        "scope_id": scope_id,
                        "worker_ids": list(worker_ids),
                        "release_id": self.control_plane.release_id,
                    },
                ).scalar_one()
            )
            workers = int(
                db.execute(
                    text(
                        """
                        SELECT count(DISTINCT reservation.worker_id)
                        FROM chat_external_worker_reservations AS reservation
                        JOIN chat_turn_latency AS latency
                          ON latency.turn_id = reservation.turn_id
                        WHERE latency.qualification_scope_id = :scope_id
                          AND reservation.worker_id = ANY(CAST(:worker_ids AS text[]))
                          AND reservation.release_id = :release_id
                          AND reservation.expires_at > now()
                          AND (
                            :include_terminal_reservations
                            OR latency.terminal_status = 'running'
                          )
                        """
                    ),
                    {
                        "scope_id": scope_id,
                        "worker_ids": list(worker_ids),
                        "release_id": self.control_plane.release_id,
                        "include_terminal_reservations": include_terminal_reservations,
                    },
                ).scalar_one()
            )
            sandbox_delta = int(
                db.execute(
                    text(
                        """
                        SELECT coalesce(sum(
                          CASE
                            WHEN event_type IN ('workspace_created','workspace_reused') THEN 1
                            WHEN event_type = 'workspace_evicted' THEN -1
                            ELSE 0
                          END
                        ), 0)
                        FROM chat_qualification_evidence_events
                        WHERE qualification_scope_id = :scope_id
                        """
                    ),
                    {"scope_id": scope_id},
                ).scalar_one()
            )
        return active_turns, workers, max(0, sandbox_delta)

    def sample(self) -> DurableResourceSample:
        active_turns, workers, sandboxes = self._scope_counts()
        active = self.control_plane.app_root / "environments/staging/active"
        if not active.is_symlink():
            raise QualificationRefused("active_staging_worker_required")
        slot = active.resolve(strict=True).name
        if slot not in {"blue", "green"}:
            raise QualificationRefused("active_staging_worker_required")
        return DurableResourceSample(
            process_memory_bytes=_systemctl_memory(
                f"paperswithcode-staging-backend@{slot}.service"
            ),
            worker_memory_bytes=_systemctl_memory(
                f"paperswithcode-staging-external-pi-worker@{slot}.service"
            ),
            host_mem_available_bytes=_proc_memory_value("MemAvailable"),
            host_cpu_percent=self._cpu_percent(),
            active_backend_turns=active_turns,
            active_external_workers=workers,
            active_sandboxes=sandboxes,
        )


def _system_prerequisites(settings: object, release_id: str):
    from sqlalchemy import select, text

    from backend.database.connection import db_manager
    from backend.models.database import ChatExternalWorker
    from backend.services.runtime_validation import (
        validate_chat_schema,
        validate_external_worker_reservation_schema,
        validate_qualification_evidence_schema,
    )

    configured_workers = configured_worker_ids(settings)
    worker_id = ",".join(configured_workers)
    migrations_ready = False
    with db_manager.session_local() as db:
        identity = db.execute(text("SELECT current_user, current_schema()")).one()
        if tuple(identity) != ("pwc_staging", "staging"):
            raise QualificationRefused("staging_database_required")
        try:
            validate_chat_schema(db, settings)
            validate_external_worker_reservation_schema(db)
            validate_qualification_evidence_schema(db)
            migrations_ready = True
        except RuntimeError:
            migrations_ready = False
        workers = tuple(
            db.scalars(
                select(ChatExternalWorker).where(
                    ChatExternalWorker.worker_id.in_(configured_workers),
                    ChatExternalWorker.environment == "staging",
                    ChatExternalWorker.lease_expires_at > datetime.now(UTC),
                )
            )
        )
    runtime_ready = all(
        getattr(settings, name, False)
        for name in (
            "chat_pi_runtime_enabled",
            "chat_external_pi_supervisor_enabled",
            "chat_external_pi_ready_registry_enabled",
            "chat_durable_turn_dispatch_enabled",
            "chat_turn_event_journal_schema_enabled",
            "chat_sandbox_executor_enabled",
            "chat_remote_workspace_tools_enabled",
            "chat_remote_bash_enabled",
            "chat_remote_read_enabled",
            "chat_lazy_workspace_enabled",
        )
    ) and (
        getattr(settings, "chat_new_session_pi_percentage", None) == 100
        and getattr(settings, "chat_external_pi_worker_contract_version", "")
        == "external-pi-v1"
        and getattr(settings, "chat_external_pi_runtime_contract_version", "")
        == "durable-external-pi-v1"
    )
    if not configured_workers or len(workers) != len(configured_workers):
        return StagingQualificationPrerequisites(
            migrations_ready=migrations_ready,
            runtime_ready=runtime_ready,
            worker_environment="",
            worker_id="",
            configured_worker_id=worker_id,
            worker_release_id="",
            worker_state="",
            worker_contract_version="",
            maximum_sessions=0,
            active_sessions=0,
        )
    worker_by_id = {worker.worker_id: worker for worker in workers}
    ordered_workers = tuple(worker_by_id[value] for value in configured_workers)
    shared_release = {worker.release_id for worker in ordered_workers}
    shared_environment = {worker.environment for worker in ordered_workers}
    shared_state = {worker.state for worker in ordered_workers}
    shared_contract = {worker.contract_version for worker in ordered_workers}
    return StagingQualificationPrerequisites(
        migrations_ready=migrations_ready,
        runtime_ready=runtime_ready,
        worker_environment=(
            shared_environment.pop() if len(shared_environment) == 1 else ""
        ),
        worker_id=worker_id,
        configured_worker_id=worker_id,
        worker_release_id=shared_release.pop() if len(shared_release) == 1 else "",
        worker_state=shared_state.pop() if len(shared_state) == 1 else "",
        worker_contract_version=(
            shared_contract.pop() if len(shared_contract) == 1 else ""
        ),
        maximum_sessions=sum(worker.maximum_sessions for worker in ordered_workers),
        active_sessions=sum(worker.active_sessions for worker in ordered_workers),
    )


def _host_cpu_percent() -> float:
    before = _SystemResourceEvidence._cpu_counters()
    time.sleep(1.0)
    after = _SystemResourceEvidence._cpu_counters()
    total = after[0] - before[0]
    idle = after[1] - before[1]
    if total <= 0:
        raise QualificationRefused("host_cpu_evidence_unavailable")
    return max(0.0, min(100.0, (total - idle) * 100 / total))


def _system_resource_preflight(
    _profile: DurableQualificationProfile,
) -> HostResourceSnapshot:
    # This explicit fixed envelope is for the approved 32-turn profile. It is
    # not scaled upward from detected host RAM.
    return HostResourceSnapshot(
        mem_available_bytes=_proc_memory_value("MemAvailable"),
        projected_additional_bytes=2 * 1024**3,
        cpu_percent=_host_cpu_percent(),
        cpu_guard_percent=80.0,
    )


def system_cleanup_state(
    control_plane: SystemDurableQualificationControlPlane,
) -> ScopedCleanupState:
    scope_id = control_plane.qualification_scope_id
    if scope_id is None:
        return ScopedCleanupState(
            not control_plane.scope_attempted, 0, 0, 0, 0, 0, 0, 0
        )
    evidence = _SystemResourceEvidence(control_plane)
    active_turns, active_workers, sandboxes = evidence._scope_counts(
        include_terminal_reservations=True
    )
    exact_drained = active_turns == 0 and active_workers == 0 and sandboxes == 0
    return ScopedCleanupState(
        exact_workers_drained=exact_drained,
        transient_workers=0,
        listeners=0,
        status_files=0,
        processes=0,
        active_backend_turns=active_turns,
        active_external_workers=active_workers,
        active_sandboxes=sandboxes,
    )


def build_system_control_plane(
    *,
    release_id: str,
    settings: object,
    app_root: Path = Path("/srv/paperswithcode"),
    environ: Mapping[str, str] = os.environ,
) -> SystemDurableQualificationControlPlane:
    control: SystemDurableQualificationControlPlane
    control = SystemDurableQualificationControlPlane(
        release_id=release_id,
        settings=settings,
        app_root=app_root,
        environ=environ,
        mem_total=lambda: _proc_memory_value("MemTotal"),
        prerequisites=lambda: _system_prerequisites(settings, release_id),
        resource_preflight=_system_resource_preflight,
        sampler_factory=lambda _profile: WholeWindowResourceSampler(
            sample=_SystemResourceEvidence(control).sample,
            interval_seconds=1.0,
        ),
        cleanup_probe=lambda: system_cleanup_state(control),
        modal_rate_path=MODAL_RATE_EVIDENCE_PATH,
    )
    return control
