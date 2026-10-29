"""Bounded diagnosis and recovery for declared production CRON jobs."""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Literal, Protocol

from backend.services.autonomous_capabilities import (
    Capability,
    ResourceKind,
    ResourceRef,
)
from backend.services.autonomous_codex_runner import (
    CodexRequest,
    EvidenceRef,
    ProposedAction,
    codex_result_schema,
    run_codex,
)
from backend.services.autonomous_cron_probe import (
    FindingState,
    HealthFinding,
)
from backend.services.autonomous_operations_repository import RunContext
from backend.services.autonomous_release_service import ReleaseVerificationError
from backend.services.autonomous_source_repair import (
    AutonomousSourceRepairService,
    RepairCandidate,
    RepairProposal,
    RepairTarget,
    ReviewBundle,
    ReviewDecision,
)
from backend.services.cron_registry import CronJobDefinition, list_cron_jobs
from deploy.cron_launcher import COMMANDS, Job


_SAFE_RETRIES = frozenset(
    {
        "paper_markdown_backfill",
        "update_hot_github_trending",
        "update_github_stars",
        "update_citations",
        "calculate_trending_scores",
        "calculate_paper_trending_scores",
        "update_hf_artifacts",
        "import_hf_daily_papers",
        "enqueue_hf_daily_paper_curation",
        "enqueue_hf_trending_model_curation",
        "enqueue_benchmark_gap_review",
        "export_enrichment_dashboard",
        "sync_hf_organizations",
        "link_openalex_organizations",
        "calculate_organization_trending_scores",
        "refresh_paper_embeddings",
        "preload_thumbnails",
        "mirror_thumbnails_to_disk",
        "backfill_method_keywords",
        "backfill_method_references",
        "review_submissions",
        "process_curation_thumbnails",
    }
)

# Jobs that can write editorial/catalog entities remain diagnosis-and-alert only
# until they run with a database role that cannot create taxonomy resources.
_SAFE_SOURCE_REPAIRS = frozenset(
    {
        "calculate_paper_trending_scores",
        "calculate_trending_scores",
    }
)

# Shared dashboard/launcher files also own chat-monitor behavior, so autonomous
# non-chat repairs may not modify them before the qualified chat baseline lands.
_SHARED_CRON_SOURCE: tuple[str, ...] = ()

_OWNED_SERVICE_PATHS: Mapping[str, tuple[str, ...]] = {
    "paper_markdown_backfill": (
        "backend/services/paper_markdown_budget_service.py",
        "backend/services/paper_markdown_job_profile.py",
    ),
    "update_github_stars": ("backend/services/repository_service.py",),
    "update_citations": ("backend/services/paper_service.py",),
    "update_hf_artifacts": ("backend/services/hf_artifact_service.py",),
    "sync_3d_arena": ("backend/services/three_d_arena_sync_service.py",),
    "sync_tabarena": ("backend/services/tabarena_sync_service.py",),
    "sync_open_asr": ("backend/services/open_asr_sync_service.py",),
    "sync_mmteb_overall": ("backend/services/mmteb_sync_service.py",),
    "sync_mmteb_retrieval": ("backend/services/mmteb_sync_service.py",),
    "sync_mmteb_reranking": ("backend/services/mmteb_sync_service.py",),
    "sync_mmeb_v2": ("backend/services/mmeb_sync_service.py",),
    "sync_mmeb_v3": ("backend/services/mmeb_sync_service.py",),
    "sync_deepswe": ("backend/services/deepswe_sync_service.py",),
    "sync_artificial_analysis": (
        "backend/services/artificial_analysis_sync_service.py",
        "backend/services/artificial_analysis_tts_sync_service.py",
    ),
    "sync_programbench": ("backend/services/programbench_sync_service.py",),
    "sync_parsebench": ("backend/services/parsebench_sync_service.py",),
    "sync_extractbench": ("backend/services/extractbench_sync_service.py",),
    "sync_physics_iq_verified": (
        "backend/services/physics_iq_verified_sync_service.py",
    ),
    "sync_vals_finance_agent": ("backend/services/vals_finance_agent_sync_service.py",),
    "sync_surge_chartography": ("backend/services/surge_chartography_sync_service.py",),
    "sync_frontiercs_2": ("backend/services/frontiercs_2_sync_service.py",),
    "sync_vals_index": (
        "backend/services/carbon_board_syncs.py",
        "backend/services/live_leaderboard_sync.py",
    ),
    "sync_swe_sweep": (
        "backend/services/carbon_board_syncs.py",
        "backend/services/live_leaderboard_sync.py",
    ),
    "sync_vending_bench_2": (
        "backend/services/carbon_board_syncs.py",
        "backend/services/live_leaderboard_sync.py",
    ),
    "sync_blueprint_bench_2": (
        "backend/services/carbon_board_syncs.py",
        "backend/services/live_leaderboard_sync.py",
    ),
    "sync_riemann_bench": (
        "backend/services/carbon_board_syncs.py",
        "backend/services/live_leaderboard_sync.py",
    ),
    "sync_cwe_bench": (
        "backend/services/carbon_board_syncs.py",
        "backend/services/live_leaderboard_sync.py",
    ),
    "sync_exploitgym": (
        "backend/services/carbon_board_syncs.py",
        "backend/services/live_leaderboard_sync.py",
    ),
    "sync_cybergym": (
        "backend/services/carbon_board_syncs.py",
        "backend/services/live_leaderboard_sync.py",
    ),
    "sync_patcheval_verified": (
        "backend/services/carbon_board_syncs.py",
        "backend/services/live_leaderboard_sync.py",
    ),
    "sync_frontiercode": ("backend/services/frontiercode_sync_service.py",),
    "sync_coarena": ("backend/services/coarena_sync_service.py",),
    "sync_arc_prize": ("backend/services/arc_prize_sync_service.py",),
    "import_hf_daily_papers": ("backend/services/organization_sync_service.py",),
    "enqueue_hf_daily_paper_curation": (
        "backend/services/hf_daily_curation_service.py",
    ),
    "enqueue_hf_trending_model_curation": (
        "backend/services/hf_trending_model_curation_service.py",
    ),
    "enqueue_benchmark_gap_review": (
        "backend/services/benchmark_gap_review_service.py",
    ),
    "scan_model_releases": ("backend/services/model_release_radar_service.py",),
    "discover_x_threads": ("backend/services/x_thread_discovery_service.py",),
    "post_trending_paper_to_x": ("backend/services/x_trending_post_service.py",),
    "warm_paper_suggested_questions": (
        "backend/services/paper_suggested_questions_service.py",
        "backend/services/paper_suggested_questions_warm_service.py",
    ),
    "post_x_insight": ("backend/services/x_insight_post_service.py",),
    "sweep_conference_deadlines": (
        "backend/services/conference_deadline_service.py",
        "backend/services/conference_deadline_sweep_service.py",
        "backend/services/conference_deadline_agent.py",
    ),
    "refresh_conference_deadlines": (
        "backend/services/conference_deadline_service.py",
        "backend/services/conference_deadline_sweep_service.py",
        "backend/services/conference_deadline_agent.py",
    ),
    "export_enrichment_dashboard": ("backend/services/enrichment_dashboard_export.py",),
    "sync_hf_organizations": ("backend/services/organization_sync_service.py",),
    "sync_hf_author_profiles": ("backend/services/author_hf_profile_sync_service.py",),
    "link_openalex_organizations": (
        "backend/services/openalex_organization_linking_service.py",
    ),
    "link_google_scholar_profiles": (
        "backend/services/google_scholar_link_service.py",
    ),
    "calculate_organization_trending_scores": (
        "backend/services/organization_trending_service.py",
    ),
    "refresh_paper_embeddings": ("backend/services/incremental_paper_embeddings.py",),
    "preload_thumbnails": ("backend/services/thumbnail_service.py",),
    "link_methods_by_references": ("backend/services/paper_method_link_service.py",),
    "backfill_method_keywords": ("backend/services/method_backfill_service.py",),
    "backfill_method_references": (
        "backend/services/cron_token_probe.py",
        "backend/services/method_backfill_service.py",
        "backend/services/openalex_reference_service.py",
    ),
    "review_submissions": (
        "backend/services/autonomous_submission_job_service.py",
        "backend/services/autonomous_submission_service.py",
    ),
    "monitor_chat_operational_alerts": (
        "backend/services/chat_operational_alert_service.py",
    ),
    "process_curation_thumbnails": (
        "backend/services/curation_thumbnail_queue_service.py",
    ),
}

_FOCUSED_TESTS: Mapping[str, tuple[str, ...]] = {
    "extract_urls": ("backend/tests/paper/test_url_extraction_agent.py",),
    "paper_markdown_backfill": (
        "backend/tests/paper/test_markdown_dispatch.py",
        "backend/tests/paper/test_markdown_mount_recovery.py",
        "backend/tests/paper/test_markdown_pdf_sources.py",
        "backend/tests/paper/test_markdown_publication.py",
        "backend/tests/paper/test_markdown_repair.py",
        "backend/tests/paper/test_markdown_semantics.py",
        "backend/tests/paper/test_markdown_stalled_jobs.py",
        "backend/tests/paper/test_markdown_storage_bridge.py",
        "backend/tests/paper/test_markdown_worker_lifecycle.py",
    ),
    "update_hot_github_trending": ("backend/tests/test_hot_github_trending.py",),
    "update_github_stars": ("backend/tests/test_update_github_stars.py",),
    "update_citations": ("backend/tests/paper/test_update_citations_cron.py",),
    "calculate_trending_scores": ("backend/tests/test_calculate_trending_scores.py",),
    "calculate_paper_trending_scores": ("backend/tests/paper/test_trending_scores.py",),
    "update_hf_artifacts": ("backend/tests/test_hf_artifact_write_sync.py",),
    "sync_3d_arena": ("backend/tests/evaluation/test_three_d_arena_sync.py",),
    "sync_tabarena": ("backend/tests/evaluation/test_tabarena_sync.py",),
    "sync_open_asr": ("backend/tests/evaluation/test_open_asr_sync.py",),
    "sync_mmteb_overall": ("backend/tests/evaluation/test_mmteb_sync.py",),
    "sync_mmteb_retrieval": ("backend/tests/evaluation/test_mmteb_sync.py",),
    "sync_mmteb_reranking": ("backend/tests/evaluation/test_mmteb_sync.py",),
    "sync_mmeb_v2": ("backend/tests/evaluation/test_mmeb_sync.py",),
    "sync_mmeb_v3": ("backend/tests/evaluation/test_mmeb_sync.py",),
    "sync_deepswe": ("backend/tests/evaluation/test_deepswe_sync.py",),
    "sync_artificial_analysis": (
        "backend/tests/evaluation/test_artificial_analysis_sync.py",
        "backend/tests/evaluation/test_artificial_analysis_tts_sync.py",
    ),
    "sync_programbench": ("backend/tests/evaluation/test_programbench_sync.py",),
    "sync_parsebench": ("backend/tests/evaluation/test_parsebench_sync.py",),
    "sync_extractbench": ("backend/tests/evaluation/test_extractbench_sync.py",),
    "sync_physics_iq_verified": (
        "backend/tests/evaluation/test_physics_iq_verified_sync.py",
    ),
    "sync_vals_finance_agent": (
        "backend/tests/evaluation/test_vals_finance_agent_sync.py",
    ),
    "sync_surge_chartography": (
        "backend/tests/evaluation/test_surge_chartography_sync.py",
    ),
    "sync_frontiercs_2": ("backend/tests/evaluation/test_frontiercs_2_sync.py",),
    "sync_vals_index": ("backend/tests/evaluation/test_carbon_board_syncs.py",),
    "sync_swe_sweep": ("backend/tests/evaluation/test_carbon_board_syncs.py",),
    "sync_vending_bench_2": ("backend/tests/evaluation/test_carbon_board_syncs.py",),
    "sync_blueprint_bench_2": ("backend/tests/evaluation/test_carbon_board_syncs.py",),
    "sync_riemann_bench": ("backend/tests/evaluation/test_carbon_board_syncs.py",),
    "sync_cwe_bench": ("backend/tests/evaluation/test_carbon_board_syncs.py",),
    "sync_exploitgym": ("backend/tests/evaluation/test_carbon_board_syncs.py",),
    "sync_cybergym": ("backend/tests/evaluation/test_carbon_board_syncs.py",),
    "sync_patcheval_verified": ("backend/tests/evaluation/test_carbon_board_syncs.py",),
    "sync_frontiercode": ("backend/tests/evaluation/test_frontiercode_sync.py",),
    "sync_coarena": ("backend/tests/evaluation/test_coarena_sync.py",),
    "sync_arc_prize": ("backend/tests/evaluation/test_arc_prize_sync.py",),
    "import_hf_daily_papers": ("backend/tests/paper/test_import_hf_daily_papers.py",),
    "enqueue_hf_daily_paper_curation": (
        "backend/tests/cron/test_job_health_contracts.py",
    ),
    "enqueue_hf_trending_model_curation": (
        "backend/tests/curation/test_trending_model_curation.py",
    ),
    "enqueue_benchmark_gap_review": (
        "backend/tests/curation/test_benchmark_gap_review.py",
    ),
    "scan_model_releases": ("backend/tests/test_model_release_radar_service.py",),
    "discover_x_threads": ("backend/tests/test_x_thread_discovery_service.py",),
    "post_trending_paper_to_x": ("backend/tests/test_x_trending_post_service.py",),
    "warm_paper_suggested_questions": (
        "backend/tests/test_paper_suggested_questions_warm_service.py",
    ),
    "post_x_insight": ("backend/tests/test_x_insight_post_service.py",),
    "sweep_conference_deadlines": (
        "backend/tests/test_conference_deadline_service.py",
    ),
    "refresh_conference_deadlines": (
        "backend/tests/test_conference_deadline_service.py",
    ),
    "export_enrichment_dashboard": (
        "backend/tests/curation/test_enrichment_dashboard_export.py",
    ),
    "sync_hf_organizations": ("backend/tests/test_organization_sync_service.py",),
    "sync_hf_author_profiles": (
        "backend/tests/test_author_hf_profile_sync_service.py",
    ),
    "link_openalex_organizations": (
        "backend/tests/test_backfill_openalex_organizations.py",
    ),
    "link_google_scholar_profiles": (
        "backend/tests/author/test_google_scholar_link_service.py",
    ),
    "calculate_organization_trending_scores": (
        "backend/tests/test_organization_trending_service.py",
    ),
    "refresh_paper_embeddings": ("backend/tests/paper/test_incremental_embeddings.py",),
    "preload_thumbnails": ("backend/tests/paper/test_preload_thumbnails.py",),
    "mirror_thumbnails_to_disk": ("backend/tests/paper/test_thumbnail_rendering.py",),
    "backfill_method_keywords": ("backend/tests/cron/test_job_health_contracts.py",),
    "backfill_method_references": (
        "backend/tests/test_historical_reference_backfill_cli.py",
    ),
    "link_methods_by_references": (
        "backend/tests/taxonomy/test_link_methods_by_references_weekly.py",
    ),
    "link_papers_by_task_keywords": (
        "backend/tests/cron/test_job_health_contracts.py",
    ),
    "review_submissions": ("backend/tests/curation/test_submission_schedule.py",),
    "process_curation_thumbnails": ("backend/tests/curation/test_thumbnail_queue.py",),
    "autonomous_cron_health": ("backend/tests/test_autonomous_cron_operator.py",),
    "autonomous_cron_audit": ("backend/tests/test_autonomous_cron_operator.py",),
    "monitor_chat_operational_alerts": (
        "backend/tests/chat/test_operational_alerts.py",
    ),
    "run_chat_synthetic_probe": ("backend/tests/chat/test_synthetic_probe.py",),
}


@dataclass(frozen=True, slots=True)
class CronRepairContract:
    job_name: str
    source_paths: tuple[str, ...]
    shared_source_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    retry_command: tuple[str, str] | None
    source_repair_allowed: bool = True
    recoverable_contracts: tuple[str, ...] = (
        "durable_data_freshness",
        "exit_state",
        "log_signature",
        "semantic_correctness",
        "throughput_backlog",
    )


@dataclass(frozen=True, slots=True)
class RepairResult:
    status: Literal["verified", "failed", "rolled_back"]
    published_sha: str | None
    deployed_sha: str | None
    rollback_performed: bool
    reason_code: str

    @classmethod
    def verified(cls, sha: str) -> "RepairResult":
        return cls("verified", sha, sha, False, "source_repaired")


@dataclass(frozen=True, slots=True)
class OperatorOutcome:
    status: Literal[
        "noop",
        "blocked",
        "diagnosis_only",
        "runtime_recovered",
        "source_repaired",
        "verification_failed",
        "failed",
        "rolled_back",
    ]
    job_name: str | None
    reason_code: str
    before_digest: str
    after_digest: str
    published_sha: str | None = None
    rollback_performed: bool = False


class Policy(Protocol):
    def authorize(
        self,
        db,
        context: RunContext,
        capability: Capability,
        resource: ResourceRef,
    ): ...


class CronCodexDiagnoser:
    """Invoke Luna/medium with only the bounded Task 8 evidence envelope."""

    def __init__(self, *, db, runner=run_codex, budget_usd: Decimal = Decimal("2")):
        self.db = db
        self.runner = runner
        self.budget_usd = budget_usd

    def __call__(
        self, context: RunContext, findings: tuple[HealthFinding, ...]
    ) -> tuple[ProposedAction, ...]:
        capabilities = (
            Capability.RETRY_DECLARED_CRON,
            Capability.REPAIR_DECLARED_CRON_SOURCE,
        )
        evidence = tuple(
            EvidenceRef(
                "cron_finding",
                f"{finding.job_name}:{finding.contract}",
                _finding_digest((finding,)),
            )
            for finding in findings
        )
        request = CodexRequest(
            context=context,
            evidence=evidence,
            capabilities=capabilities,
            output_schema=codex_result_schema(capabilities),
            budget_usd=self.budget_usd,
            model_alias="diagnosis",
            evidence_payload={"findings": [finding.as_dict() for finding in findings]},
        )
        result = self.runner(request, db=self.db)
        return result.proposed_actions if result.status == "completed" else ()


class PwcCronRetrier:
    def __init__(
        self,
        run_id: uuid.UUID,
        executable: str = "/usr/local/sbin/pwc-autonomous-cron-retry",
    ) -> None:
        if not executable.startswith("/"):
            raise ValueError("CRON retry broker executable must be absolute")
        if not isinstance(run_id, uuid.UUID):
            raise TypeError("CRON retry broker requires an exact run ID")
        self.run_id = run_id
        self.executable = executable

    def __call__(self, job_name: str) -> int:
        if job_name not in _SAFE_RETRIES or job_name not in COMMANDS:
            raise ValueError("CRON retry is not allowlisted")
        return subprocess.run(
            [self.executable, str(self.run_id), job_name],
            check=False,
            timeout=8 * 60 * 60,
            env={"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
        ).returncode


class CronCandidateEditor:
    """Let Luna edit only files remounted writable inside one Task 4 candidate."""

    def __init__(self, *, db, runner=run_codex, budget_usd: Decimal = Decimal("8")):
        self.db = db
        self.runner = runner
        self.budget_usd = budget_usd

    def __call__(
        self,
        parent_context: RunContext,
        candidate: RepairCandidate,
        contract: CronRepairContract,
        findings: tuple[HealthFinding, ...],
    ) -> None:
        capability = Capability.REPAIR_DECLARED_CRON_SOURCE
        edit_context = RunContext(
            uuid.uuid5(candidate.candidate_id, "cron-source-edit-v1"),
            parent_context.operator,
            parent_context.dry_run,
            f"{parent_context.manifest_revision}:source-edit",
        )
        writable = tuple(
            dict.fromkeys(
                (
                    *contract.source_paths,
                    *contract.shared_source_paths,
                    *contract.test_paths,
                )
            )
        )
        request = CodexRequest(
            context=edit_context,
            evidence=tuple(
                EvidenceRef(
                    "cron_finding",
                    f"{finding.job_name}:{finding.contract}",
                    _finding_digest((finding,)),
                )
                for finding in findings
            ),
            capabilities=(capability,),
            output_schema=codex_result_schema((capability,)),
            budget_usd=self.budget_usd,
            model_alias="diagnosis",
            evidence_payload={"findings": [finding.as_dict() for finding in findings]},
            workspace_path=candidate.worktree,
            writable_paths=writable,
        )
        result = self.runner(request, db=self.db)
        if (
            result.status != "completed"
            or len(result.proposed_actions) != 1
            or result.proposed_actions[0].capability is not capability
            or result.proposed_actions[0].resource
            != ResourceRef(ResourceKind.SOURCE_REPAIR, contract.job_name, True)
        ):
            raise RuntimeError("Luna did not produce the declared CRON source repair")


class CronCandidateReviewer:
    """Run a separate read-only Luna pass over the validated bounded patch."""

    def __init__(
        self,
        *,
        db,
        context: RunContext,
        job_name: str,
        runner=run_codex,
        budget_usd: Decimal = Decimal("4"),
    ) -> None:
        self.db = db
        self.context = context
        self.job_name = job_name
        self.runner = runner
        self.budget_usd = budget_usd

    def __call__(self, reviewer_alias: str, bundle: ReviewBundle) -> ReviewDecision:
        if reviewer_alias != "diagnosis":
            raise ValueError("CRON repairs require the diagnosis review alias")
        capability = Capability.REPAIR_DECLARED_CRON_SOURCE
        review_context = RunContext(
            uuid.uuid5(bundle.candidate_id, "cron-source-review-v1"),
            self.context.operator,
            self.context.dry_run,
            f"{self.context.manifest_revision}:source-review",
        )
        payload = {
            "repair_review": {
                "base_sha": bundle.base_sha,
                "candidate_id": str(bundle.candidate_id),
                "changed_paths": list(bundle.changed_paths),
                "check_outcomes": [
                    {
                        "command": list(outcome.command),
                        "output_digest": outcome.output_digest,
                    }
                    for outcome in bundle.check_outcomes
                ],
                "patch": bundle.patch,
                "patch_digest": bundle.patch_digest,
            }
        }
        request = CodexRequest(
            context=review_context,
            evidence=(EvidenceRef("cron_repair", self.job_name, bundle.patch_digest),),
            capabilities=(capability,),
            output_schema=codex_result_schema((capability,)),
            budget_usd=self.budget_usd,
            model_alias="diagnosis",
            evidence_payload=payload,
        )
        result = self.runner(request, db=self.db)
        approved = bool(
            result.status == "completed"
            and len(result.proposed_actions) == 1
            and result.proposed_actions[0].capability is capability
            and result.proposed_actions[0].resource
            == ResourceRef(ResourceKind.SOURCE_REPAIR, self.job_name, True)
            and result.proposed_actions[0].reason_code == "approve"
        )
        return ReviewDecision(reviewer_alias, approved, result.result_digest)


class CronSourceRepairPipeline:
    """Edit, review, publish, deploy, recover, and clean one Task 4 candidate."""

    def __init__(
        self,
        *,
        db,
        source_service: AutonomousSourceRepairService,
        release_service,
        policy: Policy,
        editor: CronCandidateEditor,
        reviewer: Callable[[str, ReviewBundle], ReviewDecision],
        recovery_verifier: Callable[[str], bool],
    ) -> None:
        self.db = db
        self.source_service = source_service
        self.release_service = release_service
        self.policy = policy
        self.editor = editor
        self.reviewer = reviewer
        self.recovery_verifier = recovery_verifier

    def __call__(
        self,
        context: RunContext,
        job_name: str,
        contract: CronRepairContract,
        findings: tuple[HealthFinding, ...],
    ) -> RepairResult:
        candidate = self.source_service.prepare_candidate(
            self.db,
            context,
            RepairProposal(Capability.REPAIR_DECLARED_CRON_SOURCE, job_name),
        )
        published_sha = None
        try:
            decision = self.policy.authorize(
                self.db,
                context,
                Capability.REPAIR_DECLARED_CRON_SOURCE,
                ResourceRef(ResourceKind.SOURCE_REPAIR, job_name, True),
            )
            if not decision.allowed:
                raise PermissionError(decision.reason_code)
            self.editor(context, candidate, contract, findings)
            bundle = self.source_service.review_candidate(
                self.db,
                candidate,
                reviewer_alias="diagnosis",
                reviewer=self.reviewer,
            )
            published_sha = self.source_service.publish_candidate(
                self.db, candidate, bundle
            )
            try:
                self.release_service.deploy_exact_sha(
                    self.db, context, "production", published_sha
                )
            except ReleaseVerificationError as error:
                return RepairResult(
                    "rolled_back" if error.rollback_performed else "failed",
                    published_sha,
                    None,
                    error.rollback_performed,
                    "production_verification_failed"
                    if error.rollback_performed
                    else "production_deploy_failed",
                )
            if self.recovery_verifier(job_name):
                return RepairResult.verified(published_sha)
            self.release_service.rollback(self.db, context, "production", published_sha)
            return RepairResult(
                "rolled_back",
                published_sha,
                None,
                True,
                "production_verification_failed",
            )
        except (OSError, RuntimeError, subprocess.SubprocessError):
            return RepairResult(
                "failed", published_sha, None, False, "source_repair_failed"
            )
        finally:
            self.source_service.cleanup_candidate(self.db, candidate)


def _owned_source(definition: CronJobDefinition) -> tuple[str, ...]:
    if definition.id == "extract_urls":
        entry = (
            "url_extraction_agent/agent.py",
            "url_extraction_agent/database.py",
            "url_extraction_agent/runner.py",
            "url_extraction_agent/schema.py",
        )
    else:
        path = PurePosixPath(definition.script_path)
        value = str(path)
        if not value.startswith(("backend/", ".github/")):
            value = f".github/workflows/scripts/{value}"
        entry = (value,)
    return tuple(dict.fromkeys((*entry, *_OWNED_SERVICE_PATHS.get(definition.id, ()))))


def build_cron_repair_contracts(
    definitions: Sequence[CronJobDefinition] | None = None,
    commands: Mapping[str, Job] | None = None,
) -> dict[str, CronRepairContract]:
    """Return a closed repair map for every deterministic CRON definition."""

    definitions = tuple(definitions or list_cron_jobs())
    commands = COMMANDS if commands is None else commands
    if len({definition.id for definition in definitions}) != len(definitions):
        raise ValueError("Duplicate declared CRON job")
    contracts = {}
    for definition in definitions:
        launcher = commands.get(definition.id)
        retry = (
            ("pwc-cron", definition.id)
            if definition.id in _SAFE_RETRIES and launcher is not None
            else None
        )
        contracts[definition.id] = CronRepairContract(
            job_name=definition.id,
            source_paths=_owned_source(definition),
            shared_source_paths=_SHARED_CRON_SOURCE,
            test_paths=tuple(
                dict.fromkeys(
                    (
                        *_FOCUSED_TESTS.get(definition.id, ()),
                        "backend/tests/test_autonomous_cron_operator.py",
                        "backend/tests/curation/test_cron_probe.py",
                        "backend/tests/cron/test_health.py",
                    )
                )
            ),
            retry_command=retry,
            source_repair_allowed=definition.id in _SAFE_SOURCE_REPAIRS,
        )
    return contracts


def build_cron_source_repair_targets(
    contracts: Mapping[str, CronRepairContract] | None = None,
) -> dict[str, RepairTarget]:
    contracts = contracts or build_cron_repair_contracts()
    return {
        name: RepairTarget(
            (*contract.source_paths, *contract.shared_source_paths),
            contract.test_paths,
        )
        for name, contract in contracts.items()
        if contract.source_repair_allowed
    }


def _finding_digest(findings: Sequence[HealthFinding]) -> str:
    encoded = json.dumps(
        [finding.as_dict() for finding in findings],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class AutonomousCronOperator:
    """Orchestrate one bounded action for one failing declared job."""

    def __init__(
        self,
        *,
        db,
        repository,
        policy: Policy,
        diagnose: Callable[
            [RunContext, tuple[HealthFinding, ...]], tuple[ProposedAction, ...]
        ],
        retry: Callable[[str], int],
        probe: Callable[[str], tuple[HealthFinding, ...]],
        source_repair: Callable[
            [
                RunContext,
                str,
                CronRepairContract,
                tuple[HealthFinding, ...],
            ],
            RepairResult,
        ],
        alert: Callable[[dict[str, object]], None],
        contracts: Mapping[str, CronRepairContract] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.db = db
        self.repository = repository
        self.policy = policy
        self.diagnose = diagnose
        self.retry = retry
        self.probe = probe
        self.source_repair = source_repair
        self.alert = alert
        self.contracts = dict(contracts or build_cron_repair_contracts())
        self.now = now or (lambda: datetime.now(UTC))

    def handle_cron_findings(
        self, context: RunContext, findings: Sequence[HealthFinding]
    ) -> OperatorOutcome:
        before = tuple(findings)
        before_digest = _finding_digest(before)
        actionable = tuple(
            finding for finding in before if finding.state is not FindingState.HEALTHY
        )
        if not actionable:
            return OperatorOutcome(
                "noop", None, "healthy", before_digest, before_digest
            )
        jobs = sorted({finding.job_name for finding in actionable})
        if len(jobs) != 1 or jobs[0] not in self.contracts:
            return self._blocked(
                None,
                "finding_scope_invalid",
                before_digest,
                {"jobs": jobs[:20]},
            )
        job_name = jobs[0]
        contract = self.contracts[job_name]
        actions = self.diagnose(context, actionable)
        if not actions:
            return OperatorOutcome(
                "diagnosis_only",
                job_name,
                "no_safe_action",
                before_digest,
                before_digest,
            )
        if len(actions) != 1 or actions[0].resource.identifier != job_name:
            return self._blocked(
                job_name,
                "diagnosis_scope_mismatch",
                before_digest,
                {"action_count": len(actions)},
            )
        selected = actions[0]
        ambiguous_lock = any(
            finding.contract == "lock_ownership_age"
            and finding.state is not FindingState.HEALTHY
            for finding in actionable
        )
        if ambiguous_lock:
            return self._blocked(
                job_name, "ambiguous_lock", before_digest, {"job": job_name}
            )
        unsupported_contracts = sorted(
            {
                finding.contract
                for finding in actionable
                if finding.contract not in contract.recoverable_contracts
            }
        )
        if unsupported_contracts:
            return self._blocked(
                job_name,
                "recovery_action_not_allowlisted",
                before_digest,
                {"contracts": unsupported_contracts},
            )
        if selected.capability is Capability.RETRY_DECLARED_CRON:
            return self._retry(context, job_name, contract, before, before_digest)
        if selected.capability is Capability.REPAIR_DECLARED_CRON_SOURCE:
            return self._repair(context, job_name, contract, actionable, before_digest)
        return self._blocked(
            job_name,
            "diagnosis_capability_invalid",
            before_digest,
            {"job": job_name},
        )

    def _retry(
        self,
        context: RunContext,
        job_name: str,
        contract: CronRepairContract,
        before: tuple[HealthFinding, ...],
        before_digest: str,
    ) -> OperatorOutcome:
        if contract.retry_command is None:
            return self._blocked(
                job_name, "runtime_retry_not_safe", before_digest, {"job": job_name}
            )
        decision = self.policy.authorize(
            self.db,
            context,
            Capability.RETRY_DECLARED_CRON,
            ResourceRef(ResourceKind.DECLARED_CRON, job_name, True),
        )
        if not decision.allowed:
            return self._blocked(
                job_name, decision.reason_code, before_digest, {"job": job_name}
            )
        self.repository.assert_mutation_allowed(self.db, context)
        self.repository.append_action(
            self.db,
            context=context,
            capability=Capability.RETRY_DECLARED_CRON.value,
            reason_code="retry_authorized",
            resource_kind=ResourceKind.DECLARED_CRON.value,
            resource_identifier=job_name,
            before_digest=before_digest,
            after_digest=before_digest,
            now=self.now(),
        )
        self.db.commit()
        returncode = self.retry(job_name)
        after = self.probe(job_name)
        after_digest = _finding_digest(after)
        failed_contracts = {finding.contract for finding in before}
        recovered = returncode == 0 and all(
            finding.state is FindingState.HEALTHY
            for finding in after
            if finding.contract in failed_contracts
        )
        reason = "runtime_recovered" if recovered else "runtime_verification_failed"
        self._audit(context, job_name, reason, before_digest, after_digest)
        if not recovered:
            self.alert({"job": job_name, "reason_code": reason})
        return OperatorOutcome(
            "runtime_recovered" if recovered else "verification_failed",
            job_name,
            reason,
            before_digest,
            after_digest,
        )

    def _repair(
        self,
        context: RunContext,
        job_name: str,
        contract: CronRepairContract,
        findings: tuple[HealthFinding, ...],
        before_digest: str,
    ) -> OperatorOutcome:
        if not contract.source_repair_allowed:
            return self._blocked(
                job_name,
                "source_repair_not_safely_scoped",
                before_digest,
                {"job": job_name},
            )
        decision = self.policy.authorize(
            self.db,
            context,
            Capability.REPAIR_DECLARED_CRON_SOURCE,
            ResourceRef(ResourceKind.SOURCE_REPAIR, job_name, True),
        )
        if not decision.allowed and decision.reason_code != "repair_lease_not_owned":
            return self._blocked(
                job_name, decision.reason_code, before_digest, {"job": job_name}
            )
        try:
            self.repository.assert_mutation_allowed(self.db, context)
        except Exception as error:
            return self._blocked(
                job_name,
                type(error).__name__.lower(),
                before_digest,
                {"job": job_name},
            )
        try:
            result = self.source_repair(context, job_name, contract, findings)
        except (OSError, PermissionError, RuntimeError, ValueError) as error:
            result = RepairResult(
                "failed",
                None,
                None,
                False,
                f"source_repair_{type(error).__name__.lower()}",
            )
        after_digest = hashlib.sha256(
            json.dumps(
                {
                    "deployed_sha": result.deployed_sha,
                    "published_sha": result.published_sha,
                    "reason_code": result.reason_code,
                    "rollback_performed": result.rollback_performed,
                    "status": result.status,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        self._audit(context, job_name, result.reason_code, before_digest, after_digest)
        if result.status != "verified":
            self.alert({"job": job_name, "reason_code": result.reason_code})
        status = "source_repaired" if result.status == "verified" else result.status
        return OperatorOutcome(
            status,
            job_name,
            result.reason_code,
            before_digest,
            after_digest,
            result.published_sha,
            result.rollback_performed,
        )

    def _blocked(
        self,
        job_name: str | None,
        reason_code: str,
        digest: str,
        evidence: dict[str, object],
    ) -> OperatorOutcome:
        self.alert({"job": job_name, "reason_code": reason_code, **evidence})
        return OperatorOutcome("blocked", job_name, reason_code, digest, digest)

    def _audit(
        self,
        context: RunContext,
        job_name: str,
        reason_code: str,
        before_digest: str,
        after_digest: str,
    ) -> None:
        self.repository.append_action(
            self.db,
            context=context,
            capability=Capability.RETRY_DECLARED_CRON.value
            if reason_code.startswith("runtime_")
            else Capability.REPAIR_DECLARED_CRON_SOURCE.value,
            reason_code=reason_code,
            resource_kind=ResourceKind.DECLARED_CRON.value,
            resource_identifier=job_name,
            before_digest=before_digest,
            after_digest=after_digest,
            now=self.now(),
        )
        self.db.commit()


def handle_cron_findings(
    operator: AutonomousCronOperator,
    context: RunContext,
    findings: Sequence[HealthFinding],
) -> OperatorOutcome:
    return operator.handle_cron_findings(context, findings)
