"""Tests for the per-language Open ASR boards."""

from datetime import UTC, datetime

import pytest

from backend.models.database import (
    Dataset,
    Evaluation,
    Paper,
    PaperTask,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services import open_asr_language_sync_service as lang
from backend.services.open_asr_sync_service import (
    MANAGED_METHODOLOGY_PREFIX,
    SPACE_APP_URL,
    SPACE_SOURCE_URL,
    OpenAsrEntry,
)
from backend.tests.evaluation.test_open_asr_sync import _session

HINDI = "🇮🇳 Hindi"
HINDI_SLUG = "open-asr-leaderboard-hindi"


def _cell(href: str, model_id: str) -> str:
    return f'<a target="_blank" href="{href}" style="x">{model_id}</a>'


def _table(label: str = HINDI):
    return {
        "headers": ["Rank", "Model", "Average WER ⬇️", "RTFx ⬆️️", label],
        "data": [
            [1, _cell("https://vendor.ai/docs", "vendor/api-1"), 6.5, None, 6.5],
            [
                2,
                _cell("https://huggingface.co/org/model-a", "org/model-a"),
                9.6,
                120.0,
                9.6,
            ],
            [
                3,
                _cell("https://huggingface.co/org/card-only", "org/card-only"),
                12.0,
                80.0,
                12.0,
            ],
        ],
    }


def test_parse_language_table_reads_links_and_optional_rtfx():
    entries = lang.parse_language_table({"value": _table()}, label=HINDI)

    assert entries[0] == OpenAsrEntry("vendor/api-1", 1, 6.5, None, False)
    assert entries[1] == OpenAsrEntry("org/model-a", 2, 9.6, 120.0, True)


def test_parse_language_table_rejects_gaps_and_missing_columns():
    table = _table()
    table["data"][2][0] = 4
    with pytest.raises(ValueError, match="contiguous"):
        lang.parse_language_table(table, label=HINDI)
    with pytest.raises(ValueError, match="missing required columns"):
        lang.parse_language_table(_table("🇫🇷 French"), label=HINDI)


def test_fetch_requests_each_language_average_view():
    calls = []

    class FakeClient:
        def __init__(self, url, *, verbose):
            assert (url, verbose) == (SPACE_APP_URL, False)

        def predict(self, **kwargs):
            calls.append(kwargs)
            return {"value": _table(kwargs["selected"][0])}

    boards = lang.fetch_open_asr_language_leaderboards(FakeClient)

    assert set(boards) == {
        lang.language_dataset_slug(label) for label in lang.LANGUAGE_BOARDS
    }
    assert calls[0] == {
        "version_id": "latest",
        "search_query": "",
        "show_proprietary": True,
        "selected": ["🇩🇪 German", "RTFx ⬆️️"],
        "zoom": "Language averages",
        "api_name": "/_render_multilingual_combined",
    }


def _add_hindi_board(session):
    session.add(Dataset(id=500, name="Open ASR Leaderboard — Hindi", slug=HINDI_SLUG))
    session.add(TaskDataset(task_id=12, dataset_id=500))
    session.add_all(
        [
            TaskDatasetMetric(task_id=12, dataset_id=500, metric_id=1),
            TaskDatasetMetric(task_id=12, dataset_id=500, metric_id=38),
        ]
    )
    session.add(
        Paper(
            id=3,
            title="Card only",
            source="external",
            source_url="https://huggingface.co/org/card-only",
            version="v1",
            is_latest_version=True,
        )
    )
    # English board rows give the language boards their papers.
    for paper_id, model_id in ((1, "org/model-a"), (3, "org/card-only")):
        session.add(
            Evaluation(
                paper_id=paper_id,
                task_id=12,
                dataset_id=181,
                model_name=model_id.split("/")[1],
                metrics={"WER": 5.0},
                best_metric="WER",
                is_open=True,
                hf_model_url=f"https://huggingface.co/{model_id}",
                num_parameters=600_000_000,
                external_source_url=SPACE_SOURCE_URL,
                methodology=(
                    f"{MANAGED_METHODOLOGY_PREFIX} Upstream model {model_id}; "
                    "rank 1; default Average WER; fetched x."
                ),
            )
        )
    session.commit()


def test_sync_publishes_only_paper_backed_models_and_is_idempotent():
    session = _session()
    _add_hindi_board(session)
    stale = Evaluation(
        paper_id=1,
        task_id=12,
        dataset_id=500,
        model_name="gone",
        metrics={"WER": 50.0},
        best_metric="WER",
        external_source_url=SPACE_SOURCE_URL,
        methodology=f"{MANAGED_METHODOLOGY_PREFIX} Upstream model org/gone; rank 9;",
    )
    session.add(stale)
    session.commit()
    boards = {HINDI_SLUG: lang.parse_language_table(_table(), label=HINDI)}
    now = datetime(2026, 11, 12, tzinfo=UTC)

    first = lang.OpenAsrLanguageSyncService(session).sync(boards, fetched_at=now)
    second = lang.OpenAsrLanguageSyncService(session).sync(boards, fetched_at=now)

    stats = first[HINDI_SLUG]
    assert (stats.created, stats.deleted, stats.matched) == (1, 1, 1)
    assert stats.unmatched_models == ["vendor/api-1"]
    assert stats.no_paper_models == ["org/card-only"]
    assert (second[HINDI_SLUG].created, second[HINDI_SLUG].updated) == (0, 1)
    row = session.query(Evaluation).filter(Evaluation.dataset_id == 500).one()
    assert row.paper_id == 1
    assert row.model_name == "model-a"
    assert row.metrics == {"WER": 9.6, "RTFx": 120.0}
    assert row.hf_model_url == "https://huggingface.co/org/model-a"
    assert row.num_parameters == 600_000_000
    assert row.best_rank == 1
    assert "Hindi average WER" in row.methodology
    assert session.query(PaperTask).filter(PaperTask.paper_id == 1).count() == 1


def test_sync_rejects_unknown_boards():
    session = _session()
    with pytest.raises(ValueError, match="not supported"):
        lang.OpenAsrLanguageSyncService(session).sync(
            {"open-asr-leaderboard": [OpenAsrEntry("o/m", 1, 1.0, None, True)]}
        )


def test_language_rows_inherit_english_rows_listed_with_a_runtime_suffix():
    session = _session()
    _add_hindi_board(session)
    english = session.query(Evaluation).filter(Evaluation.paper_id == 1).one()
    english.methodology = english.methodology.replace(
        "org/model-a;", "org/model-a (fast-gpu-asr);"
    )
    session.commit()
    boards = {HINDI_SLUG: lang.parse_language_table(_table(), label=HINDI)}

    stats = lang.OpenAsrLanguageSyncService(session).sync(boards)

    assert stats[HINDI_SLUG].matched == 1
    row = session.query(Evaluation).filter(Evaluation.dataset_id == 500).one()
    assert (row.paper_id, row.num_parameters) == (1, 600_000_000)
