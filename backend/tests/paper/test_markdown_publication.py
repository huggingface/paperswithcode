"""Paper-Markdown publication: content-addressed objects, version manifests, and identity keys."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from backend.tests.paper.markdown_harness import (
    MODULE,
    WORKER,
)


def test_worker_publishes_content_addressed_markdown_and_manifest(tmp_path):
    entry = {
        "arxiv_id": "2607.00001",
        "version": "v1",
        "title": "Versioned paper",
        "output_key": "2607/2607.00001.md",
    }

    result = WORKER.publish(
        entry,
        "Versioned paper explains immutable Markdown storage. " * 40,
        {},
        tmp_path,
    )

    canonical = (tmp_path / entry["output_key"]).read_bytes()
    assert result["markdown_sha256"] == hashlib.sha256(canonical).hexdigest()
    assert (tmp_path / result["markdown_content_key"]).read_bytes() == canonical
    manifest = json.loads((tmp_path / result["markdown_manifest_key"]).read_text())
    assert manifest == {
        "schema_version": 1,
        "paper_key": "2607.00001",
        "source": "arxiv",
        "content_sha256": result["markdown_sha256"],
        "content_key": result["markdown_content_key"],
        "size_bytes": len(canonical),
    }


def test_worker_repairs_missing_version_manifest_from_existing_alias(tmp_path):
    entry = {
        "arxiv_id": "2607.00001",
        "version": "v1",
        "title": "Versioned paper",
        "output_key": "2607/2607.00001.md",
    }
    canonical = (
        b"Title: Versioned paper\n\nMarkdown Content:\n\n"
        + b"Existing canonical content. " * 8
    )
    output = tmp_path / entry["output_key"]
    output.parent.mkdir(parents=True)
    output.write_bytes(canonical)

    result = WORKER.process(entry, tmp_path, tmp_path / "run")

    assert result["status"] == "succeeded"
    assert (tmp_path / result["markdown_content_key"]).read_bytes() == canonical
    manifest = json.loads((tmp_path / result["markdown_manifest_key"]).read_text())
    assert manifest["content_sha256"] == hashlib.sha256(canonical).hexdigest()


def test_worker_rejects_invalid_content_versions_and_paper_keys():
    with pytest.raises(ValueError, match="invalid_markdown_content_version"):
        WORKER.markdown_content_key("../not-a-digest")
    with pytest.raises(ValueError, match="invalid_markdown_paper_key"):
        WORKER.markdown_manifest_key("../../secret")


def test_worker_refuses_to_publish_during_version_migration(tmp_path):
    lock = tmp_path / WORKER.MARKDOWN_MIGRATION_LOCK_KEY
    lock.parent.mkdir(parents=True)
    lock.write_text("occupied")

    with pytest.raises(ValueError, match="markdown_migration_locked"):
        WORKER.publish(
            {
                "arxiv_id": "2607.00001",
                "version": "v1",
                "title": "Versioned paper",
                "output_key": "2607/2607.00001.md",
            },
            "Versioned paper explains immutable Markdown storage. " * 40,
            {},
            tmp_path,
        )


def test_arxiv_identity_and_markdown_key():
    assert MODULE.normalize_arxiv_id("2607.24653v2") == "2607.24653"
    assert MODULE.markdown_key("2607.24653") == "2607/2607.24653.md"
    assert MODULE.normalize_arxiv_id("hep-th/9901001") is None


def test_external_manifest_entry_prefers_pdf_source_url_then_explicit_pdf():
    explicit = SimpleNamespace(
        id=109743,
        source="external",
        arxiv_id=None,
        version="v1",
        title="External report",
        source_url="https://example.com/report",
        conference_url_pdf="https://example.com/report.pdf",
    )
    source_only = SimpleNamespace(
        id=109744,
        source="external",
        arxiv_id=None,
        version="v1",
        title="Source PDF",
        source_url="https://openreview.net/pdf?id=abc",
        conference_url_pdf=None,
    )
    both = SimpleNamespace(
        id=109746,
        source="external",
        arxiv_id=None,
        version="v1",
        title="Canonical source PDF",
        source_url="https://example.com/canonical.pdf",
        conference_url_pdf="https://example.com/conference-copy.pdf",
    )
    html_only = SimpleNamespace(
        id=109745,
        source="external",
        arxiv_id=None,
        version="v1",
        title="Web page",
        source_url="https://example.com/report",
        conference_url_pdf=None,
    )

    assert MODULE.paper_manifest_entry(explicit) == {
        "paper_key": "external/109743",
        "paper_id": "109743",
        "source": "external",
        "arxiv_id": None,
        "version": "v1",
        "title": "External report",
        "source_url": "https://example.com/report",
        "pdf_url": "https://example.com/report.pdf",
        "pdf_key": "external/109743/paper.pdf",
        "output_key": "external/109743.md",
    }
    assert MODULE.paper_manifest_entry(source_only)["pdf_url"] == source_only.source_url
    assert MODULE.paper_manifest_entry(both)["pdf_url"] == both.source_url
    assert MODULE.paper_manifest_entry(html_only) is None


def test_arxiv_manifest_entry_preserves_canonical_bucket_contract():
    paper = SimpleNamespace(
        id=42,
        source="arxiv",
        arxiv_id="2607.24653v2",
        version="v2",
        title="ArXiv paper",
        source_url=None,
        conference_url_pdf=None,
    )

    entry = MODULE.paper_manifest_entry(paper)

    assert entry["paper_key"] == "2607.24653"
    assert entry["output_key"] == "2607/2607.24653.md"
    assert entry["pdf_key"] is None
