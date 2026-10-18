"""Paper-Markdown remote worker lifecycle: checkpoints, deadlines, failures, and vLLM shutdown."""

from __future__ import annotations

import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from backend.tests.paper.markdown_harness import (
    WORKER,
    WORKER_SCRIPT,
)


def _candidates(count: int):
    return [
        {
            "arxiv_id": f"2607.{index:05d}",
            "version": "v1",
            "title": f"Paper {index}",
            "output_key": f"2607/2607.{index:05d}.md",
        }
        for index in range(count)
    ]


def test_chandra_worker_stub_writes_canonical_markdown_and_checkpoint(tmp_path):
    content = tmp_path / "content"
    stub = tmp_path / "stub"
    manifest = content / "_jobs" / "manifests" / "run-1" / "00000.jsonl"
    manifest.parent.mkdir(parents=True)
    stub.mkdir()
    entry = {
        "arxiv_id": "2607.24653",
        "version": "v1",
        "title": "Kimi K3",
        "output_key": "2607/2607.24653.md",
    }
    manifest.write_text(json.dumps(entry) + "\n")
    (stub / "2607.24653.md").write_text(
        "Kimi K3 paper text.\n\n![figure](figure.webp)\n\nAfter image. " * 80
    )
    asset_dir = stub / "2607.24653"
    asset_dir.mkdir()
    image_buffer = BytesIO()
    Image.new("RGB", (16, 12), "navy").save(image_buffer, format="WEBP")
    (asset_dir / "figure.webp").write_bytes(image_buffer.getvalue())
    worker = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "generate_missing_paper_markdown.py"
    )

    subprocess.run(
        [
            sys.executable,
            str(worker),
            "--manifest",
            str(manifest),
            "--content-root",
            str(content),
            "--stub-root",
            str(stub),
            "--soft-deadline-seconds",
            "30",
        ],
        check=True,
    )

    markdown = (content / entry["output_key"]).read_text()
    assert markdown.startswith("Title: Kimi K3\n\nURL Source:")
    assert "https://paperswithcode.co/paper-assets/2607/2607.24653/images/" in markdown
    assert "figure.webp" not in markdown
    status = json.loads((content / "_jobs" / "status" / "2607.24653.json").read_text())
    assert status["status"] == "succeeded"
    assert status["schema_version"] == 2
    assert status["attempt_count"] == 1
    assert status["retryable"] is False
    assert status["model_id"] == "datalab-to/chandra-ocr-2"
    assert status["image_count"] == 1
    assert len(status["asset_keys"]) == 1
    assert (content / status["asset_keys"][0]).is_file()
    progress = json.loads(
        (content / "_jobs" / "progress" / "run-1" / "00000.json").read_text()
    )
    assert progress["status"] == "completed"
    assert progress["total_papers"] == 1
    assert progress["processed_papers"] == 1
    assert progress["succeeded_papers"] == 1
    assert progress["failed_papers"] == 0
    assert progress["extracted_images"] == 1
    assert progress["omitted_images"] == 0


def test_chandra_worker_failure_records_duration(tmp_path):
    content = tmp_path / "content"
    stub = tmp_path / "stub"
    manifest = content / "_jobs" / "manifests" / "run-failure" / "00000.jsonl"
    manifest.parent.mkdir(parents=True)
    stub.mkdir()
    entry = {
        "arxiv_id": "2607.24653",
        "version": "v1",
        "title": "Kimi K3",
        "output_key": "2607/2607.24653.md",
    }
    manifest.write_text(json.dumps(entry) + "\n")
    (stub / "2607.24653.md").write_text(
        "Kimi K3 paper text.\n\n![figure](missing.webp)\n\nAfter image. " * 80
    )

    subprocess.run(
        [
            sys.executable,
            str(WORKER_SCRIPT),
            "--manifest",
            str(manifest),
            "--content-root",
            str(content),
            "--stub-root",
            str(stub),
            "--soft-deadline-seconds",
            "30",
        ],
        check=True,
    )

    status = json.loads((content / "_jobs" / "status" / "2607.24653.json").read_text())
    assert status["status"] == "failed"
    assert status["duration_seconds"] >= 0
    progress = json.loads(
        (content / "_jobs" / "progress" / "run-failure" / "00000.json").read_text()
    )
    assert progress["paper_duration_p50_seconds"] is not None
    assert progress["paper_duration_p95_seconds"] is not None


def test_chandra_worker_final_attempt_omits_missing_image(tmp_path):
    content = tmp_path / "content"
    stub = tmp_path / "stub"
    manifest = content / "_jobs" / "manifests" / "run-final" / "00000.jsonl"
    status_path = content / "_jobs" / "status" / "2607.24653.json"
    manifest.parent.mkdir(parents=True)
    status_path.parent.mkdir(parents=True)
    stub.mkdir()
    entry = {
        "arxiv_id": "2607.24653",
        "version": "v1",
        "title": "Kimi K3",
        "output_key": "2607/2607.24653.md",
    }
    manifest.write_text(json.dumps(entry) + "\n")
    (stub / "2607.24653.md").write_text(
        "Kimi K3 paper text.\n\n![figure](missing.webp)\n\nAfter image. " * 80
    )
    status_path.write_text(json.dumps({"status": "failed", "attempt_count": 2}))

    subprocess.run(
        [
            sys.executable,
            str(WORKER_SCRIPT),
            "--manifest",
            str(manifest),
            "--content-root",
            str(content),
            "--stub-root",
            str(stub),
            "--soft-deadline-seconds",
            "30",
        ],
        check=True,
    )

    markdown = (content / entry["output_key"]).read_text()
    status = json.loads(status_path.read_text())
    assert "missing.webp" not in markdown
    assert "1 generated image reference was omitted" in markdown
    assert status["status"] == "succeeded"
    assert status["attempt_count"] == 3
    assert status["omitted_image_count"] == 1
    progress = json.loads(
        (content / "_jobs" / "progress" / "run-final" / "00000.json").read_text()
    )
    assert progress["omitted_images"] == 1


def test_chandra_worker_omits_missing_image_after_one_retry(tmp_path):
    content = tmp_path / "content"
    stub = tmp_path / "stub"
    manifest = content / "_jobs" / "manifests" / "run-retry" / "00000.jsonl"
    status_path = content / "_jobs" / "status" / "2607.24653.json"
    manifest.parent.mkdir(parents=True)
    status_path.parent.mkdir(parents=True)
    stub.mkdir()
    entry = {
        "arxiv_id": "2607.24653",
        "version": "v1",
        "title": "Kimi K3",
        "output_key": "2607/2607.24653.md",
    }
    manifest.write_text(json.dumps(entry) + "\n")
    (stub / "2607.24653.md").write_text(
        "Kimi K3 paper text.\n\n![figure](missing.webp)\n\nAfter image. " * 80
    )
    status_path.write_text(
        json.dumps(
            {
                "status": "failed",
                "attempt_count": 1,
                "error_class": "missing_extracted_image",
                "retryable": True,
            }
        )
    )

    subprocess.run(
        [
            sys.executable,
            str(WORKER_SCRIPT),
            "--manifest",
            str(manifest),
            "--content-root",
            str(content),
            "--stub-root",
            str(stub),
            "--soft-deadline-seconds",
            "30",
        ],
        check=True,
    )

    markdown = (content / entry["output_key"]).read_text()
    status = json.loads(status_path.read_text())
    assert "missing.webp" not in markdown
    assert "1 generated image reference was omitted" in markdown
    assert status["status"] == "succeeded"
    assert status["attempt_count"] == 2
    assert status["omitted_image_count"] == 1


def _write_stub_manifest(tmp_path: Path, count: int = 2):
    content = tmp_path / "content"
    stub = tmp_path / "stub"
    manifest = content / "_jobs" / "manifests" / "run-2" / "00000.jsonl"
    manifest.parent.mkdir(parents=True)
    stub.mkdir()
    entries = _candidates(count)
    manifest.write_text("".join(json.dumps(item) + "\n" for item in entries))
    for entry in entries:
        (stub / f"{entry['arxiv_id']}.md").write_text(
            f"{entry['title']} valid Markdown body. " * 80
        )
    return content, stub, manifest, entries


def test_worker_soft_deadline_before_first_paper_is_clean_partial(tmp_path):
    content, stub, manifest, entries = _write_stub_manifest(tmp_path, 1)
    subprocess.run(
        [
            sys.executable,
            str(WORKER_SCRIPT),
            "--manifest",
            str(manifest),
            "--content-root",
            str(content),
            "--stub-root",
            str(stub),
            "--soft-deadline-seconds",
            "0",
        ],
        check=True,
    )
    progress = json.loads(
        (content / "_jobs" / "progress" / "run-2" / "00000.json").read_text()
    )
    assert progress["status"] == "partial"
    assert progress["processed_papers"] == 0
    assert not (content / entries[0]["output_key"]).exists()


def test_worker_partial_checkpoint_resumes_from_result_jsonl(tmp_path):
    content, stub, manifest, entries = _write_stub_manifest(tmp_path, 2)
    command = [
        sys.executable,
        str(WORKER_SCRIPT),
        "--manifest",
        str(manifest),
        "--content-root",
        str(content),
        "--stub-root",
        str(stub),
    ]
    subprocess.run(
        [*command, "--soft-deadline-seconds", "1", "--stub-delay-seconds", "1.1"],
        check=True,
    )
    progress_path = content / "_jobs" / "progress" / "run-2" / "00000.json"
    progress = json.loads(progress_path.read_text())
    assert progress["status"] == "partial"
    assert progress["processed_papers"] == 1

    subprocess.run([*command, "--soft-deadline-seconds", "30"], check=True)
    progress = json.loads(progress_path.read_text())
    assert progress["status"] == "completed"
    assert progress["processed_papers"] == 2
    results = (
        (content / "_jobs" / "results" / "run-2" / "00000.jsonl")
        .read_text()
        .splitlines()
    )
    assert len(results) == 2
    assert all((content / entry["output_key"]).exists() for entry in entries)


def test_worker_failure_classification_and_forced_cleanup():
    missing = ValueError("missing_extracted_image:figure.webp")
    assert WORKER.classify_failure(missing, 1) == ("missing_extracted_image", True)
    assert WORKER.classify_failure(missing, 3) == ("missing_extracted_image", False)
    PdfReadError = type("PdfReadError", (Exception,), {})
    assert WORKER.classify_failure(PdfReadError("invalid PDF"), 1) == (
        "PdfReadError",
        False,
    )
    assert WORKER.classify_failure(ValueError("immutable_asset_conflict:key"), 1) == (
        "immutable_asset_conflict",
        False,
    )
    assert WORKER.classify_failure(
        subprocess.TimeoutExpired("chandra", WORKER.CHANDRA_TIMEOUT_SECONDS), 1
    ) == ("chandra_timeout", True)

    for message in (
        "markdown_version_verification_failed",
        "markdown_migration_locked",
    ):
        assert WORKER.classify_failure(ValueError(message), 1) == (
            "artifact_verification_io",
            True,
        )
        assert WORKER.classify_failure(ValueError(message), WORKER.MAX_ATTEMPTS) == (
            "artifact_verification_io",
            False,
        )

    class StubbornProcess:
        def __init__(self):
            self.killed = False
            self.waits = 0

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout):
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("vllm", timeout)
            return 0

        def kill(self):
            self.killed = True

    process = StubbornProcess()
    assert WORKER.stop_vllm(process) == "killed"
    assert process.killed is True


def test_worker_gracefully_terminates_vllm():
    class GracefulProcess:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            assert timeout == WORKER.VLLM_SHUTDOWN_TIMEOUT_SECONDS
            return 0

        def kill(self):
            raise AssertionError("graceful shutdown must not kill vLLM")

    process = GracefulProcess()
    assert WORKER.stop_vllm(process) == "terminated"
    assert process.terminated is True


def test_worker_startup_failure_writes_failed_checkpoint(tmp_path, monkeypatch):
    content, _, manifest, _ = _write_stub_manifest(tmp_path, 1)

    def fail_startup():
        raise RuntimeError("vLLM startup failed")

    monkeypatch.setattr(WORKER, "start_vllm", fail_startup)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(WORKER_SCRIPT),
            "--manifest",
            str(manifest),
            "--content-root",
            str(content),
            "--soft-deadline-seconds",
            "30",
        ],
    )

    with pytest.raises(RuntimeError, match="vLLM startup failed"):
        WORKER.main()

    progress = json.loads(
        (content / "_jobs" / "progress" / "run-2" / "00000.json").read_text()
    )
    assert progress["status"] == "failed"
    assert progress["processed_papers"] == 0
    assert progress["fatal_error"] == "vLLM startup failed"
    assert progress["cleanup_state"] == "not_started"
