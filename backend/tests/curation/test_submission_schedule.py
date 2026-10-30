from __future__ import annotations

import json
import base64
import hashlib
import hmac
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx

from backend.config import Settings
from backend.services.autonomous_submission_job_service import (
    REMOTE_SUBMISSION_WORKER,
    AutonomousSubmissionJobError,
    AutonomousSubmissionJobService,
)
from backend.scripts.alert_autonomous_submission_failure import (
    build_alert_payload,
    send_failure_alert,
)
from backend.services.runtime_validation import validate_codex_jobs_configuration
from backend.services.cron_registry import get_cron_job
from deploy import cron_launcher, install_host_layout


ROOT = Path(__file__).parents[3]


class FakeJobsApi:
    def __init__(self, *, active: int = 0, active_stage: str = "RUNNING"):
        self.active = active
        self.active_stage = active_stage
        self.calls = []

    def list_jobs(self, *, namespace: str):
        return [
            SimpleNamespace(
                status=SimpleNamespace(stage=self.active_stage),
                labels={"workflow": "autonomous-submission-review"},
            )
            for _ in range(self.active)
        ]

    def run_job(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(id="job-123")

    def inspect_job(self, *, job_id: str, namespace: str):
        return SimpleNamespace(status=SimpleNamespace(stage="COMPLETED"))


def settings(**updates) -> Settings:
    values = {
        "environment": "production",
        "autonomous_submission_enabled": True,
        "autonomous_submission_jobs_enabled": True,
        "autonomous_submission_hf_namespace": "pwc",
        "autonomous_submission_hf_token": "hf-launch-only",
        "autonomous_submission_openai_api_key": "sk-remote-only",
        "autonomous_submission_job_image": (
            "registry.example/pwc-submission-reviewer@sha256:" + "a" * 64
        ),
        "autonomous_submission_callback_secret": "s" * 32,
        "autonomous_alert_slack_webhook_url": "https://alerts.example/primary",
        "autonomous_alert_fallback_webhook_url": "https://alerts.example/fallback",
        "autonomous_submission_input_usd_per_million": 1,
        "autonomous_submission_cached_input_usd_per_million": 1,
        "autonomous_submission_output_usd_per_million": 1,
    }
    values.update(updates)
    return Settings(**values)


def manifest() -> dict:
    value = {
        "schema": "pwc.autonomous-submission-review.v1",
        "run_id": "00000000-0000-0000-0000-000000000001",
        "model_alias": "luna-medium",
        "expires_at": "2026-08-28T13:00:00Z",
        "allowed_decisions": ["approve", "reject", "defer"],
        "items": [
            {
                "claim_id": "00000000-0000-0000-0000-000000000002",
                "snapshot": {"id": 7, "edit_type": "tasks"},
                "snapshot_digest": "e" * 64,
                "required_decision": None,
                "callback_url": (
                    "https://paperswithcode.co/api/v1/"
                    "autonomous-submissions/00000000-0000-0000-0000-000000000002/decision"
                ),
                "callback_token": "scoped-callback-token",
            }
        ],
    }
    value["signature"] = hmac.new(
        b"s" * 32,
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()
    return value


def test_launcher_uses_one_pinned_cpu_job_and_only_scoped_remote_secrets():
    api = FakeJobsApi()
    service = AutonomousSubmissionJobService(settings(), hf_api=api)

    result = service.launch(manifest())

    assert result.job_id == "job-123"
    call = api.calls[0]
    assert call["image"] == (
        "registry.example/pwc-submission-reviewer@sha256:" + "a" * 64
    )
    assert call["command"] == ["python", "-c", REMOTE_SUBMISSION_WORKER]
    assert call["flavor"] == "cpu-basic"
    assert call["timeout"] == "1800s"
    assert call["namespace"] == "pwc"
    assert call["secrets"] == {
        "OPENAI_API_KEY": "sk-remote-only",
        "PWC_SUBMISSION_MANIFEST": json.dumps(
            manifest(), sort_keys=True, separators=(",", ":")
        ),
    }
    serialized = json.dumps(call["env"])
    assert "DATABASE" not in serialized
    assert "hf-launch-only" not in json.dumps(call)
    assert call["env"]["PWC_SUBMISSION_MODEL"] == "gpt-6-luna"
    assert call["env"]["PWC_SUBMISSION_REASONING_EFFORT"] == "medium"


def test_launcher_fails_closed_for_capacity_or_unpinned_image():
    with pytest.raises(AutonomousSubmissionJobError, match="active"):
        AutonomousSubmissionJobService(settings(), hf_api=FakeJobsApi(active=1)).launch(
            manifest()
        )

    with pytest.raises(AutonomousSubmissionJobError, match="active"):
        AutonomousSubmissionJobService(
            settings(), hf_api=FakeJobsApi(active=1, active_stage="SCHEDULING")
        ).launch(manifest())

    with pytest.raises(AutonomousSubmissionJobError, match="immutable"):
        AutonomousSubmissionJobService(
            settings(autonomous_submission_job_image="python:latest"),
            hf_api=FakeJobsApi(),
        ).launch(manifest())


def test_second_serialized_launch_sees_first_job_scheduling():
    class SchedulingAfterLaunchApi(FakeJobsApi):
        def run_job(self, **kwargs):
            result = super().run_job(**kwargs)
            self.active = 1
            self.active_stage = "SCHEDULING"
            return result

    api = SchedulingAfterLaunchApi()
    service = AutonomousSubmissionJobService(settings(), hf_api=api)

    service.launch(manifest())
    with pytest.raises(AutonomousSubmissionJobError, match="active"):
        service.launch(manifest())

    assert len(api.calls) == 1


def test_launcher_polls_only_closed_remote_stages():
    service = AutonomousSubmissionJobService(settings(), hf_api=FakeJobsApi())

    status = service.poll("job-123")

    assert status.terminal is True
    assert status.successful is True
    assert status.stage == "COMPLETED"


def test_runtime_requires_production_and_separate_pinned_job_credentials():
    value = settings()
    validate_codex_jobs_configuration(value)

    with pytest.raises(RuntimeError, match="production-only"):
        validate_codex_jobs_configuration(
            value.model_copy(
                update={
                    "environment": "staging",
                    "autonomous_submission_callback_base_url": (
                        "https://staging.paperswithcode.co/api/v1"
                    ),
                }
            )
        )
    with pytest.raises(RuntimeError, match="separate credentials"):
        validate_codex_jobs_configuration(
            value.model_copy(update={"codex_jobs_token": "hf-launch-only"})
        )
    with pytest.raises(RuntimeError, match="separate credentials"):
        validate_codex_jobs_configuration(
            value.model_copy(update={"hf_token": "hf-launch-only"})
        )
    with pytest.raises(RuntimeError, match="separate credentials"):
        validate_codex_jobs_configuration(
            value.model_copy(update={"openai_api_key": "sk-remote-only"})
        )
    with pytest.raises(RuntimeError, match="immutable image"):
        validate_codex_jobs_configuration(
            value.model_copy(
                update={
                    "autonomous_submission_job_image": "python:latest",
                }
            )
        )
    with pytest.raises(RuntimeError, match="separate alert routes"):
        validate_codex_jobs_configuration(
            value.model_copy(
                update={
                    "autonomous_alert_fallback_webhook_url": (
                        value.autonomous_alert_slack_webhook_url
                    )
                }
            )
        )


def test_submission_failure_alert_is_content_free_and_uses_fallback(monkeypatch):
    requests = []

    class Response:
        def __init__(self, *, failing: bool):
            self.failing = failing

        def raise_for_status(self):
            if self.failing:
                raise httpx.ConnectError("delivery failed")

    class Client:
        def __init__(self, *, timeout: int):
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, *, json):
            requests.append((url, json))
            return Response(failing=len(requests) == 1)

    monkeypatch.setattr(
        "backend.scripts.alert_autonomous_submission_failure.httpx.Client", Client
    )

    payload = build_alert_payload(settings())
    delivered = send_failure_alert(settings())

    assert delivered == "fallback"
    assert [url for url, _payload in requests] == [
        "https://alerts.example/primary",
        "https://alerts.example/fallback",
    ]
    assert payload == requests[0][1]
    serialized = json.dumps(payload).lower()
    assert "submission review failed" in serialized
    assert "prompt" not in serialized
    assert "callback" not in serialized


def test_remote_worker_is_content_bounded_signed_and_database_free():
    lowered = REMOTE_SUBMISSION_WORKER.lower()
    compile(REMOTE_SUBMISSION_WORKER, "<remote-submission-worker>", "exec")
    assert "codex" in lowered
    assert "hmac" in lowered
    assert "callback_token" in lowered
    assert "database_url" not in lowered
    assert "postgres" not in lowered
    assert "print(manifest" not in lowered


def test_remote_worker_posts_one_canonical_signed_callback(tmp_path):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            received.append((dict(self.headers), self.rfile.read(length)))
            self.send_response(204)
            self.end_headers()

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fake_codex = tmp_path / "codex"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "path=sys.argv[sys.argv.index('--output-last-message')+1]\n"
        "json.dump({'status':'completed','proposed_actions':["
        "{'capability':'review_submission','resource':{'kind':'pending_edit',"
        "'identifier':'7','exists':True},'reason_code':'defer',"
        "'rationale':'Needs human review.','evidence':['snapshot'],"
        "'confidence':1,'resolved_payload':None}]},open(path,'w'))\n"
        "print(json.dumps({'usage':{'input_tokens':10,'cached_input_tokens':0,"
        "'output_tokens':5}}))\n"
    )
    fake_codex.chmod(0o755)
    value = manifest()
    value["items"][0]["callback_url"] = (
        f"http://127.0.0.1:{server.server_port}/decision"
    )

    try:
        completed = subprocess.run(
            [sys.executable, "-c", REMOTE_SUBMISSION_WORKER],
            env={
                **os.environ,
                "OPENAI_API_KEY": "remote-test-key",
                "PWC_CODEX_EXECUTABLE": str(fake_codex),
                "PWC_SUBMISSION_MANIFEST": json.dumps(value),
                "PWC_SUBMISSION_MODEL": "gpt-6-luna",
                "PWC_SUBMISSION_REASONING_EFFORT": "medium",
                "PWC_SUBMISSION_BUDGET_USD": "1",
                "PWC_SUBMISSION_INPUT_USD_PER_MILLION": "1",
                "PWC_SUBMISSION_CACHED_INPUT_USD_PER_MILLION": "1",
                "PWC_SUBMISSION_OUTPUT_USD_PER_MILLION": "1",
            },
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert completed.returncode == 0, completed.stderr
    headers, body = received[0]
    assert headers["Authorization"] == "Bearer scoped-callback-token"
    usage = json.loads(base64.urlsafe_b64decode(headers["X-Pwc-Remote-Usage"]))
    signed = json.dumps(
        {"decision": json.loads(body), "usage": usage},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    assert (
        headers["X-Pwc-Remote-Decision"]
        == hmac.new(b"scoped-callback-token", signed, hashlib.sha256).hexdigest()
    )
    assert json.loads(body)["confidence"] == 1.0
    assert usage == {"input_tokens": 10, "output_tokens": 5, "cost_usd": "0.000015"}


def test_hourly_persistent_unit_is_allowlisted_and_installed():
    job = cron_launcher.COMMANDS["review_submissions"]
    assert job.command == (
        ".github/workflows/scripts/review_submissions.py",
        "--launch-remote",
    )
    assert job.timeout == "45m"
    assert job.mutates_shared_data is True

    service = (ROOT / "deploy/autonomous/submission-review.service").read_text()
    alert_service = (
        ROOT / "deploy/autonomous/submission-review-alert.service"
    ).read_text()
    timer = (ROOT / "deploy/autonomous/submission-review.timer").read_text()
    assert "ExecStart=/usr/local/sbin/pwc-cron review_submissions" in service
    assert "OnFailure=submission-review-alert.service" in service
    assert (
        "ExecStart=/usr/local/sbin/pwc-cron alert_submission_review_failure"
        in alert_service
    )
    assert "alert_submission_review_failure" in cron_launcher.COMMANDS
    registry_job = get_cron_job("review_submissions")
    assert registry_job is not None
    assert registry_job.scheduler == "systemd"
    assert registry_job.systemd_timer == "submission-review.timer"
    assert registry_job.critical is True
    assert registry_job.enablement_settings == (
        "autonomous_submission_enabled",
        "autonomous_submission_jobs_enabled",
    )
    assert "--uid=pwc-cron" in (ROOT / "deploy/install_deploy_tools.py").read_text()
    assert "OnCalendar=hourly" in timer
    assert "RandomizedDelaySec=" in timer
    assert "Persistent=true" in timer
    assert "autonomous/submission-review.service" in install_host_layout.SYSTEMD_UNITS
    assert "autonomous/submission-review.timer" in install_host_layout.SYSTEMD_UNITS
    assert (
        "autonomous/submission-review-alert.service"
        in install_host_layout.SYSTEMD_UNITS
    )
