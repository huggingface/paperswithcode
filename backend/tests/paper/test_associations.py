from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend.services.catalog_errors import CatalogValidationError
from backend.services.paper_association_service import PaperAssociationService
from backend.utils.exceptions import DatabaseError, PaperNotFoundError


class _Query:
    def __init__(self, value):
        self.value = value

    def filter(self, *_args):
        return self

    def first(self):
        return self.value


class _SequenceSession:
    def __init__(self, query_values):
        self.query_values = iter(query_values)
        self.events = []

    def query(self, _model):
        return _Query(next(self.query_values))

    def flush(self):
        self.events.append("flush")

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")


def test_commit_false_flushes_and_returns_the_locked_row_without_hydration():
    paper = SimpleNamespace(id=1, source="external", source_url="https://old.example")
    db = _SequenceSession([paper, None])
    hydrate = Mock()

    result = PaperAssociationService(db, hydrate).update_source_url(
        1, "  https://new.example/paper  ", commit=False
    )

    assert result is paper
    assert paper.source_url == "https://new.example/paper"
    assert db.events == ["flush"]
    hydrate.assert_not_called()


def test_commit_precedes_hydration_and_returns_the_hydrated_paper():
    paper = SimpleNamespace(id=1, source="external", source_url="https://old.example")
    db = _SequenceSession([paper, None])

    def hydrate(paper_id, include_resources=False):
        db.events.append(("hydrate", paper_id, include_resources))
        return "hydrated-paper"

    result = PaperAssociationService(db, hydrate).update_source_url(
        1, "https://new.example/paper"
    )

    assert result == "hydrated-paper"
    assert db.events == ["commit", ("hydrate", 1, True)]


def test_unchanged_source_url_hydrates_without_commit_even_when_commit_is_false():
    paper = SimpleNamespace(
        id=1,
        source="external",
        source_url="https://example.com/paper",
    )
    db = _SequenceSession([paper])
    hydrate = Mock(return_value="hydrated-paper")

    result = PaperAssociationService(db, hydrate).update_source_url(
        1, " https://example.com/paper ", commit=False
    )

    assert result == "hydrated-paper"
    assert db.events == []
    hydrate.assert_called_once_with(1, include_resources=True)


@pytest.mark.parametrize("error_type", [RuntimeError, SQLAlchemyError])
def test_hydration_failure_rolls_back_after_the_committed_mutation(error_type):
    paper = SimpleNamespace(id=1, source="external", source_url="https://old.example")
    db = _SequenceSession([paper, None])

    def fail_hydration(_paper_id, include_resources=False):
        db.events.append(("hydrate", include_resources))
        raise error_type("hydrate failed")

    with pytest.raises(
        DatabaseError,
        match="^Error updating paper source URL: hydrate failed$",
    ):
        PaperAssociationService(db, fail_hydration).update_source_url(
            1, "https://new.example/paper"
        )
    assert db.events == ["commit", ("hydrate", True), "rollback"]


def test_unchanged_source_hydration_failure_uses_the_same_error_boundary():
    paper = SimpleNamespace(
        id=1, source="external", source_url="https://example.com/paper"
    )
    db = _SequenceSession([paper])

    def fail_hydration(_paper_id, include_resources=False):
        raise RuntimeError("hydrate failed")

    with pytest.raises(
        DatabaseError,
        match="^Error updating paper source URL: hydrate failed$",
    ):
        PaperAssociationService(db, fail_hydration).update_source_url(
            1, "https://example.com/paper", commit=False
        )

    assert db.events == []


ASSOCIATION_CALLS = [
    pytest.param(lambda service: service.update_tasks(9, []), id="tasks"),
    pytest.param(
        lambda service: service.update_organizations(9, []), id="organizations"
    ),
    pytest.param(lambda service: service.update_methods(9, []), id="methods"),
    pytest.param(lambda service: service.update_repositories(9, []), id="repositories"),
    pytest.param(
        lambda service: service.update_project_pages(9, []), id="project-pages"
    ),
    pytest.param(
        lambda service: service.update_source_url(9, "https://example.com/paper"),
        id="source-url",
    ),
    pytest.param(
        lambda service: service.update_hf_artifacts(9, [], [], []),
        id="hf-artifacts",
    ),
]


@pytest.mark.parametrize("invoke", ASSOCIATION_CALLS)
def test_missing_paper_rolls_back_and_preserves_the_domain_error(invoke):
    db = _SequenceSession([None])
    service = PaperAssociationService(db, Mock())

    with pytest.raises(PaperNotFoundError, match="^Paper with ID 9 not found$"):
        invoke(service)
    assert db.events == ["rollback"]


@pytest.mark.parametrize(
    ("invoke", "message"),
    [
        pytest.param(
            lambda service: service.update_tasks(9, []),
            "Error updating paper tasks: database failed",
            id="tasks",
        ),
        pytest.param(
            lambda service: service.update_organizations(9, []),
            "Error updating paper organizations: database failed",
            id="organizations",
        ),
        pytest.param(
            lambda service: service.update_methods(9, []),
            "Error updating paper methods: database failed",
            id="methods",
        ),
        pytest.param(
            lambda service: service.update_repositories(9, []),
            "Error updating paper repositories: database failed",
            id="repositories",
        ),
        pytest.param(
            lambda service: service.update_project_pages(9, []),
            "Error updating paper project pages: database failed",
            id="project-pages",
        ),
        pytest.param(
            lambda service: service.update_source_url(9, "https://example.com/paper"),
            "Error updating paper source URL: database failed",
            id="source-url",
        ),
        pytest.param(
            lambda service: service.update_hf_artifacts(9, [], [], []),
            "Error updating paper HF artifacts: database failed",
            id="hf-artifacts",
        ),
    ],
)
def test_unexpected_database_failure_rolls_back_and_keeps_exact_message(
    invoke, message
):
    class FailingSession:
        def __init__(self):
            self.rollback = Mock()

        def query(self, _model):
            raise SQLAlchemyError("database failed")

    db = FailingSession()
    with pytest.raises(DatabaseError, match=f"^{message}$"):
        invoke(PaperAssociationService(db, Mock()))
    db.rollback.assert_called_once_with()


def test_invalid_hf_url_rolls_back_without_error_prefix():
    paper = SimpleNamespace(id=1)
    db = _SequenceSession([paper])

    with pytest.raises(
        CatalogValidationError,
        match="^Invalid Hugging Face model URL: 'https://example.com/model'$",
    ):
        PaperAssociationService(db, Mock()).update_hf_artifacts(
            1, ["https://example.com/model"], [], []
        )
    assert db.events == ["rollback"]


def test_invalid_hf_url_leaves_outer_transaction_ownership_intact():
    paper = SimpleNamespace(id=1)
    db = _SequenceSession([paper])

    with pytest.raises(CatalogValidationError):
        PaperAssociationService(db, Mock()).update_hf_artifacts(
            1, ["https://example.com/model"], [], [], commit=False
        )

    assert db.events == []
