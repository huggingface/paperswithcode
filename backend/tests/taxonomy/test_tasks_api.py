"""
Tests for the Tasks API endpoints.

Focused regression coverage for the homepage "Top Domains" sidebar, which
relies on `/api/v1/tasks/?ordering=-paper_count` returning the tasks with
the most associated papers first.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import create_app
from backend.models.database import (
    Base,
    Area as DBArea,
    Method as DBMethod,
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
    Paper as DBPaper,
    Task as DBTask,
    PaperTask,
    Repository as DBRepository,
    PaperRepository as DBPaperRepository,
    TaskDataset,
)
from backend.database.connection import get_database_session
from backend.config import get_settings
from backend.services.task_service import TaskService
from backend.services.discovery_page_service import DiscoveryPageService
from backend.database.tasks_setup.add_cvpr_coverage_tasks import ensure_task


# Trending scores older than 24h are treated as missing, so test repos/papers
# stamp a fresh timestamp to be eligible for the trending sort.
_FRESH = datetime.now(timezone.utc)
_STALE = datetime.now(timezone.utc) - timedelta(hours=48)


def _pin_trending_mode(monkeypatch, mode: str) -> None:
    """Force the active trending ranking mode for a test, regardless of env."""
    monkeypatch.setattr(get_settings(), "trending_ranking_mode", mode)


# The ORM uses Postgres-only types for unrelated columns; teach SQLite to
# render them as TEXT so the schema can be created in-memory for tests.
@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def register_jsonb_typeof(dbapi_connection, _connection_record):
    dbapi_connection.create_function("jsonb_typeof", 1, lambda _value: "array")


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_database_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)

    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)


def test_legacy_lowercase_3d_tracking_slug_resolves_canonical_task(client):
    db = TestingSessionLocal()
    db.add(
        DBTask(
            id=450,
            name="3D Tracking",
            slug="3D-tracking",
            level=0,
            image_data=b"gif89a",
            image_mime_type="image/gif",
        )
    )
    db.commit()
    db.close()

    response = client.get("/api/v1/tasks/3d-tracking")
    assert response.status_code == 200
    assert response.json()["slug"] == "3D-tracking"

    image_response = client.get("/api/v1/tasks/3d-tracking/image")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/gif"
    assert image_response.content == b"gif89a"


@pytest.fixture
def canonical_deepfake_task(client):
    db = TestingSessionLocal()
    db.add(
        DBTask(
            id=451,
            name="Deepfake Detection",
            slug="deepfake-detection",
            level=0,
        )
    )
    db.add(
        DBDataset(
            id=451,
            name="DeepSpeak v2.0",
            slug="deepspeak-v2-0",
        )
    )
    db.add(
        DBTask(
            id=452,
            name="Unrelated Task",
            slug="unrelated-task",
            level=0,
        )
    )
    db.add(
        DBDataset(
            id=452,
            name="Unrelated Benchmark",
            slug="unrelated-benchmark",
        )
    )
    db.add(TaskDataset(task_id=451, dataset_id=451))
    db.add(TaskDataset(task_id=452, dataset_id=452))
    db.add(
        DBPaper(
            id=451,
            title="DeepSpeak Result",
            abstract="Reports a DeepSpeak evaluation.",
            arxiv_id="2026.00451",
            version="v1",
            is_latest_version=True,
        )
    )
    db.add(
        DBEvaluation(
            id=451,
            paper_id=451,
            task_id=451,
            dataset_id=451,
            model_name="Detector",
            metrics={"F1": 0.9},
            best_metric="F1",
        )
    )
    db.commit()
    db.close()


def test_legacy_deepfake_slug_resolves_canonical_task(client, canonical_deepfake_task):
    response = client.get("/api/v1/tasks/deepfake-and-forensics")

    assert response.status_code == 200
    assert response.json()["slug"] == "deepfake-detection"


def test_legacy_deepfake_slug_filters_canonical_task_benchmarks(
    client, canonical_deepfake_task
):
    legacy = client.get("/api/v1/datasets/?task=deepfake-and-forensics&page_size=10")
    canonical = client.get("/api/v1/datasets/?task=deepfake-detection&page_size=10")

    assert legacy.status_code == canonical.status_code == 200
    assert [row["slug"] for row in legacy.json()["results"]] == ["deepspeak-v2-0"]
    assert legacy.json()["results"] == canonical.json()["results"]

    detail = client.get("/api/v1/datasets/deepspeak-v2-0?task=deepfake-and-forensics")
    assert detail.status_code == 200
    assert detail.json()["leaderboard_summary"]["task_slug"] == "deepfake-detection"


def test_legacy_deepfake_slug_resolves_trending_benchmarks(
    client, canonical_deepfake_task
):
    legacy = client.get(
        "/api/v1/tasks/deepfake-and-forensics/trending-benchmarks?min_recent_papers=0"
    )
    canonical = client.get(
        "/api/v1/tasks/deepfake-detection/trending-benchmarks?min_recent_papers=0"
    )

    assert legacy.status_code == canonical.status_code == 200
    assert legacy.json()["task_slug"] == "deepfake-detection"
    assert legacy.json() == canonical.json()


def test_legacy_deepfake_public_url_emits_canonical_link(
    client, canonical_deepfake_task
):
    legacy = client.get("/tasks/deepfake-and-forensics")
    canonical = client.get("/tasks/deepfake-detection")

    assert legacy.status_code == canonical.status_code == 200
    expected = (
        '<link rel="canonical" '
        'href="https://paperswithcode.co/tasks/deepfake-detection">'
    )
    assert expected in legacy.text
    assert expected in canonical.text


def test_legacy_deepfake_slug_filters_benchmark_discovery_page(
    client, canonical_deepfake_task
):
    db = TestingSessionLocal()
    try:
        page = DiscoveryPageService(db).benchmark(
            "deepspeak-v2-0", "deepfake-and-forensics"
        )
    finally:
        db.close()

    assert page is not None
    assert page.canonical_path == "/benchmark/deepspeak-v2-0"


def test_cvpr_task_setup_renames_legacy_deepfake_task_in_place(client):
    db = TestingSessionLocal()
    db.add(DBArea(id=451, name="General"))
    db.add(
        DBTask(
            id=460,
            name="Deepfake and Forensics",
            slug="deepfake-and-forensics",
            description="Existing description",
            keywords="deepfake detection",
            area_id=451,
            level=0,
        )
    )
    db.add(DBDataset(id=460, name="Existing Benchmark", slug="existing-benchmark"))
    db.add(TaskDataset(task_id=460, dataset_id=460))
    db.commit()

    task_id = ensure_task(
        db,
        {
            "slug": "deepfake-detection",
            "legacy_slugs": ("deepfake-and-forensics",),
            "name": "Deepfake and Forensics",
            "description": "Existing description",
            "keywords": "deepfake detection",
            "area_id": 451,
        },
    )
    db.commit()

    assert task_id == 460
    assert db.query(DBTask).filter(DBTask.slug == "deepfake-detection").one().id == 460
    assert db.query(DBTask).count() == 1
    assert db.get(TaskDataset, (460, 460)) is not None
    db.close()


@pytest.fixture
def tasks_with_uneven_paper_counts():
    """Create tasks linked to differing numbers of papers.

    Layout:
        - Language Modeling: 4 papers
        - Robotics: 3 papers
        - Object Detection: 1 paper
        - Speech Recognition: 0 papers
    """
    db = TestingSessionLocal()

    tasks = [
        DBTask(id=1, name="Language Modeling", slug="language-modeling", level=0),
        DBTask(id=2, name="Robotics", slug="robotics", level=0),
        DBTask(id=3, name="Object Detection", slug="object-detection", level=0),
        DBTask(id=4, name="Speech Recognition", slug="speech-recognition", level=0),
    ]
    db.add_all(tasks)

    papers = [
        DBPaper(
            id=i,
            title=f"Paper {i}",
            abstract=f"Abstract {i}",
            arxiv_id=f"2025.0{i:04d}",
            version="v1",
            is_latest_version=True,
        )
        for i in range(1, 9)
    ]
    db.add_all(papers)
    db.commit()

    associations = [
        # Language Modeling: 4 papers
        (1, 1),
        (2, 1),
        (3, 1),
        (4, 1),
        # Robotics: 3 papers
        (1, 2),
        (5, 2),
        (6, 2),
        # Object Detection: 1 paper
        (7, 3),
    ]
    db.add_all(
        PaperTask(paper_id=paper_id, task_id=task_id)
        for paper_id, task_id in associations
    )
    db.add_all(
        [
            DBDataset(id=1, name="LM Benchmark A", slug="lm-benchmark-a"),
            DBDataset(id=2, name="LM Benchmark B", slug="lm-benchmark-b"),
            DBDataset(id=3, name="Robotics Benchmark", slug="robotics-benchmark"),
        ]
    )
    db.add_all(
        [
            TaskDataset(task_id=1, dataset_id=1),
            TaskDataset(task_id=1, dataset_id=2),
            TaskDataset(task_id=2, dataset_id=3),
        ]
    )
    db.add_all(
        [
            DBEvaluation(
                id=1,
                paper_id=1,
                task_id=1,
                dataset_id=1,
                model_name="LM A",
                metrics={"Accuracy": 1},
            ),
            DBEvaluation(
                id=2,
                paper_id=2,
                task_id=1,
                dataset_id=2,
                model_name="LM B",
                metrics={"Accuracy": 2},
            ),
            DBEvaluation(
                id=3,
                paper_id=5,
                task_id=2,
                dataset_id=3,
                model_name="Robot A",
                metrics={"Success": 3},
            ),
        ]
    )
    db.commit()
    db.close()


def test_tasks_ordering_by_paper_count_desc(client, tasks_with_uneven_paper_counts):
    """`ordering=-paper_count` returns tasks ranked by paper count desc."""
    response = client.get("/api/v1/tasks/?ordering=-paper_count&page_size=8")

    assert response.status_code == 200
    data = response.json()

    names = [task["name"] for task in data["results"]]
    counts = [task["paper_count"] for task in data["results"]]

    assert names[:3] == ["Language Modeling", "Robotics", "Object Detection"]
    assert counts[:3] == [4, 3, 1]
    assert "Speech Recognition" in names
    assert counts == sorted(counts, reverse=True)


def test_tasks_ordering_by_paper_count_asc(client, tasks_with_uneven_paper_counts):
    """`ordering=paper_count` returns tasks ranked by paper count asc."""
    response = client.get("/api/v1/tasks/?ordering=paper_count&page_size=8")

    assert response.status_code == 200
    data = response.json()

    counts = [task["paper_count"] for task in data["results"]]
    assert counts == sorted(counts)
    assert counts[0] == 0
    assert counts[-1] == 4


def test_tasks_default_ordering_unaffected(client, tasks_with_uneven_paper_counts):
    """Default ordering still sorts by name and reports counts correctly."""
    response = client.get("/api/v1/tasks/?page_size=8")

    assert response.status_code == 200
    data = response.json()

    names = [task["name"] for task in data["results"]]
    assert names == sorted(names)

    counts_by_name = {task["name"]: task["paper_count"] for task in data["results"]}
    assert counts_by_name["Language Modeling"] == 4
    assert counts_by_name["Robotics"] == 3
    assert counts_by_name["Object Detection"] == 1
    assert counts_by_name["Speech Recognition"] == 0

    tasks_by_name = {task["name"]: task for task in data["results"]}
    assert tasks_by_name["Language Modeling"]["benchmark_count"] == 2
    assert tasks_by_name["Language Modeling"]["evaluation_count"] == 2
    assert tasks_by_name["Robotics"]["benchmark_count"] == 1
    assert tasks_by_name["Robotics"]["evaluation_count"] == 1
    assert tasks_by_name["Speech Recognition"]["benchmark_count"] == 0
    assert tasks_by_name["Speech Recognition"]["evaluation_count"] == 0


def test_task_page_returns_research_trends(client):
    """The bundled task page exposes the structured editorial bullets."""
    db = TestingSessionLocal()
    db.add(DBArea(id=1, name="Document Processing"))
    db.add(
        DBTask(
            id=1,
            name="OCR",
            slug="ocr",
            area_id=1,
            level=0,
            research_trends=["Trend one", "Trend two", "Trend three"],
        )
    )
    db.commit()
    db.close()

    response = client.get("/api/v1/tasks/ocr/page")

    assert response.status_code == 200
    assert response.json()["task"]["research_trends"] == [
        "Trend one",
        "Trend two",
        "Trend three",
    ]
    assert response.json()["area"]["id"] == "1"
    assert response.json()["area"]["name"] == "Document Processing"


@pytest.fixture
def parent_task_with_popular_subtask():
    """Create a top-level task and a more popular child subtask."""
    db = TestingSessionLocal()

    db.add(DBArea(id=1, name="Other"))
    db.add_all(
        [
            DBTask(
                id=10,
                name="Graph Machine Learning",
                slug="graph-machine-learning",
                area_id=1,
                level=0,
            ),
            DBTask(
                id=11,
                name="Node Classification",
                slug="node-classification",
                area_id=1,
                parent_id=10,
                level=1,
            ),
        ]
    )
    db.add_all(
        DBPaper(
            id=i,
            title=f"Graph paper {i}",
            abstract=f"Abstract {i}",
            arxiv_id=f"2025.1{i:04d}",
            version="v1",
            is_latest_version=True,
        )
        for i in range(1, 7)
    )
    db.commit()

    db.add(PaperTask(paper_id=1, task_id=10))
    db.add_all(PaperTask(paper_id=i, task_id=11) for i in range(2, 7))
    db.add_all(
        [
            DBDataset(id=10, name="Graph Benchmark", slug="graph-benchmark"),
            DBDataset(id=11, name="Node Benchmark", slug="node-benchmark"),
            TaskDataset(task_id=10, dataset_id=10),
            TaskDataset(task_id=11, dataset_id=11),
            DBEvaluation(
                id=10,
                paper_id=1,
                task_id=10,
                dataset_id=10,
                model_name="Graph Model",
                metrics={"Accuracy": 1},
            ),
            DBEvaluation(
                id=11,
                paper_id=2,
                task_id=11,
                dataset_id=11,
                model_name="Node Model",
                metrics={"Accuracy": 2},
            ),
        ]
    )
    db.commit()
    db.close()


def test_public_domain_lists_hide_child_subtasks(
    client, parent_task_with_popular_subtask
):
    """Top-level domain surfaces must not flatten child subtasks."""
    top_response = client.get("/api/v1/tasks/top?limit=8")
    assert top_response.status_code == 200
    top_slugs = [task["slug"] for task in top_response.json()]
    assert "graph-machine-learning" in top_slugs
    assert "node-classification" not in top_slugs

    taxonomy_response = client.get("/api/v1/areas/with-tasks/")
    assert taxonomy_response.status_code == 200
    area = taxonomy_response.json()["results"][0]
    taxonomy_slugs = [task["slug"] for task in area["tasks"]]
    assert taxonomy_slugs == ["graph-machine-learning"]
    assert area["tasks"][0]["benchmark_count"] == 1
    assert area["tasks"][0]["evaluation_count"] == 1


def test_grouped_task_benchmarks_are_bounded_and_popular_first(client):
    db = TestingSessionLocal()
    db.add(DBArea(id=1, name="Vision"))
    db.add(
        DBTask(
            id=1,
            name="Image Classification",
            slug="image-classification",
            area_id=1,
            level=0,
        )
    )
    db.add_all(
        [
            DBDataset(
                id=1,
                name="Popular Set",
                slug="popular-set",
                description="Popular benchmark",
                hf_url="https://huggingface.co/datasets/example/popular-set",
            ),
            DBDataset(id=2, name="Featured Set", slug="featured-set"),
        ]
    )
    db.add_all(
        [
            TaskDataset(task_id=1, dataset_id=1),
            TaskDataset(task_id=1, dataset_id=2),
        ]
    )
    db.add_all(
        DBPaper(
            id=i,
            title=f"Paper {i}",
            abstract="",
            arxiv_id=f"2607.{i:05d}",
            version="v1",
            is_latest_version=True,
        )
        for i in range(1, 5)
    )
    db.add_all(
        [
            DBEvaluation(
                id=1,
                paper_id=1,
                task_id=1,
                dataset_id=1,
                model_name="Popular 1",
                metrics={"Accuracy": 1},
            ),
            DBEvaluation(
                id=2,
                paper_id=2,
                task_id=1,
                dataset_id=1,
                model_name="Popular 2",
                metrics={"Accuracy": 2},
            ),
            DBEvaluation(
                id=3,
                paper_id=3,
                task_id=1,
                dataset_id=1,
                model_name="Popular 3",
                metrics={"Accuracy": 3},
            ),
            DBEvaluation(
                id=4,
                paper_id=4,
                task_id=1,
                dataset_id=2,
                model_name="Featured",
                metrics={"Accuracy": 4},
            ),
        ]
    )
    db.commit()
    db.close()

    response = client.get(
        "/api/v1/areas/with-task-benchmarks/?benchmarks_per_task=2&min_eval_count=1"
    )

    assert response.status_code == 200
    task = response.json()["results"][0]["tasks"][0]
    assert task["slug"] == "image-classification"
    assert [
        (benchmark["slug"], benchmark["evaluation_count"])
        for benchmark in task["benchmarks"]
    ] == [("popular-set", 3), ("featured-set", 1)]
    assert task["benchmarks"][0]["description"] == "Popular benchmark"
    assert task["benchmarks"][0]["hf_url"] == (
        "https://huggingface.co/datasets/example/popular-set"
    )


@pytest.fixture
def task_with_trending_papers():
    """Create one task with papers covering each trending edge case.

    Layout (all linked to task `audio-classification`):
      - Paper 1: official repo, trending_score=10.0 (highest score)
      - Paper 2: official repo, trending_score=2.5
      - Paper 3: official repo, trending_score=NULL (no fresh score)
      - Paper 4: non-official repo with trending_score=99.0 (must NOT win;
                 only official repos contribute to trending sort)
      - Paper 5: no repository at all
    """
    db = TestingSessionLocal()

    task = DBTask(
        id=1, name="Audio Classification", slug="audio-classification", level=0
    )
    db.add(task)

    papers = [
        DBPaper(
            id=i,
            title=f"Paper {i}",
            abstract=f"Abstract {i}",
            arxiv_id=f"2025.0{i:04d}",
            version="v1",
            is_latest_version=True,
        )
        for i in range(1, 6)
    ]
    db.add_all(papers)

    repositories = [
        DBRepository(
            id=1,
            url="https://github.com/owner/repo-1",
            owner="owner",
            name="repo-1",
            num_stars=500,
            trending_score=10.0,
            trending_score_updated_at=_FRESH,
        ),
        DBRepository(
            id=2,
            url="https://github.com/owner/repo-2",
            owner="owner",
            name="repo-2",
            num_stars=200,
            trending_score=2.5,
            trending_score_updated_at=_FRESH,
        ),
        DBRepository(
            id=3,
            url="https://github.com/owner/repo-3",
            owner="owner",
            name="repo-3",
            num_stars=50,
            trending_score=None,
        ),
        DBRepository(
            id=4,
            url="https://github.com/owner/repo-4",
            owner="owner",
            name="repo-4",
            num_stars=10000,
            trending_score=99.0,
            trending_score_updated_at=_FRESH,
        ),
    ]
    db.add_all(repositories)
    db.commit()

    db.add_all(
        [PaperTask(paper_id=i, task_id=1) for i in range(1, 6)]
        + [
            DBPaperRepository(paper_id=1, repository_id=1, is_official=True),
            DBPaperRepository(paper_id=2, repository_id=2, is_official=True),
            DBPaperRepository(paper_id=3, repository_id=3, is_official=True),
            DBPaperRepository(paper_id=4, repository_id=4, is_official=False),
        ]
    )
    db.commit()
    db.close()


def test_task_papers_trending_orders_by_official_repo_trending_score(
    client, task_with_trending_papers, monkeypatch
):
    """`order_by=trending` ranks task papers by their best official repo score."""
    _pin_trending_mode(monkeypatch, "github")
    response = client.get(
        "/api/v1/tasks/audio-classification/papers?order_by=trending&page_size=10"
    )

    assert response.status_code == 200
    data = response.json()

    titles = [paper["title"] for paper in data["results"]]

    # Papers 1 and 2 have official trending scores (10.0 and 2.5) and must
    # come first, in that order. The remaining three papers have no
    # qualifying official trending score and follow.
    assert titles[:2] == ["Paper 1", "Paper 2"]
    assert set(titles[2:]) == {"Paper 3", "Paper 4", "Paper 5"}
    assert data["count"] == 5


def test_task_papers_trending_ignores_non_official_repos(
    client, task_with_trending_papers, monkeypatch
):
    """A non-official repository's trending score must not influence ordering.

    Paper 4's only repo has `trending_score=99.0` but is not official, so it
    must not outrank Paper 1 (`trending_score=10.0` via official repo).
    """
    _pin_trending_mode(monkeypatch, "github")
    response = client.get(
        "/api/v1/tasks/audio-classification/papers?order_by=trending&page_size=10"
    )

    titles = [paper["title"] for paper in response.json()["results"]]

    assert titles.index("Paper 1") < titles.index("Paper 4")


def test_task_papers_trending_deduplicates_shared_official_repository(
    client, task_with_trending_papers, monkeypatch
):
    """A repository's trend signal belongs only to its newest task paper."""
    db = TestingSessionLocal()
    db.query(DBPaper).filter(DBPaper.id == 1).update(
        {DBPaper.date_published: date(2025, 1, 1)}
    )
    db.add(
        DBPaper(
            id=6,
            title="Paper 6 follow-up",
            abstract="A newer paper for repo-1",
            arxiv_id="2025.00006",
            version="v1",
            is_latest_version=True,
            date_published=date(2025, 2, 1),
        )
    )
    db.flush()
    db.add_all(
        [
            PaperTask(paper_id=6, task_id=1),
            DBPaperRepository(paper_id=6, repository_id=1, is_official=True),
        ]
    )
    db.commit()
    db.close()

    _pin_trending_mode(monkeypatch, "github")
    response = client.get(
        "/api/v1/tasks/audio-classification/papers?order_by=trending&page_size=10"
    )

    assert response.status_code == 200
    data = response.json()
    titles = [paper["title"] for paper in data["results"]]
    assert titles[0] == "Paper 6 follow-up"
    assert "Paper 1" not in titles
    assert data["count"] == 5

    default_response = client.get(
        "/api/v1/tasks/audio-classification/papers?page_size=10"
    )
    default_titles = [paper["title"] for paper in default_response.json()["results"]]
    assert {"Paper 1", "Paper 6 follow-up"}.issubset(default_titles)
    assert default_response.json()["count"] == 6


def test_task_papers_default_ordering_unchanged(client, task_with_trending_papers):
    """Default ordering (date_published desc) is unaffected by trending logic."""
    response = client.get("/api/v1/tasks/audio-classification/papers?page_size=10")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 5
    assert {paper["title"] for paper in data["results"]} == {
        f"Paper {i}" for i in range(1, 6)
    }


@pytest.fixture
def task_with_composite_trending_papers():
    """Papers exercising composite (paper-level) trending for a single task.

    All linked to task `composite-ranking`:
      - Paper 1: papers.trending_score=80 (fresh), official repo velocity 1.0
      - Paper 2: papers.trending_score=40 (fresh), official repo velocity 50.0
      - Paper 3: papers.trending_score=99 but STALE (must be ignored)
      - Paper 4: no paper-level trending_score

    Paper 1 must outrank Paper 2 by its higher *paper* score even though
    Paper 2's repo velocity is far higher, proving composite mode ranks by
    `papers.trending_score`, not official-repo velocity.
    """
    db = TestingSessionLocal()

    task = DBTask(id=1, name="Composite Ranking", slug="composite-ranking", level=0)
    db.add(task)

    paper_scores = {1: (80.0, _FRESH), 2: (40.0, _FRESH), 3: (99.0, _STALE), 4: None}
    papers = []
    for i in range(1, 5):
        score = paper_scores[i]
        papers.append(
            DBPaper(
                id=i,
                title=f"Paper {i}",
                abstract=f"Abstract {i}",
                arxiv_id=f"2025.1{i:04d}",
                version="v1",
                is_latest_version=True,
                trending_score=score[0] if score else None,
                trending_score_updated_at=score[1] if score else None,
            )
        )
    db.add_all(papers)

    repositories = [
        DBRepository(
            id=1,
            url="https://github.com/owner/repo-1",
            owner="owner",
            name="repo-1",
            num_stars=100,
            trending_score=1.0,
            trending_score_updated_at=_FRESH,
        ),
        DBRepository(
            id=2,
            url="https://github.com/owner/repo-2",
            owner="owner",
            name="repo-2",
            num_stars=100,
            trending_score=50.0,
            trending_score_updated_at=_FRESH,
        ),
    ]
    db.add_all(repositories)
    db.commit()

    db.add_all(
        [PaperTask(paper_id=i, task_id=1) for i in range(1, 5)]
        + [
            DBPaperRepository(paper_id=1, repository_id=1, is_official=True),
            DBPaperRepository(paper_id=2, repository_id=2, is_official=True),
        ]
    )
    db.commit()
    db.close()


def test_task_papers_trending_composite_ranks_by_paper_score(
    client, task_with_composite_trending_papers, monkeypatch
):
    """In composite mode, task papers rank by `papers.trending_score`."""
    _pin_trending_mode(monkeypatch, "composite")
    response = client.get(
        "/api/v1/tasks/composite-ranking/papers?order_by=trending&page_size=10"
    )

    assert response.status_code == 200
    data = response.json()
    titles = [paper["title"] for paper in data["results"]]

    # Paper 1 (score 80) and Paper 2 (score 40) lead in that order; the stale
    # and unscored papers follow without being dropped.
    assert titles[:2] == ["Paper 1", "Paper 2"]
    assert set(titles[2:]) == {"Paper 3", "Paper 4"}
    assert data["count"] == 4


def test_task_papers_trending_composite_puts_fresh_null_scores_last(
    client, task_with_composite_trending_papers, monkeypatch
):
    """A refreshed paper without a score must not outrank scored papers."""
    db = TestingSessionLocal()
    db.query(DBPaper).filter(DBPaper.id == 4).update(
        {DBPaper.trending_score_updated_at: _FRESH}
    )
    db.commit()
    db.close()

    _pin_trending_mode(monkeypatch, "composite")

    # SQLite sorts NULLs last for DESC while production PostgreSQL sorts them
    # first. Make this endpoint test reproduce the production dialect's NULL
    # ordering so the regression remains visible in the in-memory test suite.
    def emulate_postgres_desc_null_ordering(
        _conn, _cursor, statement, parameters, _context, _executemany
    ):
        return statement.replace(" END DESC", " END DESC NULLS FIRST"), parameters

    event.listen(
        engine,
        "before_cursor_execute",
        emulate_postgres_desc_null_ordering,
        retval=True,
    )
    try:
        response = client.get(
            "/api/v1/tasks/composite-ranking/papers?order_by=trending&page_size=10"
        )
    finally:
        event.remove(
            engine,
            "before_cursor_execute",
            emulate_postgres_desc_null_ordering,
        )

    assert response.status_code == 200
    titles = [paper["title"] for paper in response.json()["results"]]
    assert titles[:2] == ["Paper 1", "Paper 2"]
    assert set(titles[2:]) == {"Paper 3", "Paper 4"}


@pytest.fixture
def trending_dataset():
    """Build papers that exercise the trending-domains scoring.

    The recent window is the last 30 days; the baseline window is the 180
    days immediately preceding it. Layout:

      - rising_domain: 10 recent papers, 10 baseline papers. Big share lift
        because its share of recent papers far exceeds its baseline share.
      - flat_domain: 5 recent papers, 100 baseline papers. Historically
        dominant but no recent over-representation, so it must be filtered
        out by `share_lift > 1.0`.
      - small_domain: 3 recent papers, 4 baseline papers. Below the recent
        and baseline support gates and must be filtered out.
      - surging_niche: 6 recent papers, 5 baseline papers. Has the highest
        share lift in the dataset but a *lower* trend_score than
        rising_domain, so it proves the sort key is share_lift, not the
        volume-weighted composite. Excluded under default gates
        (baseline < 10) so existing tests are unaffected.
      - filler_domain_*: 1 recent each, 50 baseline each. Used to pad the
        baseline window so flat_domain's baseline share stays large.
    """
    db = TestingSessionLocal()

    today = date(2026, 5, 16)
    recent_start = today - timedelta(days=30)
    recent_day = today - timedelta(days=5)
    baseline_day = today - timedelta(days=120)

    tasks = [
        DBTask(id=1, name="Rising Domain", slug="rising-domain", level=0),
        DBTask(id=2, name="Flat Domain", slug="flat-domain", level=0),
        DBTask(id=3, name="Small Domain", slug="small-domain", level=0),
        DBTask(id=4, name="Filler A", slug="filler-a", level=0),
        DBTask(id=5, name="Filler B", slug="filler-b", level=0),
        DBTask(id=6, name="Surging Niche", slug="surging-niche", level=0),
    ]
    db.add_all(tasks)

    papers = []
    associations = []
    next_paper_id = 1

    def add_papers(count: int, published: date, task_id: int) -> None:
        nonlocal next_paper_id
        for _ in range(count):
            papers.append(
                DBPaper(
                    id=next_paper_id,
                    title=f"Paper {next_paper_id}",
                    abstract=f"Abstract {next_paper_id}",
                    arxiv_id=f"2025.{next_paper_id:05d}",
                    version="v1",
                    is_latest_version=True,
                    date_published=published,
                )
            )
            associations.append((next_paper_id, task_id))
            next_paper_id += 1

    add_papers(10, recent_day, 1)
    add_papers(10, baseline_day, 1)

    add_papers(5, recent_day, 2)
    add_papers(100, baseline_day, 2)

    add_papers(3, recent_day, 3)
    add_papers(4, baseline_day, 3)

    add_papers(1, recent_day, 4)
    add_papers(50, baseline_day, 4)
    add_papers(1, recent_day, 5)
    add_papers(50, baseline_day, 5)

    add_papers(6, recent_day, 6)
    add_papers(5, baseline_day, 6)

    db.add_all(papers)
    db.commit()
    db.add_all(
        PaperTask(paper_id=paper_id, task_id=task_id)
        for paper_id, task_id in associations
    )
    db.commit()
    db.close()

    assert recent_start < recent_day <= today
    assert baseline_day <= recent_start

    return today


def test_trending_tasks_rank_by_share_lift(client, trending_dataset):
    """A small, rapidly growing domain outranks a large, flat one."""
    today = trending_dataset

    db = TestingSessionLocal()
    try:
        service = TaskService(db)
        response = service.get_trending_tasks(today=today)
    finally:
        db.close()

    names = [t.name for t in response.results]
    assert "Rising Domain" in names
    assert "Flat Domain" not in names
    assert names[0] == "Rising Domain"

    rising = next(t for t in response.results if t.name == "Rising Domain")
    assert rising.recent_paper_count == 10
    assert rising.baseline_paper_count == 10
    assert rising.share_lift > 1.0
    assert rising.trend_score > 0


def test_trending_tasks_sorted_by_share_lift(client, trending_dataset):
    """Lift beats volume: results are ordered by descending share_lift, even
    when a higher-volume domain has a larger trend_score."""
    today = trending_dataset

    db = TestingSessionLocal()
    try:
        service = TaskService(db)
        response = service.get_trending_tasks(
            today=today,
            min_baseline_papers=5,
        )
    finally:
        db.close()

    lifts = [t.share_lift for t in response.results]
    assert lifts == sorted(lifts, reverse=True)

    names = [t.name for t in response.results]
    surging = next(t for t in response.results if t.name == "Surging Niche")
    rising = next(t for t in response.results if t.name == "Rising Domain")
    assert surging.share_lift > rising.share_lift
    assert surging.trend_score < rising.trend_score
    assert names.index("Surging Niche") < names.index("Rising Domain")


def test_trending_tasks_apply_support_gates(client, trending_dataset):
    """Domains below the support thresholds are dropped."""
    today = trending_dataset

    db = TestingSessionLocal()
    try:
        service = TaskService(db)
        response = service.get_trending_tasks(today=today)
    finally:
        db.close()

    names = [t.name for t in response.results]

    assert "Small Domain" not in names
    assert "Filler A" not in names
    assert "Filler B" not in names


def test_trending_tasks_endpoint_returns_metadata(client, trending_dataset):
    """The HTTP endpoint exposes window metadata and trend fields."""
    response = client.get("/api/v1/tasks/trending?limit=8")

    assert response.status_code == 200
    data = response.json()

    assert data["recent_days"] == 30
    assert data["baseline_days"] == 180
    assert isinstance(data["results"], list)

    if data["results"]:
        first = data["results"][0]
        for key in (
            "recent_paper_count",
            "baseline_paper_count",
            "share_lift",
            "trend_score",
            "slug",
            "name",
        ):
            assert key in first
        assert first["share_lift"] > 1.0


def test_trending_tasks_level_filter_excludes_subtasks(client, trending_dataset):
    """`level=0` must be applied before LIMIT and hide child subtasks."""
    today = trending_dataset
    db = TestingSessionLocal()
    try:
        db.add(
            DBTask(
                id=7,
                name="Rising Subtask",
                slug="rising-subtask",
                parent_id=1,
                level=1,
            )
        )
        db.add_all(PaperTask(paper_id=i, task_id=7) for i in range(1, 21))
        db.commit()

        service = TaskService(db)
        response = service.get_trending_tasks(today=today, limit=8, level=0)
    finally:
        db.close()

    results = response.results
    assert results
    assert all(task.level == 0 for task in results)
    assert "rising-subtask" not in {task.slug for task in results}


def test_trending_tasks_path_not_treated_as_slug(client, trending_dataset):
    """`/tasks/trending` must hit the trending route, not the slug route."""
    response = client.get("/api/v1/tasks/trending")

    assert response.status_code == 200
    body = response.json()
    assert "results" in body
    assert "recent_days" in body


@pytest.fixture
def tasks_with_image_keyword():
    """Tasks where 'image' appears in different fields to test title-first rank.

    Layout:
      - Image Classification: name match (prefix)
      - Image Matching: name match (prefix)
      - Image Understanding: name match (prefix)
      - Scene Understanding: description-only match ("uses image features")
      - Robotics: no match at all
    """
    db = TestingSessionLocal()

    tasks = [
        DBTask(
            id=1,
            name="Image Classification",
            slug="image-classification",
            description="Categorize images into classes.",
            level=0,
        ),
        DBTask(
            id=2,
            name="Image Matching",
            slug="image-matching",
            description="Match correspondences across views.",
            level=0,
        ),
        DBTask(
            id=3,
            name="Image Understanding",
            slug="image-understanding",
            description="Understand visual scene content.",
            level=0,
        ),
        DBTask(
            id=4,
            name="Scene Understanding",
            slug="scene-understanding",
            description="High-level reasoning that uses image features.",
            level=0,
        ),
        DBTask(
            id=5,
            name="Robotics",
            slug="robotics",
            description="Embodied agents acting in the world.",
            level=0,
        ),
    ]
    db.add_all(tasks)
    db.commit()
    db.close()


def test_tasks_search_uses_displayed_name_only(client, tasks_with_image_keyword):
    """`q=image` excludes tasks that mention the term only in descriptions."""
    response = client.get("/api/v1/tasks/?q=image&page_size=20")

    assert response.status_code == 200
    data = response.json()

    names = [task["name"] for task in data["results"]]

    assert names[:3] == [
        "Image Classification",
        "Image Matching",
        "Image Understanding",
    ]
    assert "Scene Understanding" not in names
    assert "Robotics" not in names


if __name__ == "__main__":
    pytest.main([__file__])


def test_task_children_and_parents_accept_slugs(client):
    db = TestingSessionLocal()
    db.add_all(
        [
            DBTask(id=900, name="Vision", slug="vision", level=0),
            DBTask(id=901, name="Detection", slug="detection", level=1, parent_id=900),
        ]
    )
    db.commit()
    db.close()

    children = client.get("/api/v1/tasks/vision/children")
    assert children.status_code == 200
    assert [task["id"] for task in children.json()["results"]] == ["901"]

    parents = client.get("/api/v1/tasks/detection/parents")
    assert parents.status_code == 200
    assert [task["id"] for task in parents.json()] == ["900"]


def test_task_children_and_parents_return_404_for_unknown_slug(client):
    assert client.get("/api/v1/tasks/missing-task/children").status_code == 404
    assert client.get("/api/v1/tasks/missing-task/parents").status_code == 404


def test_method_lookup_treats_like_wildcards_literally(client):
    db = TestingSessionLocal()
    db.add(DBMethod(id=950, name="Dropout", slug="dropout"))
    db.commit()
    db.close()

    assert client.get("/api/v1/methods/DROPOUT").json()["name"] == "Dropout"
    assert client.get("/api/v1/methods/%25").status_code == 404
    assert client.get("/api/v1/methods/drop_ut").status_code == 404
