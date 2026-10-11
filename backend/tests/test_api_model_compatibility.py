"""Compatibility checks for bounded API model modules."""

import ast
import inspect

from pydantic import BaseModel

from backend.models import (
    api,
    conferences,
    curation,
    errors,
    evaluations,
    operations,
    organizations,
    papers,
    taxonomy,
    trends,
)

CONTRACTED_MODULES = (
    conferences,
    curation,
    errors,
    operations,
    organizations,
    taxonomy,
    trends,
)


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


def test_catalog_and_operations_imports_are_canonical_aliases():
    for module in CONTRACTED_MODULES:
        for name in module.__all__:
            canonical = getattr(module, name)
            if isinstance(canonical, type):
                assert canonical.__module__ == module.__name__
            assert getattr(api, name) is canonical


def test_every_api_model_has_one_canonical_bounded_module():
    exported = {
        name: value
        for name, value in vars(api).items()
        if isinstance(value, type) and issubclass(value, BaseModel)
    }
    assert exported
    for name, model in exported.items():
        assert model.__module__ != api.__name__, name


def test_compatibility_surface_contains_only_imports():
    tree = ast.parse(inspect.getsource(api))
    body = tree.body[1:] if isinstance(tree.body[0], ast.Expr) else tree.body
    assert all(isinstance(node, ast.ImportFrom) for node in body)
