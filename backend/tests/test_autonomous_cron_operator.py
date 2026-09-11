from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from backend.services.autonomous_capabilities import (
    AuthorizationDecision,
    Capability,
    ResourceKind,
    ResourceRef,
)
from backend.services.autonomous_codex_runner import ProposedAction
from backend.services.autonomous_cron_operator import (
    AutonomousCronOperator,
    CronCandidateEditor,
    CronCandidateReviewer,
    CronCodexDiagnoser,
    CronRepairContract,
    CronSourceRepairPipeline,
    PwcCronRetrier,
    RepairResult,
    build_cron_repair_contracts,
)
from backend.services.autonomous_cron_probe import FindingState, HealthFinding
from backend.services.autonomous_operations_repository import (
    Operator,
    RunContext,
)
from backend.services.autonomous_release_service import ReleaseVerificationError
from backend.services.autonomous_source_repair import RepairCandidate
from backend.services.autonomous_source_repair import (
    CheckOutcome,
    ReviewBundle,
)
from backend.services.cron_registry import list_cron_jobs
from deploy.cron_launcher import COMMANDS
from deploy.autonomous_cron_retry_bridge import SAFE_JOBS as BROKER_SAFE_JOBS


NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)


def context() -> RunContext:
    return RunContext(uuid.uuid4(), Operator.CRON_HEALTH, False, "cron-operator-v1")


def finding(
    job: str = "update_github_stars",
    *,
    state: FindingState = FindingState.DEGRADED,
    contract: str = "exit_state",
) -> HealthFinding:
    return HealthFinding(
        job,
        "process_logs",
        contract,
        state,
        "bounded failure",
        {"exit": "failure"},
        NOW.isoformat(),
        "/autonomous-operations?operator=cron",
        None,
    )


def action(capability: Capability, job: str = "update_github_stars"):
    kind = (
        ResourceKind.DECLARED_CRON
        if capability is Capability.RETRY_DECLARED_CRON
        else ResourceKind.SOURCE_REPAIR
    )
    return ProposedAction(capability, ResourceRef(kind, job, True), "failed_run")


@dataclass
class FakeRepository:
    mutation_checks: int = 0
    actions: list[dict] | None = None

    def __post_init__(self):
        self.actions = []

    def assert_mutation_allowed(self, _db, _context):
        self.mutation_checks += 1

    def append_action(self, _db, **values):
        self.actions.append(values)


class FakeDB:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class FakePolicy:
    def __init__(self, allowed=True, reason="authorized"):
        self.allowed = allowed
        self.reason = reason
        self.requests = []

    def authorize(self, _db, run_context, capability, resource):
        self.requests.append((run_context, capability, resource))
        return AuthorizationDecision(self.allowed, self.reason)


def operator(*, diagnoses=(), policy=None, retry=None, probe=None, repair=None):
    repository = FakeRepository()
    alerts = []
    diagnosis_calls = []

    def diagnose(run_context, findings):
        diagnosis_calls.append((run_context, findings))
        return tuple(diagnoses)

    service = AutonomousCronOperator(
        db=FakeDB(),
        repository=repository,
        policy=policy or FakePolicy(),
        diagnose=diagnose,
        retry=retry or (lambda _job: 0),
        probe=probe or (lambda _job: (finding(state=FindingState.HEALTHY),)),
        source_repair=repair
        or (
            lambda _context, _job, _contract, _findings: RepairResult.verified("a" * 40)
        ),
        alert=alerts.append,
        now=lambda: NOW,
    )
    return service, repository, alerts, diagnosis_calls


def test_every_declared_job_has_bounded_source_and_runtime_contract():
    contracts = build_cron_repair_contracts()
    assert set(contracts) == {definition.id for definition in list_cron_jobs()}
    for job_name, contract in contracts.items():
        assert contract.source_paths
        assert all(Path(path).is_file() for path in contract.source_paths)
        assert all(
            path.startswith(
                (".github/workflows/scripts/", "backend/", "url_extraction_agent/")
            )
            for path in contract.source_paths
        )
        assert contract.test_paths
        if contract.retry_command is not None:
            assert job_name in COMMANDS
            assert contract.retry_command == ("pwc-cron", job_name)
            assert len(contract.test_paths) >= 4
    assert (
        "backend/services/organization_sync_service.py"
        in contracts["sync_hf_organizations"].source_paths
    )
    assert contracts["monitor_chat_operational_alerts"].source_repair_allowed is False
    assert all(not contract.shared_source_paths for contract in contracts.values())
    assert {
        name
        for name, contract in contracts.items()
        if contract.retry_command is not None
    } == BROKER_SAFE_JOBS


def test_healthy_findings_are_a_true_noop_without_model_use():
    service, repository, alerts, diagnosis_calls = operator()
    outcome = service.handle_cron_findings(
        context(), (finding(state=FindingState.HEALTHY),)
    )
    assert outcome.status == "noop"
    assert not diagnosis_calls
    assert repository.mutation_checks == 0
    assert alerts == []


def test_safe_retry_is_authorized_reprobed_and_audited():
    retries = []
    service, repository, _, diagnosis_calls = operator(
        diagnoses=(action(Capability.RETRY_DECLARED_CRON),),
        retry=lambda job: retries.append(job) or 0,
    )
    outcome = service.handle_cron_findings(context(), (finding(),))
    assert outcome.status == "runtime_recovered"
    assert retries == ["update_github_stars"]
    assert len(diagnosis_calls) == 1
    assert repository.mutation_checks == 1
    assert repository.actions[-1]["reason_code"] == "runtime_recovered"
    assert repository.actions[0]["reason_code"] == "retry_authorized"
    assert outcome.before_digest != outcome.after_digest


def test_retrier_routes_exact_run_and_job_through_privileged_broker(monkeypatch):
    run_id = uuid.uuid4()
    executed = {}

    def run(argv, **kwargs):
        executed.update({"argv": argv, **kwargs})
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr("backend.services.autonomous_cron_operator.subprocess.run", run)

    assert PwcCronRetrier(run_id)("calculate_trending_scores") == 0
    assert executed["argv"] == [
        "/usr/local/sbin/pwc-autonomous-cron-retry",
        str(run_id),
        "calculate_trending_scores",
    ]
    assert executed["env"] == {"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"}


def test_ambiguous_lock_alerts_and_never_mutates():
    service, repository, alerts, diagnosis_calls = operator(
        diagnoses=(action(Capability.RETRY_DECLARED_CRON),)
    )
    outcome = service.handle_cron_findings(
        context(), (finding(contract="lock_ownership_age"),)
    )
    assert outcome.status == "blocked"
    assert outcome.reason_code == "ambiguous_lock"
    assert len(diagnosis_calls) == 1
    assert repository.mutation_checks == 0
    assert alerts[0]["reason_code"] == "ambiguous_lock"


def test_manual_mode_still_diagnoses_and_alerts_but_blocks_retry():
    policy = FakePolicy(False, "manual_mode")
    service, repository, alerts, diagnosis_calls = operator(
        diagnoses=(action(Capability.RETRY_DECLARED_CRON),), policy=policy
    )
    outcome = service.handle_cron_findings(context(), (finding(),))
    assert outcome.status == "blocked"
    assert outcome.reason_code == "manual_mode"
    assert len(diagnosis_calls) == 1
    assert repository.mutation_checks == 0
    assert alerts[0]["reason_code"] == "manual_mode"


def test_source_repair_uses_declared_contract_and_records_verified_sha():
    calls = []

    def repair(run_context, job_name, contract, findings):
        calls.append((run_context, job_name, contract, findings))
        return RepairResult.verified("b" * 40)

    service, repository, _, _ = operator(
        diagnoses=(
            action(
                Capability.REPAIR_DECLARED_CRON_SOURCE,
                "calculate_trending_scores",
            ),
        ),
        repair=repair,
    )
    outcome = service.handle_cron_findings(
        context(), (finding("calculate_trending_scores"),)
    )
    assert outcome.status == "source_repaired"
    assert outcome.published_sha == "b" * 40
    assert calls[0][1] == "calculate_trending_scores"
    assert calls[0][2].source_paths == (
        ".github/workflows/scripts/hourly/calculate_trending_scores.py",
    )
    assert repository.actions[-1]["reason_code"] == "source_repaired"


def test_failed_production_verification_reports_completed_rollback():
    service, _, alerts, _ = operator(
        diagnoses=(
            action(
                Capability.REPAIR_DECLARED_CRON_SOURCE,
                "calculate_trending_scores",
            ),
        ),
        repair=lambda *_args: RepairResult(
            "rolled_back", "c" * 40, None, True, "production_verification_failed"
        ),
    )
    outcome = service.handle_cron_findings(
        context(), (finding("calculate_trending_scores"),)
    )
    assert outcome.status == "rolled_back"
    assert outcome.rollback_performed is True
    assert alerts[0]["reason_code"] == "production_verification_failed"


def test_model_cannot_select_another_job_or_unsafe_retry():
    service, repository, alerts, _ = operator(
        diagnoses=(action(Capability.RETRY_DECLARED_CRON, "sync_3d_arena"),)
    )
    outcome = service.handle_cron_findings(context(), (finding(),))
    assert outcome.status == "blocked"
    assert outcome.reason_code == "diagnosis_scope_mismatch"
    assert repository.mutation_checks == 0
    assert alerts


def test_scheduler_plane_failure_is_diagnosed_but_not_retried_ad_hoc():
    service, repository, alerts, diagnosis_calls = operator(
        diagnoses=(action(Capability.RETRY_DECLARED_CRON),)
    )
    outcome = service.handle_cron_findings(
        context(), (finding(contract="scheduler_execution"),)
    )
    assert outcome.status == "blocked"
    assert outcome.reason_code == "recovery_action_not_allowlisted"
    assert diagnosis_calls
    assert repository.mutation_checks == 0
    assert alerts


def test_editorial_writer_source_repair_remains_disabled():
    service, repository, alerts, _ = operator(
        diagnoses=(action(Capability.REPAIR_DECLARED_CRON_SOURCE),)
    )
    outcome = service.handle_cron_findings(context(), (finding(),))
    assert outcome.status == "blocked"
    assert outcome.reason_code == "source_repair_not_safely_scoped"
    assert repository.mutation_checks == 0
    assert alerts


def test_manual_mode_standardizes_source_repair_as_monitoring_only_gate():
    policy = FakePolicy(False, "manual_mode")
    service, repository, alerts, _ = operator(
        diagnoses=(
            action(
                Capability.REPAIR_DECLARED_CRON_SOURCE,
                "calculate_trending_scores",
            ),
        ),
        policy=policy,
    )
    outcome = service.handle_cron_findings(
        context(), (finding("calculate_trending_scores"),)
    )
    assert outcome.status == "blocked"
    assert outcome.reason_code == "manual_mode"
    assert repository.mutation_checks == 0
    assert alerts


def test_luna_diagnosis_receives_only_bounded_typed_finding_evidence():
    captured = []

    class Result:
        status = "completed"
        proposed_actions = (action(Capability.RETRY_DECLARED_CRON),)

    diagnose = CronCodexDiagnoser(
        db=object(), runner=lambda request, *, db: captured.append(request) or Result()
    )
    actions = diagnose(context(), (finding(),))
    assert actions == Result.proposed_actions
    request = captured[0]
    assert request.model_alias == "diagnosis"
    assert request.budget_usd == Decimal("2")
    assert request.evidence_payload == {"findings": [finding().as_dict()]}
    assert set(request.capabilities) == {
        Capability.RETRY_DECLARED_CRON,
        Capability.REPAIR_DECLARED_CRON_SOURCE,
    }


def test_candidate_editor_exposes_only_declared_source_and_test_files(tmp_path):
    source = "backend/scripts/job.py"
    test = "backend/tests/test_job.py"
    for relative in (source, test):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# file\n")
    candidate = RepairCandidate(
        uuid.uuid4(), context(), object(), uuid.uuid4(), "a" * 40, tmp_path
    )
    contract = CronRepairContract(
        "update_github_stars", (source,), (), (test,), ("pwc-cron", "job")
    )
    captured = []

    class Result:
        status = "completed"
        proposed_actions = (action(Capability.REPAIR_DECLARED_CRON_SOURCE),)

    CronCandidateEditor(
        db=object(), runner=lambda request, *, db: captured.append(request) or Result()
    )(candidate.context, candidate, contract, (finding(),))
    request = captured[0]
    assert request.workspace_path == tmp_path
    assert request.writable_paths == (source, test)
    assert request.context.run_id != candidate.context.run_id


def test_candidate_review_is_a_separate_read_only_luna_run():
    captured = []
    bundle = ReviewBundle(
        uuid.uuid4(),
        "a" * 40,
        ("backend/scripts/job.py",),
        "b" * 64,
        "diff --git a/backend/scripts/job.py b/backend/scripts/job.py\n",
        (CheckOutcome(("lint", "backend/scripts/job.py"), "c" * 64),),
    )

    class Result:
        status = "completed"
        proposed_actions = (
            ProposedAction(
                Capability.REPAIR_DECLARED_CRON_SOURCE,
                ResourceRef(ResourceKind.SOURCE_REPAIR, "update_github_stars", True),
                "approve",
            ),
        )
        result_digest = "d" * 64

    decision = CronCandidateReviewer(
        db=object(),
        context=context(),
        job_name="update_github_stars",
        runner=lambda request, *, db: captured.append(request) or Result(),
    )("diagnosis", bundle)
    assert decision.approved is True
    assert decision.evidence_digest == "d" * 64
    assert captured[0].workspace_path is None
    assert captured[0].evidence_payload["repair_review"]["patch_digest"] == "b" * 64


def test_source_pipeline_rolls_back_when_job_recovery_verification_fails(tmp_path):
    candidate = RepairCandidate(
        uuid.uuid4(), context(), object(), uuid.uuid4(), "a" * 40, tmp_path
    )

    class Source:
        cleaned = False

        def prepare_candidate(self, *_args):
            return candidate

        def review_candidate(self, *_args, **_kwargs):
            return object()

        def publish_candidate(self, *_args):
            return "b" * 40

        def cleanup_candidate(self, *_args):
            self.cleaned = True

    class Release:
        deployed = []
        rolled_back = []

        def deploy_exact_sha(self, _db, _context, environment, sha):
            self.deployed.append((environment, sha))

        def rollback(self, _db, _context, environment, sha):
            self.rolled_back.append((environment, sha))

    source_service = Source()
    release = Release()
    pipeline = CronSourceRepairPipeline(
        db=object(),
        source_service=source_service,
        release_service=release,
        policy=FakePolicy(),
        editor=lambda *_args: None,
        reviewer=lambda *_args: None,
        recovery_verifier=lambda _job: False,
    )
    result = pipeline(
        candidate.context,
        "calculate_trending_scores",
        build_cron_repair_contracts()["calculate_trending_scores"],
        (finding(),),
    )
    assert result.status == "rolled_back"
    assert release.rolled_back == [("production", "b" * 40)]
    assert source_service.cleaned is True


def test_source_pipeline_cleans_candidate_after_failed_deploy(tmp_path):
    candidate = RepairCandidate(
        uuid.uuid4(), context(), object(), uuid.uuid4(), "a" * 40, tmp_path
    )

    class Source:
        cleaned = False

        def prepare_candidate(self, *_args):
            return candidate

        def review_candidate(self, *_args, **_kwargs):
            return object()

        def publish_candidate(self, *_args):
            return "b" * 40

        def cleanup_candidate(self, *_args):
            self.cleaned = True

    class Release:
        def deploy_exact_sha(self, *_args):
            raise ReleaseVerificationError("failed")

    source_service = Source()
    result = CronSourceRepairPipeline(
        db=object(),
        source_service=source_service,
        release_service=Release(),
        policy=FakePolicy(),
        editor=lambda *_args: None,
        reviewer=lambda *_args: None,
        recovery_verifier=lambda _job: True,
    )(
        candidate.context,
        "calculate_trending_scores",
        build_cron_repair_contracts()["calculate_trending_scores"],
        (finding(),),
    )
    assert result.status == "failed"
    assert result.reason_code == "production_deploy_failed"
    assert source_service.cleaned is True
