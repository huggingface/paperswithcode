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
    agent_trace_url,
    redact_trace,
    trace_folder_url,
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


def test_trace_redaction_keeps_every_jsonl_line_parseable():
    hf_token = "hf_" + "A1b2C3d4E5" * 4
    lines = [
        {"cmd": 'token = os.environ["PWC_CURATION_JOB_TOKEN"]'},
        {"token": hf_token, "max_tokens": 32768},
        {"output": json.dumps({"api_key": "plain-secret-value"})},
        {"path": "backend/services/hf_artifact_service.py"},
        {"id_token": None, "password": 1234, "secret": True, "api_key": {"v": 1}},
        {"output": json.dumps({"refresh_token": None, "token": "nested-secret"})},
        {"cmd": 'export HF_TOKEN="quoted-assignment-secret" PASSWORD=bare-secret'},
        {"msg": "token=", "x": 1},
        {"a": "token=", "b": "c"},
    ]
    raw = "\n".join(json.dumps(line) for line in lines).encode()

    redacted = redact_trace(raw).decode()

    parsed = [json.loads(line) for line in redacted.splitlines()]
    assert hf_token not in redacted
    assert "plain-secret-value" not in redacted
    assert parsed[0]["cmd"].endswith('"PWC_CURATION_JOB_TOKEN"]')
    assert parsed[1] == {"token": "<redacted>", "max_tokens": 32768}
    assert parsed[3] == lines[3]
    assert parsed[4] == lines[4]
    assert "nested-secret" not in redacted
    assert json.loads(parsed[5]["output"])["refresh_token"] is None
    assert parsed[6]["cmd"] == 'export HF_TOKEN="<redacted>" PASSWORD=<redacted>'
    assert parsed[7:] == lines[7:]


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

        def refresh(self, _row, *, with_for_update):
            assert with_for_update

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
        mutation_result=None,
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
    assert row.mutation_result == {"status": "no_changes"}


def test_finalize_cannot_replace_the_server_recorded_mutation_result(
    tmp_path, monkeypatch
):
    applied = {"status": "resolved", "paper_id": 7}

    class Database:
        def commit(self):
            pass

        def refresh(self, row, *, with_for_update):
            assert with_for_update
            row.mutation_result = dict(applied)

        def get(self, *_args):
            return None

    uploaded = {}
    monkeypatch.setattr(
        "backend.services.curation_trace_service.upload_trace_objects",
        lambda _bucket, prefix, objects, *, token: uploaded.update(objects),
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
        paper_id=None,
        cohort_date=date(2026, 10, 20),
        parent_workflow_id=None,
        repository_sha="a" * 40,
        skill_sha256="b" * 64,
        prompt_sha256=None,
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        codex_cli_version="0.75.0",
        policy_version="trending-model-v1",
        proposal=None,
        url_candidates=None,
        trace_uri=None,
        mutation_result=None,
    )
    events = base64.b64encode(gzip.compress(b'{"type":"done"}\n')).decode()

    CurationTraceService(Database(), settings, hf_api=object()).finalize(
        row,
        {
            "events_gzip_b64": events,
            "result": {"status": "resolved", "paper_id": 999},
            "benchmark_gaps": [],
            "report": "",
        },
    )

    assert row.mutation_result == applied
    assert json.loads(uploaded["result.json"]) == {
        "status": "resolved",
        "paper_id": 999,
    }


def test_finalize_stores_the_agent_session_for_the_hub_trace_viewer(
    tmp_path, monkeypatch
):
    class Database:
        def commit(self):
            pass

        def refresh(self, _row, *, with_for_update):
            assert with_for_update

        def get(self, *_args):
            return None

    uploaded = {}
    monkeypatch.setattr(
        "backend.services.curation_trace_service.upload_trace_objects",
        lambda _bucket, prefix, objects, *, token: uploaded.update(objects),
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
        cohort_date=None,
        parent_workflow_id=None,
        repository_sha="a" * 40,
        skill_sha256="b" * 64,
        prompt_sha256=None,
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        codex_cli_version="0.75.0",
        policy_version="admin-v1",
        proposal=None,
        url_candidates=None,
        trace_uri=None,
        trace_session_sha256=None,
        mutation_result=None,
    )
    session = b'{"type":"session_meta","payload":{"command":"api_key=hunter2secret"}}\n'
    encode = lambda raw: base64.b64encode(gzip.compress(raw)).decode()  # noqa: E731

    CurationTraceService(Database(), settings, hf_api=object()).finalize(
        row,
        {
            "events_gzip_b64": encode(b'{"type":"done"}\n'),
            "session_gzip_b64": encode(session),
            "report": "",
        },
    )

    stored = uploaded["session.jsonl"]
    assert b"hunter2secret" not in stored
    assert json.loads(uploaded["manifest.json"])["objects"]["session.jsonl"] == (
        row.trace_session_sha256
    )
    assert agent_trace_url(row.trace_uri, row.trace_session_sha256) == (
        "https://huggingface.co/buckets/example/curate-papers-traces/tree/"
        f"traces/admin-v1/admin/42/{row.id}/session.jsonl"
    )


def test_trace_links_point_at_the_bucket_folder_only_for_bucket_traces():
    uri = "hf://buckets/nielsr/curate-papers-traces/traces/admin-v1/admin/7/job/manifest.json"
    folder = "https://huggingface.co/buckets/nielsr/curate-papers-traces/tree/traces/admin-v1/admin/7/job"

    assert trace_folder_url(uri) == folder
    assert agent_trace_url(uri, None) is None
    assert trace_folder_url(None) is None
    assert trace_folder_url("s3://elsewhere/manifest.json") is None
