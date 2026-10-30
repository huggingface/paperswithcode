"""Contract, paper-indexing, and idempotency tests for Artificial Analysis."""

import asyncio
import pytest
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
        self.headers = {"x-ratelimit-remaining": "99", "x-ratelimit-limit": "100"}

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
            "data": [
                _api_row("reviewed-model"),
                _api_row("other-model", intelligence=12.3, agentic=None),
            ],
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
    assert (leaderboard.quota_remaining, leaderboard.quota_limit) == ("99", "100")


@pytest.mark.parametrize(
    "changed",
    [
        {"name": "Different model"},
        {"release_date": "2026-08-02"},
        {"evaluations": {"artificial_analysis_intelligence_index": 1.0}},
    ],
)
def test_rejects_conflicting_duplicate_models(changed):
    first = _api_row("duplicate-model")

    class Client:
        def get(self, *args, **kwargs):
            return _Response(
                {
                    "intelligence_index_version": "4.1",
                    "pagination": {"has_more": False, "total_pages": 1},
                    "data": [first, {**first, **changed}],
                }
            )

    with pytest.raises(ValueError, match="conflicting model slug: duplicate-model"):
        aa.fetch_artificial_analysis_leaderboard(api_key="secret", client=Client())


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


def test_reviewed_model_can_have_no_agentic_score(monkeypatch):
    monkeypatch.setattr(
        aa,
        "MODEL_PAPER_IDENTITIES",
        {"reviewed-model": aa.PaperIdentity(arxiv_id="2608.00001")},
    )
    monkeypatch.setattr(
        aa,
        "INDEXES",
        tuple(
            replace(index, min_expected_models=1, max_expected_models=10)
            for index in aa.INDEXES
        ),
    )

    class Client:
        def get(self, *args, **kwargs):
            return _Response(
                {
                    "intelligence_index_version": "4.1",
                    "pagination": {"has_more": False, "total_pages": 1},
                    "data": [
                        _api_row("reviewed-model", agentic=None),
                        _api_row("other-model"),
                    ],
                }
            )

    result = aa.fetch_artificial_analysis_leaderboard(api_key="secret", client=Client())
    assert result.entries[0].scores == {"intelligence": 42.5}


def test_sync_reviewed_model_without_optional_agentic_score(monkeypatch):
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
    session.commit()
    monkeypatch.setattr(
        aa,
        "MODEL_PAPER_IDENTITIES",
        {"reviewed-model": aa.PaperIdentity(arxiv_id="2608.00001")},
    )
    leaderboard = aa.ArtificialAnalysisLeaderboard(
        "4.1",
        [
            aa.ArtificialAnalysisEntry(
                "reviewed-model",
                "Reviewed Model",
                {"intelligence": 42.5},
                date(2026, 8, 1),
            )
        ],
    )
    result = aa.ArtificialAnalysisSyncService(session).sync(
        leaderboard,
        discovery=aa.ArtificialAnalysisDiscovery(papers={"reviewed-model": 7}),
    )
    assert result.indexes["intelligence"].created == 1
    assert result.indexes["agentic"].selected == 0
    assert session.query(Evaluation).one().metrics == {aa.METRIC_NAME: 42.5}


def test_sync_rejects_scored_reviewed_model_without_discovered_paper(monkeypatch):
    session = _session()
    monkeypatch.setattr(
        aa,
        "MODEL_PAPER_IDENTITIES",
        {"reviewed-model": aa.PaperIdentity(arxiv_id="2608.00001")},
    )
    leaderboard = aa.ArtificialAnalysisLeaderboard(
        "4.1",
        [
            aa.ArtificialAnalysisEntry(
                "reviewed-model",
                "Reviewed Model",
                {"intelligence": 42.5},
                date(2026, 8, 1),
            )
        ],
    )
    with pytest.raises(ValueError, match="incomplete reviewed model set"):
        aa.ArtificialAnalysisSyncService(session).sync(
            leaderboard, discovery=aa.ArtificialAnalysisDiscovery(papers={})
        )
    assert session.query(Evaluation).count() == 0


def test_sync_refreshes_old_managed_rows_and_retires_withdrawn_scores(monkeypatch):
    session = _session()
    Base.metadata.create_all(
        session.get_bind(),
        tables=[ModelRelease.__table__, ModelProviderAlias.__table__],
    )
    monkeypatch.setattr(aa, "MODEL_PAPER_IDENTITIES", {})
    session.add(
        Paper(
            id=7,
            title="Existing",
            source_url="https://example.com/existing",
            source="external",
            version="v1",
            is_latest_version=True,
        )
    )
    session.flush()
    for slug, managed in [
        ("old-model", True),
        ("withdrawn", True),
        ("manual", False),
        ("absent", True),
    ]:
        session.add(
            Evaluation(
                paper_id=7,
                task_id=5,
                dataset_id=581,
                model_name=slug,
                metrics={aa.METRIC_NAME: 1.0},
                best_metric=aa.METRIC_NAME,
                external_source_url=f"{aa.SOURCE_URL_PREFIX}{slug}",
                is_open=True,
                methodology=aa.MANAGED_METHODOLOGY_PREFIX if managed else "Manual",
            )
        )
    session.commit()
    leaderboard = aa.ArtificialAnalysisLeaderboard(
        "4.1",
        [
            aa.ArtificialAnalysisEntry(
                "old-model", "Old Model", {"intelligence": 39.9}, date(2026, 8, 1)
            ),
            aa.ArtificialAnalysisEntry("withdrawn", "Withdrawn", {}, date(2026, 8, 1)),
            aa.ArtificialAnalysisEntry("manual", "Manual", {}, date(2026, 8, 1)),
        ],
    )
    stats = aa.ArtificialAnalysisSyncService(session).sync(
        leaderboard, discovery=aa.ArtificialAnalysisDiscovery()
    )
    rows = {row.model_name: row for row in session.query(Evaluation).all()}
    assert set(rows) == {"Old Model", "manual", "absent"}
    assert rows["Old Model"].metrics == {aa.METRIC_NAME: 39.9}
    assert rows["Old Model"].paper_id == 7
    assert rows["Old Model"].is_open is True
    assert rows["manual"].metrics == {aa.METRIC_NAME: 1.0}
    assert stats.updated == 1
    assert stats.retired == 1


@pytest.mark.parametrize("old_slug,new_slug", aa.MODEL_SLUG_RENAMES.items())
def test_sync_migrates_reviewed_slug_rename_without_losing_paper(
    monkeypatch, old_slug, new_slug
):
    session = _session()
    Base.metadata.create_all(
        session.get_bind(),
        tables=[ModelRelease.__table__, ModelProviderAlias.__table__],
    )
    monkeypatch.setattr(aa, "MODEL_PAPER_IDENTITIES", {})
    session.add(
        Paper(
            id=7,
            title="Existing",
            source="external",
            source_url="https://example.com/existing",
            version="v1",
            is_latest_version=True,
        )
    )
    session.flush()
    old = Evaluation(
        paper_id=7,
        task_id=5,
        dataset_id=581,
        model_name="Old label",
        metrics={aa.METRIC_NAME: 1.0},
        best_metric=aa.METRIC_NAME,
        external_source_url=f"{aa.SOURCE_URL_PREFIX}{old_slug}",
        methodology=aa.MANAGED_METHODOLOGY_PREFIX,
    )
    session.add(old)
    session.commit()
    old_id = old.id
    leaderboard = aa.ArtificialAnalysisLeaderboard(
        "4.1",
        [
            aa.ArtificialAnalysisEntry(
                new_slug, "Current label", {"intelligence": 20.6}, date(2026, 8, 1)
            )
        ],
    )
    service = aa.ArtificialAnalysisSyncService(session)
    for _ in range(2):
        stats = service.sync(leaderboard, discovery=aa.ArtificialAnalysisDiscovery())
        row = session.query(Evaluation).one()
        assert row.id == old_id
        assert row.paper_id == 7
        assert row.external_source_url == f"{aa.SOURCE_URL_PREFIX}{new_slug}"
        assert row.metrics == {aa.METRIC_NAME: 20.6}
        assert stats.updated == 1
        assert stats.created == 0


def test_slug_rename_does_not_adopt_manual_old_row(monkeypatch):
    session = _session()
    monkeypatch.setattr(aa, "MODEL_PAPER_IDENTITIES", {})
    session.add(
        Paper(
            id=7,
            title="Manual",
            source="external",
            source_url="https://example.com/manual",
            version="v1",
            is_latest_version=True,
        )
    )
    session.flush()
    source = f"{aa.SOURCE_URL_PREFIX}k2-7b-ph2"
    session.add(
        Evaluation(
            paper_id=7,
            task_id=5,
            dataset_id=581,
            model_name="Manual",
            metrics={aa.METRIC_NAME: 1.0},
            best_metric=aa.METRIC_NAME,
            external_source_url=source,
            methodology="Manual",
        )
    )
    session.commit()
    board = aa.ArtificialAnalysisLeaderboard(
        "4.1",
        [
            aa.ArtificialAnalysisEntry(
                "k2-horizon-7b",
                "K2 Horizon 7B",
                {"intelligence": 20.6},
                date(2026, 8, 1),
            )
        ],
    )
    stats = aa.ArtificialAnalysisSyncService(session).sync(
        board, discovery=aa.ArtificialAnalysisDiscovery()
    )
    row = session.query(Evaluation).one()
    assert row.external_source_url == source
    assert row.metrics == {aa.METRIC_NAME: 1.0}
    assert stats.matched == 0


@pytest.mark.parametrize(
    "managed,same_paper,retired", [(True, True, 1), (False, True, 0), (True, False, 0)]
)
def test_slug_rename_retires_only_owned_duplicate_with_same_binding(
    monkeypatch, managed, same_paper, retired
):
    session = _session()
    Base.metadata.create_all(
        session.get_bind(),
        tables=[ModelRelease.__table__, ModelProviderAlias.__table__],
    )
    monkeypatch.setattr(aa, "MODEL_PAPER_IDENTITIES", {})
    for paper_id in (7, 8):
        session.add(
            Paper(
                id=paper_id,
                title="Model",
                source="arxiv",
                arxiv_id=f"2608.0000{paper_id}",
                version="v1",
                is_latest_version=True,
            )
        )
    session.flush()
    for slug, paper_id, methodology in [
        ("k2-7b-ph2", 7, aa.MANAGED_METHODOLOGY_PREFIX),
        (
            "k2-horizon-7b",
            7 if same_paper else 8,
            aa.MANAGED_METHODOLOGY_PREFIX if managed else "Manual",
        ),
    ]:
        session.add(
            Evaluation(
                paper_id=paper_id,
                task_id=5,
                dataset_id=581,
                model_name=slug,
                metrics={aa.METRIC_NAME: 1.0},
                best_metric=aa.METRIC_NAME,
                external_source_url=f"{aa.SOURCE_URL_PREFIX}{slug}",
                methodology=methodology,
            )
        )
    session.commit()
    board = aa.ArtificialAnalysisLeaderboard(
        "4.1",
        [
            aa.ArtificialAnalysisEntry(
                "k2-horizon-7b",
                "K2 Horizon 7B",
                {"intelligence": 20.6},
                date(2026, 8, 1),
            )
        ],
    )
    stats = aa.ArtificialAnalysisSyncService(session).sync(
        board, discovery=aa.ArtificialAnalysisDiscovery()
    )
    assert stats.retired == retired
    assert session.query(Evaluation).count() == 2 - retired
    if not managed:
        manual = (
            session.query(Evaluation).filter(Evaluation.methodology == "Manual").one()
        )
        assert manual.metrics == {aa.METRIC_NAME: 1.0}


def test_sync_tags_paper_once_when_reviewed_slugs_share_it(monkeypatch):
    session = _session()
    session.autoflush = False  # Matches the production session factory.
    session.add(
        Paper(
            id=7,
            title="Shared Model",
            arxiv_id="2608.00001",
            source="arxiv",
            version="v1",
            is_latest_version=True,
        )
    )
    session.commit()
    monkeypatch.setattr(
        aa,
        "MODEL_PAPER_IDENTITIES",
        {
            "shared-model": aa.PaperIdentity(arxiv_id="2608.00001"),
            "shared-model-full": aa.PaperIdentity(arxiv_id="2608.00001"),
        },
    )
    leaderboard = aa.ArtificialAnalysisLeaderboard(
        "4.1",
        [
            aa.ArtificialAnalysisEntry(
                slug, slug, {"intelligence": score}, date(2026, 8, 1)
            )
            for slug, score in (("shared-model", 40.0), ("shared-model-full", 45.0))
        ],
    )
    result = aa.ArtificialAnalysisSyncService(session).sync(
        leaderboard,
        discovery=aa.ArtificialAnalysisDiscovery(
            papers={"shared-model": 7, "shared-model-full": 7}
        ),
    )
    assert result.indexes["intelligence"].created == 2
    assert session.query(PaperTask).filter_by(paper_id=7, task_id=5).count() == 1


def _single_page_client(rows):
    class Client:
        def get(self, *args, **kwargs):
            return _Response(
                {
                    "intelligence_index_version": "5",
                    "pagination": {"has_more": False, "total_pages": 1},
                    "data": rows,
                }
            )

    return Client()


def test_fetch_reports_a_few_withdrawn_reviewed_models(monkeypatch):
    identity = aa.PaperIdentity(arxiv_id="2608.00001")
    reviewed = {f"reviewed-{index}": identity for index in range(8)}
    monkeypatch.setattr(aa, "MODEL_PAPER_IDENTITIES", reviewed)
    monkeypatch.setattr(
        aa,
        "INDEXES",
        tuple(
            replace(index, min_expected_models=1, max_expected_models=10)
            for index in aa.INDEXES
        ),
    )
    listed = [_api_row(f"reviewed-{index}") for index in range(6)]

    leaderboard = aa.fetch_artificial_analysis_leaderboard(
        api_key="secret", client=_single_page_client(listed)
    )
    assert leaderboard.missing_reviewed == ["reviewed-6", "reviewed-7"]

    with pytest.raises(ValueError, match="missing reviewed models"):
        aa.fetch_artificial_analysis_leaderboard(
            api_key="secret", client=_single_page_client(listed[:5])
        )


def test_fetch_counts_listed_unscored_models_and_withdrawn_index(monkeypatch):
    identity = aa.PaperIdentity(arxiv_id="2608.00001")
    reviewed = {f"reviewed-{index}": identity for index in range(8)}
    monkeypatch.setattr(aa, "MODEL_PAPER_IDENTITIES", reviewed)
    monkeypatch.setattr(
        aa,
        "INDEXES",
        tuple(
            replace(index, min_expected_models=1, max_expected_models=10)
            for index in aa.INDEXES
        ),
    )
    # Agentic scores are gone for everyone; half the models lost every score.
    listed = [
        _api_row(f"reviewed-{index}", agentic=None)
        if index < 4
        else _api_row(f"reviewed-{index}", intelligence=None, agentic=None)
        for index in range(8)
    ]

    leaderboard = aa.fetch_artificial_analysis_leaderboard(
        api_key="secret", client=_single_page_client(listed)
    )
    assert leaderboard.missing_reviewed == []
    assert leaderboard.withdrawn_indexes == ["agentic"]
    assert len(leaderboard.entries) == 4


def test_sync_keeps_rows_of_withdrawn_index(monkeypatch):
    calls = []
    service = aa.ArtificialAnalysisSyncService.__new__(aa.ArtificialAnalysisSyncService)
    service.db = _session()

    def fake_sync_index(index, *_args, **_kwargs):
        calls.append(index.key)
        return aa.ArtificialAnalysisIndexStats()

    monkeypatch.setattr(service, "_sync_index", fake_sync_index)
    leaderboard = aa.ArtificialAnalysisLeaderboard(
        "5", [], withdrawn_indexes=["agentic"]
    )
    stats = service.sync(leaderboard, discovery=aa.ArtificialAnalysisDiscovery())
    assert calls == ["intelligence"]
    assert "agentic" not in stats.indexes


def test_new_index_version_retires_unlisted_older_intelligence_rows(monkeypatch):
    session = _session()
    monkeypatch.setattr(
        aa,
        "MODEL_PAPER_IDENTITIES",
        {
            "rescored": aa.PaperIdentity(arxiv_id="2608.00001"),
            "withdrawn": aa.PaperIdentity(arxiv_id="2608.00002"),
        },
    )
    session.add(
        Paper(
            id=7,
            title="Existing",
            arxiv_id="2608.00001",
            source="arxiv",
            version="v1",
            is_latest_version=True,
        )
    )
    session.flush()

    def managed(version: str, index: aa.ArtificialAnalysisIndex) -> str:
        return (
            f"{aa.MANAGED_METHODOLOGY_PREFIX} Artificial Analysis Data API v2 "
            f"{index.label} {version}; fetched 2026-10-27T00:00:00+00:00."
        )

    for slug, dataset_id, task_id, methodology in [
        ("rescored", 581, 5, managed("4.3", aa.INTELLIGENCE_INDEX)),
        ("withdrawn", 581, 5, managed("4.3", aa.INTELLIGENCE_INDEX)),
        ("current", 581, 5, managed("5", aa.INTELLIGENCE_INDEX)),
        ("manual", 581, 5, "Manual Intelligence Index 4.3; fetched by hand"),
        ("withdrawn", 582, 14, managed("4.3", aa.AGENTIC_INDEX)),
    ]:
        session.add(
            Evaluation(
                paper_id=7,
                task_id=task_id,
                dataset_id=dataset_id,
                model_name=f"{slug}-{dataset_id}",
                metrics={aa.METRIC_NAME: 30.0},
                best_metric=aa.METRIC_NAME,
                external_source_url=f"{aa.SOURCE_URL_PREFIX}{slug}",
                methodology=methodology,
            )
        )
    session.commit()
    leaderboard = aa.ArtificialAnalysisLeaderboard(
        "5",
        [
            aa.ArtificialAnalysisEntry(
                "rescored", "Rescored", {"intelligence": 18.5}, date(2026, 8, 1)
            )
        ],
        missing_reviewed=["withdrawn"],
    )

    stats = aa.ArtificialAnalysisSyncService(session).sync(
        leaderboard, discovery=aa.ArtificialAnalysisDiscovery(papers={"rescored": 7})
    )

    rows = {(row.dataset_id, row.model_name): row for row in session.query(Evaluation)}
    assert set(rows) == {
        (581, "Rescored"),
        (581, "current-581"),
        (581, "manual-581"),
        (582, "withdrawn-582"),
    }
    assert rows[(581, "Rescored")].metrics == {aa.METRIC_NAME: 18.5}
    assert "Intelligence Index 5;" in rows[(581, "Rescored")].methodology
    assert stats.indexes["intelligence"].retired == 1
    assert stats.missing_upstream == ["withdrawn"]
    assert stats.to_dict()["missing_upstream"] == ["withdrawn"]
