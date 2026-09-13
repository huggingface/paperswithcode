# /// script
# requires-python = ">=3.12"
# ///
"""Materialize immutable Markdown revisions from canonical bucket objects.

Run this script inside a Hugging Face Job with the paper-content Bucket mounted
at ``--content-root``. The JSONL input is generated separately and contains one
``output_key`` per paper. Only one bounded batch is processed per invocation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

MAX_MARKDOWN_BYTES = 64 * 1024 * 1024
MAX_BATCH_SIZE = 1_000
SCHEMA_VERSION = 1
LOCK_KEY = "_content/migration.lock"
ARXIV_OUTPUT = re.compile(r"^(?P<paper>\d{4}\.\d{4,5})[:/]?(?P=paper)?$")
CANONICAL_OUTPUT = re.compile(
    r"^(?:(?P<prefix>\d{4})/(?P<arxiv>\d{4}\.\d{4,5})|"
    r"external/(?P<external>[1-9]\d{0,19}))\.md$"
)
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial-{os.getpid()}")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def paper_key_from_output(output_key: str) -> str:
    match = CANONICAL_OUTPUT.fullmatch(output_key)
    if match is None:
        raise ValueError("invalid_output_key")
    arxiv = match.group("arxiv")
    if arxiv is not None:
        if match.group("prefix") != arxiv[:4]:
            raise ValueError("invalid_output_key")
        return arxiv
    return f"external/{match.group('external')}"


def content_key(content_sha256: str) -> str:
    if SHA256_HEX.fullmatch(content_sha256) is None:
        raise ValueError("invalid_content_version")
    return f"_content/sha256/{content_sha256[:2]}/{content_sha256}.md"


def manifest_key(paper_key: str) -> str:
    if re.fullmatch(r"(?:\d{4}\.\d{4,5}|external/[1-9]\d{0,19})", paper_key) is None:
        raise ValueError("invalid_paper_key")
    return f"_content/manifests/{paper_key}.json"


def _bounded_markdown(path: Path) -> bytes:
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_MARKDOWN_BYTES + 1)
    except FileNotFoundError as error:
        raise ValueError("canonical_markdown_missing") from error
    if not data or len(data) > MAX_MARKDOWN_BYTES:
        raise ValueError("invalid_markdown_size")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("invalid_markdown_utf8") from error
    return data


def _manifest(paper_key: str, digest: str, size: int) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "paper_key": paper_key,
        "source": "external" if paper_key.startswith("external/") else "arxiv",
        "content_sha256": digest,
        "content_key": content_key(digest),
        "size_bytes": size,
    }


def migrate_entry(
    content_root: Path, entry: dict[str, object], *, dry_run: bool = False
) -> dict[str, object]:
    output_key = str(entry.get("output_key") or "")
    paper_key = paper_key_from_output(output_key)
    canonical = content_root / output_key
    data = _bounded_markdown(canonical)
    digest = hashlib.sha256(data).hexdigest()
    manifest = _manifest(paper_key, digest, len(data))
    immutable = content_root / str(manifest["content_key"])
    pointer = content_root / manifest_key(paper_key)

    if pointer.exists():
        try:
            current = json.loads(pointer.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("invalid_existing_manifest") from error
        if current != manifest:
            raise ValueError("manifest_conflict")
        if not immutable.exists() or _bounded_markdown(immutable) != data:
            raise ValueError("immutable_content_conflict")
        return {"paper_key": paper_key, "status": "already_current", **manifest}

    if immutable.exists() and _bounded_markdown(immutable) != data:
        raise ValueError("immutable_content_conflict")
    if not dry_run:
        if not immutable.exists():
            atomic_write(immutable, data)
        if _bounded_markdown(immutable) != data:
            raise ValueError("immutable_content_conflict")
        atomic_write(
            pointer,
            (
                json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode(),
        )
    return {
        "paper_key": paper_key,
        "status": "planned" if dry_run else "migrated",
        **manifest,
    }


@contextmanager
def migration_lock(content_root: Path, *, dry_run: bool) -> Iterator[None]:
    lock = content_root / LOCK_KEY
    if dry_run:
        yield
        return
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ValueError("markdown_migration_locked") from error
    try:
        payload = {
            "schema_version": 1,
            "started_at": datetime.now(UTC).isoformat(),
            "pid": os.getpid(),
        }
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        yield
    finally:
        lock.unlink(missing_ok=True)


def migrate_manifest(
    content_root: Path,
    input_path: Path,
    *,
    result_path: Path | None,
    limit: int,
    start_after: str | None,
    dry_run: bool,
) -> dict[str, int]:
    if limit < 1 or limit > MAX_BATCH_SIZE:
        raise ValueError("invalid_batch_limit")
    counts = {"processed": 0, "migrated": 0, "already_current": 0, "planned": 0}
    with migration_lock(content_root, dry_run=dry_run):
        with input_path.open("r", encoding="utf-8") as source:
            for raw_line in source:
                if counts["processed"] >= limit:
                    break
                if not raw_line.strip():
                    continue
                entry = json.loads(raw_line)
                if not isinstance(entry, dict):
                    raise ValueError("invalid_migration_entry")
                paper_key = paper_key_from_output(str(entry.get("output_key") or ""))
                if start_after is not None and paper_key <= start_after:
                    continue
                result = migrate_entry(content_root, entry, dry_run=dry_run)
                counts["processed"] += 1
                counts[str(result["status"])] += 1
                if result_path is not None:
                    result_path.parent.mkdir(parents=True, exist_ok=True)
                    with result_path.open("a", encoding="utf-8") as output:
                        output.write(json.dumps(result, sort_keys=True) + "\n")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content-root", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--start-after")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    counts = migrate_manifest(
        args.content_root,
        args.input,
        result_path=args.result,
        limit=args.limit,
        start_after=args.start_after,
        dry_run=args.dry_run,
    )
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
