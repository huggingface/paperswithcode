"""Validation and idempotency tests for the living TabArena sync."""

from datetime import UTC, datetime
from io import StringIO

import httpx
import pandas as pd
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
    ProjectPage,
    Repository,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.tabarena_sync_service import (
    EXPECTED_COLUMNS,
    MANAGED_METHODOLOGY_PREFIX,
    METRIC_NAME,
    TABARENA_CSV_URL,
    TABARENA_SOURCE_URL,
    TabArenaEntry,
    TabArenaSyncService,
    fetch_tabarena_leaderboard,
    parse_tabarena_leaderboard,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


def _csv(row_count: int = 50, *, positions: list[int] | None = None) -> str:
    positions = positions or list(range(row_count))
    rows = []
    for index in range(row_count):
        rows.append(
            {
                "#": positions[index],
                "Type": "🧠⚡",
                "TypeName": "Foundation Model",
                "Model": f"[Model-{index} (default)](https://arxiv.org/abs/2601.{index:05d})",
                "Elo [⬆️]": 1800 - index,
                "Elo 95% CI": "+50/-40",
                "Score [⬆️]": 0.9 - index / 1000,
                "Rank [⬇️]": index + 1,
                "Harmonic Rank [⬇️]": index + 0.5,
                "Improvability (%) [⬇️]": index / 10,
                "Median Train Time (s/1K) [⬇️]": index + 0.1,
                "Median Predict Time (s/1K) [⬇️]": index + 0.01,
                "Verified": "✔️",
                "Imputed (%) [⬇️]": 0,
                "Imputed": False,
                "Hardware": "GPU",
                "MethodClass": "model",
                "Tags": "",
            }
        )
    return pd.DataFrame(rows, columns=EXPECTED_COLUMNS).to_csv(index=False)


def _entry(name: str, url: str, position: int, elo: float) -> TabArenaEntry:
    return TabArenaEntry(
        model_name=name,
        model_url=url,
        position=position,
        elo=elo,
        elo_ci="+50/-40",
        score=0.5,
        average_rank=2.0,
        harmonic_rank=1.5,
        improvability_pct=5.0,
        median_train_time=1.0,
        median_predict_time=0.1,
        verified=True,
        imputed_pct=0,
        hardware="GPU",
        tags=(),
    )


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
            Repository.__table__,
            PaperRepository.__table__,
            ProjectPage.__table__,
            PaperProjectPage.__table__,
            HfArtifact.__table__,
            PaperHfArtifact.__table__,
        ],
    )
    session = Session(engine)
    task = Task(id=328, name="Tabular Learning", slug="tabular-learning")
    dataset = Dataset(id=1834, name="TabArena-v0.1", slug="tabarena-v0-1")
    metric = Metric(id=93, name=METRIC_NAME, direction="higher_is_better")
    session.add_all([task, dataset, metric])
    session.add(TaskDataset(task_id=task.id, dataset_id=dataset.id))
    session.add(
        TaskDatasetMetric(
            task_id=task.id,
            dataset_id=dataset.id,
            metric_id=metric.id,
        )
    )
    session.add_all(
        [
            Paper(
                id=1,
                title="TabPFN-3",
                arxiv_id="2605.13986",
                source="arxiv",
                version="v1",
                is_latest_version=True,
            ),
            Paper(
                id=2,
                title="External model",
                source="external",
                source_url="https://github.com/example/model",
                version="v1",
                is_latest_version=True,
            ),
        ]
    )
    session.commit()
    return session


def test_parse_and_fetch_public_leaderboard_contract():
    csv_text = _csv()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == TABARENA_CSV_URL
        return httpx.Response(200, text=csv_text)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        entries = fetch_tabarena_leaderboard(client)
    assert len(entries) == 50
    assert entries[0].model_name == "Model-0 (default)"
    assert entries[-1].position == 49


def test_parser_accepts_current_optional_metadata_columns():
    frame = pd.read_csv(StringIO(_csv()))
    frame["Commercial"] = False
    frame["License"] = "MIT"

    entries = parse_tabarena_leaderboard(frame.to_csv(index=False))

    assert len(entries) == 50
    assert entries[0].model_name == "Model-0 (default)"


def test_parser_rejects_truncated_or_noncontiguous_data():
    with pytest.raises(ValueError, match="expected 50-200"):
        parse_tabarena_leaderboard(_csv(10))
    positions = list(range(50))
    positions[-1] = 51
    with pytest.raises(ValueError, match="contiguous"):
        parse_tabarena_leaderboard(_csv(positions=positions))


def test_sync_upserts_resolved_rows_and_deletes_only_stale_managed_rows():
    session = _session()
    session.add_all(
        [
            Evaluation(
                paper_id=1,
                task_id=328,
                dataset_id=1834,
                model_name="TabPFN-3 (default)",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} old",
                metrics={METRIC_NAME: 1200},
                best_metric=METRIC_NAME,
                external_source_url=TABARENA_SOURCE_URL,
                source_url=TABARENA_SOURCE_URL,
                external=True,
            ),
            Evaluation(
                paper_id=1,
                task_id=328,
                dataset_id=1834,
                model_name="Gone model (default)",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} old",
                metrics={METRIC_NAME: 1000},
                best_metric=METRIC_NAME,
                external_source_url=TABARENA_SOURCE_URL,
                source_url=TABARENA_SOURCE_URL,
                external=True,
            ),
            Evaluation(
                paper_id=1,
                task_id=328,
                dataset_id=1834,
                model_name="Manual row",
                methodology="Human curated",
                metrics={METRIC_NAME: 2000},
                best_metric=METRIC_NAME,
            ),
        ]
    )
    session.commit()

    entries = [
        _entry("TabPFN-3 (default)", "https://arxiv.org/abs/2605.13986", 0, 1600),
        _entry("External model (default)", "https://github.com/Example/Model", 1, 1500),
        _entry("Unmatched (default)", "https://example.com/unmatched", 2, 1400),
    ]
    now = datetime(2026, 8, 16, 8, 0, tzinfo=UTC)
    stats = TabArenaSyncService(session).sync(entries, fetched_at=now)

    assert stats.created == 1
    assert stats.updated == 1
    assert stats.deleted == 1
    assert stats.matched == 2
    assert stats.unmatched_sources == [
        "Unmatched (default):https://example.com/unmatched"
    ]
    rows = {row.model_name: row for row in session.query(Evaluation).all()}
    assert set(rows) == {"TabPFN-3 (default)", "External model (default)", "Manual row"}
    assert rows["TabPFN-3 (default)"].metrics == {METRIC_NAME: 1600}
    assert rows["TabPFN-3 (default)"].uses_additional_data is False
    assert rows["External model (default)"].paper_id == 2
    assert rows["Manual row"].best_rank == 1
    assert "all 51 datasets" in rows["TabPFN-3 (default)"].methodology

    second = TabArenaSyncService(session).sync(entries, fetched_at=now)
    assert second.created == 0
    assert second.updated == 2
    assert session.query(Evaluation).count() == 3


def test_current_unmatched_model_does_not_delete_previous_row():
    session = _session()
    session.add(
        Evaluation(
            paper_id=1,
            task_id=328,
            dataset_id=1834,
            model_name="Unmatched (default)",
            methodology=f"{MANAGED_METHODOLOGY_PREFIX} old",
            metrics={METRIC_NAME: 1200},
            best_metric=METRIC_NAME,
            external_source_url=TABARENA_SOURCE_URL,
            source_url=TABARENA_SOURCE_URL,
            external=True,
        )
    )
    session.commit()

    stats = TabArenaSyncService(session).sync(
        [_entry("Unmatched (default)", "https://example.com/unmatched", 0, 1300)]
    )
    assert stats.unmatched_sources
    assert (
        session.query(Evaluation).filter_by(model_name="Unmatched (default)").count()
        == 1
    )


def test_tabfm_refreshes_existing_blog_row_using_canonical_report():
    session = _session()
    url = "https://github.com/google-research/tabfm"
    session.add(
        Paper(
            id=3,
            title="TabFM: A Zero-Shot Foundation Model for Tabular Data",
            arxiv_id="2609.37959",
            source="arxiv",
            version="v1",
            is_latest_version=True,
        )
    )
    session.add(Repository(id=1, url=url))
    session.flush()
    session.add_all(
        [
            PaperRepository(paper_id=2, repository_id=1),
            PaperRepository(paper_id=3, repository_id=1),
        ]
    )
    row = Evaluation(
        paper_id=2,
        task_id=328,
        dataset_id=1834,
        model_name="TabFM (default)",
        methodology=f"{MANAGED_METHODOLOGY_PREFIX} old",
        metrics={METRIC_NAME: 1771},
        best_metric=METRIC_NAME,
        external_source_url=TABARENA_SOURCE_URL,
        source_url=TABARENA_SOURCE_URL,
        external=True,
    )
    session.add(row)
    session.commit()
    row_id = row.id

    stats = TabArenaSyncService(session).sync([_entry("TabFM (default)", url, 0, 1774)])

    assert stats.updated == 1
    assert stats.created == 0
    assert stats.unmatched_sources == []
    assert stats.missing_papers == []
    assert row.id == row_id
    assert row.paper_id == 3
    assert row.metrics == {METRIC_NAME: 1774}
    assert row.best_rank == 1


def test_tabfm_missing_canonical_report_does_not_fall_back_to_blog():
    session = _session()
    url = "https://github.com/google-research/tabfm"
    session.get(Paper, 2).source_url = url
    session.commit()

    stats = TabArenaSyncService(session).sync([_entry("TabFM (default)", url, 0, 1774)])

    assert stats.missing_papers == [f"{url}:2609.37959"]
    assert stats.created == 0
    assert session.query(Evaluation).count() == 0
