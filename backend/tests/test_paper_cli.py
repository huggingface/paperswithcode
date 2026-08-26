from __future__ import annotations

import json
import sys
from pathlib import Path

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
