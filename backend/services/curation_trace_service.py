"""Private, content-addressed trace bundles for remote paper curation."""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import PaperCurationJob, PaperCurationSchedulerState

logger = logging.getLogger(__name__)

SECRET_PATTERNS = (
    re.compile(
        r"(?i)(authorization|api[-_]?key|token|secret|password)(\s*[:=]\s*)([^\s\"']+)"
    ),
    re.compile(r"\b(?:hf|sk)-[A-Za-z0-9_-]{12,}\b"),
)
MAX_TRACE_BYTES = 8_000_000
MAX_EXPANDED_TRACE_BYTES = 32_000_000
UPLOAD_TIMEOUT_SECONDS = 180
UPLOAD_WORKER = Path(__file__).with_name("curation_trace_upload_worker.py")


def redact_trace(raw: bytes) -> bytes:
    text = raw.decode("utf-8", "replace")
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 3:
            text = pattern.sub(r"\1\2<redacted>", text)
        else:
            text = pattern.sub("<redacted>", text)
    return text.encode()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _ordered_trace_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_ordered_trace_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    keys = sorted(value)
    if "reasoning" in value and "gap_type" in value:
        keys.remove("reasoning")
        keys.insert(0, "reasoning")
    return {key: _ordered_trace_value(value[key]) for key in keys}


def upload_trace_objects(
    bucket: str, prefix: str, objects: dict[str, bytes], *, token: str
) -> None:
    """Upload a trace bundle from a short-lived subprocess.

    ``hf_xet`` keeps its Rust runtime and allocator arenas for the life of the
    process, so uploading inside the API worker grows it by tens of megabytes
    per trace until the memory cap throttles it. A child process gives that
    memory back when it exits.
    """
    with tempfile.TemporaryDirectory(prefix="pwc-curation-trace-") as directory:
        for name, data in objects.items():
            (Path(directory) / name).write_bytes(data)
        environment = {
            **os.environ,
            "HF_TOKEN": token,
            "HF_HUB_DISABLE_PROGRESS_BARS": "1",
        }
        command = [
            sys.executable,
            str(UPLOAD_WORKER),
            "--bucket",
            bucket,
            "--prefix",
            prefix,
            "--directory",
            directory,
        ]
        try:
            completed = subprocess.run(
                command,
                env=environment,
                capture_output=True,
                text=True,
                timeout=UPLOAD_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                f"trace upload timed out after {UPLOAD_TIMEOUT_SECONDS}s"
            ) from error
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()[-1:] or ["no output"]
        raise RuntimeError(
            f"trace upload exited with status {completed.returncode}: {detail[0]}"
        )


def trace_json(value: Any, *, indent: int | None = None) -> bytes:
    return json.dumps(
        _ordered_trace_value(value),
        ensure_ascii=False,
        indent=indent,
        separators=None if indent is not None else (",", ":"),
    ).encode()


class CurationTraceService:
    def __init__(self, db: Session, settings: Settings, hf_api: HfApi | None = None):
        self.db = db
        self.settings = settings
        # Only manifest reads use this client; uploads run in a subprocess.
        self.api = hf_api or HfApi(token=settings.codex_jobs_token)

    def _recovery_path(self, row: PaperCurationJob) -> Path:
        root = Path(self.settings.codex_add_evals_spool_dir) / "curation-traces"
        root.mkdir(parents=True, exist_ok=True)
        return root / f"{row.id}.json"

    def _store_recovery_payload(self, row: PaperCurationJob, payload: dict) -> None:
        target = self._recovery_path(row)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, separators=(",", ":")), encoding="utf-8"
        )
        os.replace(temporary, target)

    def _prefix(self, row: PaperCurationJob) -> str:
        cohort = row.cohort_date.isoformat() if row.cohort_date else "admin"
        return f"traces/{row.policy_version}/{cohort}/{row.paper_id}/{row.id}"

    def _upload(
        self, row: PaperCurationJob, objects: dict[str, bytes]
    ) -> dict[str, Any]:
        if not self.settings.codex_curation_trace_upload_enabled:
            return {
                "status": "disabled",
                "objects": {name: sha256(data) for name, data in objects.items()},
            }
        bucket = self.settings.codex_curation_trace_hf_bucket_id
        if not bucket:
            raise RuntimeError("PWC_CURATION_TRACE_HF_BUCKET_ID is not configured")
        prefix = self._prefix(row)
        upload_trace_objects(
            bucket, prefix, objects, token=self.settings.codex_jobs_token
        )
        return {
            "status": "stored",
            "uri": f"hf://buckets/{bucket}/{prefix}/manifest.json",
            "objects": {name: sha256(data) for name, data in objects.items()},
        }

    @staticmethod
    def decode_events(encoded: str) -> bytes:
        compressed = base64.b64decode(encoded, validate=True)
        if len(compressed) > MAX_TRACE_BYTES:
            raise ValueError("compressed trace is too large")
        # Tool output can expand well beyond the wire-size budget. Bound the
        # read itself so oversized gzip payloads cannot exhaust an API worker.
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            raw = stream.read(MAX_EXPANDED_TRACE_BYTES + 1)
        if len(raw) > MAX_EXPANDED_TRACE_BYTES:
            raise ValueError("trace is too large")
        return redact_trace(raw)

    def preapply(
        self,
        row: PaperCurationJob,
        *,
        proposal: dict,
        events_gzip_b64: str,
        prompt: str,
        url_candidates: dict | None = None,
    ) -> dict:
        events = self.decode_events(events_gzip_b64)
        proposal_bytes = trace_json(proposal)
        prompt_bytes = redact_trace(prompt.encode())
        schema_bytes = (
            Path(__file__).parents[2] / "jobs/schemas/curation_proposal.schema.json"
        ).read_bytes()
        objects = {
            "events.preapply.jsonl": events,
            "prompt.txt": prompt_bytes,
            "proposal.json": proposal_bytes,
            "output-schema.json": schema_bytes,
        }
        result = self._upload(row, objects)
        row.proposal = proposal
        row.prompt_sha256 = sha256(prompt_bytes)
        row.url_candidates = url_candidates or {}
        row.trace_status = (
            "preapply_stored" if result["status"] == "stored" else result["status"]
        )
        row.trace_uri = result.get("uri")
        row.trace_sha256 = sha256(proposal_bytes + events)
        row.trace_attempt_count += 1
        state = self.db.get(PaperCurationSchedulerState, 1)
        if state:
            state.consecutive_trace_failures = 0
        self.db.commit()
        return result

    def finalize(self, row: PaperCurationJob, payload: dict) -> dict:
        self._store_recovery_payload(row, payload)
        events = self.decode_events(payload["events_gzip_b64"])
        result_bytes = json.dumps(payload.get("result") or {}, sort_keys=True).encode()
        gaps_bytes = trace_json(payload.get("benchmark_gaps") or {})
        report_bytes = redact_trace((payload.get("report") or "").encode())
        manifest = {
            "schema_version": "curation-trace.v1",
            "job_id": str(row.id),
            "parent_workflow_id": str(row.parent_workflow_id)
            if row.parent_workflow_id
            else None,
            "paper_id": row.paper_id,
            "repository_sha": row.repository_sha,
            "skill_sha256": row.skill_sha256,
            "prompt_sha256": row.prompt_sha256,
            "model": row.model,
            "reasoning_effort": row.reasoning_effort,
            "codex_cli_version": row.codex_cli_version,
            "policy_version": row.policy_version,
            "observed_at": datetime.now(UTC).isoformat(),
        }
        object_values = {
            "events.jsonl.gz": gzip.compress(events, compresslevel=6),
            "proposal.json": trace_json(row.proposal or {}),
            "result.json": result_bytes,
            "benchmark_gaps.json": gaps_bytes,
            "report.txt": report_bytes,
            "source-urls.json": json.dumps(
                row.url_candidates or [], sort_keys=True
            ).encode(),
        }
        manifest["objects"] = {
            name: sha256(data) for name, data in object_values.items()
        }
        manifest["objects"]["prompt.txt"] = row.prompt_sha256
        schema_path = (
            Path(__file__).parents[2] / "jobs/schemas/curation_proposal.schema.json"
        )
        manifest["objects"]["output-schema.json"] = sha256(schema_path.read_bytes())
        manifest_bytes = json.dumps(manifest, sort_keys=True, indent=2).encode()
        object_values["manifest.json"] = manifest_bytes
        result = self._upload(row, object_values)
        row.trace_status = (
            "complete" if result["status"] == "stored" else result["status"]
        )
        row.trace_uri = result.get("uri") or row.trace_uri
        row.trace_sha256 = sha256(manifest_bytes)
        # The worker's own account of the outcome is kept in result.json. A
        # result the server recorded while applying (including the resolved
        # paper the thumbnail queue targets) must not be replaceable by the
        # job's bearer, so the worker only fills in an empty result.
        if row.mutation_result is None:
            row.mutation_result = payload.get("result")
        usage = payload.get("usage") or {}
        row.input_tokens = usage.get("input_tokens")
        row.output_tokens = usage.get("output_tokens")
        row.duration_ms = payload.get("duration_ms")
        state = self.db.get(PaperCurationSchedulerState, 1)
        if state:
            state.consecutive_trace_failures = 0
        self.db.commit()
        self._recovery_path(row).unlink(missing_ok=True)
        return result

    def retry_finalize(self, row: PaperCurationJob) -> dict:
        path = self._recovery_path(row)
        if not path.exists():
            raise ValueError("No durable trace-finalization payload is available")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return self.finalize(row, payload)

    def read_manifest(self, row: PaperCurationJob) -> dict:
        if row.trace_status != "complete":
            raise ValueError("Trace manifest is not complete")
        bucket = self.settings.codex_curation_trace_hf_bucket_id
        if not bucket:
            raise RuntimeError("Trace bucket is not configured")
        remote_path = f"{self._prefix(row)}/manifest.json"
        with tempfile.TemporaryDirectory(prefix="pwc-curation-trace-") as directory:
            target = Path(directory) / "manifest.json"
            self.api.download_bucket_files(bucket, [(remote_path, target)])
            return json.loads(target.read_text(encoding="utf-8"))
