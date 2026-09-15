"""Validation and idempotency tests for the living Open ASR sync."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

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
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.open_asr_sync_service import (
    LEGACY_SOURCE_URL,
    MANAGED_METHODOLOGY_PREFIX,
    SPACE_APP_URL,
    SPACE_SOURCE_URL,
    OpenAsrDiscoveredPaper,
    OpenAsrEntry,
    OpenAsrPaperDiscoveryResult,
    OpenAsrPaperDiscoveryService,
    OpenAsrSyncService,
    _model_identity_matches_paper,
    fetch_open_asr_leaderboard,
    parse_open_asr_leaderboard,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


def _payload(count: int = 40):
    return {
        "headers": ["Rank", "model", "Average WER ⬇️", "RTFx ⬆️️", "License"],
        "data": [
            [
                rank,
                f'<a href="https://huggingface.co/org/model-{rank}">org/model-{rank}</a>',
                f"{4 + rank / 10:.1f}" + (" 🥇" if rank == 1 else ""),
                "NA" if rank == 1 else rank * 10,
                "Proprietary" if rank == 1 else "apache-2.0",
            ]
            for rank in range(1, count + 1)
        ],
    }


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
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
    task = Task(
        id=12, name="Automatic Speech Recognition", slug="automatic-speech-recognition"
    )
    dataset = Dataset(id=181, name="Open ASR Leaderboard", slug="open-asr-leaderboard")
    wer = Metric(id=1, name="WER", direction="lower_is_better")
    rtfx = Metric(id=38, name="RTFx", direction="higher_is_better")
    session.add_all([task, dataset, wer, rtfx])
    session.add(TaskDataset(task_id=task.id, dataset_id=dataset.id))
    session.add_all(
        [
            TaskDatasetMetric(task_id=task.id, dataset_id=dataset.id, metric_id=wer.id),
            TaskDatasetMetric(
                task_id=task.id, dataset_id=dataset.id, metric_id=rtfx.id
            ),
        ]
    )
    session.add_all(
        [
            Paper(
                id=1,
                title="Model paper",
                arxiv_id="2311.00430",
                source="arxiv",
                version="v1",
                is_latest_version=True,
            ),
            Paper(
                id=2,
                title="Legacy external model",
                source="external",
                source_url="https://huggingface.co/vendor/legacy",
                version="v1",
                is_latest_version=True,
            ),
        ]
    )
    session.commit()
    return session


def test_parse_and_fetch_public_leaderboard_contract():
    payload = _payload()

    class FakeClient:
        def __init__(self, url, *, verbose):
            assert url == SPACE_APP_URL
            assert verbose is False

        def predict(self, query, proprietary, llm, columns, *, api_name):
            assert (query, proprietary, llm) == ("", True, False)
            # The current English default averages all ten datasets. Keeping
            # the old Earnings22 name fails; omitting Monsoon changes scores.
            assert columns == [
                "RTFx ⬆️️",
                "License",
                "AMI-Cleaned",
                "Earnings22-Cleaned-AA-chunked",
                "Gigaspeech-Cleaned",
                "LS Clean",
                "LS Other",
                "SPGISpeech",
                "Voice Arena Monsoon",
                "Voxpopuli-AA-Cleaned",
                "Private (scripted)",
                "Private (conversational)",
            ]
            assert api_name == "/_main_table_update"
            return {
                "datatype": ["str", "str", "markdown", "number", "number"],
                "value": payload,
            }

    entries = fetch_open_asr_leaderboard(FakeClient)
    assert entries[0] == OpenAsrEntry("org/model-1", 1, 4.1, None, False)
    assert entries[1] == OpenAsrEntry("org/model-2", 2, 4.2, 20.0, True)


def test_parser_rejects_truncated_or_noncontiguous_data():
    with pytest.raises(ValueError, match="expected 40-150"):
        parse_open_asr_leaderboard(_payload(10))
    payload = _payload()
    payload["data"][-1][0] = 41
    with pytest.raises(ValueError, match="contiguous"):
        parse_open_asr_leaderboard(payload)


def test_model_identity_requires_family_and_exact_size_or_version():
    title = "Data-Efficient On-Policy Distillation for Automatic Speech Recognition"
    abstract = "We study Ark-ASR, a 0.6B-parameter audio-conditioned model."

    assert _model_identity_matches_paper("org/ARK-ASR-0.6B", title, abstract)
    assert not _model_identity_matches_paper("org/ARK-ASR-3B", title, abstract)
    assert not _model_identity_matches_paper("org/Audio8-ASR-0.1B", title, abstract)
    assert not _model_identity_matches_paper("org/ARK-ASR-0.6B-v2", title, abstract)


def test_discovery_indexes_only_single_tag_with_exact_ownership():
    session = _session()
    metadata = SimpleNamespace(
        success=True,
        error_type=None,
        title="Data-Efficient On-Policy Distillation for Automatic Speech Recognition",
        abstract="We study Ark-ASR, a 0.6B-parameter audio-conditioned model.",
    )

    class FakeHfApi:
        def model_info(self, model_id, **_kwargs):
            from huggingface_hub.utils import validate_repo_id

            validate_repo_id(model_id)
            return SimpleNamespace(
                id=model_id,
                tags=["arxiv:2605.28139"],
                safetensors=SimpleNamespace(total=1_299_463_168),
            )

    class FakeArxivService:
        async def get_paper_metadata(self, arxiv_id):
            assert arxiv_id == "2605.28139"
            return metadata

    class FakeIngestionService:
        async def get_or_import_arxiv_paper(self, arxiv_id):
            paper = Paper(
                id=3,
                title=metadata.title,
                abstract=metadata.abstract,
                arxiv_id=arxiv_id,
                source="arxiv",
                version="v1",
                is_latest_version=True,
            )
            session.add(paper)
            session.flush()
            return paper, True

    result = asyncio.run(
        OpenAsrPaperDiscoveryService(
            session,
            hf_api=FakeHfApi(),
            arxiv_service=FakeArxivService(),
            ingestion_service=FakeIngestionService(),
        ).discover(
            [
                "sophea/asr-k1 (preview)",
                "org/ARK-ASR-3B",
                "org/Audio8-ASR-0.1B",
                # Keep the accepted paper last: SQLite cannot serialize the
                # PostgreSQL ARRAY assigned to Paper.hf_models on autoflush.
                "org/ARK-ASR-0.6B",
            ]
        )
    )

    discovered = result.resolved["org/ark-asr-0.6b"]
    assert discovered.paper_id == 3
    assert discovered.arxiv_id == "2605.28139"
    assert discovered.hf_model_url == "https://huggingface.co/org/ARK-ASR-0.6B"
    assert discovered.num_parameters == 1_299_463_168
    assert result.indexed_papers == ["2605.28139"]
    assert result.unavailable_models == ["sophea/asr-k1 (preview)"]
    assert result.rejected_papers == [
        "org/ARK-ASR-3B:2605.28139",
        "org/Audio8-ASR-0.1B:2605.28139",
    ]


def test_discovery_rejects_multiple_arxiv_tags_without_importing():
    session = _session()

    class FakeHfApi:
        def model_info(self, _model_id, **_kwargs):
            return SimpleNamespace(
                id="org/ambiguous",
                tags=["arxiv:2605.28139", "arxiv:2601.21337"],
                safetensors=None,
            )

    result = asyncio.run(
        OpenAsrPaperDiscoveryService(session, hf_api=FakeHfApi()).discover(
            ["org/ambiguous"], persist=False
        )
    )

    assert result.resolved == {}
    assert result.ambiguous_models == ["org/ambiguous"]


def test_sync_replaces_legacy_and_only_deletes_stale_managed_rows(monkeypatch):
    session = _session()
    session.add_all(
        [
            Evaluation(
                paper_id=2,
                task_id=12,
                dataset_id=181,
                model_name="Legacy",
                methodology=(
                    "Open ASR Leaderboard rank 1; sourced from "
                    "vendor/legacy/.eval_results/open_asr_leaderboard.yaml (main)"
                ),
                metrics={"WER": 9.0},
                best_metric="WER",
                external_source_url=LEGACY_SOURCE_URL,
            ),
            Evaluation(
                paper_id=1,
                task_id=12,
                dataset_id=181,
                model_name="gone/model",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} old",
                metrics={"WER": 10.0},
                best_metric="WER",
                external_source_url=SPACE_SOURCE_URL,
            ),
            Evaluation(
                paper_id=1,
                task_id=12,
                dataset_id=181,
                model_name="Manual paper result",
                methodology="Human curated",
                metrics={"WER": 3.0},
                best_metric="WER",
            ),
        ]
    )
    session.commit()
    monkeypatch.setitem(
        __import__(
            "backend.services.open_asr_sync_service", fromlist=["MODEL_PAPER_ARXIV_IDS"]
        ).MODEL_PAPER_ARXIV_IDS,
        "distil-whisper/distil-large-v3.5",
        "2311.00430",
    )
    entries = [
        OpenAsrEntry("vendor/legacy", 1, 5.0, None, False),
        OpenAsrEntry("distil-whisper/distil-large-v3.5", 2, 6.0, 100.0, True),
        OpenAsrEntry("vendor/unmatched", 3, 7.0, 50.0, False),
    ]
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    stats = OpenAsrSyncService(session).sync(entries, fetched_at=now)

    assert stats.to_dict() == {
        "fetched": 3,
        "matched": 2,
        "created": 2,
        "updated": 0,
        "deleted": 2,
        "unmatched_models": ["vendor/unmatched"],
        "missing_papers": [],
    }
    rows = {row.model_name: row for row in session.query(Evaluation).all()}
    assert set(rows) == {
        "vendor/legacy",
        "distil-whisper/distil-large-v3.5",
        "Manual paper result",
    }
    assert rows["vendor/legacy"].paper_id == 2
    assert rows["vendor/legacy"].metrics == {"WER": 5.0}
    assert rows["distil-whisper/distil-large-v3.5"].metrics == {
        "WER": 6.0,
        "RTFx": 100.0,
    }
    assert rows["Manual paper result"].best_rank == 1

    second = OpenAsrSyncService(session).sync(entries, fetched_at=now)
    assert second.created == 0
    assert second.updated == 2
    assert second.deleted == 0
    assert session.query(Evaluation).count() == 3


def test_discovered_paper_creates_managed_row_and_task_link():
    session = _session()
    paper = Paper(
        id=3,
        title="New model paper",
        arxiv_id="2605.28139",
        source="arxiv",
        version="v1",
        is_latest_version=True,
    )
    session.add(paper)
    session.commit()
    discovery = OpenAsrPaperDiscoveryResult(
        resolved={
            "org/new-model-0.6b": OpenAsrDiscoveredPaper(
                paper_id=paper.id,
                arxiv_id="2605.28139",
                hf_model_url="https://huggingface.co/org/new-model-0.6B",
                num_parameters=600_000_000,
            )
        }
    )

    stats = OpenAsrSyncService(session).sync(
        [OpenAsrEntry("org/new-model-0.6B", 1, 5.5, 200.0, True)],
        discovery=discovery,
        fetched_at=datetime(2026, 8, 7, 10, 0, tzinfo=UTC),
    )

    assert stats.created == 1
    row = session.query(Evaluation).filter(Evaluation.paper_id == paper.id).one()
    assert row.metrics == {"WER": 5.5, "RTFx": 200.0}
    assert row.hf_model_url == "https://huggingface.co/org/new-model-0.6B"
    assert row.num_parameters == 600_000_000
    task_link = session.query(PaperTask).filter(PaperTask.paper_id == paper.id).one()
    assert task_link.task_id == 12
    assert task_link.source == "auto"
