"""Closed capability vocabulary for autonomous catalog and operations work."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from backend.services.autonomous_operations_repository import Operator


class Capability(StrEnum):
    REVIEW_SUBMISSION = "review_submission"
    APPLY_EXISTING_TAXONOMY_EDIT = "apply_existing_taxonomy_edit"
    APPLY_EXISTING_LEADERBOARD_EVAL = "apply_existing_leaderboard_eval"
    APPLY_PAPER_METADATA_EDIT = "apply_paper_metadata_edit"
    CREATE_EXTERNAL_PAPER = "create_external_paper"
    RESOLVE_MODEL_PAPER = "resolve_model_paper"
    RETRY_DECLARED_CRON = "retry_declared_cron"
    REPAIR_DECLARED_CRON_SOURCE = "repair_declared_cron_source"
    SWITCH_CHAT_PROVIDER = "switch_chat_provider"
    REPAIR_CHAT_SOURCE = "repair_chat_source"


class ResourceKind(StrEnum):
    PENDING_EDIT = "pending_edit"
    TASK = "task"
    METHOD = "method"
    BENCHMARK = "benchmark"
    METRIC = "metric"
    PAPER = "paper"
    EVALUATION = "evaluation"
    EXTERNAL_PAPER = "external_paper"
    TRENDING_MODEL_CANDIDATE = "trending_model_candidate"
    DECLARED_CRON = "declared_cron"
    SOURCE_REPAIR = "source_repair"
    CHAT_PROVIDER = "chat_provider"


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}$")


@dataclass(frozen=True, slots=True)
class ResourceRef:
    kind: ResourceKind
    identifier: str
    exists: bool

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ResourceKind):
            raise ValueError("Unknown autonomous resource kind")
        if (
            not isinstance(self.identifier, str)
            or _IDENTIFIER.fullmatch(self.identifier) is None
        ):
            raise ValueError("Invalid autonomous resource identifier")
        if not isinstance(self.exists, bool):
            raise ValueError("Invalid autonomous resource existence state")


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    allowed: bool
    reason_code: str


class AutonomousCapabilityDenied(PermissionError):
    """A typed autonomous adapter rejected a proposed mutation."""


CAPABILITY_MANIFESTS: Mapping[Operator, frozenset[Capability]] = MappingProxyType(
    {
        Operator.SUBMISSIONS: frozenset(
            {
                Capability.REVIEW_SUBMISSION,
                Capability.APPLY_EXISTING_TAXONOMY_EDIT,
                Capability.APPLY_EXISTING_LEADERBOARD_EVAL,
                Capability.APPLY_PAPER_METADATA_EDIT,
                Capability.CREATE_EXTERNAL_PAPER,
            }
        ),
        Operator.CURATION: frozenset(
            {
                Capability.APPLY_EXISTING_TAXONOMY_EDIT,
                Capability.APPLY_EXISTING_LEADERBOARD_EVAL,
                Capability.APPLY_PAPER_METADATA_EDIT,
                Capability.RESOLVE_MODEL_PAPER,
            }
        ),
        Operator.CRON_HEALTH: frozenset(
            {
                Capability.RETRY_DECLARED_CRON,
                Capability.REPAIR_DECLARED_CRON_SOURCE,
            }
        ),
        Operator.CHAT_RELIABILITY: frozenset(
            {Capability.SWITCH_CHAT_PROVIDER, Capability.REPAIR_CHAT_SOURCE}
        ),
    }
)


CAPABILITY_RESOURCE_KINDS: Mapping[Capability, frozenset[ResourceKind]] = (
    MappingProxyType(
        {
            Capability.REVIEW_SUBMISSION: frozenset({ResourceKind.PENDING_EDIT}),
            Capability.APPLY_EXISTING_TAXONOMY_EDIT: frozenset(
                {
                    ResourceKind.PAPER,
                    ResourceKind.TASK,
                    ResourceKind.METHOD,
                    ResourceKind.BENCHMARK,
                    ResourceKind.METRIC,
                }
            ),
            Capability.APPLY_EXISTING_LEADERBOARD_EVAL: frozenset(
                {
                    ResourceKind.PAPER,
                    ResourceKind.EVALUATION,
                    ResourceKind.TASK,
                    ResourceKind.BENCHMARK,
                    ResourceKind.METRIC,
                }
            ),
            Capability.APPLY_PAPER_METADATA_EDIT: frozenset({ResourceKind.PAPER}),
            Capability.CREATE_EXTERNAL_PAPER: frozenset({ResourceKind.EXTERNAL_PAPER}),
            Capability.RESOLVE_MODEL_PAPER: frozenset(
                {ResourceKind.TRENDING_MODEL_CANDIDATE}
            ),
            Capability.RETRY_DECLARED_CRON: frozenset({ResourceKind.DECLARED_CRON}),
            Capability.REPAIR_DECLARED_CRON_SOURCE: frozenset(
                {ResourceKind.SOURCE_REPAIR}
            ),
            Capability.SWITCH_CHAT_PROVIDER: frozenset({ResourceKind.CHAT_PROVIDER}),
            Capability.REPAIR_CHAT_SOURCE: frozenset({ResourceKind.SOURCE_REPAIR}),
        }
    )
)


HUMAN_ONLY_EDIT_TYPES = frozenset(
    {
        "new_task",
        "new_method",
        "new_benchmark",
        "new_metric",
        "new_conference",
        "new_organization",
    }
)


AUTONOMOUS_PENDING_EDIT_CAPABILITIES: Mapping[str, Capability] = MappingProxyType(
    {
        "new_external_paper": Capability.CREATE_EXTERNAL_PAPER,
        "tasks": Capability.APPLY_EXISTING_TAXONOMY_EDIT,
        "methods": Capability.APPLY_EXISTING_TAXONOMY_EDIT,
        "evaluations": Capability.APPLY_EXISTING_LEADERBOARD_EVAL,
        "repositories": Capability.APPLY_PAPER_METADATA_EDIT,
        "project_pages": Capability.APPLY_PAPER_METADATA_EDIT,
        "source_url": Capability.APPLY_PAPER_METADATA_EDIT,
        "hf_artifacts": Capability.APPLY_PAPER_METADATA_EDIT,
        "organizations": Capability.APPLY_PAPER_METADATA_EDIT,
    }
)
