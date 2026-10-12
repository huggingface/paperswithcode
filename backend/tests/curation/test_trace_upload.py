"""Trace bundles upload from a subprocess so hf_xet memory leaves the API worker."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from backend.services import curation_trace_service, curation_trace_upload_worker


def test_upload_worker_uploads_every_file_under_prefix(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_bytes(b"{}")
    (tmp_path / "events.jsonl.gz").write_bytes(b"gz")
    calls = []

    class FakeApi:
        def __init__(self, token):
            calls.append(("token", token))

        def create_bucket(self, bucket, *, private, exist_ok):
            calls.append(("bucket", bucket, private, exist_ok))

        def batch_bucket_files(self, bucket, *, add):
            calls.append(("add", bucket, add))

    monkeypatch.setenv("HF_TOKEN", "hf-secret")
    monkeypatch.setattr("huggingface_hub.HfApi", FakeApi)

    status = curation_trace_upload_worker.main(
        [
            "--bucket",
            "org/traces",
            "--prefix",
            "traces/p/1",
            "--directory",
            str(tmp_path),
        ]
    )

    assert status == 0
    assert calls[0] == ("token", "hf-secret")
    assert calls[1] == ("bucket", "org/traces", True, True)
    assert calls[2] == (
        "add",
        "org/traces",
        [
            (str(tmp_path / "events.jsonl.gz"), "traces/p/1/events.jsonl.gz"),
            (str(tmp_path / "manifest.json"), "traces/p/1/manifest.json"),
        ],
    )


def test_upload_worker_rejects_empty_bundle(tmp_path, capsys):
    status = curation_trace_upload_worker.main(
        [
            "--bucket",
            "org/traces",
            "--prefix",
            "traces/p/1",
            "--directory",
            str(tmp_path),
        ]
    )

    assert status == 2
    assert "empty" in capsys.readouterr().err


def _install_fake_worker(monkeypatch, tmp_path: Path, body: str) -> Path:
    worker = tmp_path / "fake_worker.py"
    worker.write_text(body)
    monkeypatch.setattr(curation_trace_service, "UPLOAD_WORKER", worker)
    return worker


def test_upload_trace_objects_runs_worker_with_bundle_and_token(tmp_path, monkeypatch):
    record = tmp_path / "record.json"
    _install_fake_worker(
        monkeypatch,
        tmp_path,
        f"""
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
directory = Path(args[args.index("--directory") + 1])
Path({str(record)!r}).write_text(json.dumps({{
    "bucket": args[args.index("--bucket") + 1],
    "prefix": args[args.index("--prefix") + 1],
    "files": {{p.name: p.read_text() for p in sorted(directory.iterdir())}},
    "token": os.environ.get("HF_TOKEN"),
    "progress_bars": os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS"),
}}))
""",
    )

    curation_trace_service.upload_trace_objects(
        "org/traces",
        "traces/hf-daily-v1/2026-09-18/42/job",
        {"prompt.txt": b"curate", "proposal.json": b"{}"},
        token="hf-secret",
    )

    recorded = json.loads(record.read_text())
    assert recorded == {
        "bucket": "org/traces",
        "prefix": "traces/hf-daily-v1/2026-09-18/42/job",
        "files": {"prompt.txt": "curate", "proposal.json": "{}"},
        "token": "hf-secret",
        "progress_bars": "1",
    }


def test_upload_trace_objects_surfaces_worker_failure(tmp_path, monkeypatch):
    _install_fake_worker(
        monkeypatch,
        tmp_path,
        "import sys; print('noise'); print('bucket is gone', file=sys.stderr); sys.exit(3)",
    )

    with pytest.raises(RuntimeError, match="status 3: bucket is gone"):
        curation_trace_service.upload_trace_objects(
            "org/traces", "traces/x", {"a": b"1"}, token="t"
        )


def test_upload_trace_objects_times_out(tmp_path, monkeypatch):
    _install_fake_worker(monkeypatch, tmp_path, "import time; time.sleep(5)")
    monkeypatch.setattr(curation_trace_service, "UPLOAD_TIMEOUT_SECONDS", 0.2)

    with pytest.raises(RuntimeError, match="timed out"):
        curation_trace_service.upload_trace_objects(
            "org/traces", "traces/x", {"a": b"1"}, token="t"
        )


def test_upload_worker_module_runs_under_release_interpreter():
    assert curation_trace_service.UPLOAD_WORKER.exists()
    assert (
        curation_trace_service.UPLOAD_WORKER.name == "curation_trace_upload_worker.py"
    )
    assert Path(sys.executable).exists()


def test_trace_accepts_large_compressible_events_without_losing_bytes():
    import base64
    import gzip

    raw = b'{"type":"tool_output","text":"' + b"x" * 14_200_000 + b'"}\n'
    encoded = base64.b64encode(gzip.compress(raw)).decode()
    assert curation_trace_service.CurationTraceService.decode_events(encoded) == raw


def test_trace_rejects_expansion_beyond_bound(monkeypatch):
    import base64
    import gzip

    monkeypatch.setattr(curation_trace_service, "MAX_EXPANDED_TRACE_BYTES", 1024)
    encoded = base64.b64encode(gzip.compress(b"x" * 1025)).decode()
    with pytest.raises(ValueError, match="trace is too large"):
        curation_trace_service.CurationTraceService.decode_events(encoded)


def test_trace_preserves_compressed_size_limit(monkeypatch):
    import base64
    import gzip

    monkeypatch.setattr(curation_trace_service, "MAX_TRACE_BYTES", 1)
    encoded = base64.b64encode(gzip.compress(b"ok")).decode()
    with pytest.raises(ValueError, match="compressed trace is too large"):
        curation_trace_service.CurationTraceService.decode_events(encoded)


def test_cli_recovers_only_trace_without_redispatch(monkeypatch):
    import uuid
    from types import SimpleNamespace
    from backend.scripts import enqueue_hf_daily_paper_curation as cli

    job_id = uuid.uuid4()
    row = SimpleNamespace(id=job_id, trace_status="finalize_failed")
    db = SimpleNamespace(get=lambda model, key: row if key == job_id else None)
    calls = []
    settings = object()

    def session():
        yield db

    monkeypatch.setattr(cli, "get_database_session", session)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(
        cli, "HFDailyCurationService", lambda *args: SimpleNamespace(settings=settings)
    )
    monkeypatch.setattr(
        cli,
        "CurationTraceService",
        lambda *args: SimpleNamespace(
            retry_finalize=lambda selected: calls.append(selected)
            or {"status": "stored"}
        ),
    )
    monkeypatch.setattr(sys, "argv", ["curation", "--retry-trace", str(job_id)])
    assert cli.main() == 0
    assert calls == [row]


def test_cli_rejects_trace_retry_for_nonfailed_trace(monkeypatch):
    import uuid
    from types import SimpleNamespace
    from backend.scripts import enqueue_hf_daily_paper_curation as cli

    def session():
        yield SimpleNamespace(
            get=lambda *args: SimpleNamespace(trace_status="complete")
        )

    monkeypatch.setattr(cli, "get_database_session", session)
    monkeypatch.setattr(cli, "get_settings", lambda: object())
    monkeypatch.setattr(cli, "HFDailyCurationService", lambda *args: object())
    monkeypatch.setattr(sys, "argv", ["curation", "--retry-trace", str(uuid.uuid4())])
    with pytest.raises(ValueError, match="not awaiting"):
        cli.main()
