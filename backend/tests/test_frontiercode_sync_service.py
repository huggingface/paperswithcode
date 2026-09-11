"""Validation and idempotency tests for the FrontierCode live sync."""

import asyncio
from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import (
    Base,
    Dataset,
    Evaluation,
    HfArtifact,
    Metric,
    Paper,
    PaperHfArtifact,
    PaperProjectPage,
    PaperRepository,
    PaperTask,
    ProjectPage,
    Repository,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services import frontiercode_sync_service as fc
from backend.services.frontiercode_sync_service import (
    FRONTIERCODE_ENDPOINT,
    FRONTIERCODE_SOURCE_URL,
    MANAGED_METHODOLOGY_PREFIX,
    FrontierCodeDiscovery,
    FrontierCodePaperDiscoveryService,
    FrontierCodeSyncService,
    fetch_frontiercode_leaderboard,
    parse_frontiercode_leaderboard,
    select_best_entries,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


def _payload() -> dict:
    models = [f"Model {index}" for index in range(20)]
    return {
        "v1": {},
        "v1_1": {
            "models": models,
            "colors": {},
            "lab_colors": {},
            "harness": {model: "mini-swe-agent" for model in models},
            "efforts": {model: ["low", "high"] for model in models},
            "subsets": {"main": 100, "extended": 150},
            "data": {
                model: {
                    "low": {
                        "main": {"new_score": 0.30, "correct": 0.35},
                        "extended": {"new_score": 0.40, "correct": 0.45},
                    },
                    "high": {
                        "main": {"new_score": 0.50, "correct": 0.55},
                        "extended": {"new_score": 0.35, "correct": 0.40},
                    },
                }
                for model in models
            },
        },
    }


@pytest.fixture(autouse=True)
def _reviewed_test_models(monkeypatch):
    monkeypatch.setattr(
        fc,
        "MODEL_PAPER_IDENTITIES",
        {
            f"Model {index}": fc.PaperIdentity(
                arxiv_id=f"2608.{index:05d}", is_open=index % 2 == 0
            )
            for index in range(20)
        },
    )


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Repository.__table__,
            PaperRepository.__table__,
            HfArtifact.__table__,
            PaperHfArtifact.__table__,
            ProjectPage.__table__,
            PaperProjectPage.__table__,
            Task.__table__,
            Dataset.__table__,
            Metric.__table__,
            TaskDataset.__table__,
            TaskDatasetMetric.__table__,
            Evaluation.__table__,
            PaperTask.__table__,
        ],
    )
    session = Session(engine)
    task = Task(id=15, name="Coding Agents", slug="coding-agents")
    main = Dataset(id=726, name="FrontierCode 1.1 Main", slug="frontiercode-main")
    extended = Dataset(
        id=727, name="FrontierCode 1.1 Extended", slug="frontiercode-extended"
    )
    score = Metric(id=94, name="Score", direction="higher_is_better")
    pass_rate = Metric(id=250, name="Pass Rate", direction="higher_is_better")
    session.add_all([task, main, extended, score, pass_rate])
    for dataset in (main, extended):
        session.add(
            TaskDataset(task_id=task.id, dataset_id=dataset.id, supports_harness=True)
        )
        for metric in (score, pass_rate):
            session.add(
                TaskDatasetMetric(
                    task_id=task.id,
                    dataset_id=dataset.id,
                    metric_id=metric.id,
                )
            )
    session.add(
        Paper(
            id=98109,
            title="Introducing FrontierCode",
            source="external",
            source_url="https://cognition.com/blog/frontier-code",
            version="v1",
            is_latest_version=True,
        )
    )
    session.add_all(
        [
            Paper(
                id=1000 + index,
                title=f"Model {index}",
                arxiv_id=f"2608.{index:05d}",
                source="arxiv",
                version="v1",
                is_latest_version=True,
            )
            for index in range(20)
        ]
    )
    session.commit()
    return session


def _discovery() -> FrontierCodeDiscovery:
    return FrontierCodeDiscovery(
        papers={f"Model {index}": 1000 + index for index in range(20)}
    )


def test_parse_fetch_and_select_best_reasoning_effort_per_subset():
    payload = _payload()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == FRONTIERCODE_ENDPOINT
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        leaderboard = fetch_frontiercode_leaderboard(client)

    assert len(leaderboard.entries) == 80
    selected = select_best_entries(leaderboard.entries)
    assert len(selected) == 40
    model_zero = [entry for entry in selected if entry.model == "Model 0"]
    assert {(entry.subset, entry.effort) for entry in model_zero} == {
        ("main", "high"),
        ("extended", "low"),
    }


def test_parser_rejects_truncated_or_changed_upstream_data():
    payload = _payload()
    payload["v1_1"]["models"] = payload["v1_1"]["models"][:10]
    with pytest.raises(ValueError, match="returned 10 models"):
        parse_frontiercode_leaderboard(payload)

    payload = _payload()
    payload["v1_1"]["subsets"]["main"] = 99
    with pytest.raises(ValueError, match="subset sizes changed"):
        parse_frontiercode_leaderboard(payload)

    payload = _payload()
    payload["v1_1"]["data"]["Model 0"]["high"]["main"]["new_score"] = 1.1
    with pytest.raises(ValueError, match="outside 0-1"):
        parse_frontiercode_leaderboard(payload)


def test_sync_attributes_rows_to_model_papers_and_is_idempotent():
    session = _session()
    leaderboard = parse_frontiercode_leaderboard(_payload())

    first = FrontierCodeSyncService(session).sync(leaderboard, discovery=_discovery())
    assert first.created == 40
    assert first.updated == 0
    assert session.query(Evaluation).count() == 40
    main_row = (
        session.query(Evaluation)
        .filter(Evaluation.model_name == "Model 0", Evaluation.dataset_id == 726)
        .one()
    )
    assert main_row.paper_id == 1000
    assert main_row.metrics == {"Score": 50.0, "Pass Rate": 55.0}
    assert main_row.harness == "MiniSWE-Agent"
    assert main_row.external_source_url == FRONTIERCODE_SOURCE_URL
    assert main_row.methodology.startswith(MANAGED_METHODOLOGY_PREFIX)
    assert main_row.is_open is True
    assert session.query(Evaluation).filter(Evaluation.paper_id == 98109).count() == 0
    assert session.query(PaperTask).count() == 20

    second = FrontierCodeSyncService(session).sync(leaderboard, discovery=_discovery())
    assert second.created == 0
    assert second.updated == 40
    assert session.query(Evaluation).count() == 40


def test_sync_deletes_only_disappeared_managed_rows():
    session = _session()
    session.add_all(
        [
            Evaluation(
                paper_id=98109,
                task_id=15,
                dataset_id=726,
                model_name="Gone Model",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} subset=main; old.",
                metrics={"Score": 10, "Pass Rate": 10},
                best_metric="Score",
                external_source_url=FRONTIERCODE_SOURCE_URL,
            ),
            Evaluation(
                paper_id=98109,
                task_id=15,
                dataset_id=726,
                model_name="Manual Model",
                methodology="Human curated.",
                metrics={"Score": 10, "Pass Rate": 10},
                best_metric="Score",
                external_source_url=FRONTIERCODE_SOURCE_URL,
            ),
        ]
    )
    session.commit()

    stats = FrontierCodeSyncService(session).sync(
        parse_frontiercode_leaderboard(_payload()), discovery=_discovery()
    )
    assert stats.deleted == 1
    names = {row.model_name for row in session.query(Evaluation).all()}
    assert "Gone Model" not in names
    assert "Manual Model" in names


def test_dry_run_rolls_back_all_changes():
    session = _session()
    leaderboard = parse_frontiercode_leaderboard(_payload())

    stats = FrontierCodeSyncService(session).sync(
        leaderboard, discovery=_discovery(), commit=False
    )

    assert stats.created == 40
    assert session.query(Evaluation).count() == 0


def test_parser_rejects_unreviewed_model(monkeypatch):
    identities = dict(fc.MODEL_PAPER_IDENTITIES)
    identities.pop("Model 19")
    monkeypatch.setattr(fc, "MODEL_PAPER_IDENTITIES", identities)

    with pytest.raises(ValueError, match="unreviewed=.*Model 19"):
        parse_frontiercode_leaderboard(_payload())


def test_parser_accepts_reviewed_swe_2_release(monkeypatch):
    monkeypatch.undo()  # Exercise the real reviewed identities, not test models.
    revision = _payload()["v1_1"]
    models = list(dict.fromkeys([*fc.MODEL_PAPER_IDENTITIES, "SWE-2"]))
    for field in ("harness", "efforts", "data"):
        example = revision[field]["Model 0"]
        revision[field] = {model: example for model in models}
    revision["models"] = models

    leaderboard = parse_frontiercode_leaderboard({"v1_1": revision})
    assert len([entry for entry in leaderboard.entries if entry.model == "SWE-2"]) == 4
    identity = fc.MODEL_PAPER_IDENTITIES["SWE-2"]
    assert identity.source_url == "https://cognition.com/blog/swe-2"
    assert identity.title == "Introducing SWE-2: Pushing the Pareto Frontier"
    assert identity.date_published == date(2026, 9, 10)
    assert identity.arxiv_id is None
    assert identity.is_open is False

    revision["models"].remove("SWE-2")
    with pytest.raises(ValueError, match="missing=.*SWE-2"):
        parse_frontiercode_leaderboard({"v1_1": revision})


def test_discovery_indexes_missing_external_paper(monkeypatch):
    session = _session()
    identity = fc.external("https://example.com/model", "External Model", "2026-08-01")
    monkeypatch.setattr(fc, "MODEL_PAPER_IDENTITIES", {"External Model": identity})

    class External:
        def add_external_resource(self, payload):
            paper = Paper(
                title=payload.title,
                source="external",
                source_url=payload.source_url,
                date_published=date(2026, 8, 1),
                version="v1",
                is_latest_version=True,
            )
            session.add(paper)
            session.flush()
            return SimpleNamespace(paper=SimpleNamespace(id=paper.id))

    result = asyncio.run(
        FrontierCodePaperDiscoveryService(
            session, external_service=External()
        ).discover()
    )

    assert result.papers["External Model"]
    assert result.indexed_papers == ["https://example.com/model"]
