"""Validation and idempotency tests for the living DeepSWE sync."""

from datetime import UTC, datetime

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
    ModelProviderAlias,
    ModelRelease,
    ModelReleaseArtifact,
    ModelReleaseSignal,
    Paper,
    PaperHfArtifact,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.deepswe_sync_service import (
    DEEPSWE_ENDPOINT,
    DEEPSWE_SOURCE_URL,
    HARNESS_NAME,
    MANAGED_METHODOLOGY_PREFIX,
    MODEL_DISPLAY_NAMES,
    MODEL_PAPER_IDENTITIES,
    DeepSweEntry,
    DeepSweLeaderboard,
    DeepSweSyncService,
    fetch_deepswe_leaderboard,
    parse_deepswe_leaderboard,
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
    rows = []
    for rank in range(40):
        model = f"model-{rank % 15}"
        rows.append(
            {
                "model": model,
                "harness": "mini-swe-agent",
                "reasoning_effort": "max" if rank < 15 else "high",
                "config": f"config-{rank}",
                "pass_at_1": 0.75 - rank / 100,
                "ci_half": 0.02,
                "n_attempted": 452,
                "n_tasks_attempted": 113,
                "n_runs": 4,
                "mean_cost_usd": 2.5,
                "mean_output_tokens": 50_000,
                "mean_agent_steps": 80,
                "provider": f"lab-{rank % 15}",
            }
        )
    return {
        "generated_at": "2026-08-13T16:11:55.708636+00:00",
        "n_tasks_in_set": 113,
        "rows": rows,
    }


def _entry(
    model: str,
    score: float,
    *,
    effort: str = "max",
    provider: str = "",
) -> DeepSweEntry:
    return DeepSweEntry(
        model=model,
        harness="mini-swe-agent",
        reasoning_effort=effort,
        config=f"{model}-{effort}",
        pass_at_1=score,
        ci_half=0.025,
        n_attempted=452,
        n_tasks_attempted=113,
        n_runs=4,
        mean_cost_usd=2.5,
        mean_output_tokens=50_000,
        mean_agent_steps=80,
        provider=provider,
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
            HfArtifact.__table__,
            PaperHfArtifact.__table__,
            ModelRelease.__table__,
            ModelReleaseArtifact.__table__,
            ModelProviderAlias.__table__,
            ModelReleaseSignal.__table__,
        ],
    )
    session = Session(engine)
    task = Task(id=15, name="Coding Agents", slug="coding-agents")
    dataset = Dataset(id=813, name="DeepSWE", slug="deepswe")
    metric = Metric(id=47, name="Pass@1", direction="higher_is_better", scale="0-1")
    session.add_all([task, dataset, metric])
    session.add(
        TaskDataset(task_id=task.id, dataset_id=dataset.id, supports_harness=True)
    )
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
                title="Introducing Claude Opus 5",
                source="external",
                source_url="https://www.anthropic.com/news/claude-opus-5",
                version="v1",
                is_latest_version=True,
            ),
            Paper(
                id=2,
                title="Kimi K3",
                arxiv_id="2607.24653",
                source="arxiv",
                version="v1",
                is_latest_version=True,
            ),
        ]
    )
    session.commit()
    return session


def test_parse_fetch_and_best_selection_contract():
    payload = _payload()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == DEEPSWE_ENDPOINT
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        leaderboard = fetch_deepswe_leaderboard(client)
    assert leaderboard.n_tasks == 113
    assert len(leaderboard.entries) == 40
    best = select_best_entries(leaderboard.entries)
    assert len(best) == 15
    assert best[0].config == "config-0"
    assert best[0].provider == "lab-0"


def test_parser_rejects_truncated_duplicate_or_wrong_harness_data():
    payload = _payload()
    payload["rows"] = payload["rows"][:10]
    with pytest.raises(ValueError, match="expected 40-100"):
        parse_deepswe_leaderboard(payload)

    payload = _payload()
    payload["rows"][1]["config"] = payload["rows"][0]["config"]
    with pytest.raises(ValueError, match="duplicate configs"):
        parse_deepswe_leaderboard(payload)

    payload = _payload()
    payload["rows"][0]["harness"] = "unknown-agent"
    with pytest.raises(ValueError, match="harness is invalid"):
        parse_deepswe_leaderboard(payload)


def test_every_named_upstream_model_has_a_release_identity():
    # The 28 upstream ids live on 2026-10-20 all have display names and papers.
    assert set(MODEL_DISPLAY_NAMES) == set(MODEL_PAPER_IDENTITIES)
    assert len(MODEL_PAPER_IDENTITIES) == 28


def test_sync_upserts_known_rows_and_preserves_unmatched_models():
    session = _session()
    session.add(
        Evaluation(
            paper_id=1,
            task_id=15,
            dataset_id=813,
            model_name="Claude Opus 5 (high)",
            methodology=(
                f"{MANAGED_METHODOLOGY_PREFIX} upstream_model=claude-opus-5; old."
            ),
            metrics={"Pass@1": 60},
            best_metric="Pass@1",
            harness=HARNESS_NAME,
            external_source_url=DEEPSWE_SOURCE_URL,
            source_url=DEEPSWE_SOURCE_URL,
            external=True,
        )
    )
    session.commit()
    leaderboard = DeepSweLeaderboard(
        generated_at=datetime(2026, 8, 13, 16, 11, tzinfo=UTC),
        n_tasks=113,
        entries=[
            _entry("claude-opus-5", 0.7365),
            _entry("kimi-k3", 0.6851),
            _entry("new-unmapped-model", 0.80),
        ],
    )

    stats = DeepSweSyncService(session).sync(leaderboard)
    assert stats.fetched_models == 3
    assert stats.matched == 2
    assert stats.created == 1
    assert stats.updated == 1
    assert stats.unmatched_models == ["new-unmapped-model"]
    rows = {row.model_name: row for row in session.query(Evaluation).all()}
    assert set(rows) == {"Claude Opus 5 (max)", "Kimi K3 (max)"}
    assert rows["Claude Opus 5 (max)"].metrics == {"Pass@1": 0.7365}
    assert rows["Kimi K3 (max)"].metrics == {"Pass@1": 0.6851}
    assert rows["Claude Opus 5 (max)"].is_open is False
    assert rows["Kimi K3 (max)"].is_open is True
    assert rows["Kimi K3 (max)"].harness == HARNESS_NAME
    assert rows["Kimi K3 (max)"].evaluated_on.isoformat() == "2026-08-13"

    second = DeepSweSyncService(session).sync(leaderboard)
    assert second.created == 0
    assert second.updated == 2
    assert session.query(Evaluation).count() == 2
    assert rows["Claude Opus 5 (max)"].metrics == {"Pass@1": 0.7365}
    # Without a lab there is nothing to hand to the release radar.
    assert session.query(ModelReleaseSignal).count() == 0


def test_unreviewed_models_match_a_model_release_or_become_signals():
    session = _session()
    session.add_all(
        [
            Paper(
                id=3,
                title="Introducing GPT-6.2 Terra",
                source="external",
                source_url="https://openai.com/index/introducing-gpt-6-2-terra",
                version="v1",
                is_latest_version=True,
            ),
            ModelRelease(
                id=1,
                paper_id=3,
                canonical_name="GPT-6.2 Terra",
                publisher="OpenAI",
                aliases=[],
                is_open=False,
            ),
        ]
    )
    session.commit()
    leaderboard = DeepSweLeaderboard(
        generated_at=datetime(2026, 8, 13, 16, 11, tzinfo=UTC),
        n_tasks=113,
        entries=[
            _entry("claude-opus-5", 0.7365),
            _entry("gpt-6-2-terra", 0.75, effort="high", provider="openai"),
            _entry("nova-2", 0.5, provider="newlab"),
        ],
    )

    stats = DeepSweSyncService(session).sync(leaderboard)
    assert (stats.auto_matched, stats.unmatched_models) == (
        ["gpt-6-2-terra"],
        ["nova-2"],
    )
    terra = (
        session.query(Evaluation)
        .filter(Evaluation.model_name == "gpt-6-2-terra (high)")
        .one()
    )
    assert (terra.paper_id, terra.is_open) == (3, False)
    assert "upstream_model=gpt-6-2-terra" in terra.methodology
    signal = session.query(ModelReleaseSignal).one()
    assert (signal.lab, signal.model_name) == ("newlab", "nova-2")
    assert signal.lead_url == DEEPSWE_SOURCE_URL

    second = DeepSweSyncService(session).sync(leaderboard)
    assert (second.created, second.updated) == (0, 2)
    assert session.query(ModelReleaseSignal).one().sightings == 2


def test_sync_ranks_fraction_scores_with_paper_native_results():
    session = _session()
    native = Evaluation(
        paper_id=1,
        task_id=15,
        dataset_id=813,
        model_name="Paper-native result",
        metrics={"Pass@1": 0.80},
        best_metric="Pass@1",
        harness=HARNESS_NAME,
    )
    session.add(native)
    session.commit()
    leaderboard = DeepSweLeaderboard(
        generated_at=datetime(2026, 8, 13, 16, 11, tzinfo=UTC),
        n_tasks=113,
        entries=[_entry("kimi-k3", 0.6851)],
    )

    DeepSweSyncService(session).sync(leaderboard)

    imported = session.query(Evaluation).filter_by(model_name="Kimi K3 (max)").one()
    assert native.best_rank == 1
    assert imported.best_rank == 2


def test_sync_deletes_only_disappeared_managed_rows():
    session = _session()
    session.add_all(
        [
            Evaluation(
                paper_id=1,
                task_id=15,
                dataset_id=813,
                model_name="Old managed model",
                methodology=(
                    f"{MANAGED_METHODOLOGY_PREFIX} upstream_model=gone-model; old."
                ),
                metrics={"Pass@1": 20},
                best_metric="Pass@1",
                harness=HARNESS_NAME,
                external_source_url=DEEPSWE_SOURCE_URL,
            ),
            Evaluation(
                paper_id=1,
                task_id=15,
                dataset_id=813,
                model_name="Manual model",
                methodology="Human curated.",
                metrics={"Pass@1": 10},
                best_metric="Pass@1",
                harness=HARNESS_NAME,
                external_source_url=DEEPSWE_SOURCE_URL,
            ),
        ]
    )
    session.commit()
    leaderboard = DeepSweLeaderboard(
        generated_at=datetime(2026, 8, 13, tzinfo=UTC),
        n_tasks=113,
        entries=[_entry("claude-opus-5", 0.70)],
    )

    stats = DeepSweSyncService(session).sync(leaderboard)
    assert stats.deleted == 1
    names = {row.model_name for row in session.query(Evaluation).all()}
    assert names == {"Claude Opus 5 (max)", "Manual model"}
