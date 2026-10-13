"""Parsing, import-policy, and adoption tests for the Physics-IQ Verified sync."""

from datetime import date
from pathlib import Path

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
    Metric,
    Paper,
    PaperTask,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.physics_iq_verified_sync_service import (
    MANAGED_METHODOLOGY_PREFIX,
    METRIC_BY_TRACK,
    MODEL_IDENTITIES,
    PHYSICS_IQ_README_URL,
    ModelIdentity,
    PhysicsIqSyncService,
    exclusion_reason,
    fetch_physics_iq_leaderboard,
    parse_physics_iq_leaderboard,
    select_entries,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


# Snapshot of the official README taken 2026-10-13, cut after both tables.
README = (
    Path(__file__).parent / "fixtures" / "physics_iq_verified_readme.md"
).read_text()

# The 33 rows hand-imported on 2026-10-13 and reviewed with the user:
# (model_name, track) -> stored score. Physis-Lang keeps the unrounded value
# submitted in its PR, which the README lists at one decimal.
PRODUCTION_ROWS = {
    ("Odyssey-3 Pro", "v2v"): 63.37,
    ("Odyssey-3 Pro", "i2v"): 49.99,
    ("Odyssey-3", "v2v"): 61.56,
    ("Odyssey-3", "i2v"): 48.83,
    ("FLUX 3 [large]", "v2v"): 61.11,
    ("FLUX 3 [large]", "i2v"): 51.11,
    ("MAGI-1 24B + GeoPhys (BoN)", "v2v"): 58.2,
    ("MAGI-1 24B + GeoPhys (BoN)", "i2v"): 33.7,
    ("MAGI-1 24B", "v2v"): 48.4,
    ("MAGI-1 24B", "i2v"): 30.2,
    ("Cosmos3-Super", "v2v"): 50.8,
    ("Cosmos3-Nano", "v2v"): 43.0,
    ("Cosmos3-Nano", "i2v"): 37.3,
    ("Cosmos3-Super-Image2Video", "i2v"): 42.7,
    ("Cosmos3-Edge", "i2v"): 32.7,
    ("Physis-Lang (Cosmos3 Super)", "i2v"): 48.23,
    ("Physis-Lang (Cosmos3 Nano)", "i2v"): 43.29,
    ("StrucPhysVideo-TI2V", "i2v"): 45.5,
    ("Seedance 2.5", "i2v"): 42.43,
    ("MiniMax H3", "i2v"): 39.8,
    ("MiniMax H3 Max", "i2v"): 36.2,
    ("Gemini Omni 1.1 Flash", "i2v"): 35.34,
    ("Gemini Omni Flash Preview", "i2v"): 33.36,
    ("Grok Imagine Video", "i2v"): 34.8,
    ("HunyuanVideo 1.5", "i2v"): 33.4,
    ("Wan2.2-I2V-A14B", "i2v"): 32.2,
    ("Wan2.2-TI2V-5B", "i2v"): 27.7,
    ("Veo 3.1 Lite", "i2v"): 31.83,
    ("Veo 3.1 Fast", "i2v"): 29.96,
    ("CogVideoX-5B", "i2v"): 31.8,
    ("Kandinsky-WM 1.0", "i2v"): 30.8,
    ("Sora 2", "i2v"): 26.5,
    ("P-Video", "i2v"): 25.3,
}
TASK_ID = 25
DATASET_ID = 2772


def _paper_keys() -> list[str]:
    return sorted({identity.paper_key for identity in MODEL_IDENTITIES.values()})


def _paper_id(key: str) -> int:
    return 1000 + _paper_keys().index(key)


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
    session.add(Task(id=TASK_ID, name="Video Generation", slug="video-generation"))
    session.add(
        Dataset(id=DATASET_ID, name="Physics-IQ Verified", slug="physics-iq-verified")
    )
    session.add(Dataset(id=DATASET_ID + 1, name="Other", slug="other"))
    metrics = [
        Metric(id=200 + index, name=name, direction="higher_is_better")
        for index, name in enumerate(METRIC_BY_TRACK.values())
    ]
    session.add_all(metrics)
    session.add(TaskDataset(task_id=TASK_ID, dataset_id=DATASET_ID))
    session.add_all(
        TaskDatasetMetric(task_id=TASK_ID, dataset_id=DATASET_ID, metric_id=metric.id)
        for metric in metrics
    )
    for key in _paper_keys():
        arxiv = not key.startswith("https://")
        session.add(
            Paper(
                id=_paper_id(key),
                title=key,
                arxiv_id=key if arxiv else None,
                source="arxiv" if arxiv else "external",
                source_url=None if arxiv else key,
                version="v1",
                is_latest_version=True,
            )
        )
    session.commit()
    return session


def _identity(model_name: str) -> ModelIdentity:
    return next(i for i in MODEL_IDENTITIES.values() if i.model_name == model_name)


def _seed_production(session: Session) -> None:
    for (model_name, track), score in PRODUCTION_ROWS.items():
        identity = _identity(model_name)
        session.add(
            Evaluation(
                paper_id=_paper_id(identity.paper_key),
                task_id=TASK_ID,
                dataset_id=DATASET_ID,
                model_name=model_name,
                metrics={METRIC_BY_TRACK[track]: score},
                methodology=f"Hand-reviewed notes for {model_name}.",
                best_metric=METRIC_BY_TRACK[track],
                is_open=identity.is_open,
                external=True,
            )
        )
    session.commit()


def _rows(session: Session) -> dict[tuple[str, str], Evaluation]:
    track_by_metric = {metric: track for track, metric in METRIC_BY_TRACK.items()}
    return {
        (row.model_name, track_by_metric[row.best_metric]): row
        for row in session.query(Evaluation)
        .filter(Evaluation.dataset_id == DATASET_ID)
        .all()
    }


def test_parse_and_fetch_readme_table():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == PHYSICS_IQ_README_URL
        return httpx.Response(200, text=README)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        entries = fetch_physics_iq_leaderboard(client)

    # Only the Verified table is read; the Original table follows it.
    assert len(entries) == 45
    assert [entry.position for entry in entries] == list(range(1, 46))
    flux = entries[2]
    assert flux.label == (
        "FLUX 3 [large] (Claude Opus 5.5 prompts) + WMReward + consensus (BoN)"
    )
    assert (flux.track, str(flux.score), str(flux.sd)) == ("v2v", "64.35", "0.22")
    assert flux.model_url == "https://bfl.ai/models/flux-3-video"
    assert flux.report_url == "https://github.com/felifri/flux3-physics-iq-prompts"
    odyssey = entries[0]
    assert odyssey.sd is None and odyssey.date_added == date(2026, 10, 8)
    assert entries[-1].label == "P-Video" and entries[-1].track == "i2v"


@pytest.mark.parametrize(
    "old, new, message",
    [
        ("### Physics-IQ Verified Leaderboard", "### Leaderboard", "no Verified"),
        ("| Physics-IQ verified |", "| Score |", "header changed"),
        ("| i2v | 25.3", "| t2v | 25.3", "input type is unknown"),
        ("| 25.3 <small>", "| 125.3 <small>", "outside 0-100"),
        ("| 25.3 <small>", "| n/a <small>", "score is invalid"),
        (
            "[P-Video](https://www.pruna.ai/p-video) reported",
            "[P-Video](https://www.pruna.ai/p-video) via",
            "no report link",
        ),
        ("| 45 | [P-Video]", "| 45 | | [P-Video]", "columns"),
        ("| 2026-06-17 |\n\n", "| 2026-17-06 |\n\n", "month must be"),
    ],
)
def test_parser_fails_loudly_on_layout_changes(old, new, message):
    assert old in README
    with pytest.raises(ValueError, match=message):
        parse_physics_iq_leaderboard(README.replace(old, new, 1))


def test_parser_enforces_row_bounds_and_uniqueness():
    lines = README.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("| 1 |"))
    short = "\n".join(lines[: first + 20] + lines[first + 45 :])
    with pytest.raises(ValueError, match="expected 30-300"):
        parse_physics_iq_leaderboard(short)
    duplicate = "\n".join(
        lines[: first + 45] + [lines[first + 44]] + lines[first + 45 :]
    )
    with pytest.raises(ValueError, match="repeats"):
        parse_physics_iq_leaderboard(duplicate)


def test_import_policy_selects_exactly_the_reviewed_rows():
    selection = select_entries(parse_physics_iq_leaderboard(README))

    assert {
        (identity.model_name, track) for identity, track in selection.entries
    } == set(PRODUCTION_ROWS)
    assert selection.excluded == {
        "third_party_best_of_n": 6,
        "anonymous_manuscript": 4,
    }
    # Odyssey-3's custom-prompt runs beat its best-practice-prompt runs.
    assert selection.superseded == ["Odyssey-3 (bpp) [v2v]", "Odyssey-3 (bpp) [i2v]"]
    assert selection.unreviewed == []
    for (identity, track), entry in selection.entries.items():
        assert float(entry.score) == pytest.approx(
            PRODUCTION_ROWS[(identity.model_name, track)], abs=0.05
        )


def test_exclusion_rules_keep_geophys_but_not_third_party_rerankers():
    entries = {
        (entry.position, entry.label): entry
        for entry in parse_physics_iq_leaderboard(README)
    }
    reasons = {key: exclusion_reason(entry) for key, entry in entries.items()}
    assert reasons[(7, "Magi-1 24B + GeoPhys (BoN) (op)")] is None
    assert (
        reasons[
            (
                1,
                "Odyssey-3 Pro + best-of-8 (WMReward + MBR consensus, rank-sum) "
                "(custom prompts)",
            )
        ]
        == "third_party_best_of_n"
    )
    assert (
        reasons[(11, "Physical Registry + PRS (BoN=8, Cosmos 3 Nano 16B) (bpp)")]
        == "anonymous_manuscript"
    )
    assert reasons[(15, "Physical Registry (Cosmos 3 Nano 16B) (bpp)")] == (
        "anonymous_manuscript"
    )
    for (_, label), reason in reasons.items():
        if reason is None:
            continue
        assert all(key[0] != label for key in MODEL_IDENTITIES)


def test_best_single_generation_run_wins_per_model_and_track():
    readme = README.replace(
        "| 40.99 <small>± 0.84</small>", "| 50.10 <small>± 0.5</small>"
    )
    selection = select_entries(parse_physics_iq_leaderboard(readme))
    odyssey_i2v = selection.entries[(_identity("Odyssey-3"), "i2v")]
    assert odyssey_i2v.label == "Odyssey-3 (bpp)"
    assert str(odyssey_i2v.score) == "50.10"
    assert "Odyssey-3 (custom prompts) [i2v]" in selection.superseded


def test_first_run_adopts_existing_rows_without_changes():
    session = _session()
    _seed_production(session)
    entries = parse_physics_iq_leaderboard(README)

    stats = PhysicsIqSyncService(session).sync(entries)

    assert (stats.matched, stats.adopted, stats.created, stats.changed) == (
        33,
        33,
        0,
        0,
    )
    assert stats.unreviewed == [] and stats.missing_papers == []
    rows = _rows(session)
    assert len(rows) == 33
    physis = rows[("Physis-Lang (Cosmos3 Super)", "i2v")]
    assert physis.metrics == {"Physics-IQ Verified Score (I2V)": 48.23}
    assert physis.methodology == (
        f"{MANAGED_METHODOLOGY_PREFIX} Official leaderboard entry "
        '"Physis-Lang (Cosmos3 Super)" (i2v): 48.2 ± 1.4, added 2026-09-28, '
        "reported at https://github.com/google-deepmind/physics-IQ-benchmark/pull/83. "
        "Hand-reviewed notes for Physis-Lang (Cosmos3 Super)."
    )
    assert physis.evaluated_on == date(2026, 9, 28)
    assert rows[("Odyssey-3", "i2v")].methodology.count("(custom prompts)") == 1
    assert physis.best_rank is not None

    again = PhysicsIqSyncService(session).sync(entries)
    assert (again.matched, again.adopted, again.created, again.changed) == (
        33,
        0,
        0,
        0,
    )
    assert _rows(session)[("Physis-Lang (Cosmos3 Super)", "i2v")].methodology == (
        physis.methodology
    )


def test_leaderboard_revisions_update_value_and_methodology():
    session = _session()
    _seed_production(session)
    PhysicsIqSyncService(session).sync(parse_physics_iq_leaderboard(README))
    revised = README.replace(
        "| 37.3 <small>± 0.9</small> | 2026-09-04 |",
        "| 38.1 <small>± 0.7</small> | 2026-10-20 |",
    ).replace("| 31.83 <small>± 0.32</small>", "| 31.83 <small>± 0.40</small>")

    stats = PhysicsIqSyncService(session).sync(parse_physics_iq_leaderboard(revised))

    assert (stats.matched, stats.changed, stats.adopted, stats.created) == (33, 2, 0, 0)
    rows = _rows(session)
    nano = rows[("Cosmos3-Nano", "i2v")]
    assert nano.metrics == {"Physics-IQ Verified Score (I2V)": 38.1}
    assert ": 38.1 ± 0.7, added 2026-10-20," in nano.methodology
    assert nano.methodology.endswith("Hand-reviewed notes for Cosmos3-Nano.")
    assert nano.evaluated_on == date(2026, 10, 20)
    assert rows[("Veo 3.1 Lite", "i2v")].metrics == {
        "Physics-IQ Verified Score (I2V)": 31.83
    }
    assert ": 31.83 ± 0.40," in rows[("Veo 3.1 Lite", "i2v")].methodology
    assert rows[("Cosmos3-Nano", "v2v")].metrics == {
        "Physics-IQ Verified Score (V2V)": 43.0
    }


def test_missing_mapped_rows_are_created_and_unmanaged_rows_untouched():
    session = _session()
    _seed_production(session)
    session.delete(_rows(session)[("Sora 2", "i2v")])
    manual = Evaluation(
        paper_id=_paper_id(_paper_keys()[0]),
        task_id=TASK_ID,
        dataset_id=DATASET_ID,
        model_name="Manual baseline",
        metrics={"Physics-IQ Verified Score (I2V)": 10.0},
        methodology="Curated by hand.",
        best_metric="Physics-IQ Verified Score (I2V)",
    )
    other_dataset = Evaluation(
        paper_id=_paper_id(_paper_keys()[0]),
        task_id=TASK_ID,
        dataset_id=DATASET_ID + 1,
        model_name="Sora 2",
        metrics={"Physics-IQ Verified Score (I2V)": 99.0},
        methodology="Other benchmark.",
        best_metric="Physics-IQ Verified Score (I2V)",
    )
    session.add_all([manual, other_dataset])
    session.commit()

    stats = PhysicsIqSyncService(session).sync(parse_physics_iq_leaderboard(README))

    assert (stats.matched, stats.created, stats.adopted) == (33, 1, 32)
    sora = _rows(session)[("Sora 2", "i2v")]
    assert sora.paper_id == _paper_id("https://openai.com/index/sora-2/")
    assert sora.metrics == {"Physics-IQ Verified Score (I2V)": 26.5}
    assert sora.is_open is False and sora.external is True
    assert sora.external_source_url == "https://arxiv.org/abs/2606.18943"
    assert sora.methodology.startswith(MANAGED_METHODOLOGY_PREFIX)
    assert not sora.methodology.endswith(" ")
    session.refresh(manual)
    session.refresh(other_dataset)
    assert manual.methodology == "Curated by hand."
    assert manual.metrics == {"Physics-IQ Verified Score (I2V)": 10.0}
    assert other_dataset.methodology == "Other benchmark."
    assert stats.missing_upstream == []


def test_unreviewed_models_and_missing_papers_are_reported_not_created():
    session = _session()
    _seed_production(session)
    session.delete(_rows(session)[("P-Video", "i2v")])
    session.query(Paper).filter(
        Paper.source_url == "https://www.pruna.ai/blog/p-video-fast-cheap-draft"
    ).delete()
    session.commit()
    papers_before = session.query(Paper).count()
    readme = README.replace(
        "| 45 | [P-Video]",
        "| 46 | [New Model](https://example.com) reported "
        "[here](https://example.com/report) | i2v | 20.0 | 2026-10-13 |\n"
        "| 45 | [P-Video]",
    )

    stats = PhysicsIqSyncService(session).sync(parse_physics_iq_leaderboard(readme))

    assert stats.unreviewed == ["New Model [i2v]"]
    assert stats.missing_papers == ["P-Video [i2v]"]
    assert (stats.matched, stats.created) == (32, 0)
    assert session.query(Paper).count() == papers_before
    assert len(_rows(session)) == 32


def test_managed_rows_dropped_upstream_are_reported_not_deleted():
    session = _session()
    _seed_production(session)
    PhysicsIqSyncService(session).sync(parse_physics_iq_leaderboard(README))
    lines = [line for line in README.splitlines() if "[Sora 2]" not in line]

    stats = PhysicsIqSyncService(session).sync(
        parse_physics_iq_leaderboard("\n".join(lines))
    )

    assert stats.missing_upstream == ["Sora 2 [Physics-IQ Verified Score (I2V)]"]
    assert ("Sora 2", "i2v") in _rows(session)


def test_dry_run_rolls_back_and_collapsed_selection_is_refused():
    session = _session()
    _seed_production(session)
    stats = PhysicsIqSyncService(session).sync(
        parse_physics_iq_leaderboard(README), commit=False
    )
    assert stats.adopted == 33
    assert all(
        row.methodology.startswith("Hand-reviewed") for row in _rows(session).values()
    )

    lines = README.splitlines()
    collapsed = "\n".join(
        line.replace("](", "-renamed](", 1)
        if line.startswith("| ") and line[2].isdigit()
        else line
        for line in lines
    )
    with pytest.raises(RuntimeError, match="refusing"):
        PhysicsIqSyncService(session).sync(parse_physics_iq_leaderboard(collapsed))


def test_adopting_a_stale_row_counts_as_a_change():
    session = _session()
    _seed_production(session)
    nano = _rows(session)[("Cosmos3-Nano", "i2v")]
    nano.metrics = {"Physics-IQ Verified Score (I2V)": 30.3}
    session.commit()

    stats = PhysicsIqSyncService(session).sync(parse_physics_iq_leaderboard(README))

    assert (stats.adopted, stats.changed) == (33, 1)
    assert _rows(session)[("Cosmos3-Nano", "i2v")].metrics == {
        "Physics-IQ Verified Score (I2V)": 37.3
    }


def test_unconfigured_leaderboard_is_refused():
    session = _session()
    session.query(TaskDatasetMetric).delete()
    session.commit()
    with pytest.raises(RuntimeError, match="not linked"):
        PhysicsIqSyncService(session).sync(parse_physics_iq_leaderboard(README))
