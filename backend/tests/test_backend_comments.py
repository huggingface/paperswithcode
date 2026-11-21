import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backend_comments.py"
spec = importlib.util.spec_from_file_location("backend_comments", SCRIPT)
backend_comments = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend_comments)

SOURCE = """#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# ///
# explains the module
import os  # noqa: F401


def f(x):
    s = "a # not a comment"  # trailing note
    # inner note
    return s  # type: ignore[return-value]
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "module.py").write_text(SOURCE)
    monkeypatch.setattr(backend_comments, "ROOT", tmp_path)
    monkeypatch.setattr(backend_comments, "BACKEND", backend)
    monkeypatch.setattr(backend_comments, "BASELINE", backend / "comment-baseline.json")
    return tmp_path


def test_directives_and_script_metadata_are_not_comments(repo):
    found = backend_comments.comments(repo / "backend" / "module.py")

    assert [(c["line"], c["kind"]) for c in found] == [
        (5, "own"),
        (10, "inline"),
        (11, "own"),
    ]


def test_only_closed_script_metadata_blocks_are_exempt(repo):
    path = repo / "backend" / "module.py"
    path.write_text("x = 1\n# /// script metadata is read by uv\n# later note\n")

    assert [c["line"] for c in backend_comments.comments(path)] == [2, 3]


def test_ratchet_rejects_new_comments_and_never_raises_baseline(repo, capsys):
    assert backend_comments.check() == 1
    assert backend_comments.update(allow_increase=False) == 1
    assert backend_comments.update(allow_increase=True) == 0
    assert backend_comments.check() == 0

    with (repo / "backend" / "module.py").open("a") as handle:
        handle.write("# one more\n")

    assert backend_comments.check() == 1


def test_inventory_then_delete_removes_only_comments(repo):
    inventory = repo / "blocks.jsonl"
    backend_comments.inventory(inventory)
    backend_comments.delete(inventory)

    assert (repo / "backend" / "module.py").read_text() == SOURCE.replace(
        "# explains the module\n", ""
    ).replace("  # trailing note", "").replace("    # inner note\n", "")


def test_delete_refuses_lines_that_are_no_longer_comments(repo):
    selection = repo / "stale.jsonl"
    selection.write_text(
        json.dumps({"f": "backend/module.py", "kind": "own", "start": 6, "end": 6})
    )

    with pytest.raises(SystemExit):
        backend_comments.delete(selection)
