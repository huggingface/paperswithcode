"""Contract and idempotency tests for Artificial Analysis TTS quality sync."""

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
from backend.services import artificial_analysis_sync_service as aa
from backend.services import artificial_analysis_tts_sync_service as tts


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


def _model(
    slug: str,
    *,
    name: str | None = None,
    quality_elo: float | None = 1_100.5,
    is_open: bool | None = False,
) -> dict:
    return {
        "id": f"id-{slug}",
        "name": name or slug.replace("-", " ").title(),
        "shortName": name or slug.replace("-", " ").title(),
        "slug": slug,
        "url": f"/text-to-speech/models/{slug}",
        "providersUrl": f"/text-to-speech/providers/{slug}",
        "qualityElo": quality_elo,
        "highlight": False,
        "releaseDate": "2026-08-01",
        "isOpenWeights": is_open,
        "creator": {"name": "Example Lab"},
    }


def _next_html(models: list[dict]) -> str:
    payload = json.dumps(
        [1, "0:" + json.dumps({"providers": [{"model": model} for model in models]})]
    )
    return f"<html><body><script>self.__next_f.push({payload})</script></body></html>"


def test_parse_extracts_reviewed_models_from_next_payload(monkeypatch):
    monkeypatch.setattr(
        tts,
        "MODEL_PAPER_IDENTITIES",
        {
            "model-a": aa.PaperIdentity(arxiv_id="2608.00001", is_open=True),
            "model-b": aa.PaperIdentity(arxiv_id="2608.00002"),
        },
    )
    monkeypatch.setattr(tts, "MIN_EXPECTED_MODELS", 2)
    html = _next_html(
        [
            _model("model-a", name="Model A", quality_elo=1_234.5, is_open=True),
            _model("model-a", name="Model A", quality_elo=1_234.5, is_open=True),
            _model("model-b", name="Model B", quality_elo=987.25),
            _model("unreviewed", quality_elo=999.0),
        ]
    )

    entries = tts.parse_artificial_analysis_tts_leaderboard(html)

    assert entries == [
        tts.ArtificialAnalysisTtsEntry("model-a", "Model A", 1_234.5, True),
        tts.ArtificialAnalysisTtsEntry("model-b", "Model B", 987.25, False),
    ]


def test_parse_uses_reviewed_open_status_when_upstream_flag_is_missing(monkeypatch):
    monkeypatch.setattr(
        tts,
        "MODEL_PAPER_IDENTITIES",
        {"model-a": aa.PaperIdentity(arxiv_id="2608.00001", is_open=True)},
    )
    monkeypatch.setattr(tts, "MIN_EXPECTED_MODELS", 1)
    model = _model("model-a")
    model.pop("isOpenWeights")

    entries = tts.parse_artificial_analysis_tts_leaderboard(_next_html([model]))

    assert entries == [
        tts.ArtificialAnalysisTtsEntry("model-a", "Model A", 1_100.5, True)
    ]


def test_parse_rejects_missing_reviewed_model(monkeypatch):
    monkeypatch.setattr(
        tts,
        "MODEL_PAPER_IDENTITIES",
        {
            "model-a": aa.PaperIdentity(arxiv_id="2608.00001"),
            "model-b": aa.PaperIdentity(arxiv_id="2608.00002"),
        },
    )
    monkeypatch.setattr(tts, "MIN_EXPECTED_MODELS", 1)

    with pytest.raises(ValueError, match="missing reviewed models.*model-b"):
        tts.parse_artificial_analysis_tts_leaderboard(_next_html([_model("model-a")]))


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
    task = Task(id=24, name="Text-to-speech", slug=tts.TASK_SLUG)
    dataset = Dataset(
        id=2_300,
        name="Artificial Analysis TTS Quality",
        slug=tts.DATASET_SLUG,
    )
    metric = Metric(id=77, name=tts.METRIC_NAME, direction="higher_is_better")
    paper = Paper(
        id=9,
        title="Model A Report",
        arxiv_id="2608.00001",
        source="arxiv",
        version="v1",
        is_latest_version=True,
    )
    session.add_all([task, dataset, metric, paper])
    session.add(
        TaskDatasetMetric(task_id=task.id, dataset_id=dataset.id, metric_id=metric.id)
    )
    session.commit()
    return session


def test_sync_updates_only_managed_rows_and_is_idempotent(monkeypatch):
    session = _session()
    monkeypatch.setattr(
        tts,
        "MODEL_PAPER_IDENTITIES",
        {"model-a": aa.PaperIdentity(arxiv_id="2608.00001", is_open=True)},
    )
    session.add_all(
        [
            Evaluation(
                paper_id=9,
                task_id=24,
                dataset_id=2_300,
                model_name="Old label",
                metrics={tts.METRIC_NAME: 1.0},
                best_metric=tts.METRIC_NAME,
                external_source_url=f"{tts.SOURCE_URL_PREFIX}model-a",
                methodology=tts.MANAGED_METHODOLOGY_PREFIX,
            ),
            Evaluation(
                paper_id=9,
                task_id=24,
                dataset_id=2_300,
                model_name="Manual result",
                metrics={tts.METRIC_NAME: 2.0},
                best_metric=tts.METRIC_NAME,
            ),
        ]
    )
    session.commit()
    manual_before = (
        session.query(Evaluation).filter(Evaluation.model_name == "Manual result").one()
    )
    manual_values = (
        manual_before.paper_id,
        manual_before.metrics,
        manual_before.external_source_url,
        manual_before.source_url,
        manual_before.methodology,
    )
    entries = [tts.ArtificialAnalysisTtsEntry("model-a", "Model A", 1_234.5, True)]
    discovery = aa.ArtificialAnalysisDiscovery(papers={"model-a": 9})
    now = datetime(2026, 8, 28, 12, 30, tzinfo=UTC)

    first = tts.ArtificialAnalysisTtsSyncService(session).sync(
        entries, discovery=discovery, fetched_at=now
    )
    second = tts.ArtificialAnalysisTtsSyncService(session).sync(
        entries, discovery=discovery, fetched_at=now
    )

    managed = (
        session.query(Evaluation)
        .filter(Evaluation.external_source_url == f"{tts.SOURCE_URL_PREFIX}model-a")
        .one()
    )
    assert (first.created, first.updated, first.matched) == (0, 1, 1)
    assert (second.created, second.updated, second.matched) == (0, 1, 1)
    assert managed.model_name == "Model A"
    assert managed.metrics == {tts.METRIC_NAME: 1_234.5}
    assert managed.paper_id == 9
    assert managed.is_open is True
    assert managed.evaluated_on.isoformat() == "2026-08-28"
    assert session.query(Evaluation).count() == 2
    assert session.query(PaperTask).one().source == "auto"
    manual_after = (
        session.query(Evaluation).filter(Evaluation.model_name == "Manual result").one()
    )
    assert (
        manual_after.paper_id,
        manual_after.metrics,
        manual_after.external_source_url,
        manual_after.source_url,
        manual_after.methodology,
    ) == manual_values


def test_sync_adds_one_task_tag_when_model_variants_share_a_paper(monkeypatch):
    session = _session()
    identity = aa.PaperIdentity(arxiv_id="2608.00001", is_open=True)
    monkeypatch.setattr(
        tts,
        "MODEL_PAPER_IDENTITIES",
        {"model-a": identity, "model-a-flash": identity},
    )
    entries = [
        tts.ArtificialAnalysisTtsEntry("model-a", "Model A", 1_234.5, True),
        tts.ArtificialAnalysisTtsEntry("model-a-flash", "Model A Flash", 1_200.0, True),
    ]
    discovery = aa.ArtificialAnalysisDiscovery(
        papers={"model-a": 9, "model-a-flash": 9}
    )

    stats = tts.ArtificialAnalysisTtsSyncService(session).sync(
        entries, discovery=discovery
    )

    assert (stats.created, stats.matched) == (2, 2)
    assert session.query(Evaluation).count() == 2
    assert session.query(PaperTask).count() == 1


def _current_reviewed_catalog() -> list[dict]:
    slugs = (set(tts.MODEL_PAPER_IDENTITIES) - {"st260629"}) | {"step-audio-2.5-tts"}
    return [
        *[_model(slug) for slug in sorted(slugs)],
        *[_model(f"unreviewed-{index}") for index in range(tts.MIN_EXPECTED_MODELS)],
    ]


def test_parse_requires_current_stepaudio_catalog_model():
    entries = tts.parse_artificial_analysis_tts_leaderboard(
        _next_html(_current_reviewed_catalog())
    )

    assert len(entries) == 14
    assert "st260629" not in {entry.slug for entry in entries}
    assert "step-audio-2.5-tts" in {entry.slug for entry in entries}
    assert tts.MODEL_PAPER_IDENTITIES["step-audio-2.5-tts"].arxiv_id == "2605.23463"


def test_retired_stepaudio_slug_cannot_replace_current_required_model():
    models = [
        model
        for model in _current_reviewed_catalog()
        if model["slug"] != "step-audio-2.5-tts"
    ]
    models.append(_model("st260629"))

    with pytest.raises(ValueError, match="missing reviewed models.*step-audio-2.5-tts"):
        tts.parse_artificial_analysis_tts_leaderboard(_next_html(models))


@pytest.mark.parametrize("commit", [False, True])
def test_sync_retires_only_owned_removed_stepaudio_results(monkeypatch, commit):
    session = _session()
    monkeypatch.setattr(
        tts,
        "MODEL_PAPER_IDENTITIES",
        {"step-audio-2.5-tts": aa.PaperIdentity(arxiv_id="2605.23463")},
    )
    for name, methodology in (
        ("Retired managed", tts.MANAGED_METHODOLOGY_PREFIX),
        ("Manual result", "Manually entered"),
    ):
        session.add(
            Evaluation(
                paper_id=9,
                task_id=24,
                dataset_id=2_300,
                model_name=name,
                metrics={tts.METRIC_NAME: 1205.9},
                best_metric=tts.METRIC_NAME,
                external_source_url=f"{tts.SOURCE_URL_PREFIX}st260629",
                methodology=methodology,
            )
        )
    session.commit()
    stats = tts.ArtificialAnalysisTtsSyncService(session).sync(
        [
            tts.ArtificialAnalysisTtsEntry(
                "step-audio-2.5-tts", "StepAudio 2.5 TTS", 1178.89, False
            )
        ],
        discovery=aa.ArtificialAnalysisDiscovery(papers={"step-audio-2.5-tts": 9}),
        commit=commit,
    )
    names = {row.model_name for row in session.query(Evaluation).all()}
    assert "Manual result" in names
    assert ("Retired managed" in names) is not commit
    assert ("StepAudio 2.5 TTS" in names) is commit
    assert stats.retired == 1
