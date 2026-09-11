"""Contract and idempotency tests for the living Open TTS sync."""

import asyncio
from datetime import UTC, datetime

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
from backend.services.artificial_analysis_sync_service import (
    ArtificialAnalysisDiscovery,
    PaperIdentity,
)
from backend.services import open_tts_sync_service as tts
from backend.database.datasets_setup import add_open_tts_leaderboard as setup

from backend.services.open_tts_sync_service import (
    DEFAULT_DATASETS,
    DEFAULT_LANGUAGE,
    SPACE_APP_URL,
    MANAGED_METHODOLOGY_PREFIX,
    SPACE_SOURCE_URL,
    OpenTtsEntry,
    OpenTtsSyncService,
    fetch_open_tts_leaderboard,
    parse_open_tts_leaderboard,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


def _payload(count: int = 15):
    return {
        "headers": [
            "Rank",
            "Model",
            "Average WER ⬇️",
            "Average RTFx ⬆️",
            "Size (B)",
            "License",
        ],
        "data": [
            [
                rank,
                (
                    '<a target="_blank" '
                    f'href="https://huggingface.co/org/model-{rank}">'
                    f"org/model-{rank} (variant)</a>"
                ),
                1 + rank / 10,
                rank * 2.5,
                0.5,
                "apache 2.0" if rank > 1 else "custom",
            ]
            for rank in range(1, count + 1)
        ],
    }


def _response(payload, *, language=None, datasets=None, clone=False):
    selected_language = language or [DEFAULT_LANGUAGE]
    selected_datasets = datasets or DEFAULT_DATASETS
    language_choices = [
        ["🇬🇧 English", "🇬🇧 English"],
        ["🇨🇳 Chinese", "🇨🇳 Chinese"],
    ]
    dataset_choices = [["Seed-TTS", "Seed-TTS"], ["CV3-Eval", "CV3-Eval"]]
    return (
        {"__type__": "update"},
        {"__type__": "update"},
        {"__type__": "update"},
        {
            "choices": language_choices,
            "value": selected_language,
            "__type__": "update",
        },
        {
            "choices": dataset_choices,
            "value": selected_datasets,
            "__type__": "update",
        },
        {"value": clone, "__type__": "update"},
        {
            "choices": language_choices,
            "value": selected_language,
            "__type__": "update",
        },
        {
            "choices": dataset_choices,
            "value": selected_datasets,
            "__type__": "update",
        },
        {"value": clone, "__type__": "update"},
        {"datatype": ["number"], "value": payload},
    )


def test_parse_and_fetch_default_public_leaderboard_contract():
    payload = _payload()

    class FakeClient:
        def __init__(self, url, *, verbose):
            assert url == SPACE_APP_URL
            assert verbose is False

        def predict(self, version, search, languages, datasets, clone, *, api_name):
            assert version == "latest"
            assert search == ""
            assert languages == [DEFAULT_LANGUAGE]
            assert datasets == DEFAULT_DATASETS
            assert clone is False
            assert api_name == "/partial"
            return _response(payload)

    entries = fetch_open_tts_leaderboard(FakeClient)

    assert entries[0] == OpenTtsEntry(
        model_id="org/model-1",
        model_name="org/model-1 (variant)",
        rank=1,
        wer=1.1,
        rtfx=2.5,
        is_open=True,
    )
    assert entries[1].model_id == "org/model-2"


def test_fetch_rejects_nondefault_or_missing_filter_echoes():
    class WrongDatasetClient:
        def __init__(self, _url, *, verbose):
            assert verbose is False

        def predict(self, *_args, **_kwargs):
            return _response(_payload(), datasets=["Seed-TTS"])

    try:
        fetch_open_tts_leaderboard(WrongDatasetClient)
    except ValueError as exc:
        assert "did not echo the requested default filters" in str(exc)
    else:
        raise AssertionError("non-default filter echo was accepted")

    class MissingEchoClient:
        def __init__(self, _url, *, verbose):
            assert verbose is False

        def predict(self, *_args, **_kwargs):
            return ({"datatype": ["number"], "value": _payload()},)

    try:
        fetch_open_tts_leaderboard(MissingEchoClient)
    except TypeError as exc:
        assert "default filter echoes" in str(exc)
    else:
        raise AssertionError("missing filter echoes were accepted")


def test_parser_rejects_truncated_or_noncontiguous_data():
    payload = _payload(14)
    try:
        parse_open_tts_leaderboard(payload)
    except ValueError as exc:
        assert "expected 15-100" in str(exc)
    else:
        raise AssertionError("truncated leaderboard was accepted")

    payload = _payload()
    payload["data"][-1][0] = 16
    try:
        parse_open_tts_leaderboard(payload)
    except ValueError as exc:
        assert "contiguous" in str(exc)
    else:
        raise AssertionError("noncontiguous leaderboard was accepted")


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
    task = Task(id=24, name="Text-to-Speech", slug="text-to-speech")
    dataset = Dataset(
        id=2_400, name="Open TTS Leaderboard", slug="open-tts-leaderboard"
    )
    wer = Metric(id=1, name="WER", direction="lower_is_better")
    rtfx = Metric(id=38, name="RTFx", direction="higher_is_better")
    paper = Paper(
        id=9,
        title="Model A",
        arxiv_id="2601.00001",
        source="arxiv",
        version="v1",
        is_latest_version=True,
    )
    session.add_all([task, dataset, wer, rtfx, paper])
    session.add(TaskDataset(task_id=task.id, dataset_id=dataset.id))
    session.add_all(
        [
            TaskDatasetMetric(task_id=task.id, dataset_id=dataset.id, metric_id=wer.id),
            TaskDatasetMetric(
                task_id=task.id, dataset_id=dataset.id, metric_id=rtfx.id
            ),
        ]
    )
    session.commit()
    return session


def test_sync_is_idempotent_and_only_replaces_managed_rows(monkeypatch):
    session = _session()
    monkeypatch.setattr(
        tts,
        "MODEL_PAPER_IDENTITIES",
        {"org/model-a": PaperIdentity(arxiv_id="2601.00001", is_open=True)},
    )
    session.add_all(
        [
            Evaluation(
                paper_id=9,
                task_id=24,
                dataset_id=2_400,
                model_name="org/stale",
                metrics={"WER": 9.0, "RTFx": 1.0},
                best_metric="WER",
                external_source_url=SPACE_SOURCE_URL,
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} old",
            ),
            Evaluation(
                paper_id=9,
                task_id=24,
                dataset_id=2_400,
                model_name="Unreviewed release",
                hf_model_url="https://huggingface.co/org/unreviewed",
                metrics={"WER": 4.0, "RTFx": 4.0},
                best_metric="WER",
                external_source_url=SPACE_SOURCE_URL,
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} old",
            ),
            Evaluation(
                paper_id=9,
                task_id=24,
                dataset_id=2_400,
                model_name="Manual result",
                metrics={"WER": 0.5},
                best_metric="WER",
                methodology="Human curated",
            ),
        ]
    )
    session.commit()
    entries = [
        OpenTtsEntry("org/model-a", "Model A (RL)", 1, 1.25, 12.5, True),
        OpenTtsEntry("org/unreviewed", "Unreviewed release", 2, 2.0, 5.0, True),
    ]
    discovery = ArtificialAnalysisDiscovery(papers={"org/model-a": 9})
    now = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)

    first = OpenTtsSyncService(session).sync(
        entries, discovery=discovery, fetched_at=now
    )
    second = OpenTtsSyncService(session).sync(
        entries, discovery=discovery, fetched_at=now
    )

    assert first.to_dict() == {
        "fetched": 2,
        "matched": 1,
        "created": 1,
        "updated": 0,
        "deleted": 2,
        "excluded_models": ["org/unreviewed"],
        "missing_papers": [],
    }
    assert (second.created, second.updated, second.deleted) == (0, 1, 0)
    assert second.excluded_models == ["org/unreviewed"]
    rows = {row.model_name: row for row in session.query(Evaluation).all()}
    assert set(rows) == {"Model A (RL)", "Manual result"}
    managed = rows["Model A (RL)"]
    assert managed.metrics == {"WER": 1.25, "RTFx": 12.5}
    assert managed.paper_id == 9
    assert managed.hf_model_url == "https://huggingface.co/org/model-a"
    assert managed.external_source_url == SPACE_SOURCE_URL
    assert managed.is_open is True
    assert managed.evaluated_on.isoformat() == "2026-09-11"
    assert rows["Manual result"].best_rank == 1
    assert session.query(PaperTask).one().source == "auto"


def test_sync_rolls_back_dry_run(monkeypatch):
    session = _session()
    monkeypatch.setattr(
        tts,
        "MODEL_PAPER_IDENTITIES",
        {"org/model-a": PaperIdentity(arxiv_id="2601.00001", is_open=True)},
    )
    stats = OpenTtsSyncService(session).sync(
        [OpenTtsEntry("org/model-a", "Model A", 1, 2.0, 3.0, True)],
        discovery=ArtificialAnalysisDiscovery(papers={"org/model-a": 9}),
        commit=False,
    )

    assert stats.created == 1
    assert session.query(Evaluation).count() == 0
    assert session.query(PaperTask).count() == 0


def test_discovery_resolves_reviewed_model_to_existing_paper(monkeypatch):
    session = _session()
    monkeypatch.setattr(
        tts,
        "MODEL_PAPER_IDENTITIES",
        {"org/model-a": PaperIdentity(arxiv_id="2601.00001", is_open=True)},
    )

    discovery = asyncio.run(tts.discover_open_tts_papers(session))

    assert discovery.papers == {"org/model-a": 9}
    assert discovery.indexed_papers == []


def test_reviewed_model_manifest_contains_only_arxiv_papers():
    assert tts.MODEL_PAPER_IDENTITIES
    assert all(
        identity.arxiv_id and identity.source_url is None
        for identity in tts.MODEL_PAPER_IDENTITIES.values()
    )


def test_benchmark_source_uses_space_creation_date():
    assert setup.SOURCE_DATE.isoformat() == "2026-09-07"
