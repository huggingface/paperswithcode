"""Contract and idempotency tests for the living Open TTS sync."""

import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
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


def _response(
    payload, *, language=None, datasets=None, clone=False, language_choices=None
):
    selected_language = language or [DEFAULT_LANGUAGE]
    selected_datasets = datasets or DEFAULT_DATASETS
    language_choices = language_choices or [
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


def test_parse_accepts_footnote_markers_after_model_link():
    payload = _payload()
    payload["data"][2][1] += "<sup>¹</sup>"
    payload["data"][3][1] += " <sup>2</sup>"

    entries = parse_open_tts_leaderboard(payload)

    assert len(entries) == 15
    assert entries[2].model_name == "org/model-3 (variant)"


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


def test_fetches_english_and_every_available_language_view():
    all_languages = [
        "🇬🇧 English",
        "🇨🇳 Chinese",
        "🇫🇷 French",
        "🇪🇸 Spanish",
        "🇩🇪 German",
        "🇮🇹 Italian",
        "🇯🇵 Japanese",
        "🇰🇷 Korean",
        "🇷🇺 Russian",
    ]
    choices = [[language, language] for language in all_languages]
    multilingual_payload = _payload()
    for row in multilingual_payload["data"][5:]:
        row[0] = None
        row[2] = None
        row[3] = None

    class FakeClient:
        def __init__(self, url, *, verbose):
            assert url == SPACE_APP_URL
            assert verbose is False
            self.calls = 0

        def predict(self, version, search, languages, datasets, clone, *, api_name):
            assert (version, search, datasets, clone, api_name) == (
                "latest",
                "",
                DEFAULT_DATASETS,
                False,
                "/partial",
            )
            self.calls += 1
            if self.calls == 1:
                assert languages == [DEFAULT_LANGUAGE]
                return _response(_payload(), language_choices=choices)
            assert languages == all_languages
            return _response(
                multilingual_payload,
                language=all_languages,
                language_choices=choices,
            )

    leaderboards = tts.fetch_open_tts_leaderboards(FakeClient)

    assert len(leaderboards[tts.DATASET_SLUG]) == 15
    assert len(leaderboards[tts.ALL_LANGUAGE_DATASET_SLUG]) == 5


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


def test_parser_accepts_complete_ranked_subset_from_multilingual_view():
    payload = _payload()
    for row in payload["data"][5:]:
        row[0] = None
        row[2] = None
        row[3] = None

    entries = parse_open_tts_leaderboard(payload, min_ranked_entries=5)

    assert len(entries) == 5
    assert [entry.rank for entry in entries] == [1, 2, 3, 4, 5]


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
    all_language_dataset = Dataset(
        id=2_401,
        name="Open TTS Leaderboard - All Languages Average",
        slug="open-tts-leaderboard-all-languages",
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
    session.add_all([task, dataset, all_language_dataset, wer, rtfx, paper])
    session.add_all(
        [
            TaskDataset(task_id=task.id, dataset_id=dataset.id),
            TaskDataset(task_id=task.id, dataset_id=all_language_dataset.id),
        ]
    )
    session.add_all(
        [
            TaskDatasetMetric(task_id=task.id, dataset_id=dataset.id, metric_id=wer.id),
            TaskDatasetMetric(
                task_id=task.id, dataset_id=dataset.id, metric_id=rtfx.id
            ),
            TaskDatasetMetric(
                task_id=task.id,
                dataset_id=all_language_dataset.id,
                metric_id=wer.id,
            ),
            TaskDatasetMetric(
                task_id=task.id,
                dataset_id=all_language_dataset.id,
                metric_id=rtfx.id,
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


def test_syncs_english_and_all_language_benchmarks(monkeypatch):
    session = _session()
    monkeypatch.setattr(
        tts,
        "MODEL_PAPER_IDENTITIES",
        {"org/model-a": PaperIdentity(arxiv_id="2601.00001", is_open=True)},
    )
    leaderboards = {
        tts.DATASET_SLUG: [OpenTtsEntry("org/model-a", "Model A", 1, 1.25, 12.5, True)],
        tts.ALL_LANGUAGE_DATASET_SLUG: [
            OpenTtsEntry("org/model-a", "Model A", 1, 3.5, 10.0, True)
        ],
    }

    stats = OpenTtsSyncService(session).sync_benchmarks(
        leaderboards,
        discovery=ArtificialAnalysisDiscovery(papers={"org/model-a": 9}),
        fetched_at=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
    )

    assert {slug: value.created for slug, value in stats.items()} == {
        tts.DATASET_SLUG: 1,
        tts.ALL_LANGUAGE_DATASET_SLUG: 1,
    }
    rows = {
        session.get(Dataset, row.dataset_id).slug: row
        for row in session.query(Evaluation).all()
    }
    assert rows[tts.DATASET_SLUG].metrics == {"WER": 1.25, "RTFx": 12.5}
    multilingual = rows[tts.ALL_LANGUAGE_DATASET_SLUG]
    assert multilingual.metrics == {"WER": 3.5, "RTFx": 10.0}
    assert "all available languages" in multilingual.methodology
    assert multilingual.best_rank == 1


def test_sync_uses_curated_model_name_in_both_benchmarks(monkeypatch):
    session = _session()
    model_id = "k2-fsa/OmniVoice"
    monkeypatch.setattr(
        tts,
        "MODEL_PAPER_IDENTITIES",
        {model_id: PaperIdentity(arxiv_id="2601.00001", is_open=True)},
    )
    entry = OpenTtsEntry(model_id, model_id, 1, 3.25, 37.52, True)

    OpenTtsSyncService(session).sync_benchmarks(
        {
            tts.DATASET_SLUG: [entry],
            tts.ALL_LANGUAGE_DATASET_SLUG: [entry],
        },
        discovery=ArtificialAnalysisDiscovery(papers={model_id: 9}),
    )

    rows = session.query(Evaluation).order_by(Evaluation.dataset_id).all()
    assert [row.model_name for row in rows] == ["OmniVoice", "OmniVoice"]
    assert {row.hf_model_url for row in rows} == {
        "https://huggingface.co/k2-fsa/OmniVoice"
    }


def test_sync_uses_curated_names_for_every_reviewed_model(monkeypatch):
    expected_names = {
        "microsoft/VibeVoice-Realtime-0.5B": "VibeVoice Realtime 0.5B",
        "fishaudio/s2-pro": "Fish Audio S2 Pro",
        "k2-fsa/OmniVoice": "OmniVoice",
        "kyutai/pocket-tts": "Pocket TTS",
        "FunAudioLLM/Fun-CosyVoice3-0.5B-2512": "CosyVoice 3 0.5B (RL)",
        "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice": "Qwen3-TTS 1.7B (CustomVoice)",
        "facebook/seamless-m4t-v2-large": "SeamlessM4T v2 Large",
        "microsoft/speecht5_tts": "SpeechT5",
        "OpenMOSS-Team/MOSS-TTS": "MOSS-TTS",
        "Qwen/Qwen3-Omni-30B-A3B-Instruct": "Qwen3-Omni 30B-A3B",
        "mistralai/Voxtral-4B-TTS-2603": "Voxtral 4B TTS",
    }

    for model_id, expected_name in expected_names.items():
        session = _session()
        monkeypatch.setattr(
            tts,
            "MODEL_PAPER_IDENTITIES",
            {model_id: PaperIdentity(arxiv_id="2601.00001", is_open=True)},
        )
        OpenTtsSyncService(session).sync(
            [OpenTtsEntry(model_id, model_id, 1, 1.0, 1.0, True)],
            discovery=ArtificialAnalysisDiscovery(papers={model_id: 9}),
        )

        row = session.query(Evaluation).one()
        assert row.model_name == expected_name
        assert row.hf_model_url == f"https://huggingface.co/{model_id}"


def test_two_benchmark_sync_rolls_back_if_either_benchmark_is_unconfigured(
    monkeypatch,
):
    session = _session()
    all_language_dataset = (
        session.query(Dataset)
        .filter(Dataset.slug == tts.ALL_LANGUAGE_DATASET_SLUG)
        .one()
    )
    session.query(TaskDatasetMetric).filter(
        TaskDatasetMetric.dataset_id == all_language_dataset.id
    ).delete()
    session.commit()
    monkeypatch.setattr(
        tts,
        "MODEL_PAPER_IDENTITIES",
        {"org/model-a": PaperIdentity(arxiv_id="2601.00001", is_open=True)},
    )
    entry = OpenTtsEntry("org/model-a", "Model A", 1, 1.25, 12.5, True)

    try:
        OpenTtsSyncService(session).sync_benchmarks(
            {
                tts.DATASET_SLUG: [entry],
                tts.ALL_LANGUAGE_DATASET_SLUG: [entry],
            },
            discovery=ArtificialAnalysisDiscovery(papers={"org/model-a": 9}),
        )
    except RuntimeError as exc:
        assert "metrics are not linked" in str(exc)
    else:
        raise AssertionError("sync accepted a missing multilingual benchmark")

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


def test_setup_creates_english_and_all_language_benchmarks(monkeypatch):
    session = _session()
    session.query(TaskDatasetMetric).delete()
    session.query(TaskDataset).delete()
    session.query(Dataset).delete()
    session.commit()

    @contextmanager
    def session_local():
        yield session

    monkeypatch.setattr(
        setup, "db_manager", SimpleNamespace(session_local=session_local)
    )
    monkeypatch.setattr(
        setup.ExternalResourceService,
        "add_external_resource",
        lambda _self, _payload, *, commit: SimpleNamespace(paper=SimpleNamespace(id=9)),
    )

    setup.main()

    datasets = {dataset.slug: dataset for dataset in session.query(Dataset).all()}
    assert set(datasets) == {
        tts.DATASET_SLUG,
        tts.ALL_LANGUAGE_DATASET_SLUG,
    }
    assert all(dataset.introducing_paper_id == 9 for dataset in datasets.values())
    assert session.query(TaskDataset).count() == 2
    assert session.query(TaskDatasetMetric).count() == 4


def test_cron_syncs_both_open_tts_views(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(".github/workflows").resolve()))
    from scripts.hourly import sync_open_tts as job

    session = _session()
    english = [OpenTtsEntry("org/model-a", "Model A", 1, 1.25, 12.5, True)]
    leaderboards = {
        tts.DATASET_SLUG: english,
        tts.ALL_LANGUAGE_DATASET_SLUG: [
            OpenTtsEntry("org/model-a", "Model A", 1, 3.5, 10.0, True)
        ],
    }
    monkeypatch.setattr(job, "fetch_open_tts_leaderboards", lambda: leaderboards)
    monkeypatch.setattr(
        job,
        "run_open_tts_discovery",
        lambda _session, *, persist: ArtificialAnalysisDiscovery(
            papers={"org/model-a": 9}
        ),
    )
    monkeypatch.setattr(
        job, "db_manager", SimpleNamespace(session_local=lambda: session)
    )
    monkeypatch.setattr(
        tts,
        "MODEL_PAPER_IDENTITIES",
        {"org/model-a": PaperIdentity(arxiv_id="2601.00001", is_open=True)},
    )

    job.SyncOpenTtsJob().run()

    dataset_slugs = {
        session.get(Dataset, row.dataset_id).slug
        for row in session.query(Evaluation).all()
    }
    assert dataset_slugs == {
        tts.DATASET_SLUG,
        tts.ALL_LANGUAGE_DATASET_SLUG,
    }
