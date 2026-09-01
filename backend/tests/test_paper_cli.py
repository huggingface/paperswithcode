from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from backend.chat_sandbox_worker import paper_cli


def test_draft_submits_the_current_turn_candidate_without_exposing_a_write_api(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """The worker can publish its first bounded AI draft through the broker."""

    source = tmp_path / "main.tex"
    source.write_text(
        "\\documentclass{article}\\begin{document}Draft\\end{document}",
        encoding="utf-8",
    )
    observed: list[tuple[str, dict[str, object]]] = []

    def command(operation: str, **values: object) -> dict:
        observed.append((operation, values))
        return {
            "operation": operation,
            "activated": True,
            "paper": {"artifact_id": "paper-1", "title": "Draft"},
        }

    monkeypatch.setattr(paper_cli, "_command", command)
    monkeypatch.setattr(paper_cli, "WORKSPACE", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pwc-paper",
            "draft",
            "--directory",
            str(tmp_path),
            "--artifact-id",
            "paper-1",
            "--expected-parent-version-id",
            "version-1",
        ],
    )

    assert paper_cli.main() == 0
    assert observed == [
        (
            "draft",
            {
                "artifact_id": "paper-1",
                "expected_parent_version_id": "version-1",
                "files": [
                    {
                        "path": "main.tex",
                        "content": "\\documentclass{article}\\begin{document}Draft\\end{document}",
                    }
                ],
            },
        )
    ]
    receipt = json.loads(capsys.readouterr().out.removeprefix(paper_cli.EVENT_PREFIX))
    assert receipt["operation"] == "draft"
    assert receipt["activated"] is True


def test_publish_refuses_a_directory_outside_the_workspace_before_gateway_call(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.tex").write_text("private source", encoding="utf-8")

    monkeypatch.setattr(paper_cli, "WORKSPACE", workspace)
    monkeypatch.setattr(
        paper_cli,
        "_command",
        lambda *args, **kwargs: pytest.fail(
            "must not send outside files to the gateway"
        ),
    )

    with pytest.raises(RuntimeError, match="workspace"):
        paper_cli._publish("draft", outside, "version-1", "paper-1")


def test_publish_refuses_a_source_symlink_before_gateway_call(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    paper = workspace / "paper"
    paper.mkdir()
    secret = tmp_path / "secret.tex"
    secret.write_text("private source", encoding="utf-8")
    (paper / "secret.tex").symlink_to(secret)

    monkeypatch.setattr(paper_cli, "WORKSPACE", workspace)
    monkeypatch.setattr(
        paper_cli,
        "_command",
        lambda *args, **kwargs: pytest.fail(
            "must not send symlinked files to the gateway"
        ),
    )

    with pytest.raises(RuntimeError, match="symlink"):
        paper_cli._publish("draft", paper, "version-1", "paper-1")


def test_publish_refuses_a_hard_link_before_gateway_call(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    paper = workspace / "paper"
    paper.mkdir()
    secret = tmp_path / "secret.tex"
    secret.write_text("private source", encoding="utf-8")
    os.link(secret, paper / "secret.tex")

    monkeypatch.setattr(paper_cli, "WORKSPACE", workspace)
    monkeypatch.setattr(
        paper_cli,
        "_command",
        lambda *args, **kwargs: pytest.fail(
            "must not send hard-linked files to the gateway"
        ),
    )

    with pytest.raises(RuntimeError, match="hard link"):
        paper_cli._publish("draft", paper, "version-1", "paper-1")


def test_publish_refuses_a_non_regular_source_entry_before_gateway_call(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    paper = workspace / "paper"
    paper.mkdir()
    os.mkfifo(paper / "untrusted.pipe")

    monkeypatch.setattr(paper_cli, "WORKSPACE", workspace)
    monkeypatch.setattr(
        paper_cli,
        "_command",
        lambda *args, **kwargs: pytest.fail(
            "must not send incomplete source to the gateway"
        ),
    )

    with pytest.raises(RuntimeError, match="non-regular"):
        paper_cli._publish("draft", paper, "version-1", "paper-1")


def test_publish_refuses_a_parent_directory_swap_after_opening_a_source_file(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    paper = workspace / "paper"
    paper.mkdir()
    (paper / "main.tex").write_text("safe source", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "main.tex").write_text("private source", encoding="utf-8")

    original_open_source_file = paper_cli._open_source_file

    def swap_parent_after_open(*args: object) -> int:
        descriptor = original_open_source_file(*args)
        paper.rename(workspace / "paper-original")
        paper.symlink_to(outside, target_is_directory=True)
        return descriptor

    monkeypatch.setattr(paper_cli, "WORKSPACE", workspace)
    monkeypatch.setattr(paper_cli, "_open_source_file", swap_parent_after_open)
    monkeypatch.setattr(
        paper_cli,
        "_command",
        lambda *args, **kwargs: pytest.fail(
            "must not send source after the paper directory changes"
        ),
    )

    with pytest.raises(
        RuntimeError, match="Paper directory changed during publication"
    ):
        paper_cli._publish("draft", paper, "version-1", "paper-1")


def test_publish_refuses_a_regular_source_replaced_by_a_fifo_without_blocking(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    paper = workspace / "paper"
    paper.mkdir()
    target = paper / "main.tex"
    target.write_text("safe source", encoding="utf-8")
    original_open = paper_cli.os.open
    swapped = False

    def replace_before_source_open(
        path: object, flags: int, *args: object, **kwargs: object
    ) -> int:
        nonlocal swapped
        if path == "main.tex" and kwargs.get("dir_fd") is not None and not swapped:
            assert flags & os.O_NONBLOCK
            target.unlink()
            os.mkfifo(target)
            swapped = True
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(paper_cli, "WORKSPACE", workspace)
    monkeypatch.setattr(paper_cli.os, "open", replace_before_source_open)
    monkeypatch.setattr(
        paper_cli,
        "_command",
        lambda *args, **kwargs: pytest.fail("must not send a raced source file"),
    )

    with pytest.raises(RuntimeError, match="changed"):
        paper_cli._publish("draft", paper, "version-1", "paper-1")

    assert swapped


def test_repair_context_refuses_an_outside_directory_before_gateway_call(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"

    monkeypatch.setattr(paper_cli, "WORKSPACE", workspace)
    monkeypatch.setattr(
        paper_cli,
        "_command",
        lambda *args, **kwargs: pytest.fail(
            "must not request repair context outside the workspace"
        ),
    )

    with pytest.raises(RuntimeError, match="workspace"):
        paper_cli._write_context(outside)


def test_repair_context_refuses_a_workspace_symlink_before_gateway_call(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    paper = workspace / "paper"
    paper.mkdir()
    symlink = workspace / "paper-link"
    symlink.symlink_to(paper, target_is_directory=True)

    monkeypatch.setattr(paper_cli, "WORKSPACE", workspace)
    monkeypatch.setattr(
        paper_cli,
        "_command",
        lambda *args, **kwargs: pytest.fail(
            "must not use a symlinked repair directory"
        ),
    )

    with pytest.raises(RuntimeError, match="symlink"):
        paper_cli._write_context(symlink)


def test_repair_context_refuses_a_file_swapped_to_a_symlink(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    paper = workspace / "paper"
    paper.mkdir()
    target = paper / "main.tex"
    target.write_text("old source", encoding="utf-8")
    secret = tmp_path / "secret.tex"
    secret.write_text("private source", encoding="utf-8")

    def command(operation: str, **values: object) -> dict:
        assert operation == "repair-context"
        return {"paper": {}, "files": [{"path": "main.tex", "content": "repair"}]}

    original_repair_path = paper_cli._repair_path

    def swap_after_validation(*args: object) -> Path:
        path = original_repair_path(*args)
        target.unlink()
        target.symlink_to(secret)
        return path

    monkeypatch.setattr(paper_cli, "WORKSPACE", workspace)
    monkeypatch.setattr(paper_cli, "_command", command)
    monkeypatch.setattr(paper_cli, "_repair_path", swap_after_validation)

    with pytest.raises(RuntimeError, match="symlink"):
        paper_cli._write_context(paper)

    assert secret.read_text(encoding="utf-8") == "private source"


def test_repair_context_refuses_a_regular_destination_replaced_before_open(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    paper = workspace / "paper"
    paper.mkdir()
    target = paper / "main.tex"
    target.write_text("old source", encoding="utf-8")
    replacement = tmp_path / "replacement.tex"
    replacement.write_text("private source", encoding="utf-8")

    def command(operation: str, **values: object) -> dict:
        assert operation == "repair-context"
        return {"paper": {}, "files": [{"path": "main.tex", "content": "repair"}]}

    original_validate = paper_cli._validate_repair_destination

    def replace_after_validation(*args: object) -> object:
        result = original_validate(*args)
        os.replace(replacement, target)
        return result

    monkeypatch.setattr(paper_cli, "WORKSPACE", workspace)
    monkeypatch.setattr(paper_cli, "_command", command)
    monkeypatch.setattr(
        paper_cli, "_validate_repair_destination", replace_after_validation
    )

    with pytest.raises(RuntimeError, match="changed"):
        paper_cli._write_context(paper)

    assert target.read_text(encoding="utf-8") == "private source"


def test_repair_context_refuses_a_regular_destination_replaced_after_open(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    paper = workspace / "paper"
    paper.mkdir()
    target = paper / "main.tex"
    target.write_text("old source", encoding="utf-8")
    replacement = tmp_path / "replacement.tex"
    replacement.write_text("private source", encoding="utf-8")

    def command(operation: str, **values: object) -> dict:
        assert operation == "repair-context"
        return {"paper": {}, "files": [{"path": "main.tex", "content": "repair"}]}

    original_ftruncate = paper_cli.os.ftruncate
    swapped = False

    def replace_after_open(descriptor: int, length: int) -> None:
        nonlocal swapped
        if not swapped:
            os.replace(replacement, target)
            swapped = True
        original_ftruncate(descriptor, length)

    monkeypatch.setattr(paper_cli, "WORKSPACE", workspace)
    monkeypatch.setattr(paper_cli, "_command", command)
    monkeypatch.setattr(paper_cli.os, "ftruncate", replace_after_open)

    with pytest.raises(RuntimeError, match="changed"):
        paper_cli._write_context(paper)

    assert swapped
    assert target.read_text(encoding="utf-8") == "private source"


def test_repair_context_leaves_unrelated_temp_named_files_untouched(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    paper = workspace / "paper"
    paper.mkdir()
    temporary = paper / ".pwc-paper-collision"
    temporary.write_text("keep", encoding="utf-8")

    def command(operation: str, **values: object) -> dict:
        assert operation == "repair-context"
        return {"paper": {}, "files": [{"path": "main.tex", "content": "repair"}]}

    monkeypatch.setattr(paper_cli, "WORKSPACE", workspace)
    monkeypatch.setattr(paper_cli, "_command", command)

    assert paper_cli._write_context(paper) == 0
    assert temporary.read_text(encoding="utf-8") == "keep"
