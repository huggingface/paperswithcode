"""Modal deltas, latency fixtures, and builders shared by fleet qualification tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


from backend.loadtests.external_pi_fleet_core import (
    CleanupEvidence,
    FleetReplica,
    ForbiddenActivity,
    HostResourceSnapshot,
    ResourceEvidence,
    ResourcePreflight,
    UnitResourceEvidence,
    WorkerEvidence,
    aggregate_round,
    evaluate_resource_preflight,
    qualification_unit_names,
    resolve_fleet_shape,
    aggregate_durable_profile,
    DurableTurnObservation,
    ModalLifecycleDelta,
    ModalLifecycleSnapshot,
    ModalRateEvidence,
    DurableQualificationEvidence,
    PERSISTENT_TRANSPORT_SCENARIOS,
)
from backend.loadtests.external_pi_shadow_core import (
    BaselineObservation,
)
from deploy.external_pi_qualification_contract import (
    QUALIFICATION_PORTS,
    QUALIFICATION_SUPERVISOR_UNITS,
    QUALIFICATION_WORKER_IDS,
    QUALIFICATION_WORKER_UNITS,
)


_NO_MODAL = ModalLifecycleDelta(creates=0, reuses=0, evictions=0, active_duration_ms=0)


_FUNCTIONAL_MODAL = ModalLifecycleDelta(
    creates=1, reuses=15, evictions=0, active_duration_ms=16_000
)


_MODAL_RATE = ModalRateEvidence(
    microusd_per_second=25,
    source="protected_runtime",
    source_id="modal-staging-price-v1",
    release_id="0123456789ab-staging",
    attested_at_ms=1,
)


_SERVER_LATENCY_P95 = {
    "no_tool": {
        "provider_gateway_received_ms": 300,
        "provider_ttft_ms": 400,
        "first_semantic_event_ms": 500,
    },
    "read": {
        "provider_gateway_received_ms": 310,
        "provider_ttft_ms": 410,
        "first_semantic_event_ms": 510,
    },
    "bash": {
        "provider_gateway_received_ms": 320,
        "provider_ttft_ms": 420,
        "first_semantic_event_ms": 520,
    },
}


def _persistent_transport_manifest() -> dict[str, object]:
    return {
        "schema_version": "persistent-executor-release-qualification-v1",
        "status": "release_qualification",
        "attempt_id": "a" * 64,
        "source_commit": "b" * 40,
        "preliminary_report_sha256": "c" * 64,
        "signed_component_manifest_sha256": "d" * 64,
        "modal_image_digest": "e" * 64,
        "modal_region": "eu-west",
        "chaos_declared": False,
        "percentile_method": "nearest_rank",
        "scenarios": list(PERSISTENT_TRANSPORT_SCENARIOS),
        "concurrent_turns": 32,
        "operations_per_turn": 4,
        "concurrent_operations": 128,
        "offered_turns": 64,
        "overload_rejections": 32,
        "loaded_clients": 1000,
        "minimum_soak_turns": 320,
        "minimum_soak_minutes": 60,
        "reconnect_ready_p99_ms_max": 5000,
        "authentication_starts_per_second_max": 250,
        "route_health_ms_max": 5000,
        "breaker_open_failures": 3,
        "breaker_failure_window_seconds": 60,
        "breaker_open_seconds": 30,
        "breaker_close_successes": 3,
        "drain_seconds_max": 240,
        "alert_ack_ms_max": 60000,
        "heartbeat_checkpoint_updates_per_second_max": 34,
        "public_operation_output_bytes_max": 24576,
        "public_turn_output_bytes_max": 98304,
        "operation_unacked_bytes_max": 65536,
        "stream_unacked_bytes_max": 262144,
        "connection_unacked_bytes_max": 524288,
        "command_bytes_max": 65536,
        "path_bytes_max": 4096,
        "bash_timeout_ms_max": 30000,
        "remote_read_bytes_max": 1048576,
        "preauth_frame_bytes_max": 2048,
        "preauth_deadline_ms_max": 2000,
        "invalid_per_source_rate": 10,
        "invalid_per_source_burst": 20,
        "invalid_per_shard_rate": 100,
        "invalid_per_shard_burst": 200,
        "host_cpu_percent_exclusive_max": 80,
        "host_mem_available_mib_min": 1536,
        "total_spend_microusd_max": 16250000,
        "provider_call_max": 0,
        "retain_unknown_spend_reservation": True,
        "stop_on_first_failed_gate": True,
    }


def _live_qualification_evidence():
    return DurableQualificationEvidence(
        expected_users=32,
        admitted_turns=32,
        admission_denominator_events=32,
        terminal_turns=32,
        queued_states=0,
        stale_fences=0,
        executor_starts=16,
        duplicate_executor_starts=0,
        workspace_creates=1,
        workspace_reuses=15,
        workspace_evictions=16,
        billed_duration_ms=16_000,
        window_started_at_ms=1,
        window_ended_at_ms=2,
        p95_server_latency_ms_by_workload=_SERVER_LATENCY_P95,
        source="durable_qualification_records",
    )


class _LifecycleSource:
    def __init__(self, delta: ModalLifecycleDelta = _NO_MODAL):
        self.delta = delta
        self.calls = 0

    def snapshot(self, _profile_name):
        self.calls += 1
        before = self.calls % 2 == 1
        return ModalLifecycleSnapshot(
            captured_at_ms=self.calls,
            creates=0 if before else self.delta.creates,
            reuses=0 if before else self.delta.reuses,
            evictions=0 if before else self.delta.evictions,
            active_duration_ms=0 if before else self.delta.active_duration_ms,
            source="application_modal_lifecycle",
        )


class _DurableOperator:
    def __init__(
        self,
        *,
        environment=None,
        refuse_profile=None,
        failure_stage=None,
        prior_flags=None,
        cpu_percent=20.0,
        cpu_guard_percent=80.0,
        mutate_snapshot=False,
        no_op_proof=False,
    ):
        from backend.scripts.qualify_durable_external_turns import (
            QualificationEnvironment,
        )

        self.current_environment = environment or QualificationEnvironment(
            name="staging",
            target_release="0123456789ab-staging",
            staging_release="0123456789ab-staging",
            production_release="fedcba987654-production",
            host_mem_total_bytes=16 * 1024**3,
            public_external_admission_flags=(False, False, False),
        )
        self.refuse_profile = refuse_profile
        self.failure_stage = failure_stage
        self.prior_flags = (
            prior_flags
            if prior_flags is not None
            else {"external": False, "executor": False, "remote": False}
        )
        self.cpu_percent = cpu_percent
        self.cpu_guard_percent = cpu_guard_percent
        self.mutate_snapshot = mutate_snapshot
        self.no_op_proof = no_op_proof
        self.events = []

    def _fail(self, stage):
        if self.failure_stage == stage:
            raise RuntimeError(f"TOP_SECRET_{stage}")
        if self.failure_stage == f"interrupt:{stage}":
            raise KeyboardInterrupt(f"TOP_SECRET_{stage}")

    def environment(self):
        self.events.append(("environment",))
        self._fail("environment")
        return self.current_environment

    def snapshot_flags(self):
        self.events.append(("snapshot_flags",))
        self._fail("snapshot_flags")
        return self.prior_flags

    def resource_snapshot(self, profile):
        self.events.append(("resource", profile.name))
        self._fail("resource")
        available = 1024**3 if profile.name == self.refuse_profile else 3 * 1024**3
        return HostResourceSnapshot(
            available,
            0,
            self.cpu_percent,
            self.cpu_guard_percent,
        )

    def setup_profile(self, profile):
        self.events.append(("setup", profile.name))
        if self.mutate_snapshot:
            self.prior_flags["external"] = True
        self._fail("setup")

    def run_profile(self, profile):
        self.events.append(("run", profile.name))
        self._fail("run")
        observations = tuple(
            DurableTurnObservation(
                workload=workload,
                outcome="completed",
                ttft_ms=100,
                completion_ms=1_000,
                model_starts=1,
                operation_start_count=0,
                duplicate_operation_start_count=0,
                terminal_cause="completed",
            )
            for workload in profile.workloads
        )
        return aggregate_durable_profile(
            profile=profile,
            observations=observations,
            peak_memory_bytes=1024**3,
            minimum_host_mem_available_bytes=2 * 1024**3,
            peak_cpu_percent=20.0,
            peak_active_backend_turns=profile.expected_users,
            peak_active_external_workers=4,
            peak_active_sandboxes=(1 if profile.name == "32-functional-turns" else 0),
            modal_lifecycle=(
                _FUNCTIONAL_MODAL
                if profile.name == "32-functional-turns"
                else _NO_MODAL
            ),
            modal_rate=_MODAL_RATE,
        )

    def teardown_profile(self, profile, scope_id=None):
        self.events.append(("teardown", profile.name))
        if self.failure_stage == f"teardown:{profile.name}":
            raise RuntimeError("TOP_SECRET_teardown")
        self._fail("teardown")

    def restore_flags(self, flags):
        restored = dict(flags)
        self.events.append(("restore_flags", restored))
        self._fail("restore_flags")
        return None if self.no_op_proof else restored

    def cleanup_transient_workers(self):
        self.events.append(("cleanup_transient_workers",))
        self._fail("cleanup_transient_workers")
        if self.no_op_proof:
            return None
        from backend.scripts.qualify_durable_external_turns import CleanupProof

        return CleanupProof(
            exact_workers_drained=True,
            transient_workers_removed=True,
            listeners_gone=True,
            status_files_gone=True,
            processes_gone=True,
            final_active_backend_turns=0,
            final_active_external_workers=0,
            final_active_sandboxes=0,
        )


def _round(
    name: str, *, expected_users: int = 100, latency_ms: int = 100, activity=None
):
    return aggregate_round(
        name=name,
        expected_users=expected_users,
        observations=tuple(
            BaselineObservation("compatible", latency_ms) for _ in range(expected_users)
        ),
        protocol_errors=0,
        transport_errors=0,
        forbidden_activity=activity or ForbiddenActivity(),
    )


def _cleanup(**updates) -> CleanupEvidence:
    values = {
        "drain_proven": True,
        "registry_offline": True,
        "supervisors_stopped_before_workers": True,
        "units_removed": True,
        "status_files_removed": True,
        "ports_free": True,
        "processes_gone": True,
    }
    values.update(updates)
    return CleanupEvidence(**values)


def _unit_resources(shape_name: str) -> tuple[UnitResourceEvidence, ...]:
    return tuple(
        UnitResourceEvidence(
            unit_name=unit_name,
            peak_memory_bytes=100_000_000,
            peak_cpu_percent=10.0,
            peak_tasks=4,
        )
        for unit_name in qualification_unit_names(resolve_fleet_shape(shape_name))
    )


def _resources(shape_name: str = "5x32", **updates) -> ResourceEvidence:
    values = {
        "peak_memory_bytes": 300_000_000,
        "peak_cpu_percent": 40.0,
        "peak_tasks": 20,
        "minimum_host_mem_available_bytes": 2 * 1024**3,
        "unit_peaks": _unit_resources(shape_name),
    }
    values.update(updates)
    return ResourceEvidence(**values)


def _passed_resource_preflight():
    return evaluate_resource_preflight(
        HostResourceSnapshot(
            mem_available_bytes=3 * 1024**3,
            projected_additional_bytes=1024**3,
            cpu_percent=20.0,
            cpu_guard_percent=80.0,
        )
    )


def _workers(shape_name: str) -> tuple[WorkerEvidence, ...]:
    shape = resolve_fleet_shape(shape_name)
    return tuple(
        WorkerEvidence(
            worker_id=replica.worker_id,
            port=replica.port,
            generation=index + 1,
            maximum_sessions=shape.sessions_per_worker,
        )
        for index, replica in enumerate(shape.replicas)
    )


class _FleetOperator:
    runtime_id = "external-pi-runtime-1"
    owner_id = "test-owner"

    def __init__(self, *, refuse=()):
        self.refuse = set(refuse)
        self.events = []

    def revalidate(self, shape, active):
        self.events.append(
            ("revalidate", shape.name, tuple(item.worker_id for item in active))
        )

    def resource_preflight(self, shape):
        self.events.append(("resource_preflight", shape.name))
        if shape.name in self.refuse:
            return ResourcePreflight("resource_refused", 1024**3, 20.0, 80.0)
        return _passed_resource_preflight()

    def resolve(self, shape, index):
        replica = FleetReplica(
            QUALIFICATION_WORKER_IDS[index], QUALIFICATION_PORTS[index]
        )
        return SimpleNamespace(
            index=index,
            worker_id=replica.worker_id,
            port=replica.port,
            maximum_sessions=shape.sessions_per_worker,
            supervisor_unit=QUALIFICATION_SUPERVISOR_UNITS[index],
            worker_unit=QUALIFICATION_WORKER_UNITS[index],
            status_path=Path(f"/tmp/{replica.worker_id}.json"),
        )

    def start(self, resolved):
        self.events.append(("start", resolved.worker_id))

    def wait_ready(self, resolved):
        generation = resolved.index + 10
        self.events.append(("ready", resolved.worker_id, generation))
        return generation

    def prepare_round(self):
        self.events.append(("prepare_round", None))

    def run_round(
        self,
        name,
        workers,
        *,
        expected_users=100,
        abort_requested=lambda: False,
    ):
        self.events.append(
            (
                "round",
                name,
                tuple(worker.worker_id for worker in workers),
                expected_users,
            )
        )
        return _round(name, expected_users=expected_users)

    def sample_resources(self, shape):
        self.events.append(("resources", shape.name))
        return _resources(shape.name)

    def cleanup(self, resolved, generation):
        self.events.append(("cleanup", resolved.worker_id, generation))
        return SimpleNamespace(
            registry_offline=True,
            supervisors_stopped_before_workers=True,
            units_removed=True,
            status_files_removed=True,
            ports_free=True,
            processes_gone=True,
        )

    def cleanup_postconditions(self, _shape):
        return _cleanup()

    def set_owner(self, owner_id):
        self.owner_id = owner_id

    def owned_units(self, _resolved):
        return ()

    def recovery_postconditions(self, resolved, owned_units):
        cleaned = any(
            event[0] == "cleanup" and event[1] == resolved.worker_id
            for event in self.events
        )
        cleanup = (
            _cleanup()
            if cleaned or not owned_units
            else _cleanup(units_removed=False, processes_gone=False)
        )
        return cleanup, (() if cleanup.passed else owned_units)
