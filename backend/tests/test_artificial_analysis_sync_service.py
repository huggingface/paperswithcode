"""Contract, paper-indexing, and idempotency tests for Artificial Analysis."""

import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import (
    Base,
    Dataset,
    Evaluation,
    Metric,
    HfArtifact,
    ModelProviderAlias,
    ModelRelease,
    ModelReleaseArtifact,
    Paper,
    PaperTask,
    Task,
    TaskDatasetMetric,
)
from backend.services import artificial_analysis_sync_service as aa


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


def _api_row(
    slug: str, intelligence: float | None = 42.5, agentic: float | None = 41.0
):
    evaluations = {}
    if intelligence is not None:
        evaluations["artificial_analysis_intelligence_index"] = intelligence
    if agentic is not None:
        evaluations["artificial_analysis_agentic_index"] = agentic
    return {
        "slug": slug,
        "name": slug.replace("-", " ").title(),
        "release_date": "2026-08-01",
        "evaluations": evaluations,
    }


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_fetches_every_api_page_and_validates_reviewed_models(monkeypatch):
    identity = aa.PaperIdentity(arxiv_id="2608.00001", is_open=True)
    monkeypatch.setattr(aa, "MODEL_PAPER_IDENTITIES", {"reviewed-model": identity})
    monkeypatch.setattr(
        aa,
        "INDEXES",
        (
            replace(
                aa.INTELLIGENCE_INDEX, min_expected_models=2, max_expected_models=10
            ),
            replace(aa.AGENTIC_INDEX, min_expected_models=1, max_expected_models=10),
        ),
    )
    pages = [
        {
            "intelligence_index_version": "4.1",
            "pagination": {"has_more": True, "total_pages": 2},
            "data": [_api_row("reviewed-model")],
        },
        {
            "intelligence_index_version": "4.1",
            "pagination": {"has_more": False, "total_pages": 2},
            "data": [_api_row("other-model", intelligence=12.3, agentic=None)],
        },
    ]

    class Client:
        def get(self, url, *, headers, params):
            assert url == aa.API_ENDPOINT
            assert headers == {"x-api-key": "secret"}
            assert params["page_size"] == 200
            return _Response(pages[params["page"] - 1])

    leaderboard = aa.fetch_artificial_analysis_leaderboard(
        api_key="secret", client=Client()
    )

    assert leaderboard.index_version == "4.1"
    assert [entry.slug for entry in leaderboard.entries] == [
        "reviewed-model",
        "other-model",
    ]
    assert leaderboard.entries[0].scores == {"intelligence": 42.5, "agentic": 41.0}
    assert leaderboard.entries[1].scores == {"intelligence": 12.3}


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
    session = Session(engine)
    language = Task(
        id=5, name="Language Modeling", slug=aa.INTELLIGENCE_INDEX.task_slug
    )
    agents = Task(id=14, name="Agents", slug=aa.AGENTIC_INDEX.task_slug)
    intelligence = Dataset(
        id=581, name="Artificial Analysis", slug=aa.INTELLIGENCE_INDEX.dataset_slug
    )
    agentic = Dataset(
        id=582, name="Artificial Analysis Agentic", slug=aa.AGENTIC_INDEX.dataset_slug
    )
    metric = Metric(id=1, name=aa.METRIC_NAME, direction="higher_is_better")
    session.add_all([language, agents, intelligence, agentic, metric])
    session.add_all(
        [
            TaskDatasetMetric(
                task_id=language.id, dataset_id=intelligence.id, metric_id=metric.id
            ),
            TaskDatasetMetric(
                task_id=agents.id, dataset_id=agentic.id, metric_id=metric.id
            ),
        ]
    )
    session.commit()
    return session


def test_discovery_resolves_new_model_through_shared_release_identity(monkeypatch):
    session = _session()
    Base.metadata.create_all(
        session.get_bind(),
        tables=[
            HfArtifact.__table__,
            ModelRelease.__table__,
            ModelReleaseArtifact.__table__,
            ModelProviderAlias.__table__,
        ],
    )
    paper = Paper(
        title="Qwen3.8 Report",
        source="external",
        source_url="https://qwen.ai/blog/qwen3.8",
        version="v1",
        is_latest_version=True,
    )
    session.add(paper)
    session.flush()
    release = ModelRelease(
        paper_id=paper.id,
        canonical_name="Qwen3.8 27B",
        publisher="Qwen",
        aliases=[],
        is_open=True,
    )
    session.add(release)
    session.flush()
    artifact = HfArtifact(
        repo_id="Qwen/Qwen3.8-27B",
        kind="model",
        url="https://huggingface.co/Qwen/Qwen3.8-27B",
    )
    session.add(artifact)
    session.flush()
    session.add(
        ModelReleaseArtifact(model_release_id=release.id, hf_artifact_id=artifact.id)
    )
    session.commit()
    monkeypatch.setattr(aa, "MODEL_PAPER_IDENTITIES", {})
    leaderboard = aa.ArtificialAnalysisLeaderboard(
        "4.1",
        [
            aa.ArtificialAnalysisEntry(
                "qwen3-8-27b",
                "Qwen3.8 27B",
                {"intelligence": 50.0},
                date(2026, 8, 1),
            )
        ],
    )

    result = asyncio.run(
        aa.ArtificialAnalysisPaperDiscoveryService(session).discover(
            leaderboard=leaderboard
        )
    )

    assert result.papers == {"qwen3-8-27b": paper.id}
    alias = session.query(ModelProviderAlias).one()
    assert (alias.provider, alias.alias, alias.model_release_id) == (
        "artificial-analysis",
        "qwen3-8-27b",
        release.id,
    )


def test_shared_release_identity_fails_closed_on_ambiguous_names():
    session = _session()
    Base.metadata.create_all(
        session.get_bind(),
        tables=[
            HfArtifact.__table__,
            ModelRelease.__table__,
            ModelReleaseArtifact.__table__,
            ModelProviderAlias.__table__,
        ],
    )
    for index in range(2):
        paper = Paper(
            title=f"Shared Model Report {index}",
            source="external",
            source_url=f"https://example.com/shared-{index}",
            version="v1",
            is_latest_version=True,
        )
        session.add(paper)
        session.flush()
        session.add(
            ModelRelease(
                paper_id=paper.id,
                canonical_name="Shared Model",
                publisher=f"org-{index}",
                aliases=[],
            )
        )
    session.commit()

    release = aa.ModelReleaseIdentityService(session).resolve(
        "artificial-analysis", "shared-model", name="Shared Model"
    )

    assert release is None
    assert session.query(ModelProviderAlias).count() == 0


def test_discovery_indexes_missing_arxiv_and_external_papers(monkeypatch):
    session = _session()
    identities = {
        "arxiv-model": aa.PaperIdentity(arxiv_id="2608.00001", is_open=True),
        "external-model": aa.external(
            "https://example.com/release", "External Model", "2026-08-01"
        ),
    }
    monkeypatch.setattr(aa, "MODEL_PAPER_IDENTITIES", identities)

    class Ingestion:
        async def get_or_import_arxiv_paper(self, arxiv_id):
            paper = Paper(
                title="Arxiv Model",
                arxiv_id=arxiv_id,
                source="arxiv",
                version="v1",
                is_latest_version=True,
            )
            session.add(paper)
            session.flush()
            return paper, True

    class External:
        def add_external_resource(self, payload):
            paper = Paper(
                title=payload.title,
                source="external",
                source_url=payload.source_url,
                date_published=payload.date_published,
                version="v1",
                is_latest_version=True,
            )
            session.add(paper)
            session.flush()
            return SimpleNamespace(paper=SimpleNamespace(id=paper.id))

    result = asyncio.run(
        aa.ArtificialAnalysisPaperDiscoveryService(
            session,
            ingestion_service=Ingestion(),
            external_service=External(),
        ).discover()
    )

    assert set(result.papers) == set(identities)
    assert result.indexed_papers == ["2608.00001", "https://example.com/release"]


def test_sync_adopts_existing_row_and_is_idempotent(monkeypatch):
    session = _session()
    paper = Paper(
        id=7,
        title="Reviewed Model",
        arxiv_id="2608.00001",
        source="arxiv",
        version="v1",
        is_latest_version=True,
    )
    session.add(paper)
    session.flush()
    source_url = f"{aa.SOURCE_URL_PREFIX}reviewed-model"
    session.add(
        Evaluation(
            paper_id=paper.id,
            task_id=5,
            dataset_id=581,
            model_name="Old label",
            metrics={aa.METRIC_NAME: 1.0},
            best_metric=aa.METRIC_NAME,
            external_source_url=source_url,
        )
    )
    session.commit()
    monkeypatch.setattr(
        aa,
        "MODEL_PAPER_IDENTITIES",
        {"reviewed-model": aa.PaperIdentity(arxiv_id="2608.00001", is_open=True)},
    )
    leaderboard = aa.ArtificialAnalysisLeaderboard(
        "4.1",
        [
            aa.ArtificialAnalysisEntry(
                "reviewed-model",
                "Reviewed Model (high)",
                {"intelligence": 42.5, "agentic": 39.0},
                date(2026, 8, 1),
            )
        ],
    )
    discovery = aa.ArtificialAnalysisDiscovery(papers={"reviewed-model": paper.id})
    now = datetime(2026, 8, 14, tzinfo=UTC)

    first = aa.ArtificialAnalysisSyncService(session).sync(
        leaderboard, discovery=discovery, fetched_at=now
    )
    second = aa.ArtificialAnalysisSyncService(session).sync(
        leaderboard, discovery=discovery, fetched_at=now
    )

    intelligence_row = (
        session.query(Evaluation).filter(Evaluation.dataset_id == 581).one()
    )
    agentic_row = session.query(Evaluation).filter(Evaluation.dataset_id == 582).one()
    assert first.indexes["intelligence"].updated == 1
    assert first.indexes["agentic"].created == 1
    assert second.indexes["intelligence"].updated == 1
    assert second.indexes["agentic"].updated == 1
    assert first.created == 1
    assert first.updated == 1
    assert intelligence_row.model_name == "Reviewed Model (high)"
    assert intelligence_row.metrics == {aa.METRIC_NAME: 42.5}
    assert intelligence_row.task_id == 5
    assert agentic_row.metrics == {aa.METRIC_NAME: 39.0}
    assert agentic_row.task_id == 14
    assert intelligence_row.is_open is True
    assert intelligence_row.source_url == source_url
    assert {row.task_id for row in session.query(PaperTask).all()} == {5, 14}
