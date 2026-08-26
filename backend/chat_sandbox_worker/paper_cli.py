#!/usr/bin/env python3
"""Authenticated, current-turn-only client for private paper operations."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BROKER = "http://127.0.0.1:8765"
EVENT_PREFIX = "@@PWC_PAPER@@"
MAX_RESPONSE = 3 * 1024 * 1024


def _command(operation: str, **values: object) -> dict:
    payload = {"operation": operation, **values}
    request = urllib.request.Request(
        f"{BROKER}/paper",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
        {"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=130) as response:
            data = response.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as error:
        detail = error.read(8 * 1024).decode(errors="replace")
        raise RuntimeError(detail or f"Paper request failed ({error.code})") from None
    if len(data) > MAX_RESPONSE:
        raise RuntimeError("Paper response exceeded its bound")
    result = json.loads(data)
    if not isinstance(result, dict) or not isinstance(result.get("paper"), dict):
        raise RuntimeError("Invalid paper response")
    return result


def _write_context(directory: Path) -> int:
    result = _command("repair-context")
    files = result.get("files")
    if not isinstance(files, list):
        raise RuntimeError("Invalid paper repair context")
    directory.mkdir(parents=True, exist_ok=True)
    for file in files:
        if (
            not isinstance(file, dict)
            or not isinstance(file.get("path"), str)
            or not isinstance(file.get("content"), str)
        ):
            raise RuntimeError("Invalid paper repair source")
        path = (directory / file["path"]).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise RuntimeError("Invalid paper repair path")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(file["content"], encoding="utf-8")
    print("Checked out the failed paper source for repair.")
    return 0


def _repair(directory: Path, parent_version_id: str, artifact_id: str) -> int:
    return _publish("repair", directory, parent_version_id, artifact_id)


def _draft(directory: Path, parent_version_id: str, artifact_id: str) -> int:
    """Publish the worker-authored first complete draft for this turn only."""
    return _publish("draft", directory, parent_version_id, artifact_id)


def _publish(
    operation: str, directory: Path, parent_version_id: str, artifact_id: str
) -> int:
    files = [
        {
            "path": path.relative_to(directory).as_posix(),
            "content": path.read_text(encoding="utf-8"),
        }
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".tex", ".bib"}
    ]
    result = _command(
        operation,
        artifact_id=artifact_id,
        expected_parent_version_id=parent_version_id,
        files=files,
    )
    activated = result.get("activated")
    if not isinstance(activated, bool):
        raise RuntimeError("Invalid paper publication response")
    receipt = {**result, "operation": operation, "activated": activated}
    print(EVENT_PREFIX + json.dumps(receipt, ensure_ascii=False, separators=(",", ":")))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="pwc-paper")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--title", required=True)
    commands.add_parser("begin-edit")
    checkout = commands.add_parser("repair-context")
    checkout.add_argument("--directory", required=True)
    repair = commands.add_parser("repair")
    repair.add_argument("--directory", required=True)
    repair.add_argument("--artifact-id", required=True)
    repair.add_argument("--expected-parent-version-id", required=True)
    draft = commands.add_parser("draft")
    draft.add_argument("--directory", required=True)
    draft.add_argument("--artifact-id", required=True)
    draft.add_argument("--expected-parent-version-id", required=True)
    args = parser.parse_args()
    try:
        if args.command == "repair-context":
            return _write_context(Path(args.directory))
        if args.command == "repair":
            return _repair(
                Path(args.directory), args.expected_parent_version_id, args.artifact_id
            )
        if args.command == "draft":
            return _draft(
                Path(args.directory), args.expected_parent_version_id, args.artifact_id
            )
        result = _command(args.command, title=getattr(args, "title", None))
        print(
            EVENT_PREFIX + json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        )
        return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
