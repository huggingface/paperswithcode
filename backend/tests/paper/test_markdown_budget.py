from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from backend.services.paper_markdown_job_profile import (
    PAPER_MARKDOWN_BACKFILL_JOB_PROFILE,
    PAPER_MARKDOWN_LIVE_JOB_PROFILE,
    paper_markdown_job_profile,
)
from backend.services.paper_markdown_budget_service import (
    paper_markdown_budget_decision,
    paper_markdown_budget_snapshot,
)


def _job(
    *,
    mode: str,
    created_at: datetime,
    stage: str = "COMPLETED",
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    profile_id: str | None = None,
):
    labels = {"mode": mode}
    if profile_id:
        labels["profile_id"] = profile_id
    return SimpleNamespace(
        labels=labels,
        created_at=created_at,
        status=SimpleNamespace(stage=stage),
        started_at=started_at,
        finished_at=finished_at,
    )


def test_live_budget_separates_spend_reservations_and_next_launch():
    now = datetime(2026, 8, 17, 12, tzinfo=UTC)
    completed = _job(
        mode="live",
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        started_at=datetime(2026, 8, 1, 1, tzinfo=UTC),
        finished_at=datetime(2026, 8, 1, 3, tzinfo=UTC),
    )
    active = _job(
        mode="live",
        created_at=datetime(2026, 8, 10, tzinfo=UTC),
        stage="RUNNING",
        started_at=datetime(2026, 8, 10, 1, tzinfo=UTC),
    )
    expired = _job(
        mode="live",
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )

    budget = paper_markdown_budget_snapshot(
        [completed, active, expired],
        mode="live",
        ceiling_usd=40,
        planned_jobs=1,
        now=now,
    )

    assert budget["spent_usd"] == 3.6
    assert budget["active_reserved_usd"] == 21.6
    assert budget["current_exposure_usd"] == 25.2
    assert budget["desired_jobs"] == 1
    assert budget["affordable_jobs"] == 1
    assert budget["planned_reserved_usd"] == 12.6
    assert budget["projected_usd"] == 37.8
    assert budget["can_launch_planned"] is True
    assert budget["next_release_at"] == "2026-08-31T00:00:00Z"
    assert budget["next_release_usd"] == 3.6
    assert budget["relevant_jobs"] == 2


def test_budget_decision_admits_largest_affordable_prefix_and_exact_boundary():
    partial = paper_markdown_budget_decision(
        desired_jobs=4,
        current_exposure_usd=678.42,
        ceiling_usd=750,
        reservation_per_job_usd=21.60,
    )
    assert partial.affordable_jobs == 3
    assert partial.planned_reservation_usd == 64.8
    assert partial.projected_exposure_usd == 743.22

    exact = paper_markdown_budget_decision(
        desired_jobs=1,
        current_exposure_usd=728.40,
        ceiling_usd=750,
        reservation_per_job_usd=21.60,
    )
    assert exact.affordable_jobs == 1
    assert exact.projected_exposure_usd == 750

    zero = paper_markdown_budget_decision(
        desired_jobs=1,
        current_exposure_usd=728.41,
        ceiling_usd=750,
        reservation_per_job_usd=21.60,
    )
    assert zero.affordable_jobs == 0
    assert zero.reason == "no shard fits within remaining budget"

    exact_cent = paper_markdown_budget_decision(
        desired_jobs=1,
        current_exposure_usd=87.40,
        ceiling_usd=100,
        reservation_per_job_usd=12.60,
    )
    one_cent_short = paper_markdown_budget_decision(
        desired_jobs=1,
        current_exposure_usd=87.41,
        ceiling_usd=100,
        reservation_per_job_usd=12.60,
    )
    assert exact_cent.affordable_jobs == 1
    assert exact_cent.projected_exposure_usd == 100
    assert one_cent_short.affordable_jobs == 0


def test_budget_mode_isolation_excludes_other_lane_reservations():
    now = datetime(2026, 8, 17, tzinfo=UTC)
    live = _job(mode="live", created_at=now, stage="RUNNING")
    backfill = _job(mode="backfill", created_at=now, stage="RUNNING")
    budget = paper_markdown_budget_snapshot(
        [live, backfill], mode="live", ceiling_usd=100, planned_jobs=1, now=now
    )
    assert budget["relevant_jobs"] == 1
    assert budget["active_reserved_usd"] == 21.6


def test_backfill_budget_is_all_history_and_fails_closed_without_timing():
    old_terminal = _job(
        mode="backfill",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        stage="ERROR",
    )

    budget = paper_markdown_budget_snapshot(
        [old_terminal],
        mode="backfill",
        ceiling_usd=750,
        planned_jobs=1,
        now=datetime(2026, 8, 17, tzinfo=UTC),
    )

    assert budget["window"] == "all_history"
    assert budget["next_release_at"] is None
    assert budget["spent_usd"] == 21.6
    assert budget["unknown_terminal_reservation_count"] == 1
    assert budget["unknown_terminal_reservation_usd"] == 21.6
    assert budget["projected_usd"] == 34.2
    assert budget["next_admission_at"] is None


def test_measured_profiles_share_launch_and_reservation_contract():
    assert paper_markdown_job_profile("live") is PAPER_MARKDOWN_LIVE_JOB_PROFILE
    assert paper_markdown_job_profile("backfill") is PAPER_MARKDOWN_BACKFILL_JOB_PROFILE
    for profile, concurrency in (
        (PAPER_MARKDOWN_LIVE_JOB_PROFILE, 1),
        (PAPER_MARKDOWN_BACKFILL_JOB_PROFILE, 4),
    ):
        assert profile.max_papers == 100
        assert profile.hard_timeout_seconds == 7 * 3600
        assert profile.hard_timeout == "7h"
        assert profile.soft_deadline_seconds == int(6.5 * 3600)
        assert profile.concurrency == concurrency
        assert profile.reservation_hours == 7
        assert profile.reservation_per_job_usd == 12.6
        assert profile.as_dict()["reservation_per_job_usd"] == 12.6


def test_recovery_profile_fits_current_live_and_backfill_headrooms():
    for headroom in (13.27, 19.07):
        decision = paper_markdown_budget_decision(
            desired_jobs=1,
            current_exposure_usd=100 - headroom,
            ceiling_usd=100,
            reservation_per_job_usd=(
                PAPER_MARKDOWN_LIVE_JOB_PROFILE.reservation_per_job_usd
            ),
        )
        assert decision.affordable_jobs == 1
        assert decision.planned_reservation_usd == 12.6


def test_profile_labeled_active_job_uses_measured_hard_timeout():
    now = datetime(2026, 8, 17, tzinfo=UTC)
    active = _job(
        mode="live",
        created_at=now,
        stage="RUNNING",
        profile_id=PAPER_MARKDOWN_LIVE_JOB_PROFILE.profile_id,
    )

    budget = paper_markdown_budget_snapshot(
        [active], mode="live", ceiling_usd=100, planned_jobs=1, now=now
    )

    assert budget["active_reserved_usd"] == 12.6
    assert budget["reservation_per_job_usd"] == 12.6
    assert budget["planned_reserved_usd"] == 12.6
    assert budget["profile"] == PAPER_MARKDOWN_LIVE_JOB_PROFILE.as_dict()


def test_next_admission_uses_cumulative_live_releases():
    now = datetime(2026, 8, 17, tzinfo=UTC)
    jobs = [
        _job(
            mode="live",
            created_at=datetime(2026, 7, 20, tzinfo=UTC),
            stage="RUNNING",
            profile_id=PAPER_MARKDOWN_LIVE_JOB_PROFILE.profile_id,
        ),
        _job(
            mode="live",
            created_at=datetime(2026, 7, 21, tzinfo=UTC),
            stage="RUNNING",
            profile_id=PAPER_MARKDOWN_LIVE_JOB_PROFILE.profile_id,
        ),
    ]
    budget = paper_markdown_budget_snapshot(
        jobs, mode="live", ceiling_usd=20, planned_jobs=1, now=now
    )

    assert budget["current_exposure_usd"] == 25.2
    assert budget["next_release_at"] == "2026-08-19T00:00:00Z"
    assert budget["next_admission_at"] == "2026-08-20T00:00:00Z"

    available = paper_markdown_budget_snapshot(
        jobs[:1], mode="live", ceiling_usd=100, planned_jobs=0, now=now
    )
    assert available["next_admission_at"] is None


def test_unmetered_hf_policy_admits_every_requested_shard():
    now = datetime(2026, 8, 24, tzinfo=UTC)
    historical = _job(
        mode="backfill",
        created_at=now,
        stage="COMPLETED",
        started_at=now,
        finished_at=now,
    )

    budget = paper_markdown_budget_snapshot(
        [historical],
        mode="backfill",
        ceiling_usd=1,
        planned_jobs=4,
        now=now,
        cost_policy="unmetered_hf",
    )

    assert budget["cost_policy"] == "unmetered_hf"
    assert budget["desired_jobs"] == 4
    assert budget["affordable_jobs"] == 4
    assert budget["budget_enforced"] is False
    assert budget["next_admission_at"] is None
