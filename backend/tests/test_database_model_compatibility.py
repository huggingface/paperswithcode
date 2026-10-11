"""Compatibility checks for bounded persistence model modules."""

import subprocess
import sys

from backend.models import database
from backend.models.database import (
    autonomous,
    chat,
    chat_artifacts,
    chat_providers,
    chat_sandbox,
    chat_transcripts,
    curation,
)

BOUNDED_MODULES = (
    autonomous,
    chat,
    chat_artifacts,
    chat_providers,
    chat_sandbox,
    chat_transcripts,
    curation,
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


def test_every_mapped_class_is_exported_once():
    exported = [name for name in database.__all__ if name != "Base"]
    assert len(exported) == len(set(exported))
    assert {getattr(database, name) for name in exported} == {
        mapper.class_ for mapper in database.Base.registry.mappers
    }


def test_importing_one_bounded_module_configures_every_mapper():
    code = (
        "from sqlalchemy.orm import configure_mappers\n"
        "from backend.models.database.chat_sandbox import Base\n"
        "configure_mappers()\n"
        "print(len(Base.registry.mappers), len(Base.metadata.tables))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == [
        str(len(database.Base.registry.mappers)),
        str(len(database.Base.metadata.tables)),
    ]
