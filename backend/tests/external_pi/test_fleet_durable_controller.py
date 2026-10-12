"""Durable qualification controller ordering, restoration, and cleanup."""

from __future__ import annotations

import uuid

import pytest

from backend.tests.external_pi.fleet_harness import (
    _DurableOperator,
)


def test_durable_controller_runs_only_32_and_restores_everything():
    from backend.scripts.qualify_durable_external_turns import (
        run_durable_qualification,
    )

    operator = _DurableOperator()
    result = run_durable_qualification(operator)

    assert result.status == "completed"
    assert result.passed is True


def test_durable_controller_finalizes_billed_evidence_after_profile_teardown():
    from backend.scripts.qualify_durable_external_turns import (
        run_durable_qualification,
    )

    class TwoPhaseOperator(_DurableOperator):
        def finalize_profile(self, profile, measurement):
            self.events.append(("finalize", profile.name))
            return measurement

    operator = TwoPhaseOperator()
    result = run_durable_qualification(operator)

    assert result.passed is True
    for name in ("32-functional-turns",):
        assert operator.events.index(("teardown", name)) < operator.events.index(
            ("finalize", name)
        )
    assert [report.profile for report in result.profiles] == ["32-functional-turns"]
    assert [event for event in operator.events if event[0] == "run"] == [
        ("run", "32-functional-turns"),
    ]
    assert [event[1] for event in operator.events if event[0] == "resource"] == [
        "32-functional-turns",
    ]
    assert result.flags_restored is True
    assert result.exact_workers_drained is True
    assert operator.events[-2][0] == "restore_flags"
    assert operator.events[-1] == ("cleanup_transient_workers",)


def test_durable_controller_treats_resource_refusal_as_evidence_and_stops():
    from backend.scripts.qualify_durable_external_turns import (
        run_durable_qualification,
    )

    operator = _DurableOperator(refuse_profile="32-functional-turns")
    result = run_durable_qualification(operator)

    assert result.status == "resource_refused"
    assert result.reason == "memory_headroom"
    assert result.profiles == ()
    assert ("setup", "32-functional-turns") not in operator.events
    assert operator.events[-1] == ("cleanup_transient_workers",)


def test_durable_controller_uses_fixed_cpu_guard_and_typed_refusal():
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    operator = _DurableOperator(cpu_percent=90.0, cpu_guard_percent=100.0)
    result = run_durable_qualification(operator)

    assert result.status == "resource_refused"
    assert result.reason == "cpu_headroom"
    assert not any(event[0] == "setup" for event in operator.events)
    assert [event[0] for event in operator.events].count("resource") == 1
    assert operator.events[-1] == ("cleanup_transient_workers",)


@pytest.mark.parametrize(
    "updates",
    (
        {"name": "production"},
        {"target_release": "fedcba987654-staging"},
        {"production_release": "0123456789ab-staging"},
        {"production_release": "0123456789ab-production"},
        {"host_mem_total_bytes": 4 * 1024**3},
        {"public_external_admission_flags": (False, True, False)},
    ),
)
def test_durable_controller_refuses_unsafe_environment_but_still_restores(updates):
    from backend.scripts.qualify_durable_external_turns import (
        QualificationEnvironment,
        QualificationRefused,
        run_durable_qualification,
    )

    values = {
        "name": "staging",
        "target_release": "0123456789ab-staging",
        "staging_release": "0123456789ab-staging",
        "production_release": "fedcba987654-production",
        "host_mem_total_bytes": 16 * 1024**3,
        "public_external_admission_flags": (False, False, False),
    }
    values.update(updates)
    operator = _DurableOperator(environment=QualificationEnvironment(**values))

    with pytest.raises(QualificationRefused):
        run_durable_qualification(operator)

    assert not any(event[0] == "setup" for event in operator.events)
    assert not any(event[0] == "restore_flags" for event in operator.events)
    assert operator.events[-1] == ("cleanup_transient_workers",)


def test_durable_controller_restores_after_setup_failure():
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    operator = _DurableOperator(failure_stage="setup")
    result = run_durable_qualification(operator)

    assert result.status == "failed"
    assert result.reason == "durable_qualification_failed"
    assert "TOP_SECRET" not in result.model_dump_json()
    assert ("teardown", "32-functional-turns") in operator.events
    assert operator.events[-2][0] == "restore_flags"
    assert operator.events[-1] == ("cleanup_transient_workers",)


def test_post_validation_typed_prerequisite_failure_returns_bounded_report():
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        run_durable_qualification,
    )

    class RefusingOperator(_DurableOperator):
        def setup_profile(self, profile):
            self.events.append(("setup", profile.name))
            raise QualificationRefused("staging_prerequisite_missing")

    report = run_durable_qualification(RefusingOperator())

    assert report.status == "failed"
    assert report.reason == "staging_prerequisite_missing"
    assert "traceback" not in report.model_dump_json().lower()


def test_durable_controller_teardown_failure_retains_no_profile():
    from backend.scripts.qualify_durable_external_turns import (
        run_durable_qualification,
    )

    operator = _DurableOperator(failure_stage="teardown:32-functional-turns")

    result = run_durable_qualification(operator)

    assert result.status == "failed"
    assert result.reason == "cleanup_failed"
    assert result.profiles == ()
    assert result.cleanup_passed is True


def test_durable_controller_cannot_skip_or_reverse_the_binding_profile_order():
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        run_durable_qualification,
    )

    operator = _DurableOperator()
    for forbidden in (
        ("100-immediate-admission", "32-functional-turns"),
        ("32-functional-turns", "100-immediate-admission"),
    ):
        with pytest.raises(QualificationRefused, match="profile_order"):
            run_durable_qualification(operator, profiles=forbidden)
    assert not any(event[0] == "setup" for event in operator.events)
    assert operator.events[-1] == ("cleanup_transient_workers",)


def test_durable_controller_accepts_standalone_functional_profile_only():
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        run_durable_qualification,
    )

    operator = _DurableOperator()
    report = run_durable_qualification(
        operator,
        profiles=("32-functional-turns",),
    )

    assert report.status == "completed"
    assert [profile.profile for profile in report.profiles] == ["32-functional-turns"]
    assert [event for event in operator.events if event[0] == "run"] == [
        ("run", "32-functional-turns")
    ]

    for forbidden in ((), ("100-immediate-admission",)):
        with pytest.raises(QualificationRefused, match="profile_order"):
            run_durable_qualification(_DurableOperator(), profiles=forbidden)


def test_durable_controller_requires_snapshot_flags_off_before_setup():
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    operator = _DurableOperator(
        prior_flags={"external": True, "executor": False, "remote": False}
    )
    result = run_durable_qualification(operator)
    assert result.status == "failed"
    assert result.reason == "public_external_admission_flags_must_be_off"
    assert not any(event[0] == "setup" for event in operator.events)
    assert operator.events[-1] == ("cleanup_transient_workers",)


@pytest.mark.parametrize(
    "stage",
    (
        "snapshot_flags",
        "resource",
        "setup",
        "run",
        "teardown",
        "restore_flags",
        "cleanup_transient_workers",
        "interrupt:snapshot_flags",
        "interrupt:run",
    ),
)
def test_durable_controller_attempts_cleanup_at_every_failure_boundary(stage):
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    operator = _DurableOperator(failure_stage=stage)
    result = run_durable_qualification(operator)

    assert result.status == "failed"
    assert result.reason in {"durable_qualification_failed", "cleanup_failed"}
    assert operator.events[-1] == ("cleanup_transient_workers",)
    if stage in {"snapshot_flags", "interrupt:snapshot_flags"}:
        assert not any(event[0] == "restore_flags" for event in operator.events)


@pytest.mark.parametrize(
    ("stage", "expected_reason"),
    (
        ("setup", "durable_qualification_failed"),
        ("run", "durable_qualification_failed"),
        ("interrupt:run", "durable_qualification_failed"),
        ("teardown", "cleanup_failed"),
        ("finalize", "durable_qualification_failed"),
        ("cleanup_evidence", "cleanup_failed"),
    ),
)
def test_durable_controller_retains_scope_when_teardown_fails_for_cleanup_retry(
    stage, expected_reason
):
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    class ScopedOperator(_DurableOperator):
        def setup_profile(self, profile):
            self.events.append(("scope_created", profile.name))
            super().setup_profile(profile)

        def qualification_scope_id(self, profile):
            self.events.append(("scope_id", profile.name))
            return uuid.UUID("d0000000-0000-4000-8000-000000000001")

        def finalize_profile(self, profile, result):
            self.events.append(("finalize", profile.name))
            self._fail("finalize")
            return result

        def cleanup_profile_evidence(self, profile):
            self.events.append(("cleanup_evidence", profile.name))
            self._fail("cleanup_evidence")

    operator = ScopedOperator(failure_stage=stage)
    report = run_durable_qualification(operator)

    assert report.status == "failed"
    assert report.reason == expected_reason
    assert ("teardown", "32-functional-turns") in operator.events
    if stage in {"teardown", "cleanup_transient_workers"}:
        assert ("cleanup_evidence", "32-functional-turns") not in operator.events
    else:
        assert ("cleanup_evidence", "32-functional-turns") in operator.events
    assert operator.events.index(("cleanup_transient_workers",)) < (
        operator.events.index(("cleanup_evidence", "32-functional-turns"))
        if ("cleanup_evidence", "32-functional-turns") in operator.events
        else len(operator.events)
    )


def test_durable_controller_does_not_delete_scope_when_final_probe_finds_leak():
    from backend.scripts.qualify_durable_external_turns import (
        CleanupProof,
        run_durable_qualification,
    )

    class LeakingOperator(_DurableOperator):
        def cleanup_profile_evidence(self, profile):
            self.events.append(("cleanup_evidence", profile.name))

        def cleanup_transient_workers(self):
            self.events.append(("cleanup_transient_workers",))
            return CleanupProof(True, True, True, True, True, 0, 1, 0)

    operator = LeakingOperator()
    report = run_durable_qualification(operator)

    assert report.reason == "cleanup_failed"
    assert not any(event[0] == "cleanup_evidence" for event in operator.events)


def test_primary_profile_failure_plus_worker_cleanup_failure_is_typed_cleanup_failed():
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    class CombinedFailureOperator(_DurableOperator):
        def cleanup_transient_workers(self):
            self.events.append(("cleanup_transient_workers",))
            return None

    report = run_durable_qualification(CombinedFailureOperator(failure_stage="run"))

    assert report.status == "failed"
    assert report.reason == "cleanup_failed"
    assert report.cleanup_passed is False


def test_durable_controller_cleans_after_environment_probe_failure():
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        run_durable_qualification,
    )

    operator = _DurableOperator(failure_stage="environment")
    with pytest.raises(QualificationRefused) as exc:
        run_durable_qualification(operator)

    assert "TOP_SECRET" not in str(exc.value)
    assert operator.events[-1] == ("cleanup_transient_workers",)
    assert not any(event[0] == "restore_flags" for event in operator.events)


def test_durable_controller_copies_mutable_flag_snapshot_before_setup():
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    flags = {"external": False, "executor": False, "remote": False}
    operator = _DurableOperator(prior_flags=flags, mutate_snapshot=True)
    result = run_durable_qualification(operator)

    assert result.status == "completed"
    assert flags["external"] is True
    restore = next(event for event in operator.events if event[0] == "restore_flags")
    assert restore[1] == {"external": False, "executor": False, "remote": False}


def test_durable_controller_no_op_cleanup_adapter_cannot_complete():
    from backend.scripts.qualify_durable_external_turns import run_durable_qualification

    result = run_durable_qualification(_DurableOperator(no_op_proof=True))

    assert result.status == "failed"
    assert result.reason == "cleanup_failed"
    assert result.passed is False
