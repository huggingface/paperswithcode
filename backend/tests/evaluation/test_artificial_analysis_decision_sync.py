"""Contract and idempotency tests for the Artificial Analysis Decision Index sync."""

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import (
    Base,
    Dataset,
    Evaluation,
    Metric,
    Paper,
    PaperTask,
    Task,
    TaskDatasetMetric,
)
from backend.services import artificial_analysis_decision_sync_service as decision
from backend.services import artificial_analysis_sync_service as aa
from backend.services.leaderboard_model_matching_service import MatchedModel


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


REVIEWED = {
    "lab_model-a": aa.PaperIdentity(arxiv_id="2611.00001", is_open=True),
    "lab_chat-model": aa.PaperIdentity(arxiv_id="2611.00002"),
    "lab_chat-model-low": aa.PaperIdentity(arxiv_id="2611.00002"),
}


def _contestant(slug, name, score, kind="decisionModel", lab="Example Lab"):
    return {
        "slug": slug,
        "kind": kind,
        "isDefault": True,
        "name": name,
        "creatorName": lab,
        "indexScore": score,
        "scores": {"hleDecisionScore": 50.0},
    }


def _contestants(extra: int = 10) -> list[dict]:
    return [
        _contestant("lab_model-a", "Model A", 72.5),
        _contestant("lab_chat-model", "Chat Model (Max)", 76.0, kind="llm"),
        _contestant("lab_chat-model-low", "Chat Model (Low)", 67.0, kind="llm"),
        *[_contestant(f"lab_other-{i}", f"Other {i}", 60.0 + i) for i in range(extra)],
    ]


def _page(contestants: list[dict], version: str = "v2.1") -> str:
    chunks = [
        '0:{"decisionIndex":{"slug":"artificial-analysis-decision-index",'
        f'"name":"Artificial Analysis Decision Index {version}"}}}}\n',
        "1:" + json.dumps({"contestants": contestants}),
    ]
    scripts = "".join(
        f"<script>self.__next_f.push({json.dumps([1, chunk])})</script>"
        for chunk in chunks
    )
    return f"<html><body>{scripts}</body></html>"


@pytest.fixture(autouse=True)
def _reviewed(monkeypatch):
    monkeypatch.setattr(decision, "MODEL_PAPER_IDENTITIES", REVIEWED)


def test_parse_reads_headline_scores_and_model_pages():
    leaderboard = decision.parse_decision_index_leaderboard(_page(_contestants()))

    assert leaderboard.version == "v2.1"
    assert len(leaderboard.entries) == 13
    first, chat = leaderboard.entries[:2]
    assert (first.name, first.lab, first.score) == ("Model A", "Example Lab", 72.5)
    assert first.source_url == "https://artificialanalysis.ai/decision-models/model-a"
    assert chat.source_url == "https://artificialanalysis.ai/models/chat-model"


def test_parse_refuses_another_index_version():
    with pytest.raises(ValueError, match="v2.2, not v2.1"):
        decision.parse_decision_index_leaderboard(_page(_contestants(), version="v2.2"))


def test_parse_refuses_missing_reviewed_model():
    contestants = [c for c in _contestants() if c["slug"] != "lab_model-a"]
    contestants.append(_contestant("lab_spare", "Spare", 50.0))
    with pytest.raises(ValueError, match="missing reviewed models: lab_model-a"):
        decision.parse_decision_index_leaderboard(_page(contestants))


def test_parse_refuses_a_truncated_board():
    with pytest.raises(ValueError, match="decision models"):
        decision.parse_decision_index_leaderboard(_page(_contestants(extra=3)))


def test_parse_refuses_invalid_scores():
    contestants = _contestants()
    contestants[0]["indexScore"] = None
    with pytest.raises(TypeError, match="score is invalid: lab_model-a"):
        decision.parse_decision_index_leaderboard(_page(contestants))


class _FakeMatcher:
    matches: dict[str, MatchedModel] = {}
    reported: list[str] = []

    def __init__(self, *_args, **_kwargs):
        pass

    def match(self, models):
        return {m.name: self.matches[m.name] for m in models if m.name in self.matches}

    def report_unmatched(self, models, *, now=None):
        type(self).reported = [m.name for m in models]
        return type(self).reported


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Task.__table__,
            Dataset.__table__,
            Metric.__table__,
            TaskDatasetMetric.__table__,
            Evaluation.__table__,
            PaperTask.__table__,
        ],
    )
    session = Session(engine, autoflush=False)
    task = Task(id=31, name="Decision Making", slug=decision.TASK_SLUG)
    dataset = Dataset(id=3_354, name="AA Decision Index", slug=decision.DATASET_SLUG)
    metric = Metric(id=5, name=decision.METRIC_NAME, direction="higher_is_better")
    papers = [
        Paper(
            id=paper_id,
            title=f"Paper {paper_id}",
            source="arxiv",
            arxiv_id=f"2611.0000{paper_id}",
            version="v1",
            is_latest_version=True,
        )
        for paper_id in (1, 2, 3)
    ]
    session.add_all([task, dataset, metric, *papers])
    session.add(
        TaskDatasetMetric(task_id=task.id, dataset_id=dataset.id, metric_id=metric.id)
    )
    session.commit()
    return session


def test_sync_binds_collapses_retires_and_reports(monkeypatch):
    session = _session()
    monkeypatch.setattr(decision, "LeaderboardModelMatcher", _FakeMatcher)
    _FakeMatcher.matches = {"Other 1": MatchedModel(3, "Other 1", True)}
    prefix = "https://artificialanalysis.ai/"
    session.add_all(
        [
            # Owned row for a contestant the page no longer lists.
            Evaluation(
                paper_id=1,
                task_id=31,
                dataset_id=3_354,
                model_name="Withdrawn",
                metrics={"Score": 1.0},
                best_metric="Score",
                external_source_url=f"{prefix}decision-models/withdrawn",
                methodology=decision.MANAGED_METHODOLOGY_PREFIX,
            ),
            Evaluation(
                paper_id=1,
                task_id=31,
                dataset_id=3_354,
                model_name="Manual result",
                metrics={"Score": 2.0},
                best_metric="Score",
            ),
        ]
    )
    session.commit()
    leaderboard = decision.parse_decision_index_leaderboard(_page(_contestants()))
    discovery = aa.ArtificialAnalysisDiscovery(
        papers={"lab_model-a": 1, "lab_chat-model": 2, "lab_chat-model-low": 2}
    )
    now = datetime(2026, 11, 12, 12, 35, tzinfo=UTC)

    first = decision.DecisionIndexSyncService(session).sync(
        leaderboard, discovery=discovery, fetched_at=now
    )
    second = decision.DecisionIndexSyncService(session).sync(
        leaderboard, discovery=discovery, fetched_at=now
    )

    assert (first.created, first.updated, first.retired) == (3, 0, 1)
    assert (second.created, second.updated, second.retired) == (0, 3, 0)
    assert first.collapsed == ["Chat Model (Low)"]
    assert first.auto_matched == ["Other 1"]
    assert "Other 0" in _FakeMatcher.reported
    assert "Other 1" not in _FakeMatcher.reported
    rows = {
        row.model_name: row
        for row in session.query(Evaluation).filter(Evaluation.dataset_id == 3_354)
    }
    assert set(rows) == {"Model A", "Chat Model (Max)", "Other 1", "Manual result"}
    assert rows["Model A"].metrics == {"Score": 72.5}
    assert rows["Model A"].is_open is True
    assert rows["Chat Model (Max)"].is_open is False
    assert rows["Chat Model (Max)"].source_url == f"{prefix}models/chat-model"
    assert rows["Other 1"].paper_id == 3
    assert "Decision Index v2.1 headline score" in rows["Model A"].methodology
    assert rows["Manual result"].methodology is None
    assert {tag.paper_id for tag in session.query(PaperTask)} == {1, 2, 3}


def test_sync_requires_reviewed_papers_when_committing(monkeypatch):
    session = _session()
    monkeypatch.setattr(decision, "LeaderboardModelMatcher", _FakeMatcher)
    _FakeMatcher.matches = {}
    leaderboard = decision.parse_decision_index_leaderboard(_page(_contestants()))

    with pytest.raises(RuntimeError, match="lab_model-a"):
        decision.DecisionIndexSyncService(session).sync(
            leaderboard, discovery=aa.ArtificialAnalysisDiscovery()
        )
    dry = decision.DecisionIndexSyncService(session).sync(
        leaderboard, discovery=aa.ArtificialAnalysisDiscovery(), commit=False
    )
    assert dry.matched == 0
    assert session.query(Evaluation).count() == 0


def test_sync_keeps_an_earlier_binding_when_rematch_misses(monkeypatch):
    session = _session()
    monkeypatch.setattr(decision, "LeaderboardModelMatcher", _FakeMatcher)
    _FakeMatcher.matches = {"Other 1": MatchedModel(3, "Other 1", True)}
    leaderboard = decision.parse_decision_index_leaderboard(_page(_contestants()))
    discovery = aa.ArtificialAnalysisDiscovery(
        papers={"lab_model-a": 1, "lab_chat-model": 2, "lab_chat-model-low": 2}
    )
    decision.DecisionIndexSyncService(session).sync(leaderboard, discovery=discovery)
    _FakeMatcher.matches = {}

    stats = decision.DecisionIndexSyncService(session).sync(
        leaderboard, discovery=discovery
    )

    assert stats.retired == 0
    assert "Other 1" not in stats.unreviewed
    assert "Other 1" not in _FakeMatcher.reported
    row = session.query(Evaluation).filter(Evaluation.model_name == "Other 1").one()
    assert (row.paper_id, row.is_open) == (3, True)
