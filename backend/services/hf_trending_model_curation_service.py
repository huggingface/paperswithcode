"""Hourly reconciliation from the Hub trending feed into scoped Codex jobs."""

from __future__ import annotations

import subprocess
import uuid
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    ModelRelease,
    PaperCurationJob,
    PaperCurationWorkflow,
    TrendingModelCandidate,
    TrendingModelCurationState,
)
from backend.services.codex_add_evals_service import (
    CodexPaperJobService,
    codex_paper_job_service,
)
from backend.services.hf_trending_model_discovery_service import (
    HFModelCardClient,
    HFTrendingDiscoveryClient,
    is_obvious_conversion,
    should_requeue_card,
)
from backend.services.trending_model_resolution_service import model_family_key


class HFTrendingModelCurationService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        discovery: HFTrendingDiscoveryClient | None = None,
        cards: HFModelCardClient | None = None,
        jobs: CodexPaperJobService = codex_paper_job_service,
        rollout: bool = False,
    ) -> None:
        self.db = db
        self.settings = settings
        self.discovery = discovery or HFTrendingDiscoveryClient()
        self.cards = cards or HFModelCardClient()
        self.jobs = jobs
        self.rollout = rollout

    def _rollout_state(self) -> TrendingModelCurationState:
        state = self.db.get(TrendingModelCurationState, 1)
        if state is None:
            state = TrendingModelCurationState(id=1)
            self.db.add(state)
            self.db.flush()
        return state

    def _rejected_candidate_can_converge(
        self, candidate: TrendingModelCandidate, latest_job: PaperCurationJob | None
    ) -> bool:
        """Retry when a matching family paper appeared after the rejection."""
        if candidate.status != "rejected" or latest_job is None or not candidate.author:
            return False
        resolution = (latest_job.proposal or {}).get("resolve_model_paper") or {}
        if resolution.get("decision") != "reject" or resolution.get(
            "novelty_kind"
        ) not in {"new_weights", "new_method", "new_release", "uncertain"}:
            return False
        candidate_family = model_family_key(candidate.repo_id)
        if not candidate_family:
            return False
        rejected_at = (
            latest_job.applied_at
            or latest_job.submitted_at
            or latest_job.finished_at
            or latest_job.created_at
        )
        releases = (
            self.db.query(ModelRelease)
            .filter(
                func.lower(ModelRelease.publisher) == candidate.author.casefold(),
                ModelRelease.created_at > rejected_at,
            )
            .order_by(ModelRelease.created_at.desc(), ModelRelease.id.desc())
            .limit(50)
            .all()
        )
        return any(
            candidate_family
            in {
                model_family_key(identity)
                for identity in [release.canonical_name, *(release.aliases or [])]
            }
            for release in releases
        )

    def _release_canary_if_healthy(self, state: TrendingModelCurationState) -> bool:
        if state.canary_released_at is not None:
            return True
        candidate_ids = list(state.canary_candidate_ids or [])
        if state.canary_started_at is None:
            return False
        candidates = {
            str(candidate.id): candidate
            for candidate in self.db.query(TrendingModelCandidate)
            .filter(
                TrendingModelCandidate.id.in_(
                    [uuid.UUID(candidate_id) for candidate_id in candidate_ids]
                )
            )
            .all()
        }
        for candidate_id in candidate_ids:
            candidate = candidates.get(str(candidate_id))
            if candidate is None:
                return False
            if candidate.status == "rejected":
                continue
            if candidate.status != "resolved":
                return False
            revision = candidate.readme_revision or candidate.readme_sha
            completed = (
                self.db.query(PaperCurationWorkflow.id)
                .filter(
                    PaperCurationWorkflow.source_candidate_id == candidate.id,
                    PaperCurationWorkflow.source_revision == revision,
                    PaperCurationWorkflow.policy_version == "hf-trending-v1",
                    PaperCurationWorkflow.status.in_({"completed", "satisfied"}),
                )
                .first()
            )
            if completed is None:
                return False
        state.canary_released_at = datetime.now(UTC)
        return True

    def _retry_failed_canary(
        self, state: TrendingModelCurationState, *, limit: int
    ) -> list[str]:
        if limit <= 0:
            return []
        candidate_ids = [
            uuid.UUID(candidate_id)
            for candidate_id in list(state.canary_candidate_ids or [])
        ]
        failed = (
            self.db.query(TrendingModelCandidate)
            .filter(
                TrendingModelCandidate.id.in_(candidate_ids),
                TrendingModelCandidate.status == "failed",
            )
            .order_by(TrendingModelCandidate.processed_at, TrendingModelCandidate.id)
            .limit(min(limit, 10))
            .all()
        )
        retried: list[str] = []
        for candidate in failed:
            attempts = (
                self.db.query(PaperCurationJob)
                .filter(
                    PaperCurationJob.candidate_id == candidate.id,
                    PaperCurationJob.kind == "resolve-model-paper",
                )
                .count()
            )
            if attempts >= 3:
                continue
            self.jobs.enqueue_resolution(
                self.db,
                candidate=candidate,
                requested_by="hf-trending-cron-canary-retry",
                settings=self.settings,
                dispatch=False,
                commit=False,
            )
            retried.append(str(candidate.id))
        return retried

    def status(self) -> dict:
        candidate_counts = {
            status: int(count)
            for status, count in self.db.query(
                TrendingModelCandidate.status,
                func.count(TrendingModelCandidate.id),
            )
            .group_by(TrendingModelCandidate.status)
            .all()
        }
        active_jobs = (
            self.db.query(PaperCurationJob)
            .filter(
                PaperCurationJob.trigger == "hf-trending-cron",
                PaperCurationJob.status.in_({"queued", "dispatching", "running"}),
            )
            .count()
        )
        latest_seen = self.db.query(
            func.max(TrendingModelCandidate.last_seen_at)
        ).scalar()
        result = {
            "candidate_counts": candidate_counts,
            "active_jobs": int(active_jobs),
            "latest_seen_at": latest_seen,
        }
        if self.rollout:
            state = self.db.get(TrendingModelCurationState, 1)
            result["rollout"] = {
                "discovery_dry_run_completed": bool(
                    state and state.discovery_dry_run_completed
                ),
                "canary_started_at": state.canary_started_at if state else None,
                "canary_candidate_ids": list(state.canary_candidate_ids or [])
                if state
                else [],
                "canary_released_at": state.canary_released_at if state else None,
            }
        return result

    def reconcile(
        self,
        *,
        dispatch: bool = True,
        dry_run: bool = False,
        max_queued: int = 10,
    ) -> dict:
        if not self.rollout:
            return self._reconcile_once(
                dispatch=dispatch, dry_run=dry_run, max_queued=max_queued
            )

        state = self._rollout_state()
        if not state.discovery_dry_run_completed:
            summary = self._reconcile_once(
                dispatch=False, dry_run=True, max_queued=max_queued
            )
            # The discovery transaction was rolled back. Persist only the
            # rollout marker so this exact dry cycle cannot publish anything.
            state = self._rollout_state()
            state.discovery_dry_run_completed = True
            self.db.commit()
            summary["rollout_phase"] = "discovery_dry_run_completed"
            return summary

        if dry_run:
            summary = self._reconcile_once(
                dispatch=False, dry_run=True, max_queued=max_queued
            )
            summary["rollout_phase"] = "dry_run"
            return summary

        if state.canary_started_at is not None and state.canary_released_at is None:
            retried = self._retry_failed_canary(state, limit=max_queued)
            summary = self._reconcile_once(
                dispatch=dispatch, dry_run=False, max_queued=0
            )
            summary["retried_canary"] = len(retried)
            summary["queued"] += len(retried)
            summary["queued_candidate_ids"].extend(retried)
            state = self._rollout_state()
            released = self._release_canary_if_healthy(state)
            self.db.commit()
            summary["rollout_phase"] = (
                "canary_released" if released else "canary_in_progress"
            )
            summary["canary_candidate_ids"] = list(state.canary_candidate_ids or [])
            return summary

        summary = self._reconcile_once(
            dispatch=dispatch,
            dry_run=False,
            max_queued=min(max_queued, 10)
            if state.canary_released_at is None
            else max_queued,
        )
        if state.canary_released_at is None:
            state = self._rollout_state()
            state.canary_started_at = datetime.now(UTC)
            state.canary_candidate_ids = list(summary["queued_candidate_ids"])
            self._release_canary_if_healthy(state)
            self.db.commit()
            summary["rollout_phase"] = (
                "canary_released"
                if state.canary_released_at is not None
                else "canary_started"
            )
        else:
            summary["rollout_phase"] = "steady_state"
        return summary

    def _reconcile_once(
        self,
        *,
        dispatch: bool,
        dry_run: bool,
        max_queued: int,
    ) -> dict:
        # A paper may have had an active daily workflow when its model was first
        # resolved. Revisit these idempotently so it is released as soon as that
        # workflow finishes.
        if not dry_run:
            for resolved in (
                self.db.query(TrendingModelCandidate)
                .outerjoin(
                    PaperCurationWorkflow,
                    (
                        PaperCurationWorkflow.source_candidate_id
                        == TrendingModelCandidate.id
                    )
                    & (
                        PaperCurationWorkflow.source_revision
                        == func.coalesce(
                            TrendingModelCandidate.readme_revision,
                            TrendingModelCandidate.readme_sha,
                        )
                    )
                    & (PaperCurationWorkflow.policy_version == "hf-trending-v1"),
                )
                .filter(
                    TrendingModelCandidate.status == "resolved",
                    PaperCurationWorkflow.id.is_(None),
                )
                .order_by(
                    TrendingModelCandidate.processed_at, TrendingModelCandidate.id
                )
                .limit(50)
                .all()
            ):
                self.jobs.enqueue_resolved_candidate_workflow(
                    self.db, resolved, self.settings, dispatch=False
                )
        summary = {
            "discovered": 0,
            "queued": 0,
            "rejected_conversions": 0,
            "unchanged": 0,
            "errors": [],
            "queued_candidate_ids": [],
        }
        # A sibling release can establish the canonical family paper after the
        # original model has fallen out of the live trending page. Reconsider
        # those bounded rejections independently of today's discovery feed.
        rejected_candidates = (
            self.db.query(TrendingModelCandidate)
            .filter(TrendingModelCandidate.status == "rejected")
            .order_by(
                TrendingModelCandidate.processed_at.desc(),
                TrendingModelCandidate.id,
            )
            .limit(100)
            .all()
        )
        for candidate in rejected_candidates:
            attempts = (
                self.db.query(PaperCurationJob)
                .filter(
                    PaperCurationJob.candidate_id == candidate.id,
                    PaperCurationJob.kind == "resolve-model-paper",
                )
                .count()
            )
            latest_resolution = (
                self.db.query(PaperCurationJob)
                .filter(
                    PaperCurationJob.candidate_id == candidate.id,
                    PaperCurationJob.kind == "resolve-model-paper",
                )
                .order_by(PaperCurationJob.created_at.desc())
                .first()
            )
            if (
                attempts < 3
                and summary["queued"] < max_queued
                and self._rejected_candidate_can_converge(candidate, latest_resolution)
            ):
                self.jobs.enqueue_resolution(
                    self.db,
                    candidate=candidate,
                    requested_by="hf-trending-cron-family-retry",
                    settings=self.settings,
                    dispatch=False,
                    commit=False,
                )
                summary["queued"] += 1
                summary["queued_candidate_ids"].append(str(candidate.id))

        models = self.discovery.list_top_models()
        summary["discovered"] = len(models)
        now = datetime.now(UTC)
        for model in models:
            candidate = (
                self.db.query(TrendingModelCandidate)
                .filter(TrendingModelCandidate.repo_id == model.repo_id)
                .one_or_none()
            )
            if is_obvious_conversion(model):
                if candidate is None:
                    candidate = TrendingModelCandidate(
                        repo_id=model.repo_id,
                        author=model.author,
                    )
                    self.db.add(candidate)
                candidate.status = "rejected"
                candidate.rejection_reason = (
                    "Deterministic format/quantization conversion"
                )
                candidate.featured_publisher = model.featured_publisher
                candidate.trending_score = model.trending_score
                candidate.last_seen_at = now
                candidate.processed_at = now
                summary["rejected_conversions"] += 1
                continue

            try:
                snapshot = self.cards.snapshot(model.repo_id)
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                summary["errors"].append(
                    {"repo_id": model.repo_id, "error": str(exc)[:500]}
                )
                continue
            if candidate is not None and not should_requeue_card(
                previous_sha=candidate.readme_sha,
                current_sha=snapshot.readme_sha,
            ):
                candidate.last_seen_at = now
                candidate.trending_score = model.trending_score
                attempts = (
                    self.db.query(PaperCurationJob)
                    .filter(
                        PaperCurationJob.candidate_id == candidate.id,
                        PaperCurationJob.kind == "resolve-model-paper",
                    )
                    .count()
                )
                latest_resolution = (
                    self.db.query(PaperCurationJob)
                    .filter(
                        PaperCurationJob.candidate_id == candidate.id,
                        PaperCurationJob.kind == "resolve-model-paper",
                    )
                    .order_by(PaperCurationJob.created_at.desc())
                    .first()
                )
                if (
                    candidate.status == "failed"
                    and attempts < 3
                    and summary["queued"] < max_queued
                ):
                    self.jobs.enqueue_resolution(
                        self.db,
                        candidate=candidate,
                        requested_by="hf-trending-cron-retry",
                        settings=self.settings,
                        dispatch=False,
                        commit=False,
                    )
                    summary["queued"] += 1
                    summary["queued_candidate_ids"].append(str(candidate.id))
                    continue
                if (
                    self._rejected_candidate_can_converge(candidate, latest_resolution)
                    and attempts < 3
                    and summary["queued"] < max_queued
                ):
                    self.jobs.enqueue_resolution(
                        self.db,
                        candidate=candidate,
                        requested_by="hf-trending-cron-family-retry",
                        settings=self.settings,
                        dispatch=False,
                        commit=False,
                    )
                    summary["queued"] += 1
                    summary["queued_candidate_ids"].append(str(candidate.id))
                    continue
                summary["unchanged"] += 1
                continue
            active = None
            if candidate is not None:
                active = (
                    self.db.query(PaperCurationJob)
                    .filter(
                        PaperCurationJob.candidate_id == candidate.id,
                        PaperCurationJob.kind == "resolve-model-paper",
                        PaperCurationJob.status.in_(
                            {"queued", "dispatching", "running"}
                        ),
                    )
                    .first()
                )
            if active is not None:
                # Do not move the pinned card revision underneath an active job.
                # The next hourly pass will observe and queue the new revision.
                candidate.last_seen_at = now
                candidate.trending_score = model.trending_score
                continue
            if summary["queued"] >= max_queued:
                continue
            if candidate is None:
                candidate = TrendingModelCandidate(
                    repo_id=model.repo_id,
                    author=model.author,
                )
                self.db.add(candidate)
            candidate.author = model.author
            candidate.readme_sha = snapshot.readme_sha
            candidate.readme_revision = snapshot.repo_revision
            candidate.status = "discovered"
            candidate.rejection_reason = None
            candidate.featured_publisher = model.featured_publisher
            candidate.trending_score = model.trending_score
            candidate.last_seen_at = now
            candidate.processed_at = None
            self.db.flush()

            self.jobs.enqueue_resolution(
                self.db,
                candidate=candidate,
                requested_by="hf-trending-cron",
                settings=self.settings,
                dispatch=False,
                commit=False,
            )
            summary["queued"] += 1
            summary["queued_candidate_ids"].append(str(candidate.id))

        if dry_run:
            self.db.rollback()
            summary["dry_run"] = True
            return summary
        self.db.commit()
        if dispatch:
            self.jobs.dispatch_next(self.db, self.settings)
        return summary
