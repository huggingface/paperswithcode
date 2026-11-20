"""Ratchet check that keeps comments out of the backend.

Rationale for a non-obvious decision belongs in an ADR under ``docs/adr/``,
hacks belong in a GitHub issue, and everything else belongs in the code itself.
Tool directives such as ``# noqa`` or ``# type: ignore`` are not comments for
this rule, and neither is PEP 723 ``# /// script`` metadata, which uv reads.

Subcommands:

* ``check`` fails when a file has more comments than ``backend/comment-baseline.json``
  allows. Files missing from the baseline allow none.
* ``update`` rewrites the baseline to the current counts. It refuses to raise a
  count unless ``--allow-increase`` is passed.
* ``inventory`` writes every comment block as JSON lines for the
  ``delete-comment`` skill.
* ``delete`` removes the comment blocks listed in a JSON lines file of
  ``{"f", "start", "end", "kind"}`` records produced by ``inventory``.
"""

import argparse
import io
import json
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
BASELINE = BACKEND / "comment-baseline.json"
SKIPPED_PARTS = {".venv", "__pycache__", "node_modules"}
DIRECTIVE = re.compile(
    r"#\s*(noqa\b|type:\s*ignore|pragma:|fmt:|pyright:|mypy:|ruff:|isort:)"
)
ENCODING = re.compile(r"#.*coding[:=]")


def backend_files() -> list[Path]:
    return sorted(
        path
        for path in BACKEND.rglob("*.py")
        if not SKIPPED_PARTS.intersection(path.parts)
    )


def is_directive(token: tokenize.TokenInfo) -> bool:
    line_number = token.start[0]
    if line_number == 1 and token.string.startswith("#!"):
        return True
    if line_number <= 2 and ENCODING.match(token.string):
        return True
    return bool(DIRECTIVE.match(token.string))


def comments(path: Path) -> list[dict]:
    source = path.read_text()
    lines = source.splitlines()
    found = []
    in_script_metadata = False
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        if token.string.startswith("# /// "):
            in_script_metadata = True
        if in_script_metadata:
            in_script_metadata = token.string.rstrip() != "# ///"
            continue
        if is_directive(token):
            continue
        line_number = token.start[0]
        own_line = lines[line_number - 1].lstrip().startswith("#")
        found.append(
            {
                "line": line_number,
                "kind": "own" if own_line else "inline",
                "text": token.string,
            }
        )
    return found


def counts() -> dict[str, int]:
    result = {}
    for path in backend_files():
        number = len(comments(path))
        if number:
            result[path.relative_to(ROOT).as_posix()] = number
    return result


def load_baseline() -> dict[str, int]:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text())


def write_baseline(baseline: dict[str, int]) -> None:
    BASELINE.write_text(json.dumps(dict(sorted(baseline.items())), indent=2) + "\n")


def check() -> int:
    baseline = load_baseline()
    current = counts()
    failures = [
        (name, number, baseline.get(name, 0))
        for name, number in sorted(current.items())
        if number > baseline.get(name, 0)
    ]
    for name, number, allowed in failures:
        print(
            f"{name}: {number} comments, baseline allows {allowed}. "
            "Delete the new comments; record decisions in docs/adr/ and hacks in a GitHub issue."
        )
    loose = sum(baseline.get(name, 0) - current.get(name, 0) for name in baseline)
    if not failures and loose > 0:
        print(
            f"Baseline allows {loose} more comments than exist. "
            "Run `python3 scripts/backend_comments.py update` to tighten it."
        )
    return 1 if failures else 0


def update(allow_increase: bool) -> int:
    baseline = load_baseline()
    current = counts()
    increases = {
        name: (baseline.get(name, 0), number)
        for name, number in current.items()
        if number > baseline.get(name, 0)
    }
    if increases and not allow_increase:
        for name, (allowed, number) in sorted(increases.items()):
            print(f"{name}: {allowed} -> {number} would raise the baseline")
        return 1
    write_baseline(current)
    print(
        f"Baseline now allows {sum(current.values())} comments in {len(current)} files."
    )
    return 0


def inventory(output: Path) -> int:
    with output.open("w") as handle:
        for path in backend_files():
            name = path.relative_to(ROOT).as_posix()
            block = None
            for comment in comments(path):
                continues_block = (
                    block is not None
                    and comment["kind"] == "own"
                    and block["kind"] == "own"
                    and comment["line"] == block["end"] + 1
                )
                if continues_block:
                    block["end"] = comment["line"]
                    block["text"] += "\n" + comment["text"]
                    continue
                if block is not None:
                    handle.write(json.dumps(block) + "\n")
                block = {
                    "f": name,
                    "kind": comment["kind"],
                    "start": comment["line"],
                    "end": comment["line"],
                    "text": comment["text"],
                }
            if block is not None:
                handle.write(json.dumps(block) + "\n")
    return 0


def strip_inline_comment(line: str) -> str:
    tokens = list(tokenize.generate_tokens(io.StringIO(line + "\n").readline))
    comment = next(token for token in tokens if token.type == tokenize.COMMENT)
    return line[: comment.start[1]].rstrip()


def delete(selection: Path) -> int:
    by_file: dict[str, list[dict]] = {}
    for raw in selection.read_text().splitlines():
        if raw.strip():
            record = json.loads(raw)
            by_file.setdefault(record["f"], []).append(record)
    for name, records in sorted(by_file.items()):
        path = ROOT / name
        lines = path.read_text().splitlines(keepends=True)
        current = {comment["line"]: comment for comment in comments(path)}
        drop = set()
        for record in records:
            for line_number in range(record["start"], record["end"] + 1):
                if line_number not in current:
                    raise SystemExit(f"{name}:{line_number} is no longer a comment")
            if record["kind"] == "own":
                drop.update(range(record["start"], record["end"] + 1))
                continue
            index = record["start"] - 1
            ending = "\n" if lines[index].endswith("\n") else ""
            lines[index] = strip_inline_comment(lines[index].rstrip("\n")) + ending
        kept = [
            line for number, line in enumerate(lines, start=1) if number not in drop
        ]
        path.write_text("".join(kept))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    update_parser = commands.add_parser("update")
    update_parser.add_argument("--allow-increase", action="store_true")
    inventory_parser = commands.add_parser("inventory")
    inventory_parser.add_argument("output", type=Path)
    delete_parser = commands.add_parser("delete")
    delete_parser.add_argument("selection", type=Path)
    args = parser.parse_args()
    if args.command == "check":
        return check()
    if args.command == "update":
        return update(args.allow_increase)
    if args.command == "inventory":
        return inventory(args.output)
    return delete(args.selection)


if __name__ == "__main__":
    sys.exit(main())
