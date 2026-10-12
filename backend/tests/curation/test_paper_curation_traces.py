"""Trace redaction, proposal schema, and trace bundle manifests."""

from __future__ import annotations

import base64
import gzip
import json
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator

from backend.config import get_settings
from backend.models.database import (
    PaperCurationSchedulerState,
)
from backend.services.curation_trace_service import (
    CurationTraceService,
    redact_trace,
    trace_json,
)


def test_trace_redaction_removes_planted_credentials():
    redacted = redact_trace(
        b"Authorization: Bearer-secret\nOPENAI_API_KEY=sk-exampleexampleexample\nhf-exampleexampleexample"
    ).decode()

    assert "Bearer-secret" not in redacted
    assert "sk-example" not in redacted
    assert "hf-example" not in redacted
    assert redacted.count("<redacted>") >= 3


def test_checked_in_proposal_schema_requires_benchmark_gaps():
    schema = json.loads(Path("jobs/schemas/curation_proposal.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    assert "benchmark_gaps" in schema["required"]
    assert "evaluation_removals" in schema["required"]
    assert "validation_evidence" in schema["required"]
    assert (
        schema["properties"]["benchmark_gaps"]["items"]["properties"]["reasoning"][
            "maxLength"
        ]
        == 2000
    )


def test_trace_json_keeps_gap_reasoning_first_with_deterministic_nested_keys():
    encoded = trace_json(
        {
            "benchmark_gaps": [
                {
                    "gap_type": "dataset_missing",
                    "reasoning": "Evidence-based summary.",
                    "assessment": {"why": "reusable", "confidence": "high"},
                }
            ]
        }
    ).decode()

    gap = encoded[encoded.index("[{") + 2 : encoded.index("}]")]
    assert gap.startswith('"reasoning":"Evidence-based summary."')
    assert '"assessment":{"confidence":"high","why":"reusable"}' in encoded


def test_trace_bundle_manifest_hashes_every_uploaded_object(tmp_path, monkeypatch):
    scheduler = SimpleNamespace(consecutive_trace_failures=2)

    class Database:
        def commit(self):
            pass

        def get(self, model, *_args):
            return scheduler if model is PaperCurationSchedulerState else None

    class Hub:
        def __init__(self):
            self.objects = {}

        def upload(self, _bucket, prefix, objects, *, token):
            assert token == settings.codex_jobs_token
            self.objects.update(
                {f"{prefix}/{name}": data for name, data in objects.items()}
            )

    settings = get_settings().model_copy(
        update={
            "codex_curation_trace_upload_enabled": True,
            "codex_curation_trace_hf_bucket_id": "example/curate-papers-traces",
            "codex_add_evals_spool_dir": str(tmp_path),
        }
    )
    row = SimpleNamespace(
        id=uuid.uuid4(),
        paper_id=42,
        cohort_date=date(2026, 8, 18),
        policy_version="hf-daily-v1",
        parent_workflow_id=uuid.uuid4(),
        repository_sha="a" * 40,
        skill_sha256="b" * 64,
        prompt_sha256=None,
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        codex_cli_version="0.75.0",
        proposal=None,
        url_candidates=None,
        trace_attempt_count=0,
        trace_uri=None,
    )
    hub = Hub()
    monkeypatch.setattr(
        "backend.services.curation_trace_service.upload_trace_objects", hub.upload
    )
    service = CurationTraceService(Database(), settings, hf_api=object())
    events = base64.b64encode(gzip.compress(b'{"type":"done"}\n')).decode()
    service.preapply(
        row,
        proposal={"evaluations": [], "benchmark_gaps": []},
        events_gzip_b64=events,
        prompt="curate paper 42",
        url_candidates={"complete": True, "candidates": [], "sources": []},
    )
    service.finalize(
        row,
        {
            "events_gzip_b64": events,
            "result": {"status": "no_changes"},
            "benchmark_gaps": [],
            "report": "No eligible changes.",
            "usage": {"input_tokens": 10, "output_tokens": 2},
            "duration_ms": 50,
        },
    )

    manifest_path = next(path for path in hub.objects if path.endswith("manifest.json"))
    manifest = json.loads(hub.objects[manifest_path])
    assert row.trace_status == "complete"
    assert scheduler.consecutive_trace_failures == 0
    assert {"events.jsonl.gz", "prompt.txt", "proposal.json", "result.json"} <= set(
        manifest["objects"]
    )
    assert not (tmp_path / "curation-traces" / f"{row.id}.json").exists()
