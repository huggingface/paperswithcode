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
    display_model_names,
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

        def predict(
            self,
            *,
            version_id,
            search_query,
            show_proprietary,
            show_llm,
            selected_columns,
            api_name,
        ):
            assert version_id == "latest"
            assert (search_query, show_proprietary, show_llm) == ("", True, False)
            # The current English default averages all eleven datasets. Keeping
            # the old Earnings22 name fails; omitting a dataset changes scores.
            assert selected_columns == [
                "RTFx ⬆️️",
                "License",
                "AMI-Cleaned",
                "Earnings22-Cleaned-AA-chunked",
                "Gigaspeech-Cleaned",
                "LS Clean",
                "LS Other",
                "SPGISpeech",
                "URGENT24",
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


def test_fetch_accepts_table_and_plot_update_tuple():
    payload = _payload()

    class FakeClient:
        def __init__(self, url, *, verbose):
            pass

        def predict(self, **_kwargs):
            table = {"datatype": ["str"], "value": payload}
            plot = {"value": {"type": "plotly", "plot": "{}"}}
            return (table, plot)

    entries = fetch_open_asr_leaderboard(FakeClient)
    assert len(entries) == 40
    assert entries[0] == OpenAsrEntry("org/model-1", 1, 4.1, None, False)


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
    assert set(rows) == {"legacy", "distil-large-v3.5", "Manual paper result"}
    assert rows["legacy"].paper_id == 2
    assert rows["legacy"].metrics == {"WER": 5.0}
    assert rows["distil-large-v3.5"].hf_model_url == (
        "https://huggingface.co/distil-whisper/distil-large-v3.5"
    )
    assert rows["distil-large-v3.5"].metrics == {
        "WER": 6.0,
        "RTFx": 100.0,
    }
    assert rows["Manual paper result"].best_rank == 1

    second = OpenAsrSyncService(session).sync(entries, fetched_at=now)
    assert second.created == 0
    assert second.updated == 2
    assert second.deleted == 0
    assert session.query(Evaluation).count() == 3


def test_sync_refreshes_throughput_rank_on_preserved_paper_native_rows(monkeypatch):
    session = _session()
    manual = Evaluation(
        paper_id=1,
        task_id=12,
        dataset_id=181,
        model_name="Paper-native throughput",
        methodology="Paper Table 2",
        metrics={"RTFx": 150.0},
        best_metric="RTFx",
        best_rank=21,
    )
    session.add(manual)
    session.commit()
    monkeypatch.setitem(
        __import__(
            "backend.services.open_asr_sync_service", fromlist=["MODEL_PAPER_ARXIV_IDS"]
        ).MODEL_PAPER_ARXIV_IDS,
        "vendor/legacy",
        "2311.00430",
    )
    service = OpenAsrSyncService(session)
    service.sync([OpenAsrEntry("vendor/legacy", 1, 5.0, 200.0, False)])
    assert manual.best_rank == 2
    assert manual.metrics == {"RTFx": 150.0}
    # Updating or dropping secondary throughput must refresh manual ranks too.
    service.sync([OpenAsrEntry("vendor/legacy", 1, 5.0, None, False)])
    assert manual.best_rank == 1


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


def test_display_names_drop_org_and_hf_suffix_but_keep_runtime_and_collisions():
    entries = [
        OpenAsrEntry("Qwen/Qwen3-ASR-1.7B-hf", 1, 5.4, None, True),
        OpenAsrEntry("microsoft/VibeVoice-ASR-HF", 2, 8.1, None, True),
        OpenAsrEntry("nvidia/parakeet-tdt-0.6b-v2 (fast-gpu-asr)", 3, 6.0, None, True),
        OpenAsrEntry("sophea/asr-k1 (preview)", 4, 5.2, None, False),
        OpenAsrEntry("a/same-model", 5, 7.0, None, True),
        OpenAsrEntry("b/same-model-hf", 6, 7.1, None, True),
    ]

    assert display_model_names(entries) == {
        "Qwen/Qwen3-ASR-1.7B-hf": "Qwen3-ASR-1.7B",
        "microsoft/VibeVoice-ASR-HF": "VibeVoice-ASR",
        "nvidia/parakeet-tdt-0.6b-v2 (fast-gpu-asr)": (
            "parakeet-tdt-0.6b-v2 (fast-gpu-asr)"
        ),
        "sophea/asr-k1 (preview)": "Sophea ASR K1 (preview)",
        "a/same-model": "a/same-model",
        "b/same-model-hf": "b/same-model-hf",
    }


def test_sync_renames_old_rows_and_supersedes_stale_curated_scores(monkeypatch):
    session = _session()
    old_managed = Evaluation(
        paper_id=1,
        task_id=12,
        dataset_id=181,
        model_name="org/model-hf",
        methodology=f"{MANAGED_METHODOLOGY_PREFIX} Upstream rank 3; old.",
        metrics={"WER": 9.0},
        best_metric="WER",
        external_source_url=SPACE_SOURCE_URL,
    )
    stale_paper_score = Evaluation(
        paper_id=2,
        task_id=12,
        dataset_id=181,
        model_name="vendor/api (preview)",
        methodology="Paper reports the board average as of an older version.",
        metrics={"WER": 4.2},
        best_metric="WER",
    )
    session.add_all([old_managed, stale_paper_score])
    session.commit()
    module = __import__(
        "backend.services.open_asr_sync_service",
        fromlist=["MODEL_PAPER_ARXIV_IDS"],
    )
    monkeypatch.setattr(
        module,
        "MODEL_PAPER_ARXIV_IDS",
        {"org/model-hf": "2311.00430", "org/model": "2311.00430"},
    )
    entries = [
        OpenAsrEntry("org/model-hf", 1, 6.0, 100.0, True),
        # Runtime variants resolve through their Hub repository id.
        OpenAsrEntry("org/model (fast-gpu-asr)", 2, 6.1, 900.0, True),
        OpenAsrEntry("vendor/api (preview)", 3, 5.2, None, False),
    ]
    discovery = OpenAsrPaperDiscoveryResult(
        resolved={"vendor/api": OpenAsrDiscoveredPaper(paper_id=2, arxiv_id="x")}
    )
    service = OpenAsrSyncService(session)
    assert service.models_needing_discovery(entries) == ["vendor/api"]

    stats = service.sync(entries, discovery=discovery)

    assert (stats.created, stats.updated, stats.deleted) == (1, 2, 0)
    assert old_managed.model_name == "model"
    assert old_managed.metrics == {"WER": 6.0, "RTFx": 100.0}
    assert stale_paper_score.model_name == "api (preview)"
    assert stale_paper_score.metrics == {"WER": 5.2}
    assert stale_paper_score.methodology.startswith(
        f"{MANAGED_METHODOLOGY_PREFIX} Upstream model vendor/api (preview); rank 3;"
    )
    variant = (
        session.query(Evaluation)
        .filter(Evaluation.model_name == "model (fast-gpu-asr)")
        .one()
    )
    assert variant.paper_id == 1
    assert variant.hf_model_url == "https://huggingface.co/org/model"

    again = service.sync(entries, discovery=discovery)
    assert (again.created, again.updated, again.deleted) == (0, 3, 0)
    assert service.models_needing_discovery(entries) == []
