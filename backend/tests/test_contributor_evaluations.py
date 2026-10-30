from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.config import get_settings
from backend.services import github_issue_body_service as body_service
from backend.services.contributor_evaluations import (
    contributor_evaluation_ids,
    snapshot_evaluation_ids,
)


@pytest.fixture(autouse=True)
def outreach_identity(monkeypatch):
    monkeypatch.setenv("PWC_GITHUB_OUTREACH_SIGNER", "Alex")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_snapshot_evaluation_ids_reads_every_recorded_shape():
    assert snapshot_evaluation_ids({"evaluations": [{"id": 1}, {"id": 2}]}) == {1, 2}
    assert snapshot_evaluation_ids([{"id": 3}]) == {3}
    assert snapshot_evaluation_ids({"id": 4, "metrics": {}}) == {4}
    assert snapshot_evaluation_ids(None) == set()


def test_contributor_ids_are_rows_an_edit_added_not_rows_it_touched():
    # SurGe (paper 85681): the author's first batch created all five rows; later
    # batches only edited them.
    db = Mock()
    db.execute.return_value = [
        ({"evaluations": []}, {"evaluations": [{"id": 46210}, {"id": 46211}]}),
        (
            {"evaluations": [{"id": 46210}, {"id": 9}]},
            {"evaluations": [{"id": 46210}, {"id": 9}]},
        ),
    ]
    assert contributor_evaluation_ids(db) == {46210, 46211}


def evaluation_row(evaluation_id):
    return (
        SimpleNamespace(
            id=evaluation_id,
            paper_id=85681,
            task_id=2,
            dataset_id=3,
            model_name="SurGe",
            best_metric=None,
            metrics={"Accuracy": 90},
        ),
        SimpleNamespace(name="Task", slug="task"),
        SimpleNamespace(name="Benchmark", slug="benchmark"),
    )


@pytest.fixture
def surge(monkeypatch):
    paper = SimpleNamespace(id=85681, title="SurGe")
    monkeypatch.setattr(
        body_service, "resolve_paper", lambda *args: (paper, "2605.31577")
    )
    monkeypatch.setattr(
        body_service, "contributor_evaluation_ids", lambda *args: {46210, 46211}
    )


def test_draft_refuses_paper_whose_evaluations_all_came_from_contributors(surge):
    db = Mock()
    db.execute.return_value = Mock(
        **{"all.return_value": [evaluation_row(46210), evaluation_row(46211)]}
    )
    with pytest.raises(ValueError, match="came from contributors"):
        body_service.generate_github_issue_draft(db, "85681")


def test_draft_counts_only_evaluations_we_imported(surge):
    rows = [evaluation_row(46210), evaluation_row(46211), evaluation_row(7)]
    db = Mock()
    db.execute.side_effect = [
        Mock(**{"all.return_value": rows}),
        Mock(**{"all.return_value": rows}),
        Mock(**{"scalars.return_value": []}),
        Mock(**{"scalars.return_value": ["https://github.com/lab/surge"]}),
    ]
    draft = body_service.generate_github_issue_draft(db, "85681")
    assert draft.native_evaluation_count == 1
    assert "[1 paper-native evaluation]" in draft.body
