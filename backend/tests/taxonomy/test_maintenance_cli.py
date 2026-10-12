import json
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import cli, cli_admin, cli_papers
from backend.models.papers import (
    PaperSummary,
    RepositoryTrendingPaper,
    RepositoryTrendingRepository,
    RepositoryTrendingScore,
)
from backend.models.database import (
    Base,
    Area,
    Dataset,
    Metric,
    Paper,
    PaperTask,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.benchmark_admin_service import add_benchmark
from backend.services import paper_markdown_service
from backend.services.metric_admin_service import add_or_update_metric
from backend.services.task_admin_service import add_or_update_task


def test_search_command_defaults_to_hybrid():
    args = cli.build_parser().parse_args(["search", "vision-language models"])

    assert args.handler is cli_papers.search_papers
    assert args.query == "vision-language models"
    assert args.limit == 10
    assert args.mode == "hybrid"
    assert not args.json


def test_search_command_uses_retrieval_service_and_prints_json(monkeypatch, capsys):
    result = PaperSummary(
        id="42",
        title="A Hybrid Retrieval Paper",
        arxiv_id="2601.12345",
        authors=["Ada Lovelace", "Alan Turing"],
        published="2026-01-20",
        citation_count=7,
    )
    calls = []

    class FakeSessionContext:
        def __enter__(self):
            return "database-session"

        def __exit__(self, *_args):
            return None

    class FakePaperService:
        def __init__(self, db):
            calls.append(("init", db))

        def search_papers(self, query, limit, mode):
            calls.append(("search", query, limit, mode))
            return [result]

    fake_manager = type(
        "FakeDatabaseManager",
        (),
        {"session_local": staticmethod(FakeSessionContext)},
    )()
    monkeypatch.setattr(cli_papers, "db_manager", fake_manager)
    monkeypatch.setattr(cli_papers, "PaperService", FakePaperService)
    args = cli.build_parser().parse_args(
        ["search", "hybrid retrieval", "--limit", "3", "--json"]
    )

    assert args.handler(args) == 0
    assert calls == [
        ("init", "database-session"),
        ("search", "hybrid retrieval", 3, "hybrid"),
    ]
    assert json.loads(capsys.readouterr().out) == [result.model_dump(mode="json")]


def test_paper_read_commands_and_benchmark_list_parse():
    parser = cli.build_parser()
    info = parser.parse_args(["paper", "info", "2601.12345", "--json"])
    listing = parser.parse_args(["paper", "list", "--page-size", "5"])
    recent = parser.parse_args(["paper", "recent"])
    trending = parser.parse_args(["paper", "trending", "--max-age-days", "30"])
    related = parser.parse_args(["paper", "related", "2601.12345"])
    external = parser.parse_args(
        ["paper", "add-external", "https://example.com/research"]
    )
    benchmarks = parser.parse_args(
        ["benchmark", "list", "--task", "image-classification", "--json"]
    )

    assert info.handler is cli_papers.show_paper_info
    assert listing.handler is cli_papers.list_papers
    assert listing.page_size == 5
    assert recent.handler is cli_papers.list_recent_papers
    assert trending.handler is cli_papers.list_trending_papers
    assert trending.max_age_days == 30
    assert related.handler is cli_papers.list_related_papers
    assert related.limit == 4
    assert external.handler is cli_papers.add_external_paper
    assert benchmarks.handler is cli_admin.list_benchmarks


@pytest.mark.parametrize("json_output", [False, True])
def test_trending_cli_uses_repository_trending_service(
    monkeypatch, capsys, json_output
):
    result = RepositoryTrendingPaper(
        paper_id="42",
        arxiv_id="2601.12345",
        source="arxiv",
        source_url=None,
        title="A Trending Paper",
        abstract=None,
        authors=["Ada Lovelace"],
        date_published=None,
        thumbnail_url=None,
        tasks=[],
        repository=RepositoryTrendingRepository(
            id="7",
            url="https://github.com/example/repository",
            owner="example",
            name="repository",
            num_stars=100,
        ),
        trending=RepositoryTrendingScore(
            velocity_24h=1.25,
            trending_score=3.5,
            stars_gained_24h=30,
        ),
        paper_age_days=2.0,
        has_official_implementation=True,
        code_repository_count=1,
    )
    calls = []

    class FakeSessionContext:
        def __enter__(self):
            return "database-session"

        def __exit__(self, *_args):
            return None

    class FakePaperService:
        def __init__(self, db):
            calls.append(("init", db))

        def get_repository_trending_papers(self, **kwargs):
            calls.append(("trending", kwargs))
            return [result]

    monkeypatch.setattr(
        cli_papers,
        "db_manager",
        SimpleNamespace(session_local=FakeSessionContext),
    )
    monkeypatch.setattr(cli_papers, "PaperService", FakePaperService)
    command = [
        "paper",
        "trending",
        "--limit",
        "3",
        "--max-age-days",
        "30",
        "--min-velocity",
        "1.25",
    ]
    if json_output:
        command.append("--json")
    args = cli.build_parser().parse_args(command)

    assert args.handler(args) == 0
    assert calls == [
        ("init", "database-session"),
        (
            "trending",
            {"limit": 3, "max_age_days": 30, "min_velocity": 1.25},
        ),
    ]
    output = capsys.readouterr().out
    if json_output:
        assert json.loads(output) == [result.model_dump(mode="json")]
    else:
        assert output == (
            "1. A Trending Paper\n   2601.12345  score=3.500 velocity=1.250/h\n"
        )


def test_paper_info_prints_markdown_lineage_section(monkeypatch, capsys):
    paper = SimpleNamespace(
        title="A Paper",
        arxiv_id="2601.12345",
        id="42",
        published="2026-01-20",
        authors=["Ada Lovelace"],
        citation_count=7,
        url_abs="https://arxiv.org/abs/2601.12345",
        source_url=None,
        abstract="Paper abstract.",
        predecessor_papers=[
            SimpleNamespace(
                title="Earlier [Paper]",
                route_identifier="2501.00001",
                published="2025-01-01",
            )
        ],
        successor_papers=[
            SimpleNamespace(
                title="Later Paper",
                route_identifier="2701.00001",
                published=None,
            )
        ],
    )

    class FakeSessionContext:
        def __enter__(self):
            return "database-session"

        def __exit__(self, *_args):
            return None

    class FakePaperService:
        def __init__(self, db):
            assert db == "database-session"

        def get_paper_by_id_or_arxiv(self, reference, include_resources):
            assert reference == "2601.12345"
            assert not include_resources
            return paper

    fake_manager = SimpleNamespace(session_local=FakeSessionContext)
    monkeypatch.setattr(cli_papers, "db_manager", fake_manager)
    monkeypatch.setattr(cli_papers, "PaperService", FakePaperService)
    args = cli.build_parser().parse_args(["paper", "info", "2601.12345"])

    assert args.handler(args) == 0
    output = capsys.readouterr().out
    assert "\n## Paper lineage\n" in output
    assert "\n### Predecessors\n" in output
    assert (
        "- [Earlier \\[Paper\\]](https://paperswithcode.co/paper/2501.00001)"
        " (2025-01-01)"
    ) in output
    assert "\n### Successors\n" in output
    assert "- [Later Paper](https://paperswithcode.co/paper/2701.00001)" in output


def test_paper_info_prints_empty_lineage_groups(monkeypatch, capsys):
    paper = SimpleNamespace(
        title="An Unrelated Paper",
        arxiv_id="2601.12345",
        id="42",
        published=None,
        authors=[],
        citation_count=0,
        url_abs=None,
        source_url=None,
        abstract="",
        predecessor_papers=None,
        successor_papers=None,
    )

    class FakeSessionContext:
        def __enter__(self):
            return "database-session"

        def __exit__(self, *_args):
            return None

    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, _reference, include_resources):
            assert not include_resources
            return paper

    fake_manager = SimpleNamespace(session_local=FakeSessionContext)
    monkeypatch.setattr(cli_papers, "db_manager", fake_manager)
    monkeypatch.setattr(cli_papers, "PaperService", FakePaperService)
    args = cli.build_parser().parse_args(["paper", "info", "2601.12345"])

    assert args.handler(args) == 0
    output = capsys.readouterr().out
    assert "### Predecessors\n- None" in output
    assert "### Successors\n- None" in output


def test_paper_list_passes_api_filters_to_service(monkeypatch, capsys):
    calls = []
    page = SimpleNamespace(model_dump=lambda **_kwargs: {"count": 0, "results": []})

    class FakeSessionContext:
        def __enter__(self):
            return "database-session"

        def __exit__(self, *_args):
            return None

    class FakePaperService:
        def __init__(self, db):
            assert db == "database-session"

        def get_papers(self, **kwargs):
            calls.append(kwargs)
            return page

    fake_manager = SimpleNamespace(session_local=FakeSessionContext)
    monkeypatch.setattr(cli_papers, "db_manager", fake_manager)
    monkeypatch.setattr(cli_papers, "PaperService", FakePaperService)
    args = cli.build_parser().parse_args(
        [
            "paper",
            "list",
            "--page",
            "2",
            "--page-size",
            "5",
            "--conference",
            "ICLR",
            "--order-by",
            "citation_count",
            "--all-versions",
            "--json",
        ]
    )

    assert args.handler(args) == 0
    assert calls == [
        {
            "page": 2,
            "page_size": 5,
            "search": None,
            "published_after": None,
            "published_before": None,
            "conference": "ICLR",
            "latest_only": False,
            "order_by": "citation_count",
            "order_dir": "desc",
            "time_window": "all_time",
            "include_resources": False,
        }
    ]
    assert json.loads(capsys.readouterr().out) == {"count": 0, "results": []}


def test_add_external_rejects_invalid_date_before_ingestion():
    args = cli.build_parser().parse_args(
        [
            "paper",
            "add-external",
            "https://example.com/research",
            "--date-published",
            "July 22",
        ]
    )

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        args.handler(args)


def test_add_external_passes_overrides_to_ingestion_service(monkeypatch, capsys):
    calls = []
    paper = PaperSummary(
        id="42",
        title="External Research Release",
        source="external",
        source_url="https://example.com/research",
        authors=["Ada Lovelace"],
        published="2026-07-20",
    )
    result = SimpleNamespace(
        paper=paper,
        repositories_added=1,
        repositories_existing=0,
        hf_models_added=0,
        hf_datasets_added=0,
        hf_spaces_added=0,
        hf_artifacts_existing=0,
        authors_added=1,
        authors_existing=0,
    )

    class FakeSessionContext:
        def __enter__(self):
            return "database-session"

        def __exit__(self, *_args):
            return None

    class FakeExternalResourceService:
        def __init__(self, db):
            assert db == "database-session"

        async def add_from_url(self, **kwargs):
            calls.append(kwargs)
            return result

    monkeypatch.setattr(
        cli_papers, "db_manager", SimpleNamespace(session_local=FakeSessionContext)
    )
    monkeypatch.setattr(
        cli_papers, "ExternalResourceService", FakeExternalResourceService
    )
    args = cli.build_parser().parse_args(
        [
            "paper",
            "add-external",
            "https://example.com/research",
            "--date-published",
            "2026-07-20",
            "--title",
            "External Research Release",
            "--author",
            "Ada Lovelace",
            "--json",
        ]
    )

    assert args.handler(args) == 0
    assert calls[0]["source_url"] == "https://example.com/research"
    assert calls[0]["date_published"].isoformat() == "2026-07-20"
    assert calls[0]["title_override"] == "External Research Release"
    assert calls[0]["authors_override"] == ["Ada Lovelace"]
    assert json.loads(capsys.readouterr().out)["paper"]["id"] == "42"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(BigInteger, "sqlite")
def _compile_big_integer_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


def test_paper_index_and_update_commands_parse():
    index = cli.build_parser().parse_args(["paper", "index", "2501.12345", "--json"])
    update = cli.build_parser().parse_args(
        [
            "paper",
            "update",
            "2501.12345",
            "repositories",
            "https://github.com/example/official",
            "--unofficial",
            "https://github.com/example/community",
            "--json",
        ]
    )

    assert index.handler is cli_papers.index_paper
    assert index.arxiv_id == "2501.12345"
    assert update.handler is cli_papers.update_paper
    assert update.paper_update_command == "repositories"
    assert update.urls == ["https://github.com/example/official"]
    assert update.unofficial == ["https://github.com/example/community"]


def test_paper_read_command_prints_markdown(monkeypatch, capsys):
    args = cli.build_parser().parse_args(
        ["paper", "read", "https://paperswithcode.co/paper/1706.03762"]
    )
    monkeypatch.setattr(
        cli_papers,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "paper_markdown_hf_bucket_id": "owner/papers-content",
                "hf_token": "token",
            },
        )(),
    )
    calls = []

    def fake_read(arxiv_id, *, bucket_id, token):
        calls.append((arxiv_id, bucket_id, token))
        return "# Attention Is All You Need\n"

    monkeypatch.setattr(cli_papers, "read_paper_markdown", fake_read)

    assert args.handler is cli_papers.read_paper
    assert args.handler(args) == 0
    assert capsys.readouterr().out == "# Attention Is All You Need\n"
    assert calls == [("1706.03762", "owner/papers-content", "token")]


def test_paper_markdown_service_uses_hf_corpus_path(monkeypatch):
    calls = []

    def fake_download(bucket_id, files, *, raise_on_missing_files, token):
        calls.append((bucket_id, files[0][0], raise_on_missing_files, token))
        files[0][1].write_text("# Paper\n\nMarkdown body.\n", encoding="utf-8")

    monkeypatch.setattr(paper_markdown_service, "download_bucket_files", fake_download)

    markdown = paper_markdown_service.read_paper_markdown(
        "1706.03762v7",
        bucket_id="owner/papers-content",
        token="secret",
    )

    assert markdown == "# Paper\n\nMarkdown body.\n"
    assert calls == [("owner/papers-content", "1706/1706.03762.md", True, "secret")]


def test_benchmark_add_command_parses_repeatable_tasks_and_metrics(tmp_path):
    description = tmp_path / "description.md"
    description.write_text("A benchmark description.")
    args = cli.build_parser().parse_args(
        [
            "benchmark",
            "add",
            "ExampleBench",
            "--description-file",
            str(description),
            "--task",
            "question-answering",
            "--task",
            "42",
            "--metric",
            "Accuracy",
            "--source-paper",
            "2501.12345",
            "--supports-harness",
        ]
    )

    assert args.handler is cli_admin.add_benchmark_command
    assert args.task == ["question-answering", "42"]
    assert args.metric == ["Accuracy"]
    assert args.description_file == description
    assert args.supports_harness


def test_metric_add_command_parses_metadata():
    args = cli.build_parser().parse_args(
        [
            "metric",
            "add",
            "R@1 IoU=0.5",
            "--direction",
            "higher_is_better",
            "--full-name",
            "Recall at 1 with temporal IoU 0.5",
            "--scale",
            "0-100",
            "--description",
            "Percentage of queries localized at temporal IoU 0.5 or better.",
        ]
    )

    assert args.handler is cli_admin.add_metric_command
    assert args.direction == "higher_is_better"
    assert args.scale == "0-100"


def test_task_add_command_parses_parent_and_metadata(tmp_path):
    description = tmp_path / "description.md"
    description.write_text("A task description.")
    args = cli.build_parser().parse_args(
        [
            "task",
            "add",
            "video-temporal-grounding",
            "--name",
            "Video Temporal Grounding",
            "--description-file",
            str(description),
            "--keywords",
            "video temporal grounding, moment retrieval",
            "--area",
            "Video",
            "--parent",
            "video-understanding",
        ]
    )

    assert args.handler is cli_admin.add_task
    assert args.parent == "video-understanding"
    assert args.description_file == description


def test_add_task_is_idempotent_and_builds_hierarchy():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[Area.__table__, Task.__table__])
    session_local = sessionmaker(bind=engine)

    with session_local() as db:
        area = Area(name="Video")
        parent = Task(
            name="Video Understanding",
            slug="video-understanding",
            area=area,
            level=0,
        )
        db.add(parent)
        db.commit()

        inputs = {
            "slug": "video-temporal-grounding",
            "name": "Video Temporal Grounding",
            "description": "Locate evidence intervals in video.",
            "keywords": "video temporal grounding, moment retrieval",
            "area_name": "Video",
            "parent_reference": "video-understanding",
        }
        created = add_or_update_task(db, **inputs)
        updated = add_or_update_task(db, **inputs)
        task = db.execute(
            select(Task).where(Task.slug == "video-temporal-grounding")
        ).scalar_one()

    assert created.status == "created"
    assert updated.status == "updated"
    assert task.parent_id == parent.id
    assert task.level == 1
    assert task.area_id == area.id
    assert not hasattr(task, "is_visible")


def test_add_benchmark_is_idempotent_and_builds_native_source_links():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Paper.__table__,
            Task.__table__,
            Dataset.__table__,
            Metric.__table__,
            PaperTask.__table__,
            TaskDataset.__table__,
            TaskDatasetMetric.__table__,
        ],
    )
    session_local = sessionmaker(bind=engine)

    with session_local() as db:
        paper = Paper(
            title="The Example Benchmark",
            arxiv_id="2501.12345",
            version="v1",
            is_latest_version=True,
        )
        task = Task(name="Question Answering", slug="question-answering")
        metric = Metric(name="Accuracy", direction="higher_is_better")
        db.add_all([paper, task, metric])
        db.commit()

        inputs = {
            "name": "ExampleBench",
            "description": "A reproducible benchmark.",
            "task_references": ["question-answering"],
            "metric_names": ["Accuracy"],
            "source_paper": "2501.12345",
            "supports_harness": True,
            "full_name": "The Example Benchmark",
            "homepage": "https://example.com/benchmark",
        }
        created = add_benchmark(db, **inputs)
        existing = add_benchmark(db, **inputs)

        benchmark = db.execute(
            select(Dataset).where(Dataset.slug == "examplebench")
        ).scalar_one()
        paper_task = db.get(PaperTask, (paper.id, task.id))
        task_dataset = db.get(TaskDataset, (task.id, benchmark.id))
        metric_link = db.get(TaskDatasetMetric, (task.id, benchmark.id, metric.id))

    assert created.status == "created"
    assert existing.status == "existing"
    assert benchmark.paper_url == "https://paperswithcode.co/paper/2501.12345"
    assert benchmark.introducing_paper_id == paper.id
    assert benchmark.description == inputs["description"]
    assert benchmark.full_name == inputs["full_name"]
    assert benchmark.homepage == inputs["homepage"]
    assert paper_task.source == "manual"
    assert task_dataset.supports_harness
    assert metric_link is not None


def test_add_metric_is_idempotent_and_updates_metadata():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[Metric.__table__])
    session_local = sessionmaker(bind=engine)

    with session_local() as db:
        inputs = {
            "name": "R@1 IoU=0.5",
            "direction": "higher_is_better",
            "full_name": "Recall at 1 with temporal IoU 0.5",
            "scale": "0-100",
            "description": "Percentage localized at temporal IoU 0.5 or better.",
        }
        created = add_or_update_metric(db, **inputs)
        updated = add_or_update_metric(db, **inputs)
        metric = db.execute(
            select(Metric).where(Metric.name == "R@1 IoU=0.5")
        ).scalar_one()

    assert created.status == "created"
    assert updated.status == "updated"
    assert metric.full_name == inputs["full_name"]
    assert metric.direction == "higher_is_better"
    assert metric.scale == "0-100"
