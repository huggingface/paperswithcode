import uuid
import pytest

from backend.services.autonomous_capabilities import (
    CAPABILITY_MANIFESTS,
    Capability,
    ResourceKind,
    ResourceRef,
)
from backend.services.autonomous_operations_repository import (
    DryRunMutation,
    ManualModeEnabled,
    Operator,
    OperatorDisabled,
    RunContext,
)
from backend.services.autonomous_policy import AutonomousPolicy


class FakeRepository:
    def __init__(self):
        self.blocked_by: Exception | None = None
        self.run_valid = True
        self.lease_owned = True
        self.attempt_owned = True

    def assert_mutation_allowed(self, _db, _context):
        if self.blocked_by is not None:
            raise self.blocked_by

    def assert_run_context(self, _db, _context):
        if not self.run_valid:
            raise ValueError("mismatched run")

    def owns_repair_lease(self, _db, *, context):
        return self.lease_owned

    def owns_chat_repair_attempt(self, _db, *, context, signature, attempt_id):
        assert len(signature) == 64
        return self.attempt_owned


def context(operator: Operator, *, dry_run: bool = False) -> RunContext:
    return RunContext(uuid.uuid4(), operator, dry_run, "manifest-v1")


@pytest.mark.parametrize(
    ("operator", "capability"),
    [
        (operator, capability)
        for operator, capabilities in CAPABILITY_MANIFESTS.items()
        for capability in capabilities
    ],
)
def test_manifest_allows_only_declared_operator_capabilities(operator, capability):
    policy = AutonomousPolicy(FakeRepository())
    resource_kind = {
        Capability.REVIEW_SUBMISSION: ResourceKind.PENDING_EDIT,
        Capability.APPLY_EXISTING_TAXONOMY_EDIT: ResourceKind.PAPER,
        Capability.APPLY_EXISTING_LEADERBOARD_EVAL: ResourceKind.PAPER,
        Capability.APPLY_PAPER_METADATA_EDIT: ResourceKind.PAPER,
        Capability.CREATE_EXTERNAL_PAPER: ResourceKind.EXTERNAL_PAPER,
        Capability.RETRY_DECLARED_CRON: ResourceKind.DECLARED_CRON,
        Capability.REPAIR_DECLARED_CRON_SOURCE: ResourceKind.SOURCE_REPAIR,
        Capability.SWITCH_CHAT_PROVIDER: ResourceKind.CHAT_PROVIDER,
        Capability.REPAIR_CHAT_SOURCE: ResourceKind.SOURCE_REPAIR,
        Capability.RESOLVE_MODEL_PAPER: ResourceKind.TRENDING_MODEL_CANDIDATE,
        Capability.CREATE_BENCHMARK_FROM_GAP: ResourceKind.BENCHMARK_CANDIDATE,
    }[capability]
    decision = policy.authorize(
        object(),
        context(operator),
        capability,
        ResourceRef(resource_kind, "42", True),
        incident_signature="a" * 64,
        incident_attempt_id=uuid.uuid4(),
    )
    assert decision.allowed, decision.reason_code


@pytest.mark.parametrize("operator", list(Operator))
def test_manifest_denies_every_undeclared_capability(operator):
    policy = AutonomousPolicy(FakeRepository())
    for capability in Capability:
        if capability in CAPABILITY_MANIFESTS[operator]:
            continue
        decision = policy.authorize(
            object(),
            context(operator),
            capability,
            ResourceRef(ResourceKind.PAPER, "42", True),
        )
        assert not decision.allowed
        assert decision.reason_code == "capability_not_in_manifest"


@pytest.mark.parametrize(
    ("blocked_by", "reason"),
    [
        (ManualModeEnabled("manual"), "manual_mode"),
        (OperatorDisabled("off"), "operator_disabled"),
        (DryRunMutation("dry"), "dry_run"),
    ],
)
def test_runtime_controls_fail_closed(blocked_by, reason):
    repository = FakeRepository()
    repository.blocked_by = blocked_by
    decision = AutonomousPolicy(repository).authorize(
        object(),
        context(Operator.SUBMISSIONS),
        Capability.REVIEW_SUBMISSION,
        ResourceRef(ResourceKind.PENDING_EDIT, "7", True),
    )
    assert not decision.allowed
    assert decision.reason_code == reason


def test_curation_capabilities_are_isolated_from_submission_review():
    curation = CAPABILITY_MANIFESTS[Operator.CURATION]
    submissions = CAPABILITY_MANIFESTS[Operator.SUBMISSIONS]

    assert Capability.RESOLVE_MODEL_PAPER in curation
    assert Capability.REVIEW_SUBMISSION not in curation
    assert Capability.RESOLVE_MODEL_PAPER not in submissions
    # Benchmark creation from gaps is the curation operator's narrow exception;
    # submission review keeps every taxonomy creation human-only.
    assert Capability.CREATE_BENCHMARK_FROM_GAP in curation
    assert Capability.CREATE_BENCHMARK_FROM_GAP not in submissions


def test_unknown_and_mismatched_run_fail_closed():
    repository = FakeRepository()
    policy = AutonomousPolicy(repository)
    run = context(Operator.SUBMISSIONS)
    assert not policy.authorize(
        object(), run, "create_task", ResourceRef(ResourceKind.TASK, "1", True)
    ).allowed
    invalid_context = RunContext(uuid.uuid4(), "submissions", False, "manifest-v1")
    assert (
        policy.authorize(
            object(),
            invalid_context,
            Capability.REVIEW_SUBMISSION,
            ResourceRef(ResourceKind.PENDING_EDIT, "7", True),
        ).reason_code
        == "invalid_run_context"
    )
    repository.run_valid = False
    assert (
        policy.authorize(
            object(),
            run,
            Capability.REVIEW_SUBMISSION,
            ResourceRef(ResourceKind.PENDING_EDIT, "7", True),
        ).reason_code
        == "invalid_run_context"
    )


def test_admission_enforces_controls_without_requiring_a_terminal_run():
    repository = FakeRepository()
    repository.run_valid = False
    policy = AutonomousPolicy(repository)
    decision = policy.authorize_admission(
        object(),
        context(Operator.CURATION),
        Capability.APPLY_EXISTING_TAXONOMY_EDIT,
        ResourceRef(ResourceKind.PAPER, "42", True),
    )
    assert decision.allowed

    repository.blocked_by = OperatorDisabled("off")
    decision = policy.authorize_admission(
        object(),
        context(Operator.CURATION),
        Capability.APPLY_EXISTING_TAXONOMY_EDIT,
        ResourceRef(ResourceKind.PAPER, "42", True),
    )
    assert decision.reason_code == "operator_disabled"


def test_manifests_are_closed_and_complete():
    assert set(CAPABILITY_MANIFESTS) == set(Operator)
    assert set().union(*CAPABILITY_MANIFESTS.values()) == set(Capability)
    with pytest.raises(TypeError):
        CAPABILITY_MANIFESTS[Operator.SUBMISSIONS] = frozenset()


@pytest.mark.parametrize(
    "kind",
    [
        ResourceKind.TASK,
        ResourceKind.METHOD,
        ResourceKind.BENCHMARK,
        ResourceKind.METRIC,
    ],
)
def test_taxonomy_references_must_already_exist(kind):
    decision = AutonomousPolicy(FakeRepository()).authorize(
        object(),
        context(Operator.SUBMISSIONS),
        Capability.APPLY_EXISTING_TAXONOMY_EDIT,
        ResourceRef(kind, "123", False),
    )
    assert not decision.allowed
    assert decision.reason_code == "resource_not_found"


def test_repairs_require_owned_lease_and_chat_attempt_budget():
    repository = FakeRepository()
    policy = AutonomousPolicy(repository)
    cron = context(Operator.CRON_HEALTH)
    resource = ResourceRef(ResourceKind.SOURCE_REPAIR, "refresh-papers", True)
    repository.lease_owned = False
    assert (
        policy.authorize(
            object(), cron, Capability.REPAIR_DECLARED_CRON_SOURCE, resource
        ).reason_code
        == "repair_lease_not_owned"
    )

    repository.lease_owned = True
    repository.attempt_owned = False
    chat = context(Operator.CHAT_RELIABILITY)
    assert (
        policy.authorize(
            object(),
            chat,
            Capability.REPAIR_CHAT_SOURCE,
            ResourceRef(ResourceKind.SOURCE_REPAIR, "chat", True),
            incident_signature="b" * 64,
            incident_attempt_id=uuid.uuid4(),
        ).reason_code
        == "incident_attempt_not_owned"
    )
