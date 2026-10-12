"""Paper-Markdown bucket bridge and storage transfers: isolated SDK, manifests, and the volume probe."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from backend.tests.paper.markdown_harness import (
    MODULE,
    PROBE,
    WORKER,
    WORKER_SCRIPT,
)


def test_bucket_bridge_uses_isolated_sdk_without_exposing_token(monkeypatch):
    observed = {}

    def run(command, **kwargs):
        observed.update(command=command, **kwargs)
        return SimpleNamespace(returncode=0, stdout='{"paths": []}', stderr="")

    monkeypatch.setattr(WORKER.subprocess, "run", run)

    result = WORKER.run_bucket_bridge(
        "secret-token",
        {
            "operation": "existing",
            "bucket_id": "test/paper-markdown",
            "keys": ["paper.md"],
        },
    )

    assert result == {"paths": []}
    assert observed["command"][:6] == [
        "uv",
        "run",
        "--no-project",
        "--with",
        "huggingface-hub==1.23.0",
        "python",
    ]
    assert "secret-token" not in observed["command"]
    assert observed["env"]["HF_TOKEN"] == "secret-token"
    assert json.loads(observed["input"])["operation"] == "existing"
    assert observed["capture_output"] is True


def test_bucket_bridge_code_uses_bucket_apis_for_all_operations(tmp_path, monkeypatch):
    remote = {"manifest.jsonl": b'{"arxiv_id":"2608.00001"}\n'}
    uploads = []

    class Api:
        def get_bucket_paths_info(self, bucket_id, keys):
            assert bucket_id == "test/paper-markdown"
            return [SimpleNamespace(path=key) for key in keys if key in remote]

        def download_bucket_files(self, bucket_id, files, *, raise_on_missing_files):
            assert bucket_id == "test/paper-markdown"
            assert raise_on_missing_files is True
            for key, destination in files:
                Path(destination).write_bytes(remote[key])

        def batch_bucket_files(self, bucket_id, *, add):
            assert bucket_id == "test/paper-markdown"
            uploads.extend(
                (Path(source).read_bytes(), destination) for source, destination in add
            )

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(HfApi=Api))

    def execute(request):
        output = StringIO()
        monkeypatch.setattr(sys, "stdin", StringIO(json.dumps(request)))
        monkeypatch.setattr(sys, "stdout", output)
        exec(WORKER.BUCKET_BRIDGE_CODE, {})  # noqa: S102 - exercise trusted code
        return json.loads(output.getvalue())

    assert execute(
        {
            "operation": "existing",
            "bucket_id": "test/paper-markdown",
            "keys": ["manifest.jsonl", "missing.json"],
        }
    ) == {"paths": ["manifest.jsonl"]}

    downloaded = tmp_path / "downloaded.jsonl"
    assert (
        execute(
            {
                "operation": "download",
                "bucket_id": "test/paper-markdown",
                "files": [["manifest.jsonl", str(downloaded)]],
            }
        )
        == {}
    )
    assert downloaded.read_bytes() == remote["manifest.jsonl"]

    upload = tmp_path / "result.json"
    upload.write_text('{"status":"succeeded"}')
    assert (
        execute(
            {
                "operation": "upload",
                "bucket_id": "test/paper-markdown",
                "files": [[str(upload), "_jobs/results/result.json"]],
            }
        )
        == {}
    )
    assert uploads == [(upload.read_bytes(), "_jobs/results/result.json")]


def test_bucket_worker_downloads_manifest_and_uploads_outputs_without_mount(
    tmp_path, monkeypatch
):
    manifest_key = "_jobs/manifests/backfill-20260824T120000-12345678/00000.jsonl"
    entry = {
        "arxiv_id": "2608.00001",
        "version": "v1",
        "title": "Bucket transport",
        "output_key": "2608/2608.00001.md",
    }
    remote = {manifest_key: (json.dumps(entry) + "\n").encode()}
    upload_batches = []
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "2608.00001.md").write_text("Bucket transport paper text. " * 12)

    def bucket_bridge(token, request):
        assert token == "secret"
        assert request["bucket_id"] == "test/paper-markdown"
        if request["operation"] == "existing":
            return {"paths": [key for key in request["keys"] if key in remote]}
        if request["operation"] == "download":
            for key, destination_value in request["files"]:
                destination = Path(destination_value)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(remote[key])
            return {}
        if request["operation"] == "upload":
            upload_batches.append([key for _source, key in request["files"]])
            for source, key in request["files"]:
                remote[key] = Path(source).read_bytes()
            return {}
        raise AssertionError(f"unexpected bridge operation: {request['operation']}")

    monkeypatch.setattr(WORKER, "run_bucket_bridge", bucket_bridge)
    monkeypatch.setenv("HF_TOKEN", "secret")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(WORKER_SCRIPT),
            "--bucket-id",
            "test/paper-markdown",
            "--manifest-key",
            manifest_key,
            "--stub-root",
            str(stub),
            "--soft-deadline-seconds",
            "60",
        ],
    )

    WORKER.main()

    assert remote[entry["output_key"]].startswith(b"Title: Bucket transport")
    status = json.loads(remote["_jobs/status/2608.00001.json"])
    assert status["status"] == "succeeded"
    assert remote[status["markdown_content_key"]] == remote[entry["output_key"]]
    version_manifest = json.loads(remote[status["markdown_manifest_key"]])
    assert version_manifest["content_sha256"] == status["markdown_sha256"]
    content_batch = next(
        batch for batch in upload_batches if status["markdown_content_key"] in batch
    )
    manifest_batch = next(
        batch for batch in upload_batches if status["markdown_manifest_key"] in batch
    )
    assert upload_batches.index(content_batch) < upload_batches.index(manifest_batch)
    assert status["markdown_content_key"] not in manifest_batch
    progress = json.loads(
        remote["_jobs/progress/backfill-20260824T120000-12345678/00000.json"]
    )
    assert progress["status"] == "completed"


def test_bucket_prepare_downloads_alias_when_version_manifest_is_missing(
    tmp_path, monkeypatch
):
    entry = {
        "arxiv_id": "2608.00001",
        "version": "v1",
        "title": "Interrupted publication",
        "output_key": "2608/2608.00001.md",
    }
    output_key = entry["output_key"]
    canonical = b"canonical markdown"
    remote = {output_key: canonical}

    def bucket_bridge(_token, request):
        if request["operation"] == "existing":
            return {"paths": [key for key in request["keys"] if key in remote]}
        if request["operation"] == "download":
            for key, destination_value in request["files"]:
                destination = Path(destination_value)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(remote[key])
            return {}
        raise AssertionError(f"unexpected bridge operation: {request['operation']}")

    monkeypatch.setattr(WORKER, "run_bucket_bridge", bucket_bridge)
    store = WORKER.BucketContentStore("test/paper-markdown", "secret", tmp_path)

    store.prepare("_jobs/manifests/run/00000.jsonl", [entry])

    assert (tmp_path / output_key).read_bytes() == canonical


def test_volume_probe_reads_writes_verifies_and_cleans_only_temporary_object(
    tmp_path,
):
    content = tmp_path / "content"
    manifest = content / "_jobs/capabilities/probe-test.manifest.json"
    result = content / "_jobs/capabilities/probe-test.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "probe_id": "probe-test",
                "nonce": "a" * 32,
                "bucket_id": "test/paper-markdown",
                "namespace": "test-owner",
                "mount_path": "/content",
                "read_only": False,
            }
        )
    )

    evidence = PROBE.run_probe(
        content_root=content, manifest_path=manifest, result_path=result
    )

    assert evidence["status"] == "succeeded"
    assert evidence["temporary_object_cleaned"] is True
    assert manifest.exists()
    assert result.exists()
    assert list(manifest.parent.glob("*.probe")) == []


@pytest.mark.parametrize(
    "error",
    [httpx.RemoteProtocolError("truncated response"), httpx.ReadError("disconnected")],
)
def test_http_transfer_failures_retry_with_attempt_limit(error):
    assert WORKER.classify_failure(error, 1) == ("arxiv_transport", True)
    assert WORKER.classify_failure(error, 3) == ("arxiv_transport", False)
    old = {
        "status": "failed",
        "schema_version": 2,
        "error_class": type(error).__name__,
        "retryable": False,
        "attempt_count": 1,
    }
    assert MODULE.status_disposition(old) == "retryable_due"
    old["attempt_count"] = 3
    assert MODULE.status_disposition(old) == "attempts_exhausted"
