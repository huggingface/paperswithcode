"""Compatibility checks for bounded API model modules."""

from backend.models import api, evaluations, papers


def test_legacy_paper_imports_are_canonical_class_aliases():
    for name in papers.__all__:
        canonical = getattr(papers, name)
        assert canonical.__module__ == papers.__name__
        assert getattr(api, name) is canonical


def test_legacy_evaluation_imports_are_canonical_class_aliases():
    for name in evaluations.__all__:
        canonical = getattr(evaluations, name)
        assert canonical.__module__ == evaluations.__name__
        assert getattr(api, name) is canonical


def test_task_import_remains_the_canonical_shared_contract():
    from backend.models.tasks import Task
    from backend.models.public_api import DatasetTasks

    assert api.Task is Task
    assert api.DatasetTasks is DatasetTasks
    assert (
        DatasetTasks.model_validate(
            {"count": 1, "results": [{"id": 1, "name": "Example"}]}
        )
        .results[0]
        .id
        == "1"
    )
