"""Behavioral characterization of general and task feed selection on local SQL."""

import json
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import (
    Base,
    Paper,
    Task,
    PaperTask,
    Repository,
    PaperRepository,
    HfArtifact,
    PaperHfArtifact,
)
from backend.models.papers import Paper as PaperCard
from backend.services.paper_service import PaperService
from backend.services.task_service import TaskService


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
def _sqlite_json(_type, _compiler, **_kwargs):
    return "TEXT"


@pytest.fixture
def feeds(monkeypatch):
    engine = create_engine("sqlite://")
    # PostgreSQL ``cardinality`` over the JSON the SQLite array variant stores.
    event.listen(
        engine,
        "connect",
        lambda connection, _record: connection.create_function(
            "cardinality", 1, lambda value: len(json.loads(value or "null") or [])
        ),
    )
    Base.metadata.create_all(
        engine,
        tables=[
            model.__table__
            for model in (
                Paper,
                Task,
                PaperTask,
                Repository,
                PaperRepository,
                HfArtifact,
                PaperHfArtifact,
            )
        ],
    )
    hydrated = []

    def cards(self, rows, *, include_resources=False, repository_limit=None):
        hydrated.append(([row.id for row in rows], include_resources))
        return [PaperCard.model_construct(id=str(row.id)) for row in rows]

    monkeypatch.setattr(PaperService, "hydrate_cards", cards)
    with Session(engine) as db:
        db.add(Task(id=1, name="Robotics", slug="robotics"))
        for ident, day, latest in [
            (1, 1, True),
            (2, 2, True),
            (3, 2, True),
            (4, 3, False),
        ]:
            db.add(
                Paper(
                    id=ident,
                    title=f"Robot {ident}",
                    abstract="Robotics",
                    source="arxiv",
                    arxiv_id=f"2601.0000{ident}",
                    version="v1",
                    date_published=date(2026, 1, day),
                    is_latest_version=latest,
                    citation_count=10,
                )
            )
            db.add(PaperTask(paper_id=ident, task_id=1))
        db.add(
            Repository(
                id=1,
                url="https://github.com/org/repo",
                owner="org",
                name="repo",
                num_stars=20,
                trending_score=10,
                trending_score_updated_at=datetime.now(timezone.utc),
            )
        )
        db.add_all(
            [
                PaperRepository(paper_id=i, repository_id=1, is_official=True)
                for i in (1, 2)
            ]
        )
        db.add(
            HfArtifact(
                id=1,
                kind="model",
                repo_id="org/model",
                url="https://huggingface.co/org/model",
            )
        )
        db.add(PaperHfArtifact(paper_id=2, hf_artifact_id=1))
        db.commit()
        yield db, hydrated
    engine.dispose()


def ids(response):
    return [row.id for row in response.results]


@pytest.mark.parametrize("mode", ["github", "composite"])
def test_task_trending_dedup_is_not_general_taxonomy_filter_policy(
    feeds, monkeypatch, mode
):
    db, hydrated = feeds
    monkeypatch.setattr(PaperService(db).settings, "trending_ranking_mode", mode)
    task = TaskService(db).get_task_papers(
        "robotics", order_by="trending", include_resources=True
    )
    general = PaperService(db).get_papers(task="robotics", order_by="trending")
    assert ids(task) == ["2", "3"]  # unscored paper remains
    assert ids(general) == ["2", "1", "3"]  # same repo can appear twice
    assert task.count == 2 and general.count == 3
    assert hydrated == [([2, 3], True), ([2, 1, 3], False)]


@pytest.mark.parametrize("task_feed", [False, True])
def test_feed_filters_count_and_paginate_before_hydration(feeds, task_feed):
    db, hydrated = feeds
    get = TaskService(db).get_task_papers if task_feed else PaperService(db).get_papers
    scope = {"task_id": "1"} if task_feed else {"task": "robotics", "search": "Robot"}
    result = get(
        **scope,
        order_by="date_published",
        has_code=True,
        has_hf_artifacts=True,
        start_date=date(2026, 1, 2),
        end_date=date(2026, 1, 2),
        page_size=1,
    )
    assert ids(result) == ["2"] and result.count == 1
    assert result.next_page is None and result.previous_page is None
    assert hydrated == [([2], False)]
    result = get(**scope, order_by="date_published", page=5, page_size=1)
    assert result.count == 3 and ids(result) == []
    assert result.previous_page == 4 and result.next_page is None


def test_task_trending_winner_is_chosen_before_requested_date_filter(feeds):
    db, _ = feeds
    result = TaskService(db).get_task_papers(
        "1", order_by="trending", end_date=date(2026, 1, 1)
    )
    assert (
        result.count == 0
    )  # newer linked paper outside window still displaces old one


def test_nontrending_endpoint_ties_and_direction_contract(feeds):
    db, _ = feeds
    statements = []

    def capture(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", capture)
    task = TaskService(db).get_task_papers("1", order_by="citation_count", page_size=2)
    assert ids(task) == ["3", "2"] and task.next_page == 2
    assert any(
        "ORDER BY papers.citation_count DESC, papers.id DESC" in sql
        for sql in statements
    )
    statements.clear()
    PaperService(db).get_papers(task="1", order_by="citation_count", order_dir="DESC")
    assert any(
        "ORDER BY papers.citation_count DESC NULLS LAST" in sql for sql in statements
    )
    assert not any("papers.id DESC" in sql for sql in statements)
    # Task's existing internal contract treats uppercase DESC as ascending.
    assert ids(
        TaskService(db).get_task_papers("1", order_by="unknown", order_dir="DESC")
    ) == ["1", "2", "3"]


@pytest.mark.parametrize("task_feed", [False, True])
def test_latest_only_can_be_disabled(feeds, task_feed):
    db, _ = feeds
    result = (
        TaskService(db).get_task_papers("1", latest_only=False)
        if task_feed
        else PaperService(db).get_papers(
            task="1", latest_only=False, order_by="date_published"
        )
    )
    assert result.count == 4 and ids(result)[0] == "4"


def test_hf_artifact_filter_matches_explicit_hub_links(feeds):
    db, _ = feeds
    # External papers list Hub links on the row instead of the junction table.
    db.get(Paper, 3).hf_spaces = ["https://huggingface.co/spaces/org/demo"]
    db.commit()
    result = PaperService(db).get_papers(
        task="1", has_hf_artifacts=True, order_by="date_published"
    )
    assert sorted(ids(result)) == ["2", "3"]


def test_search_and_official_implementation_filter_real_rows(feeds):
    db, _ = feeds
    service = PaperService(db)
    assert ids(
        service.get_papers(
            task="1",
            search="Robot 2",
            has_official_implementation=True,
            order_by="date_published",
        )
    ) == ["2"]
    assert (
        service.get_papers(task="1", search="missing", order_by="date_published").count
        == 0
    )


def test_global_trending_selector_preserves_sql_order_and_empty_page(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    database = MagicMock()
    database.execute.return_value.fetchall.return_value = [(2, 3), (1, 3)]
    database.query.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(id=1),
        SimpleNamespace(id=2),
    ]
    service = PaperService(database)
    hydrated = []

    def cards(rows, **kwargs):
        hydrated.append(([row.id for row in rows], kwargs))
        return [PaperCard.model_construct(id=str(row.id)) for row in rows]

    monkeypatch.setattr(service, "hydrate_cards", cards)
    result = service._get_trending_papers(page_size=2, include_resources=True)
    assert ids(result) == ["2", "1"] and result.count == 3 and result.next_page == 2
    assert hydrated == [([2, 1], {"include_resources": True, "repository_limit": None})]
    database.execute.return_value.fetchall.return_value = []
    result = service._get_trending_papers(page=5, page_size=2)
    assert (
        result.count == 0 and result.previous_page is None and result.next_page is None
    )


@pytest.fixture
def entity_feeds(feeds):
    from backend.models.database import (
        Method,
        PaperMethod,
        Organization,
        PaperOrganization,
        Conference,
        PaperConference,
    )
    from backend.services.method_service import MethodService
    from backend.services.organization_service import OrganizationService
    from backend.services.conference_service import ConferenceService

    db, hydrated = feeds
    Base.metadata.create_all(
        db.bind,
        tables=[
            model.__table__
            for model in (
                Method,
                PaperMethod,
                Organization,
                PaperOrganization,
                Conference,
                PaperConference,
            )
        ],
    )
    db.add_all(
        [
            Method(id=1, name="Robotics", slug="robotics"),
            Organization(id=1, name="Lab", slug="lab"),
            Conference(id=1, name="CVPR 2026", slug="cvpr-2026"),
        ]
    )
    for ident, award in [
        (1, "honorable_mention"),
        (2, "outstanding"),
        (3, "best_paper_finalist"),
        (4, None),
    ]:
        db.add_all(
            [
                PaperMethod(paper_id=ident, method_id=1),
                PaperOrganization(paper_id=ident, organization_id=1),
                PaperConference(paper_id=ident, conference_id=1, award=award),
            ]
        )
        db.get(Paper, ident).proceeding = (
            "CVPR 2026 Oral" if ident == 1 else "CVPR 2026 Spotlight"
        )
    db.commit()
    return (
        db,
        hydrated,
        {
            "method": lambda **kw: MethodService(db).get_method_papers(
                "robotics", **kw
            ),
            "organization": lambda **kw: OrganizationService(
                db
            ).get_organization_papers("lab", **kw),
            "conference": lambda **kw: ConferenceService(db).get_conference_papers(
                "cvpr-2026", **kw
            ),
        },
    )


@pytest.mark.parametrize("entity", ["method", "organization", "conference"])
def test_entity_feed_filters_ties_empty_pages_and_hydration(entity_feeds, entity):
    _, hydrated, services = entity_feeds
    get = services[entity]
    result = get(page_size=2, include_resources=True)
    assert ids(result) == ["3", "2"] and result.count == 3 and result.next_page == 2
    assert hydrated[-1] == ([3, 2], True)
    assert ids(get(order_by="title", order_dir="asc")) == ["1", "2", "3"]
    assert ids(get(order_by="unknown", order_dir="DESC")) == ["1", "2", "3"]
    assert ids(get(latest_only=False)) == ["4", "3", "2", "1"]
    assert ids(
        get(
            has_code=True,
            has_hf_artifacts=True,
            start_date=date(2026, 1, 2),
            end_date=date(2026, 1, 2),
        )
    ) == ["2"]
    empty = get(page=5, page_size=1)
    assert empty.count == 3 and ids(empty) == []
    assert empty.previous_page == 4 and empty.next_page is None


@pytest.mark.parametrize("entity", ["method", "organization", "conference"])
@pytest.mark.parametrize("mode", ["github", "composite"])
def test_entity_trending_keeps_shared_repositories_and_unscored_papers(
    entity_feeds, monkeypatch, entity, mode
):
    db, _, services = entity_feeds
    monkeypatch.setattr(PaperService(db).settings, "trending_ranking_mode", mode)
    result = services[entity](order_by="trending")
    assert ids(result) == ["2", "1", "3"] and result.count == 3


@pytest.mark.parametrize("entity", ["organization", "conference"])
def test_entity_task_scope_intersects_entity_membership(entity_feeds, entity):
    db, _, services = entity_feeds
    db.query(PaperTask).filter(PaperTask.paper_id != 2).delete()
    db.commit()
    assert ids(services[entity](task_slug="robotics")) == ["2"]


def test_conference_presentation_order_overrides_requested_trending(entity_feeds):
    _, _, services = entity_feeds
    get = services["conference"]
    assert ids(get(presentation="oral")) == ["1"]
    assert ids(get(presentation="spotlight")) == ["3", "2"]
    awarded = get(presentation="outstanding", order_by="trending", page_size=1)
    assert ids(awarded) == ["2"] and awarded.count == 2 and awarded.next_page == 2
    assert awarded.results[0].conference_award == "outstanding"
    second = get(presentation="outstanding", page=2, page_size=1)
    assert (
        ids(second) == ["1"]
        and second.results[0].conference_award == "honorable_mention"
    )
    assert ids(get(presentation="outstanding", page=5)) == []
    assert (
        get(presentation="best_paper_finalist").results[0].conference_award
        == "best_paper_finalist"
    )


def test_cvpr_finalists_use_curated_order_other_conferences_use_title(entity_feeds):
    from backend.database.conferences_setup.cvpr2026_best_paper_finalist_order import (
        CVPR_2026_BEST_PAPER_FINALIST_ARXIV_ORDER,
    )
    from backend.models.database import Conference, PaperConference
    from backend.services.conference_service import ConferenceService

    db, _, services = entity_feeds
    for ident in (1, 2, 3):
        db.get(Paper, ident).arxiv_id = CVPR_2026_BEST_PAPER_FINALIST_ARXIV_ORDER[
            3 - ident
        ]
    db.query(PaperConference).update({PaperConference.award: "best_paper_finalist"})
    db.commit()
    assert ids(
        services["conference"](presentation="best_paper_finalist", order_by="trending")
    ) == ["3", "2", "1"]
    db.get(Conference, 1).slug = "other"
    db.commit()
    assert ids(
        ConferenceService(db).get_conference_papers(
            "other", presentation="best_paper_finalist", order_by="trending"
        )
    ) == ["1", "2", "3"]
