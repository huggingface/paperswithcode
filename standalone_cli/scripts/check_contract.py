#!/usr/bin/env python3
"""Fail CI when parser, sandbox guide, or public-skill inventory drifts."""

from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "standalone_cli" / "src"))

from pwc_cli.cli import build_parser  # noqa: E402

COMMANDS = (
    "search",
    "paper info",
    "paper read",
    "paper list",
    "paper recent",
    "paper trending",
    "paper related",
    "paper lineage list",
    "benchmark",
    "benchmark list",
    "version",
)


def parser_commands() -> set[str]:
    parser = build_parser()
    discovered: set[str] = set()

    def visit(current, prefix: str = ""):
        for action in current._actions:
            choices = getattr(action, "choices", None)
            if not isinstance(choices, dict):
                continue
            for name, child in choices.items():
                command = f"{prefix} {name}".strip()
                nested = any(
                    isinstance(getattr(item, "choices", None), dict)
                    for item in child._actions
                )
                if nested:
                    if "handler" in child._defaults:
                        discovered.add(command)
                    visit(child, command)
                else:
                    discovered.add(command)

    visit(parser)
    return discovered


def main() -> int:
    expected = set(COMMANDS)
    if parser_commands() != expected:
        raise SystemExit("standalone parser command inventory drifted")
    guide = (
        REPOSITORY / "backend" / "chat_sandbox_worker" / "CLI_GUIDE.md"
    ).read_text()
    skill = (REPOSITORY / "standalone_cli" / "SKILL.md").read_text()
    for command in COMMANDS:
        if command == "version":
            continue
        invocation = f"pwc {command}"
        if invocation not in guide or invocation not in skill:
            raise SystemExit(f"missing read-only inventory entry: {invocation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
