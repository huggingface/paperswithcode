"""Compatibility checks for bounded persistence model modules."""

import importlib
import pkgutil
import subprocess
import sys

import pytest

from backend.models import database

BOUNDED_MODULES = tuple(
    importlib.import_module(f"{database.__name__}.{info.name}")
    for info in pkgutil.iter_modules(database.__path__)
    if info.name != "base"
)


def _owned_models(module):
    return {
        name: value
        for name, value in vars(module).items()
        if isinstance(value, type)
        and issubclass(value, database.Base)
        and value.__module__ == module.__name__
    }


def test_legacy_imports_are_canonical_class_aliases():
    for module in BOUNDED_MODULES:
        assert _owned_models(module)
        for name, model in _owned_models(module).items():
            assert getattr(database, name) is model


def test_every_mapped_class_has_one_bounded_owner_and_one_export():
    mapped = {mapper.class_ for mapper in database.Base.registry.mappers}
    owned = [model for m in BOUNDED_MODULES for model in _owned_models(m).values()]
    assert len(owned) == len(set(owned))
    assert set(owned) == mapped

    exported = [name for name in database.__all__ if name != "Base"]
    assert len(exported) == len(set(exported))
    assert {getattr(database, name) for name in exported} == mapped


@pytest.mark.parametrize("module", BOUNDED_MODULES, ids=lambda m: m.__name__)
def test_importing_any_bounded_module_first_configures_every_mapper(module):
    code = (
        "from sqlalchemy.orm import configure_mappers\n"
        f"from {module.__name__} import Base\n"
        "configure_mappers()\n"
        "print(len(Base.registry.mappers), len(Base.metadata.tables))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    )
    assert result.stdout.split() == [
        str(len(database.Base.registry.mappers)),
        str(len(database.Base.metadata.tables)),
    ]
