from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "migrate_paper_markdown_versions.py"
)
SPEC = importlib.util.spec_from_file_location("migrate_paper_markdown_versions", SCRIPT)
assert SPEC and SPEC.loader
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def _canonical(root: Path, key: str = "2607/2607.00001.md") -> bytes:
    data = ("Title: Versioned paper\n\nMarkdown Content:\n\n" + "body " * 30).encode()
    path = root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def test_migrate_entry_publishes_immutable_content_before_manifest(tmp_path):
    data = _canonical(tmp_path)

    result = MIGRATION.migrate_entry(tmp_path, {"output_key": "2607/2607.00001.md"})

    digest = hashlib.sha256(data).hexdigest()
    immutable = tmp_path / f"_content/sha256/{digest[:2]}/{digest}.md"
    pointer = tmp_path / "_content/manifests/2607.00001.json"
    assert immutable.read_bytes() == data
    assert json.loads(pointer.read_text()) == {
        "schema_version": 1,
        "paper_key": "2607.00001",
        "source": "arxiv",
        "content_sha256": digest,
        "content_key": f"_content/sha256/{digest[:2]}/{digest}.md",
        "size_bytes": len(data),
    }
    assert result["status"] == "migrated"


def test_migrate_entry_is_idempotent_and_rejects_manifest_conflicts(tmp_path):
    _canonical(tmp_path)
    entry = {"output_key": "2607/2607.00001.md"}
    MIGRATION.migrate_entry(tmp_path, entry)

    assert MIGRATION.migrate_entry(tmp_path, entry)["status"] == "already_current"

    pointer = tmp_path / "_content/manifests/2607.00001.json"
    payload = json.loads(pointer.read_text())
    payload["size_bytes"] += 1
    pointer.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="manifest_conflict"):
        MIGRATION.migrate_entry(tmp_path, entry)


def test_migrate_entry_supports_external_papers_and_validates_paths(tmp_path):
    _canonical(tmp_path, "external/109743.md")

    result = MIGRATION.migrate_entry(
        tmp_path, {"output_key": "external/109743.md"}, dry_run=True
    )

    assert result["paper_key"] == "external/109743"
    assert result["source"] == "external"
    assert result["status"] == "planned"
    assert not (tmp_path / "_content").exists()
    for key in ("../secret.md", "2608/2607.00001.md", "external/0.md"):
        with pytest.raises(ValueError, match="invalid_output_key"):
            MIGRATION.paper_key_from_output(key)


def test_migrate_entry_rejects_oversize_and_invalid_utf8(tmp_path, monkeypatch):
    path = tmp_path / "2607/2607.00001.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="invalid_markdown_utf8"):
        MIGRATION.migrate_entry(tmp_path, {"output_key": "2607/2607.00001.md"})

    monkeypatch.setattr(MIGRATION, "MAX_MARKDOWN_BYTES", 3)
    path.write_bytes(b"four")
    with pytest.raises(ValueError, match="invalid_markdown_size"):
        MIGRATION.migrate_entry(tmp_path, {"output_key": "2607/2607.00001.md"})


def test_migrate_manifest_is_bounded_resumable_and_cleans_lock(tmp_path):
    entries = []
    for suffix in ("00001", "00002", "00003"):
        key = f"2607/2607.{suffix}.md"
        _canonical(tmp_path, key)
        entries.append({"output_key": key})
    source = tmp_path / "input.jsonl"
    source.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
    result_path = tmp_path / "results.jsonl"

    counts = MIGRATION.migrate_manifest(
        tmp_path,
        source,
        result_path=result_path,
        limit=1,
        start_after="2607.00001",
        dry_run=False,
    )

    assert counts == {
        "processed": 1,
        "migrated": 1,
        "already_current": 0,
        "planned": 0,
    }
    rows = [json.loads(line) for line in result_path.read_text().splitlines()]
    assert [row["paper_key"] for row in rows] == ["2607.00002"]
    assert not (tmp_path / MIGRATION.LOCK_KEY).exists()


def test_migration_lock_blocks_concurrent_jobs_and_writer(tmp_path):
    lock = tmp_path / MIGRATION.LOCK_KEY
    lock.parent.mkdir(parents=True)
    lock.write_text("occupied")

    with pytest.raises(ValueError, match="markdown_migration_locked"):
        with MIGRATION.migration_lock(tmp_path, dry_run=False):
            pass


def test_migration_lock_is_removed_after_failure(tmp_path):
    with pytest.raises(RuntimeError, match="boom"):
        with MIGRATION.migration_lock(tmp_path, dry_run=False):
            raise RuntimeError("boom")

    assert not (tmp_path / MIGRATION.LOCK_KEY).exists()
