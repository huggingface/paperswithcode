"""Scheduled usage thresholds, deferred bootstrap bundles, and dispatch pauses."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.services.codex_add_evals_service import (
    CodexPaperJobService,
)
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
)


def test_scheduled_usage_snapshot_exposes_enforced_threshold(monkeypatch):
    from backend.services import codex_add_evals_service

    now = datetime(2026, 8, 18, 12, tzinfo=UTC)
    monkeypatch.setattr(codex_add_evals_service, "_now", lambda: now)
    rows = [
        SimpleNamespace(
            finished_at=now,
            input_tokens=400,
            output_tokens=200,
        )
    ] + [
        SimpleNamespace(
            finished_at=now - codex_add_evals_service.timedelta(days=offset),
            input_tokens=80,
            output_tokens=20,
        )
        for offset in range(1, 8)
    ]

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return rows

    class Database:
        def query(self, *_args):
            return Query()

    snapshot = CodexPaperJobService._scheduled_usage_snapshot(
        Database(),
        SimpleNamespace(
            first_enabled_at=now - codex_add_evals_service.timedelta(days=8)
        ),
    )

    assert snapshot == {
        "mode": "enforced",
        "current_day_tokens": 600,
        "trailing_seven_day_median_tokens": 100,
        "positive_baseline_days": 7,
        "pause_threshold_tokens": 200,
    }


def test_scheduled_usage_filters_for_completed_jobs(monkeypatch):
    from backend.services import codex_add_evals_service

    now = datetime(2026, 8, 18, 12, tzinfo=UTC)
    monkeypatch.setattr(codex_add_evals_service, "_now", lambda: now)
    filters = []
    selected = []

    class Query:
        def filter(self, *predicates):
            filters.extend(str(predicate) for predicate in predicates)
            return self

        def all(self):
            return []

    class Database:
        def query(self, *entities):
            selected.extend(entity.key for entity in entities)
            return Query()

    CodexPaperJobService._scheduled_usage_snapshot(Database(), None)

    assert any("paper_curation_jobs.status" in predicate for predicate in filters)
    # Summing tokens must not load whole job rows.
    assert selected == ["finished_at", "input_tokens", "output_tokens"]


@pytest.mark.parametrize(
    ("daily_tokens", "mode", "median_tokens", "threshold"),
    [
        ([100, 300], "baseline_alert_only", 200, None),
        ([100, 300, 500], "enforced", 300, 600),
    ],
)
def test_scheduled_usage_excludes_zero_days_and_requires_three_positive_days(
    monkeypatch, daily_tokens, mode, median_tokens, threshold
):
    from backend.services import codex_add_evals_service

    now = datetime(2026, 8, 18, 12, tzinfo=UTC)
    monkeypatch.setattr(codex_add_evals_service, "_now", lambda: now)
    rows = [
        SimpleNamespace(
            finished_at=now - codex_add_evals_service.timedelta(days=offset),
            input_tokens=tokens,
            output_tokens=0,
        )
        for offset, tokens in enumerate(daily_tokens, start=1)
    ]

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return rows

    class Database:
        def query(self, *_args):
            return Query()

    snapshot = CodexPaperJobService._scheduled_usage_snapshot(
        Database(),
        SimpleNamespace(
            first_enabled_at=now - codex_add_evals_service.timedelta(days=30)
        ),
    )

    assert snapshot == {
        "mode": mode,
        "current_day_tokens": 0,
        "trailing_seven_day_median_tokens": median_tokens,
        "positive_baseline_days": len(daily_tokens),
        "pause_threshold_tokens": threshold,
    }


def test_cross_job_callback_token_cancels_only_the_token_owner(monkeypatch):
    from types import SimpleNamespace

    from backend.routers import codex_curation_callbacks

    added = []
    canceled = []

    class Database:
        def get(self, *_args):
            return None

        def add(self, value):
            added.append(value)

        def commit(self):
            pass

    owner = SimpleNamespace(id=uuid.uuid4(), error=None, callback_token_hash="h")
    monkeypatch.setattr(
        codex_curation_callbacks.codex_paper_job_service,
        "authenticate",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        codex_curation_callbacks.codex_paper_job_service,
        "token_owner_for_other_job",
        lambda *_args: owner,
    )
    monkeypatch.setattr(
        codex_curation_callbacks.codex_paper_job_service,
        "cancel",
        lambda _db, row, _settings: canceled.append(row),
    )

    with pytest.raises(HTTPException) as error:
        codex_curation_callbacks._callback_job(
            uuid.uuid4(), "Bearer valid-for-another-job", Database()
        )

    assert error.value.status_code == 401
    # The offending job is stopped; the global scheduler is never paused.
    assert canceled == [owner]
    assert owner.error == "Callback token was presented for another job"
    assert added == []


def test_cross_job_token_is_revoked_even_if_cancel_fails(monkeypatch):
    from types import SimpleNamespace

    from backend.routers import codex_curation_callbacks

    commits = []

    class Database:
        def commit(self):
            commits.append(owner.callback_token_hash)

    owner = SimpleNamespace(id=uuid.uuid4(), error=None, callback_token_hash="h")
    service = codex_curation_callbacks.codex_paper_job_service
    monkeypatch.setattr(service, "authenticate", lambda *_args: None)
    monkeypatch.setattr(service, "token_owner_for_other_job", lambda *_args: owner)

    def remote_failure(*_args):
        raise RuntimeError("Hugging Face unavailable")

    monkeypatch.setattr(service, "cancel", remote_failure)

    with pytest.raises(RuntimeError):
        codex_curation_callbacks._callback_job(
            uuid.uuid4(), "Bearer valid-for-another-job", Database()
        )

    # The revocation was committed before the remote cancel was attempted.
    assert commits == [None]


@pytest.mark.parametrize(
    ("scale", "value"),
    [("0-1", 1.01), ("0-100", 100.01), ("0-1000", 1000.01)],
)
def test_metric_scale_guard_rejects_out_of_range_values(scale, value):
    with pytest.raises(ValueError, match="outside configured scale"):
        CodexCurationCallbackService._validate_metric_scale(scale, value)
