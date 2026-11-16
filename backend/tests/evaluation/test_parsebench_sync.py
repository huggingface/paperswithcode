"""Validation and idempotency tests for the ParseBench live sync."""

import asyncio
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

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
    PaperTask,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services import parsebench_sync_service as pb
from backend.services.parsebench_sync_service import (
    EXCLUDED_PROVIDERS,
    MANAGED_METHODOLOGY_PREFIX,
    METRIC_NAMES,
    MODEL_PAPER_IDENTITIES,
    PARSEBENCH_CSV_URL,
    PARSEBENCH_SOURCE_URL,
    PRIMARY_METRIC_NAME,
    ParseBenchDiscovery,
    ParseBenchPaperDiscoveryService,
    ParseBenchSyncService,
    fetch_parsebench_leaderboard,
    parse_parsebench_leaderboard,
)
from backend.tests.evaluation.model_evidence import add_release_evidence


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


HEADER = (
    "Provider,Category,Overall,Tables,Charts,Content_Faithfulness,"
    "Semantic_Formatting,Visual_Grounding,Cost_Per_Page,Cost_Charts,"
    "Cost_Tables,Cost_Text,Cost_Layout,HF_Model_ID\n"
)


def _row(
    provider: str,
    overall: float,
    *,
    hf: str = "",
    cost: str = "",
    category: str = "VLM - Open Weight",
) -> str:
    return (
        f"{provider},{category},{overall},{overall + 1},{overall - 1},"
        f"{overall},{overall},{overall},{cost},,,,,{hf}\n"
    )


def _csv(count: int = 40) -> str:
    return HEADER + "".join(
        _row(f"model-{index}", 50 + index / 10, hf=f"org/model-{index}")
        for index in range(count)
    )


def _identities(count: int = 40) -> dict[str, pb.PaperIdentity]:
    return {
        f"model-{index}": pb.external(
            f"https://example.com/model-{index}",
            f"Model {index}",
            "2026-08-01",
            is_open=True,
        )
        for index in range(count)
    }


def _board(
    identities: dict[str, pb.PaperIdentity], excluded: frozenset[str] = frozenset()
) -> pb.ParseBenchBoard:
    return replace(pb.PARSEBENCH, identities=identities, excluded=excluded)


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
            HfArtifact.__table__,
            PaperHfArtifact.__table__,
            ModelRelease.__table__,
            ModelReleaseArtifact.__table__,
            ModelProviderAlias.__table__,
            ModelReleaseSignal.__table__,
        ],
    )
    session = Session(engine)
    task = Task(id=4, name="OCR", slug="ocr")
    dataset = Dataset(id=847, name="ParseBench", slug="parsebench")
    metrics = [
        Metric(id=100 + index, name=name, direction="higher_is_better")
        for index, name in enumerate(METRIC_NAMES)
    ]
    session.add_all([task, dataset, *metrics])
    session.add(TaskDataset(task_id=task.id, dataset_id=dataset.id))
    session.add_all(
        TaskDatasetMetric(task_id=task.id, dataset_id=dataset.id, metric_id=metric.id)
        for metric in metrics
    )
    session.add_all(
        Paper(
            id=1000 + index,
            title=f"Model {index}",
            source="external",
            source_url=f"https://example.com/model-{index}",
            version="v1",
            is_latest_version=True,
        )
        for index in range(40)
    )
    session.commit()
    return session


def _discovery(count: int = 40) -> ParseBenchDiscovery:
    return ParseBenchDiscovery(
        papers={
            f"https://example.com/model-{index}": 1000 + index for index in range(count)
        }
    )


def test_reviewed_identities_are_well_formed():
    assert not set(MODEL_PAPER_IDENTITIES) & EXCLUDED_PROVIDERS
    for identity in MODEL_PAPER_IDENTITIES.values():
        assert identity.key
    with pytest.raises(ValueError, match="exactly one stable identity"):
        pb.PaperIdentity()
    with pytest.raises(ValueError, match="title and publication date"):
        pb.PaperIdentity(source_url="https://example.com")


def test_parse_and_fetch_leaderboard_csv():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == PARSEBENCH_CSV_URL
        return httpx.Response(200, text=_csv())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        entries = fetch_parsebench_leaderboard(client)

    assert len(entries) == 40
    assert entries[0].provider == "model-0"
    assert entries[0].overall == 50
    assert entries[0].dimensions["Tables"] == 51
    assert entries[0].hf_model_id == "org/model-0"
    assert entries[0].cost_per_page_cents is None
    assert set(entries[0].metrics) == set(METRIC_NAMES)


def test_parser_rejects_malformed_upstream_data():
    with pytest.raises(ValueError, match="expected 40-400"):
        parse_parsebench_leaderboard(_csv(39))
    with pytest.raises(ValueError, match="missing columns"):
        parse_parsebench_leaderboard("Provider,Overall\nA,1\n")
    with pytest.raises(ValueError, match="repeats provider"):
        parse_parsebench_leaderboard(_csv() + _row("model-0", 10))
    with pytest.raises(ValueError, match="outside 0-100"):
        parse_parsebench_leaderboard(_csv() + _row("too-high", 101))
    with pytest.raises(ValueError, match="Tables is invalid"):
        parse_parsebench_leaderboard(
            _csv() + "blank,VLM - Open Weight,50,,50,50,50,50,,,,,,\n"
        )
    with pytest.raises(ValueError, match="HF model id is invalid"):
        parse_parsebench_leaderboard(_csv() + _row("bad-hf", 10, hf="no-slash"))


def test_sync_upserts_managed_rows_and_preserves_manual_rows():
    session = _session()
    identities = _identities()
    identities.pop("model-39")
    board = _board(identities, frozenset({"model-39"}))
    session.add_all(
        [
            Evaluation(
                paper_id=1000,
                task_id=4,
                dataset_id=847,
                model_name="Old label",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} provider=model-0; old",
                metrics={"Accuracy": 10},
                best_metric="Accuracy",
            ),
            Evaluation(
                paper_id=1000,
                task_id=4,
                dataset_id=847,
                model_name="Gone model",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} provider=gone; old",
                metrics={"Accuracy": 5},
                best_metric="Accuracy",
            ),
            Evaluation(
                paper_id=1000,
                task_id=4,
                dataset_id=847,
                model_name="Manual model",
                methodology="Human curated",
                metrics={PRIMARY_METRIC_NAME: 99},
                best_metric=PRIMARY_METRIC_NAME,
            ),
        ]
    )
    session.commit()
    csv_text = (
        HEADER
        + "".join(
            _row(f"model-{index}", 50 + index / 10, hf=f"org/model-{index}")
            for index in range(1, 40)
        )
        + _row("Brand New Product", 95)
        + _row("model-0", 70, cost="5.625")
    )
    entries = parse_parsebench_leaderboard(csv_text)

    first = ParseBenchSyncService(session, board).sync(entries, discovery=_discovery())
    assert first.to_dict() == {
        "fetched": 41,
        "matched": 39,
        "created": 38,
        "updated": 1,
        "adopted": 0,
        "deleted": 1,
        "excluded": 1,
        "auto_matched": [],
        "unreviewed": ["Brand New Product"],
        "missing_papers": [],
    }
    rows = {row.model_name: row for row in session.query(Evaluation).all()}
    assert "Gone model" not in rows and "Old label" not in rows
    assert "model-39" not in rows and "Brand New Product" not in rows
    assert rows["Manual model"].metrics == {PRIMARY_METRIC_NAME: 99}
    updated = rows["model-0"]
    assert updated.metrics[PRIMARY_METRIC_NAME] == 70
    assert updated.metrics["Tables"] == 71
    assert updated.best_metric == PRIMARY_METRIC_NAME
    assert updated.is_open is True
    assert updated.external is True
    assert updated.source_url == PARSEBENCH_SOURCE_URL
    assert updated.hf_model_url is None
    assert "5.625 cents/page" in updated.methodology
    assert rows["model-1"].hf_model_url == "https://huggingface.co/org/model-1"
    assert rows["Manual model"].best_rank == 1
    assert updated.best_rank == 2
    assert session.query(PaperTask).count() == 39

    second = ParseBenchSyncService(session, board).sync(entries, discovery=_discovery())
    assert second.created == 0
    assert second.updated == 39
    assert second.deleted == 0
    assert session.query(Evaluation).count() == 40


def test_unknown_models_match_announcements_or_become_radar_signals():
    session = _session()
    board = _board(_identities())
    session.add(
        Paper(
            id=2000,
            title="NovaOCR-3: Reading Every Page",
            source="external",
            source_url="https://example.com/novaocr-3",
            version="v1",
            is_latest_version=True,
        )
    )
    add_release_evidence(session, 2000)
    session.commit()
    entries = parse_parsebench_leaderboard(
        _csv()
        + _row("NovaOCR-3", 81, hf="nova-lab/NovaOCR-3")
        + _row("Ear-OCR-2", 77, hf="ear-lab/Ear-OCR-2")
        + _row("Anthropic Opus 9", 79, category="VLM - Proprietary")
        + _row("Acme Parse", 83, category="Commercial - Startup APIs")
    )

    first = ParseBenchSyncService(session, board).sync(entries, discovery=_discovery())
    second = ParseBenchSyncService(session, board).sync(entries, discovery=_discovery())

    assert first.auto_matched == second.auto_matched == ["NovaOCR-3"]
    assert first.unreviewed == ["Acme Parse", "Ear-OCR-2", "Anthropic Opus 9"]
    assert (first.created, second.created, second.updated) == (41, 0, 41)
    row = session.query(Evaluation).filter(Evaluation.paper_id == 2000).one()
    assert (row.model_name, row.metrics[PRIMARY_METRIC_NAME]) == ("NovaOCR-3", 81)
    assert row.is_open is True
    assert row.hf_model_url == "https://huggingface.co/nova-lab/NovaOCR-3"
    assert session.query(PaperTask).filter(PaperTask.paper_id == 2000).count() == 1
    # Products never become release signals; unmatched models do.
    signals = {
        signal.model_name: signal.lab
        for signal in session.query(ModelReleaseSignal).all()
    }
    assert signals == {"Ear-OCR-2": "ear-lab", "Opus 9": "Anthropic"}


def test_sync_refuses_when_reviewed_coverage_collapses():
    session = _session()
    with pytest.raises(RuntimeError, match="only 10 reviewed rows"):
        ParseBenchSyncService(session, _board(_identities(10))).sync(
            parse_parsebench_leaderboard(_csv()), discovery=_discovery()
        )
    assert session.query(Evaluation).count() == 0


def test_sync_requires_resolved_papers_unless_dry_run():
    session = _session()
    board = _board(_identities())
    entries = parse_parsebench_leaderboard(_csv())
    partial = _discovery(39)

    with pytest.raises(RuntimeError, match="No reviewed paper resolved for 'model-39'"):
        ParseBenchSyncService(session, board).sync(entries, discovery=partial)
    assert session.query(Evaluation).count() == 0

    stats = ParseBenchSyncService(session, board).sync(
        entries, discovery=partial, commit=False
    )
    assert stats.missing_papers == ["model-39"]
    assert stats.matched == 39
    assert session.query(Evaluation).count() == 0


def test_discovery_reuses_existing_and_indexes_missing_external_papers():
    session = _session()
    board = _board(
        {
            "Existing A": pb.external(
                "https://example.com/model-0", "Model 0", "2026-08-01"
            ),
            "Existing A (Thinking)": pb.external(
                "https://example.com/model-0", "Model 0", "2026-08-01"
            ),
            "New Model": pb.external(
                "https://example.com/new", "New Model", "2026-08-01"
            ),
        }
    )

    class External:
        def add_external_resource(self, payload):
            assert payload.date_published == date(2026, 8, 1)
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

    dry = asyncio.run(
        ParseBenchPaperDiscoveryService(
            session, board=board, external_service=External()
        ).discover(persist=False)
    )
    assert dry.papers == {"https://example.com/model-0": 1000}
    assert dry.would_index == ["https://example.com/new"]

    result = asyncio.run(
        ParseBenchPaperDiscoveryService(
            session, board=board, external_service=External()
        ).discover()
    )
    assert result.papers["https://example.com/model-0"] == 1000
    assert result.papers["https://example.com/new"]
    assert result.indexed_papers == ["https://example.com/new"]


@pytest.mark.parametrize(
    ("provider", "key"),
    [
        (
            "OpenAI GPT-6.1 Terra (Reasoning Medium)",
            "https://openai.com/index/introducing-gpt-6-1-terra",
        ),
        (
            "OpenAI GPT-6.1 Terra (Reasoning Low)",
            "https://openai.com/index/introducing-gpt-6-1-terra",
        ),
        ("OvisOCR3", "2610.33066"),
        ("Unlimited-OCR-2", "2610.39308"),
        ("Nemotron-3.5-Parse", "https://huggingface.co/nvidia/Nemotron-3.5-Parse"),
        ("MiniCPM-OCR 1.0", "https://huggingface.co/openbmb/MiniCPM-OCR-1.0"),
    ],
)
def test_new_upstream_providers_resolve_to_their_release(provider, key):
    assert MODEL_PAPER_IDENTITIES[provider].key == key
    assert provider not in EXCLUDED_PROVIDERS


def test_upstage_api_snapshot_is_a_reviewed_exclusion():
    assert "Upstage Document Parse 2 (Enhanced)" in EXCLUDED_PROVIDERS


V2_HEADER = (
    "Provider,Category,Overall,Text,Formatting,Tables,Charts,Visual_Grounding,"
    "Forms,Cost_Per_Page,Verified\n"
)


def _v2_row(provider: str, overall: float, category: str = "Open Weight") -> str:
    return (
        f"{provider},{category},{overall},{overall + 1},{overall},{overall},"
        f"{overall},{overall},{overall - 1},,yes\n"
    )


def _v2_csv(count: int = 40) -> str:
    return V2_HEADER + "".join(
        _v2_row(f"model-{index}", 50 + index / 10) for index in range(count)
    )


def _v2_session() -> Session:
    session = _session()
    session.add(Dataset(id=3422, name="ParseBench-2", slug="parsebench-2"))
    metrics = [
        Metric(id=200 + index, name=name, direction="higher_is_better")
        for index, name in enumerate(pb.PARSEBENCH_2.metric_names)
    ]
    session.add_all(metrics)
    session.add(TaskDataset(task_id=4, dataset_id=3422))
    session.add_all(
        TaskDatasetMetric(task_id=4, dataset_id=3422, metric_id=metric.id)
        for metric in metrics
    )
    session.commit()
    return session


def test_parsebench_2_reviewed_map_is_well_formed():
    board = pb.PARSEBENCH_2
    assert len(board.identities) == 40
    assert not set(board.identities) & board.excluded
    assert set(board.hf_model_ids) <= set(board.identities)
    # Open-weight rows carry their Hub checkpoint; API models do not.
    for label, identity in board.identities.items():
        assert (label in board.hf_model_ids) == identity.is_open, label
    assert board.identities["LlamaParse (Agentic Plus)"].title == (
        "ParseBench-2: Severity-Aware Evaluation of Document Parsing"
    )
    assert "Muse Ember 1.0 (low)" not in board.identities


def test_kdl_nano_v2_is_bound_to_the_kdl_release_on_both_boards():
    kdl = "https://huggingface.co/KDLAI/KDL-Frontier-Parser-nano"
    assert MODEL_PAPER_IDENTITIES["KDL-Frontier-Parser-nano-v2"].key == kdl
    assert pb.PARSEBENCH_2.identities["KDL-Frontier-Parser-nano-v2"].key == kdl


def test_parse_parsebench_2_csv():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == pb.PARSEBENCH_2_CSV_URL
        return httpx.Response(200, text=_v2_csv())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        entries = fetch_parsebench_leaderboard(client, pb.PARSEBENCH_2)

    assert len(entries) == 40
    assert entries[0].hf_model_id is None
    assert entries[0].metrics == {
        "Overall (ParseBench-2)": 50,
        "Text (ParseBench-2)": 51,
        "Formatting (ParseBench-2)": 50,
        "Tables (ParseBench-2)": 50,
        "Charts (ParseBench-2)": 50,
        "Visual Grounding (ParseBench-2)": 50,
        "Forms (ParseBench-2)": 49,
    }
    with pytest.raises(ValueError, match="ParseBench-2 CSV is missing columns"):
        parse_parsebench_leaderboard(HEADER + _row("x", 1), pb.PARSEBENCH_2)


def test_parsebench_2_adopts_hand_imported_rows_and_leaves_v1_alone():
    session = _v2_session()
    identities = _identities()
    board = replace(
        pb.PARSEBENCH_2,
        identities=identities,
        excluded=frozenset({"Reducto"}),
        hf_model_ids={"model-1": "org/model-1"},
    )
    session.add_all(
        [
            # The reviewed one-time import: same paper and label.
            Evaluation(
                paper_id=1000,
                task_id=4,
                dataset_id=3422,
                model_name="model-0",
                methodology="Imported 2026-11-16 from the official leaderboard.",
                metrics={"Overall (ParseBench-2)": 1},
                best_metric="Overall (ParseBench-2)",
            ),
            # Same label on another paper stays a separate manual row.
            Evaluation(
                paper_id=1002,
                task_id=4,
                dataset_id=3422,
                model_name="model-1",
                methodology="Human curated",
                metrics={"Overall (ParseBench-2)": 2},
                best_metric="Overall (ParseBench-2)",
            ),
            # The v1 board's managed rows are never touched by the v2 sync.
            Evaluation(
                paper_id=1000,
                task_id=4,
                dataset_id=847,
                model_name="model-0",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} provider=model-0; x",
                metrics={PRIMARY_METRIC_NAME: 3},
                best_metric=PRIMARY_METRIC_NAME,
            ),
        ]
    )
    session.commit()
    entries = parse_parsebench_leaderboard(
        _v2_csv()
        + _v2_row("Reducto", 90, category="Document Parsers")
        + _v2_row("Acme Parse", 80, category="Document Parsers"),
        board,
    )

    first = ParseBenchSyncService(session, board).sync(entries, discovery=_discovery())
    second = ParseBenchSyncService(session, board).sync(entries, discovery=_discovery())

    assert (first.adopted, first.created, first.updated) == (1, 39, 0)
    assert (second.adopted, second.created, second.updated) == (0, 0, 40)
    assert first.excluded == 1
    assert first.unreviewed == ["Acme Parse"]
    v2_rows = session.query(Evaluation).filter(Evaluation.dataset_id == 3422).all()
    assert len(v2_rows) == 41
    adopted = next(
        row for row in v2_rows if row.model_name == "model-0" and row.paper_id == 1000
    )
    assert adopted.metrics["Overall (ParseBench-2)"] == 50
    assert adopted.best_metric == "Overall (ParseBench-2)"
    assert adopted.methodology.startswith(
        "Managed by the Papers with Code ParseBench-2 live sync. provider=model-0;"
    )
    assert "six ParseBench-2 dimension scores" in adopted.methodology
    managed_1 = next(
        row for row in v2_rows if row.model_name == "model-1" and row.paper_id == 1001
    )
    assert managed_1.hf_model_url == "https://huggingface.co/org/model-1"
    manual = next(
        row for row in v2_rows if row.paper_id == 1002 and row.model_name == "model-1"
    )
    assert manual.methodology == "Human curated"
    v1 = session.query(Evaluation).filter(Evaluation.dataset_id == 847).one()
    assert v1.metrics == {PRIMARY_METRIC_NAME: 3}
