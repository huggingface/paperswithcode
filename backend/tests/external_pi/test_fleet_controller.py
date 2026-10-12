"""Fleet controller sequencing, recovery, and cleanup."""

from __future__ import annotations

import json
import signal
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.loadtests.external_pi_fleet_core import (
    FleetRunRefused,
    ForbiddenActivity,
    WorkerEvidence,
    resolve_fleet_shape,
)
from deploy.external_pi_qualification_contract import (
    QUALIFICATION_SUPERVISOR_UNITS,
    QUALIFICATION_WORKER_IDS,
)
from backend.tests.external_pi.fleet_harness import (
    _FleetOperator,
    _cleanup,
)


def test_guarded_round_prepares_runtime_before_starting_resource_sampler():
    from backend.scripts.qualify_external_pi_fleet import _run_guarded_round

    class OrderedOperator(_FleetOperator):
        def prepare_round(self):
            assert threading.current_thread() is threading.main_thread()
            super().prepare_round()

        def sample_resources(self, shape):
            assert ("prepare_round", None) in self.events
            return super().sample_resources(shape)

    operator = OrderedOperator()
    shape = resolve_fleet_shape("2x32")
    workers = tuple(
        WorkerEvidence(
            worker_id=replica.worker_id,
            port=replica.port,
            generation=1,
            maximum_sessions=shape.sessions_per_worker,
        )
        for replica in shape.replicas
    )

    report, samples = _run_guarded_round(operator, shape, "healthy", workers)

    assert report.passed is True
    assert samples
    assert operator.events.index(("prepare_round", None)) < next(
        index for index, event in enumerate(operator.events) if event[0] == "resources"
    )


def test_controller_runs_shapes_sequentially_healthy_then_exact_generation_loss(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    operator = _FleetOperator(refuse={"16x8"})
    report_path = tmp_path / "fleet.json"
    report = run_fleet_controller(
        operator,
        release_id="0123456789ab-staging",
        report_path=report_path,
        report_root=tmp_path,
        geteuid=lambda: 0,
    )

    assert [shape.status for shape in report.shapes] == [
        "completed",
        "completed",
        "resource_refused",
    ]
    assert [shape.removed_worker_id for shape in report.shapes[:2]] == [
        "staging-qualification-00",
        "staging-qualification-00",
    ]
    assert [event[:2] for event in operator.events if event[0] == "round"] == [
        ("round", "healthy"),
        ("round", "survivor"),
        ("round", "healthy"),
        ("round", "survivor"),
    ]
    assert ("cleanup", "staging-qualification-00", 10) in operator.events
    second_shape_preflight = operator.events.index(("resource_preflight", "8x16"))
    first_shape_last_cleanup = max(
        index
        for index, event in enumerate(operator.events)
        if index < second_shape_preflight and event[0] == "cleanup"
    )
    assert first_shape_last_cleanup < second_shape_preflight
    assert any(event[0] == "resources" for event in operator.events)
    transition_indices = [
        index
        for index, event in enumerate(operator.events)
        if event[0] in {"start", "ready", "round", "cleanup"}
    ]
    revalidation_indices = [
        index for index, event in enumerate(operator.events) if event[0] == "revalidate"
    ]
    for index in transition_indices:
        assert any(candidate < index for candidate in revalidation_indices)
        assert any(candidate > index for candidate in revalidation_indices)
    assert report_path.stat().st_mode & 0o777 == 0o600


def test_controller_binds_capacity_profile_rounds_to_exact_expected_users(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    operator = _FleetOperator()
    report = run_fleet_controller(
        operator,
        release_id="0123456789ab-staging",
        report_path=tmp_path / "capacity.json",
        report_root=tmp_path,
        shape_names=("2x32",),
        geteuid=lambda: 0,
    )

    assert report.shapes[0].expected_users == 32
    assert [event[3] for event in operator.events if event[0] == "round"] == [
        32,
        32,
    ]


def test_capacity_controller_stops_at_first_resource_refusal(tmp_path: Path):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    operator = _FleetOperator(refuse={"4x16"})
    report = run_fleet_controller(
        operator,
        release_id="0123456789ab-staging",
        report_path=tmp_path / "capacity.json",
        report_root=tmp_path,
        shape_names=("2x32", "4x16", "3x32"),
        stop_on_nonpassing_shape=True,
        geteuid=lambda: 0,
    )

    assert [shape.shape for shape in report.shapes] == ["2x32", "4x16"]
    assert not any(event[1] == "3x32" for event in operator.events)


def test_capacity_controller_stops_at_first_failed_shape(tmp_path: Path):
    from backend.scripts.qualify_external_pi_fleet import (
        qualification_exit_code,
        run_fleet_controller,
    )

    class FailedVerdictOperator(_FleetOperator):
        def run_round(
            self,
            name,
            workers,
            *,
            expected_users,
            abort_requested=lambda: False,
        ):
            report = super().run_round(
                name,
                workers,
                expected_users=expected_users,
                abort_requested=abort_requested,
            )
            if len(workers) in {3, 4} and expected_users == 48:
                return report.model_copy(
                    update={"forbidden_activity": ForbiddenActivity(model_calls=1)}
                )
            return report

    operator = FailedVerdictOperator()
    report = run_fleet_controller(
        operator,
        release_id="0123456789ab-staging",
        report_path=tmp_path / "capacity.json",
        report_root=tmp_path,
        shape_names=("2x32", "4x16", "3x32"),
        stop_on_nonpassing_shape=True,
        geteuid=lambda: 0,
    )

    assert [shape.shape for shape in report.shapes] == ["2x32", "4x16"]
    assert report.shapes[-1].overall_passed is False
    assert qualification_exit_code(report) == 1
    assert not any(event[1] == "3x32" for event in operator.events)


def test_controller_always_cleans_every_observed_generation_on_round_failure(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class FailingOperator(_FleetOperator):
        def run_round(
            self,
            name,
            workers,
            *,
            expected_users,
            abort_requested=lambda: False,
        ):
            super().run_round(
                name,
                workers,
                expected_users=expected_users,
                abort_requested=abort_requested,
            )
            raise RuntimeError("protected response body")

    operator = FailingOperator()
    report_path = tmp_path / "fleet.json"
    report_path.write_text('{"previous":true}\n', encoding="utf-8")

    with pytest.raises(RuntimeError, match="protected response body"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    assert [event for event in operator.events if event[0] == "cleanup"] == [
        ("cleanup", "staging-qualification-00", 10),
        ("cleanup", "staging-qualification-01", 11),
        ("cleanup", "staging-qualification-02", 12),
        ("cleanup", "staging-qualification-03", 13),
        ("cleanup", "staging-qualification-04", 14),
    ]
    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["report_type"] == "recovery"
    assert retained["release_id"] == "0123456789ab-staging"
    assert len(retained["replicas"]) == 5
    assert [item["generation"] for item in retained["replicas"]] == [10, 11, 12, 13, 14]
    assert all(item["unresolved_units"] == [] for item in retained["replicas"])
    assert retained["cleanup_complete"] is True
    assert "protected response body" not in report_path.read_text(encoding="utf-8")
    assert report_path.stat().st_mode & 0o777 == 0o600


def test_controller_recovery_reports_allowlisted_content_free_failure_reason(
    tmp_path: Path,
):
    from backend.loadtests.external_pi_fleet_core import FleetRecoveryReport
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    secret = "protected_response_body_token"

    class FailingOperator(_FleetOperator):
        def run_round(
            self,
            name,
            workers,
            *,
            expected_users,
            abort_requested=lambda: False,
        ):
            raise RuntimeError(secret)

    report_path = tmp_path / "fleet.json"
    with pytest.raises(RuntimeError, match=secret):
        run_fleet_controller(
            FailingOperator(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("2x32",),
            geteuid=lambda: 0,
        )

    retained_text = report_path.read_text(encoding="utf-8")
    retained = json.loads(retained_text)
    assert retained["failure_stage"] == "locust_round"
    assert retained["failure_code"] == "locust_round_failed"
    assert secret not in retained_text

    validation_payload = {
        key: value for key, value in retained.items() if key != "cleanup_complete"
    }
    for field in ("failure_stage", "failure_code"):
        invalid = dict(validation_payload)
        invalid[field] = "protected_response_body_token"
        with pytest.raises(ValidationError):
            FleetRecoveryReport.model_validate_json(json.dumps(invalid))

    mismatched = dict(validation_payload)
    mismatched["failure_code"] = "cleanup_failed"
    with pytest.raises(ValidationError):
        FleetRecoveryReport.model_validate_json(json.dumps(mismatched))


def test_controller_preserves_round_failure_when_sampler_fails_later(tmp_path: Path):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class OrderedFailureOperator(_FleetOperator):
        guard_started = threading.Event()
        round_failed = threading.Event()

        def prepare_round(self):
            self.guard_started.set()
            return super().prepare_round()

        def sample_resources(self, shape):
            if (
                self.guard_started.is_set()
                and threading.current_thread() is not threading.main_thread()
            ):
                assert self.round_failed.wait(timeout=1)
                raise RuntimeError("later sampler detail")
            return super().sample_resources(shape)

        def run_round(self, name, workers, *, expected_users, abort_requested):
            self.round_failed.set()
            raise RuntimeError("first round detail")

    report_path = tmp_path / "fleet.json"
    with pytest.raises(RuntimeError, match="first round detail"):
        run_fleet_controller(
            OrderedFailureOperator(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("2x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["failure_stage"] == "locust_round"
    assert retained["failure_code"] == "locust_round_failed"


def test_controller_publishes_conservative_recovery_when_inspection_fails(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class InspectionFailureOperator(_FleetOperator):
        def run_round(self, name, workers, *, expected_users, abort_requested):
            raise RuntimeError("first round detail")

        def recovery_postconditions(self, resolved, owned_units):
            raise RuntimeError("later cleanup inspection detail")

    report_path = tmp_path / "fleet.json"
    report_path.write_text('{"previous":true}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="first round detail"):
        run_fleet_controller(
            InspectionFailureOperator(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("2x32",),
            geteuid=lambda: 0,
        )

    retained_text = report_path.read_text(encoding="utf-8")
    retained = json.loads(retained_text)
    assert retained["report_type"] == "recovery"
    assert retained["failure_stage"] == "locust_round"
    assert retained["failure_code"] == "locust_round_failed"
    assert retained["cleanup_complete"] is False
    assert len(retained["replicas"]) == 16
    assert all(not item["cleanup"]["units_removed"] for item in retained["replicas"])
    assert all(len(item["unresolved_units"]) == 2 for item in retained["replicas"])
    assert all(
        item["unresolved_units"] == item["owned_units"]
        for item in retained["replicas"][:2]
    )
    assert all(not item["owned_units"] for item in retained["replicas"][2:])
    assert "first round detail" not in retained_text
    assert "later cleanup inspection detail" not in retained_text


@pytest.mark.parametrize(
    ("failure", "expected_stage", "expected_code"),
    (
        ("revalidation", "revalidation", "revalidation_failed"),
        ("resource_sampling", "resource_sampling", "resource_sampling_failed"),
        ("resource_threshold", "resource_threshold", "resource_threshold_crossed"),
        ("replica_lifecycle", "replica_lifecycle", "replica_lifecycle_failed"),
        ("cleanup", "cleanup", "cleanup_failed"),
    ),
)
def test_controller_recovery_distinguishes_failure_stage_without_error_text(
    tmp_path: Path,
    failure: str,
    expected_stage: str,
    expected_code: str,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    secret = "protected_failure_detail"

    class FailingOperator(_FleetOperator):
        def revalidate(self, shape, active):
            if failure == "revalidation":
                raise RuntimeError(secret)
            return super().revalidate(shape, active)

        def sample_resources(self, shape):
            if failure == "resource_sampling":
                raise RuntimeError(secret)
            evidence = super().sample_resources(shape)
            if failure == "resource_threshold":
                return evidence.model_copy(update={"peak_cpu_percent": 80.0})
            return evidence

        def start(self, resolved):
            if failure == "replica_lifecycle":
                raise RuntimeError(secret)
            return super().start(resolved)

        def cleanup(self, resolved, generation):
            if failure == "cleanup":
                raise RuntimeError(secret)
            return super().cleanup(resolved, generation)

    report_path = tmp_path / "fleet.json"
    with pytest.raises(RuntimeError):
        run_fleet_controller(
            FailingOperator(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("2x32",),
            geteuid=lambda: 0,
        )

    retained_text = report_path.read_text(encoding="utf-8")
    retained = json.loads(retained_text)
    assert retained["failure_stage"] == expected_stage
    assert retained["failure_code"] == expected_code
    assert secret not in retained_text


def test_initial_eighty_percent_cpu_checkpoint_retains_clean_threshold_recovery(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class ThresholdOperator(_FleetOperator):
        def sample_resources(self, shape):
            return (
                super()
                .sample_resources(shape)
                .model_copy(update={"peak_cpu_percent": 80.0})
            )

    report_path = tmp_path / "fleet.json"
    with pytest.raises(FleetRunRefused, match="resource guard crossed"):
        run_fleet_controller(
            ThresholdOperator(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("2x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["failure_stage"] == "resource_threshold"
    assert retained["failure_code"] == "resource_threshold_crossed"
    assert retained["replicas"] == []
    assert retained["cleanup_complete"] is True


@pytest.mark.parametrize(
    ("failure", "expected_stage", "expected_code"),
    (
        ("worker_status", "worker_status", "worker_status_failed"),
        ("locust_round", "locust_round", "locust_round_failed"),
        ("counter", "counter", "counter_mismatch"),
    ),
)
def test_system_round_classifies_only_allowlisted_failure_reason(
    tmp_path: Path,
    failure: str,
    expected_stage: str,
    expected_code: str,
):
    from backend.scripts.qualify_external_pi_fleet import (
        SystemFleetOperator,
        _FleetOperationFailure,
    )

    prompt = tmp_path / "prompt.txt"
    prompt.write_text("synthetic", encoding="utf-8")
    operator = object.__new__(SystemFleetOperator)
    operator._prompt_path = prompt
    operator.environ = {"PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN": "protected"}
    status = SimpleNamespace(operation_counters=SimpleNamespace(shadow_requests=0))
    if failure == "worker_status":
        operator._worker_status = lambda _worker: (_ for _ in ()).throw(
            RuntimeError("protected worker detail")
        )
    else:
        operator._worker_status = lambda _worker: status
    operator._validate_worker_status = lambda _worker, _status: None
    if failure == "locust_round":
        operator._round_runner = lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("protected Locust detail")
        )
    else:
        operator._round_runner = lambda **_kwargs: SimpleNamespace(
            observations=(), protocol_errors=0, transport_errors=0
        )
    worker = WorkerEvidence(
        worker_id="staging-qualification-00",
        port=8780,
        generation=1,
        maximum_sessions=32,
    )

    with pytest.raises(_FleetOperationFailure) as raised:
        operator.run_round(
            "healthy",
            (worker,),
            expected_users=1,
            abort_requested=lambda: False,
        )

    assert raised.value.stage == expected_stage
    assert raised.value.code == expected_code


@pytest.mark.parametrize(
    ("shape_names", "failure_round", "expected_workers"),
    (
        (("5x32", "8x16"), 2, 8),
        (("5x32", "8x16", "16x8"), 3, 16),
    ),
)
def test_later_shape_failure_publishes_only_unique_current_shape_recovery(
    tmp_path: Path,
    shape_names,
    failure_round,
    expected_workers,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class SecondShapeFailure(_FleetOperator):
        healthy_rounds = 0

        def run_round(
            self,
            name,
            workers,
            *,
            expected_users,
            abort_requested=lambda: False,
        ):
            if name == "healthy":
                self.healthy_rounds += 1
                if self.healthy_rounds == failure_round:
                    raise RuntimeError("later shape failed")
            return super().run_round(
                name,
                workers,
                expected_users=expected_users,
                abort_requested=abort_requested,
            )

    report_path = tmp_path / "fleet.json"
    with pytest.raises(RuntimeError, match="later shape failed"):
        run_fleet_controller(
            SecondShapeFailure(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=shape_names,
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["report_type"] == "recovery"
    assert [item["worker_id"] for item in retained["replicas"]] == list(
        QUALIFICATION_WORKER_IDS[:expected_workers]
    )
    assert len({item["worker_id"] for item in retained["replicas"]}) == expected_workers


def test_first_checkpoint_foreign_unit_and_port_are_retained_as_recovery(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class ForeignPreflight(_FleetOperator):
        def revalidate(self, _shape, _active):
            raise FleetRunRefused("foreign reserved slot")

        def recovery_postconditions(self, resolved, _owned_units):
            if resolved.index == 6:
                return _cleanup(units_removed=False, processes_gone=False), (
                    resolved.supervisor_unit,
                )
            if resolved.index == 7:
                return _cleanup(ports_free=False, processes_gone=False), ()
            return _cleanup(), ()

    report_path = tmp_path / "fleet.json"
    with pytest.raises(FleetRunRefused, match="foreign reserved slot"):
        run_fleet_controller(
            ForeignPreflight(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["cleanup_complete"] is False
    assert [item["worker_id"] for item in retained["replicas"]] == [
        "staging-qualification-06",
        "staging-qualification-07",
    ]
    assert retained["replicas"][0]["unresolved_units"] == [
        QUALIFICATION_SUPERVISOR_UNITS[6]
    ]
    assert retained["replicas"][1]["cleanup"]["ports_free"] is False


@pytest.mark.parametrize("pointer_failure", ("current missing", "current changed"))
def test_partial_attempt_recovery_uses_cached_descriptors_after_pointer_drift(
    tmp_path: Path,
    pointer_failure: str,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class PointerDrift(_FleetOperator):
        pointer_valid = True

        def resolve(self, shape, index):
            if not self.pointer_valid:
                raise FleetRunRefused(pointer_failure)
            return super().resolve(shape, index)

        def start(self, resolved):
            self.pointer_valid = False
            raise RuntimeError("protected partial-start detail")

        def owned_units(self, resolved):
            return (resolved.worker_unit,) if resolved.index == 0 else ()

    report_path = tmp_path / "fleet.json"
    report_path.write_text('{"previous":true}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="protected partial-start detail"):
        run_fleet_controller(
            PointerDrift(),
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    retained_text = report_path.read_text(encoding="utf-8")
    retained = json.loads(retained_text)
    assert retained["report_type"] == "recovery"
    assert retained["cleanup_complete"] is True
    assert len(retained["replicas"]) == 1
    assert retained["replicas"][0]["worker_id"] == "staging-qualification-00"
    assert retained["replicas"][0]["port"] == 8780
    assert retained["replicas"][0]["supervisor_unit"] == (
        "paperswithcode-staging-external-pi-qualification@00.service"
    )
    assert retained["replicas"][0]["worker_unit"] == (
        "paperswithcode-staging-external-pi-qualification-worker@00.service"
    )
    assert pointer_failure not in retained_text
    assert "protected partial-start detail" not in retained_text
    assert report_path.stat().st_mode & 0o777 == 0o600


def test_controller_retains_exact_unresolved_worker_only_partial_start(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class PartialStartFailure(_FleetOperator):
        def start(self, resolved):
            raise RuntimeError("partial start")

        def owned_units(self, resolved):
            return (resolved.worker_unit,) if resolved.index == 0 else ()

        def cleanup(self, _resolved, _generation):
            raise RuntimeError("cleanup unavailable")

    operator = PartialStartFailure()
    report_path = tmp_path / "fleet.json"
    with pytest.raises(RuntimeError, match="partial start"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=report_path,
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["cleanup_complete"] is False
    assert len(retained["replicas"]) == 1
    replica = retained["replicas"][0]
    assert replica["generation"] is None
    assert replica["owned_units"] == [
        "paperswithcode-staging-external-pi-qualification-worker@00.service"
    ]
    assert replica["unresolved_units"] == replica["owned_units"]


def test_controller_cleans_started_replica_when_readiness_has_no_generation(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class ReadinessFailure(_FleetOperator):
        def wait_ready(self, resolved):
            if resolved.index == 1:
                raise RuntimeError("readiness failed")
            return super().wait_ready(resolved)

    operator = ReadinessFailure()
    with pytest.raises(RuntimeError, match="readiness failed"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=tmp_path / "fleet.json",
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    assert [event for event in operator.events if event[0] == "cleanup"] == [
        ("cleanup", "staging-qualification-00", 10),
        ("cleanup", "staging-qualification-01", None),
    ]


def test_controller_cleanup_continues_when_pre_cleanup_revalidation_fails(
    tmp_path: Path,
):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    class SafetyFailure(_FleetOperator):
        unsafe = False

        def revalidate(self, shape, active):
            if self.unsafe:
                raise FleetRunRefused("safety changed")
            super().revalidate(shape, active)

        def run_round(
            self,
            name,
            workers,
            *,
            expected_users,
            abort_requested=lambda: False,
        ):
            self.unsafe = True
            raise RuntimeError("round failed")

    operator = SafetyFailure()
    with pytest.raises(RuntimeError, match="round failed"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=tmp_path / "fleet.json",
            report_root=tmp_path,
            shape_names=("5x32",),
            geteuid=lambda: 0,
        )

    assert [event for event in operator.events if event[0] == "cleanup"] == [
        ("cleanup", "staging-qualification-00", 10),
        ("cleanup", "staging-qualification-01", 11),
        ("cleanup", "staging-qualification-02", 12),
        ("cleanup", "staging-qualification-03", 13),
        ("cleanup", "staging-qualification-04", 14),
    ]


def test_controller_refuses_non_root_before_operator_actions(tmp_path: Path):
    from backend.scripts.qualify_external_pi_fleet import run_fleet_controller

    operator = _FleetOperator()
    with pytest.raises(FleetRunRefused, match="root operator"):
        run_fleet_controller(
            operator,
            release_id="0123456789ab-staging",
            report_path=tmp_path / "fleet.json",
            report_root=tmp_path,
            geteuid=lambda: 1000,
        )
    assert operator.events == []


def test_controller_signal_context_converts_interrupt_and_restores_handlers():
    from backend.scripts.qualify_external_pi_fleet import (
        FleetQualificationInterrupted,
        qualification_signal_context,
    )

    previous = {
        number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)
    }
    with pytest.raises(FleetQualificationInterrupted), qualification_signal_context():
        signal.raise_signal(signal.SIGTERM)
    assert {
        number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)
    } == previous
