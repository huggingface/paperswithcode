"""Signed-in users' paper edits apply immediately unless the policy holds them."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.config import get_settings
from backend.models.database import (
    CatalogMutationEvent,
    Organization,
    PaperOrganization,
    PaperTask,
)
from backend.models.database import Paper as DBPaper
from backend.models.database import ProjectPage as DBProjectPage
from backend.models.database import Task as DBTask
from backend.services.pending_edit_auto_approval import (
    AutoApprovalPolicy,
    removed_values,
)
from backend.services.hf_organization_service import HFOrganizationProfile
from backend.services.pending_edit_service import PendingEditService
from backend.tests.paper_edits import pending_harness

db_session = pending_harness.db_session
paper_fixture = pending_harness.paper_fixture
hf_organizations = pending_harness.hf_organizations


@pytest.fixture(autouse=True)
def auto_approve_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "paper_edit_auto_approve_enabled", True)


def submit(db, edit_type, payload, *, paper_id=1, username="alice"):
    return PendingEditService(db).submit(
        paper_id=paper_id,
        hf_username=username,
        hf_subject=f"sub-{username}",
        edit_type=edit_type,
        proposed_payload=payload,
    )


def task_ids(db, paper_id=1):
    return {
        row.task_id
        for row in db.query(PaperTask).filter(PaperTask.paper_id == paper_id)
    }


def test_task_addition_is_applied_and_audited_as_the_submitter(
    db_session, paper_fixture
):
    row = submit(db_session, "tasks", {"task_ids": [1, 2, 3]})

    assert row.status == "approved"
    assert row.reviewed_by_kind == "auto"
    assert task_ids(db_session) == {1, 2, 3}
    event = db_session.get(CatalogMutationEvent, row.catalog_event_id)
    assert event.actor_hf_subject == "sub-alice"
    assert event.actor_role == "contributor"
    assert event.request_id == f"submission-auto:{row.id}"


def test_removal_is_applied_too(db_session, paper_fixture):
    row = submit(db_session, "tasks", {"task_ids": [1]})

    assert row.status == "approved"
    assert task_ids(db_session) == {1}


def test_switch_off_queues_everything(db_session, paper_fixture, monkeypatch):
    monkeypatch.setattr(get_settings(), "paper_edit_auto_approve_enabled", False)

    row = submit(db_session, "tasks", {"task_ids": [1, 2, 3]})

    assert row.status == "pending"
    assert task_ids(db_session) == {1, 2}


def test_taxonomy_suggestions_stay_queued(db_session):
    row = PendingEditService(db_session).submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_task",
        proposed_payload={"name": "Brand new task"},
    )

    assert row.status == "pending"


def test_organization_with_a_real_hf_org_is_created_from_its_profile(
    db_session, paper_fixture, hf_organizations
):
    hf_organizations["generalreasoning"] = HFOrganizationProfile(
        hf_slug="GeneralReasoning",
        name="General Reasoning",
        logo_url="https://cdn-avatars.huggingface.co/gr.jpeg",
        website_url="https://gr.inc",
        is_verified=False,
        followers=88,
    )

    row = submit(
        db_session,
        "new_organization",
        {
            "name": "General Reasoning",
            "hf_slug": "https://huggingface.co/generalreasoning",
            "website_url": "https://elsewhere.example.com",
        },
    )

    assert (row.status, row.reviewed_by_kind) == ("approved", "auto")
    organization = db_session.get(Organization, int(row.result_entity_id))
    assert (organization.hf_slug, organization.hf_url, organization.website_url) == (
        "GeneralReasoning",
        "https://huggingface.co/GeneralReasoning",
        "https://gr.inc",
    )
    assert organization.logo_data == b"\x89PNG hf avatar"
    assert db_session.get(PaperOrganization, (1, organization.id)) is not None


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"hf_slug": "nobody-here"}, "organization nobody-here not found"),
        ({"website_url": "https://lab.example.org"}, "no Hugging Face organization"),
    ],
)
def test_organization_without_a_real_hf_org_is_held(
    db_session, paper_fixture, payload, reason
):
    row = submit(db_session, "new_organization", {"name": "Some Lab", **payload})

    assert row.status == "pending"
    assert reason in row.admin_note
    assert db_session.query(Organization).count() == 0


def test_unfamiliar_domain_is_held_with_a_reason(db_session, paper_fixture):
    row = submit(
        db_session,
        "project_pages",
        {
            "project_pages": [
                {"url": "https://sketchy.example.org/p", "is_official": False}
            ]
        },
    )

    assert row.status == "pending"
    assert "sketchy.example.org" in row.admin_note


def test_trusted_and_known_domains_apply(db_session, paper_fixture):
    db_session.add_all(
        DBProjectPage(url=f"https://lab.example.org/{i}", is_official=False)
        for i in range(3)
    )
    db_session.commit()

    github = submit(
        db_session,
        "project_pages",
        {
            "project_pages": [
                {"url": "https://someone.github.io/x", "is_official": True}
            ]
        },
    )
    known = submit(
        db_session,
        "project_pages",
        {
            "project_pages": [
                {"url": "https://lab.example.org/new", "is_official": True}
            ]
        },
        username="bob",
    )

    assert github.status == "approved"
    assert known.status == "approved"


def test_host_only_mentioned_in_other_urls_earns_no_trust(db_session, paper_fixture):
    db_session.add_all(
        DBProjectPage(
            url=f"https://someone.github.io/p{i}?ref=https://lab.example.org/x",
            is_official=False,
        )
        for i in range(3)
    )
    db_session.commit()

    row = submit(
        db_session,
        "project_pages",
        {
            "project_pages": [
                {"url": "https://lab.example.org/new", "is_official": True}
            ]
        },
    )

    assert row.status == "pending"


def test_extra_configured_domain_applies(db_session, paper_fixture, monkeypatch):
    monkeypatch.setattr(
        get_settings(), "paper_edit_auto_approve_extra_domains", "lab.example.org"
    )

    row = submit(
        db_session,
        "project_pages",
        {"project_pages": [{"url": "https://lab.example.org/p", "is_official": True}]},
    )

    assert row.status == "approved"


def test_removals_over_the_limit_are_queued(db_session, paper_fixture, monkeypatch):
    monkeypatch.setattr(get_settings(), "paper_edit_auto_approve_removal_papers", 2)
    for paper_id in (2, 3, 4):
        db_session.add(
            DBPaper(
                id=paper_id,
                title="P",
                abstract="A",
                source="external",
                source_url=f"https://example.com/{paper_id}",
            )
        )
        db_session.add(PaperTask(paper_id=paper_id, task_id=1))
        db_session.add(PaperTask(paper_id=paper_id, task_id=2))
    db_session.commit()

    first = submit(db_session, "tasks", {"task_ids": [1]}, paper_id=2)
    second = submit(db_session, "tasks", {"task_ids": [1]}, paper_id=3)
    third = submit(db_session, "tasks", {"task_ids": [1]}, paper_id=4)
    addition = submit(db_session, "tasks", {"task_ids": [1, 2, 3]}, paper_id=1)

    assert [first.status, second.status] == ["approved", "approved"]
    assert third.status == "pending"
    assert "removals on more than 2 papers" in third.admin_note
    assert task_ids(db_session, 4) == {1, 2}
    assert addition.status == "approved"


def test_taking_back_own_addition_is_not_a_removal(
    db_session, paper_fixture, monkeypatch
):
    monkeypatch.setattr(get_settings(), "paper_edit_auto_approve_removal_papers", 1)
    db_session.add(
        DBPaper(
            id=2,
            title="P",
            abstract="A",
            source="external",
            source_url="https://example.com/2",
        )
    )
    db_session.add(PaperTask(paper_id=2, task_id=1))
    db_session.add(PaperTask(paper_id=2, task_id=2))
    db_session.commit()
    submit(db_session, "tasks", {"task_ids": [1]}, paper_id=2)  # removal, 1 paper
    submit(db_session, "tasks", {"task_ids": [1, 2, 3]})  # adds task 3 on paper 1

    undo = submit(db_session, "tasks", {"task_ids": [1, 2]})  # removes own task 3

    assert undo.status == "approved"
    assert task_ids(db_session) == {1, 2}


def test_daily_paper_budget_queues_the_overflow(db_session, paper_fixture, monkeypatch):
    monkeypatch.setattr(get_settings(), "paper_edit_auto_approve_daily_papers", 1)
    db_session.add(
        DBPaper(
            id=2,
            title="P",
            abstract="A",
            source="external",
            source_url="https://example.com/2",
        )
    )
    db_session.commit()

    first = submit(db_session, "tasks", {"task_ids": [1, 2, 3]})
    again = submit(db_session, "tasks", {"task_ids": [1, 2]})
    other_paper = submit(db_session, "tasks", {"task_ids": [3]}, paper_id=2)

    assert first.status == "approved"
    assert again.status == "approved"  # same paper does not use more budget
    assert other_paper.status == "pending"
    assert "auto-applied papers today" in other_paper.admin_note


def test_apply_failure_leaves_the_edit_queued(db_session, paper_fixture, monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("database is unhappy")

    monkeypatch.setattr(
        "backend.services.pending_edit_mutations.PendingEditMutationService.apply_human_review",
        fail,
    )

    row = submit(db_session, "tasks", {"task_ids": [1, 2, 3]})

    assert row.status == "pending"
    assert task_ids(db_session) == {1, 2}


def test_policy_error_leaves_the_stored_edit_queued(
    db_session, paper_fixture, monkeypatch
):
    def fail(*_args, **_kwargs):
        raise RuntimeError("policy query failed")

    monkeypatch.setattr(AutoApprovalPolicy, "decide", fail)

    row = submit(db_session, "tasks", {"task_ids": [1, 2, 3]})

    assert row.status == "pending"
    assert task_ids(db_session) == {1, 2}


def test_removed_values_cover_every_edit_type():
    current = {"tasks": [{"id": 1}, {"id": 2}]}
    assert removed_values("tasks", current, {"task_ids": [1]}) == {"2"}
    assert removed_values(
        "repositories",
        {"repositories": [{"url": "https://github.com/a/b", "is_official": True}]},
        {"repositories": [{"url": "https://github.com/a/c", "is_official": True}]},
    ) == {"https://github.com/a/b"}
    assert removed_values(
        "evaluations",
        {},
        {
            "operations": [
                {"op": "delete", "evaluation_id": 5},
                {"op": "create", "data": {}},
            ]
        },
    ) == {"evaluation:5"}
    assert removed_values(
        "hf_artifacts",
        {"hf_models": ["a/b"], "hf_datasets": [], "hf_spaces": []},
        {"hf_models": [], "hf_datasets": [], "hf_spaces": []},
    ) == {"hf_models:a/b"}


ADMIN = {"hf_subject": "admin", "username": "admin", "role": "admin"}


def revert(db, username="alice", hours=24):
    from backend.services.auto_approved_revert_service import AutoApprovedRevertService

    return AutoApprovedRevertService(db).revert(
        hf_subject=f"sub-{username}",
        since=datetime.now(timezone.utc) - timedelta(hours=hours),
        actor=ADMIN,
        request_id="test-revert",
    )


def test_bulk_revert_restores_every_auto_applied_edit(db_session, paper_fixture):
    db_session.add(DBTask(id=4, name="Task D", slug="task-d", level=0))
    db_session.commit()
    submit(db_session, "tasks", {"task_ids": [1, 2, 3]})
    submit(db_session, "tasks", {"task_ids": [1, 2, 3, 4]})
    assert task_ids(db_session) == {1, 2, 3, 4}

    result = revert(db_session)

    assert result == {"reverted": 2, "skipped": []}
    assert task_ids(db_session) == {1, 2}
    assert revert(db_session) == {"reverted": 0, "skipped": []}


def test_bulk_revert_skips_edits_changed_since_and_other_accounts(
    db_session, paper_fixture
):
    db_session.add(DBTask(id=4, name="Task D", slug="task-d", level=0))
    db_session.add(
        DBPaper(
            id=2,
            title="P",
            abstract="A",
            source="external",
            source_url="https://example.com/2",
        )
    )
    db_session.commit()
    submit(db_session, "tasks", {"task_ids": [1, 2, 3]})
    submit(db_session, "tasks", {"task_ids": [3]}, paper_id=2, username="bob")
    submit(db_session, "tasks", {"task_ids": [1, 2, 3, 4]}, username="bob")

    result = revert(db_session)

    assert result["reverted"] == 0
    assert len(result["skipped"]) == 1
    assert task_ids(db_session, 2) == {3}
