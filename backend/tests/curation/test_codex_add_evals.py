from __future__ import annotations

import hashlib
import importlib
import io
import json
import sys
import urllib.error
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from httpx import Request, Response
from huggingface_hub.errors import HfHubHTTPError

from backend.codex_add_evals_app import create_codex_add_evals_app
from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.main import create_app
from backend.services.codex_add_evals_service import (
    CURATOR_BOOTSTRAP_PATHS,
    CURATOR_COMMAND,
    CodexPaperJob,
    CodexPaperJobCounts,
    CodexPaperJobService,
    CodexPaperJobsResponse,
    _git_revision,
    _launch_error,
    _release_git_revision,
)
from backend.utils.auth import require_hf_admin
from deploy.configure_host_env import production_codex_image_values
from jobs import curation_api
from jobs.curation_api import USER_AGENT as HELPER_USER_AGENT


def _job(kind: str = "add-evals") -> CodexPaperJob:
    return CodexPaperJob(
        id=uuid.UUID("00000000-0000-0000-0000-000000000042"),
        paper_id=42,
        paper_route="2601.00001",
        paper_title="A useful model",
        requested_by="niels",
        kind=kind,
        status="queued",
        created_at=datetime.now(UTC),
        attempt_count=0,
    )


def test_serializer_exposes_hf_job_url():
    row = SimpleNamespace(
        id=_job().id,
        paper_id=42,
        paper_route="2601.00001",
        paper_title="A useful model",
        requested_by="niels",
        kind="add-evals",
        status="running",
        hf_job_id="hf-job",
        created_at=datetime.now(UTC),
        started_at=None,
        finished_at=None,
        applied_at=None,
        report=None,
        error=None,
        attempt_count=1,
    )
    settings = get_settings().model_copy(update={"codex_jobs_namespace": "huggingface"})
    serialized = CodexPaperJobService.serialize(row, settings)
    assert serialized.hf_job_url == "https://huggingface.co/jobs/huggingface/hf-job"
    assert CodexPaperJobService._serialize(row, settings) == serialized


def test_git_revision_can_be_pinned_for_remote_jobs(monkeypatch):
    monkeypatch.setenv("PWC_CODEX_JOBS_GIT_SHA", "published-curation-revision")
    assert _git_revision() == "published-curation-revision"


def test_release_manifest_pins_remote_worker_revision(tmp_path):
    revision = "a" * 40
    (tmp_path / "release.json").write_text(json.dumps({"git_sha": revision}))
    assert _release_git_revision(tmp_path) == revision


def test_remote_job_uses_immutable_curator_image():
    settings = get_settings()
    # Each deployment pins its own curator image; production's pin lives in
    # the host-environment tooling, not in the application defaults.
    assert settings.codex_jobs_image == ""
    assert "@sha256:" in production_codex_image_values()["PWC_CODEX_JOBS_IMAGE"]
    assert settings.codex_jobs_image_revision == ""
    assert settings.codex_jobs_namespace == ""
    assert CURATOR_COMMAND == "exec python3 /runner/run_paper_curation.py"
    assert "npm install" not in CURATOR_COMMAND


def test_curator_image_and_dockerfile_pin_current_runner():
    runner_digest = hashlib.sha256(
        Path("jobs/run_paper_curation.py").read_bytes()
    ).hexdigest()
    image = production_codex_image_values()["PWC_CODEX_JOBS_IMAGE"]

    assert f":runner-{runner_digest[:12]}@sha256:" in image
    assert f'"{runner_digest}"' in Path("jobs/Dockerfile.codex-curator").read_text(
        encoding="utf-8"
    )


def test_curator_bootstrap_allowlist_matches_service_bundle(monkeypatch):
    monkeypatch.setenv("PWC_CURATION_API_URL", "https://paperswithcode.co/api/v1")
    monkeypatch.setenv("PWC_CURATION_JOB_ID", str(uuid.uuid4()))
    monkeypatch.setenv("PWC_CURATION_JOB_TOKEN", "test-token")
    monkeypatch.setenv("PWC_CURATION_KIND", "add-evals")
    monkeypatch.setenv("PWC_GIT_SHA", "a" * 40)
    run_paper_curation = importlib.import_module("jobs.run_paper_curation")

    assert run_paper_curation.BOOTSTRAP_PATHS == set(CURATOR_BOOTSTRAP_PATHS)


@pytest.fixture
def runner_module(monkeypatch):
    monkeypatch.setenv("PWC_CURATION_API_URL", "https://paperswithcode.co/api/v1")
    monkeypatch.setenv("PWC_CURATION_JOB_ID", str(uuid.uuid4()))
    monkeypatch.setenv("PWC_CURATION_JOB_TOKEN", "test-token")
    monkeypatch.setenv("PWC_CURATION_KIND", "add-evals")
    monkeypatch.setenv("PWC_GIT_SHA", "a" * 40)
    module = importlib.import_module("jobs.run_paper_curation")
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    return module


def test_runner_retries_a_read_callback_that_lost_its_connection(
    monkeypatch, runner_module
):
    calls = []

    def send(path, payload, method, timeout):
        calls.append((path, method, timeout))
        if len(calls) < 3:
            raise urllib.error.URLError(TimeoutError("timed out"))
        return {"job": {}}

    monkeypatch.setattr(runner_module, "_send", send)

    assert runner_module.api_request("context") == {"job": {}}
    assert calls == [("context", "GET", 60)] * 3


def test_runner_gives_up_after_four_lost_read_callbacks(monkeypatch, runner_module):
    calls = []

    def send(*_args):
        calls.append(1)
        raise ConnectionResetError

    monkeypatch.setattr(runner_module, "_send", send)

    with pytest.raises(ConnectionResetError):
        runner_module.api_request("bootstrap")
    assert len(calls) == 4


def test_runner_does_not_retry_a_rejected_callback(monkeypatch, runner_module):
    calls = []

    def send(*_args):
        calls.append(1)
        raise urllib.error.HTTPError("url", 404, "Not found", {}, io.BytesIO())

    monkeypatch.setattr(runner_module, "_send", send)

    with pytest.raises(urllib.error.HTTPError):
        runner_module.api_request("context")
    assert len(calls) == 1


def test_runner_completion_survives_a_lost_response(monkeypatch, runner_module):
    calls = []

    def send(path, payload, method, timeout):
        calls.append((path, method, timeout))
        if len(calls) == 1:
            raise runner_module.http.client.RemoteDisconnected("closed")
        # The first attempt reached the server, so the job is already terminal.
        raise urllib.error.HTTPError("url", 401, "Invalid", {}, io.BytesIO())

    monkeypatch.setattr(runner_module, "_send", send)

    assert runner_module.complete({"report": "done", "error": None}) == {}
    assert calls == [("complete", "POST", 300)] * 2


def test_runner_completion_401_on_first_attempt_is_an_error(monkeypatch, runner_module):
    def send(*_args):
        raise urllib.error.HTTPError("url", 401, "Invalid", {}, io.BytesIO())

    monkeypatch.setattr(runner_module, "_send", send)

    with pytest.raises(urllib.error.HTTPError):
        runner_module.complete({"report": "", "error": None})


def test_launch_error_keeps_hub_validation_message():
    response = Response(
        403,
        request=Request("POST", "https://huggingface.co/api/jobs/huggingface"),
        json={
            "error": "User does not have permission to create a Job in this namespace"
        },
    )
    error = HfHubHTTPError(
        "forbidden",
        response=response,
        server_message="User does not have permission to create a Job in this namespace",
    )

    message = _launch_error(error)

    assert "does not have permission" in message
    assert "HfHubHTTPError" not in message


@pytest.mark.parametrize(
    ("validation_summary", "mutation_result", "expected_status"),
    [
        (
            {"post_write_verification": "passed"},
            {"status": "no_changes"},
            "completed",
        ),
        (
            {"status": "rejected", "error": "invalid metric"},
            None,
            "failed",
        ),
        (
            {"policy": "scheduled-add-evals-v1", "mode": "shadow"},
            {"status": "shadow"},
            "completed",
        ),
    ],
)
def test_completion_requires_an_accepted_verified_apply(
    validation_summary, mutation_result, expected_status
):
    row = SimpleNamespace(
        status="running",
        submitted_at=datetime.now(UTC),
        validation_summary=validation_summary,
        mutation_result=mutation_result,
        thumbnail_status=None,
        applied_at=None,
        report=None,
        error=None,
        finished_at=None,
    )

    class Database:
        def refresh(self, _row, *, with_for_update):
            assert with_for_update is True

        def flush(self):
            pass

        def commit(self):
            pass

    service = CodexPaperJobService()
    service.serialize = lambda candidate, _settings: candidate
    service._advance_workflow = lambda *_args: None
    service._evaluate_scheduled_health = lambda *_args: None
    service.dispatch_next = lambda *_args: None

    result = service.complete(
        Database(), row, report="audit", error=None, settings=get_settings()
    )

    assert result.status == expected_status
    assert (result.error is None) == (expected_status == "completed")


def test_acknowledged_failures_are_outside_the_new_rate_window():
    acknowledged_at = datetime.now(UTC)
    state = SimpleNamespace(
        acknowledged_at=acknowledged_at,
        consecutive_apply_failures=0,
        paused_at=None,
        pause_condition=None,
        pause_reason=None,
    )

    class Query:
        def __init__(self):
            self.after_acknowledgement = False

        def filter(self, *conditions):
            self.after_acknowledgement = any(
                getattr(getattr(condition, "left", None), "key", None) == "finished_at"
                and getattr(getattr(condition, "right", None), "value", None)
                == acknowledged_at
                for condition in conditions
            )
            return self

        def order_by(self, *_args):
            return self

        def limit(self, *_args):
            return self

        def all(self):
            if self.after_acknowledgement:
                return []
            return [
                SimpleNamespace(status="failed", error="validator failure")
                for _ in range(25)
            ]

    class Database:
        def get(self, *_args):
            return state

        def query(self, *_args):
            return Query()

        def commit(self):
            pass

    row = SimpleNamespace(
        trigger="hf-daily-cron",
        status="completed",
        error=None,
    )
    CodexPaperJobService()._evaluate_scheduled_health(Database(), row)

    assert state.paused_at is None
    assert state.consecutive_apply_failures == 0


def test_awaiting_markdown_is_not_counted_as_a_curation_failure():
    state = SimpleNamespace(
        acknowledged_at=None,
        consecutive_apply_failures=2,
        paused_at=None,
        pause_condition=None,
        pause_reason=None,
    )
    row = SimpleNamespace(
        trigger="hf-daily-cron",
        status="failed",
        error="[awaiting_markdown] Awaiting paper Markdown extraction: 2608.00042",
    )

    class Query:
        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def limit(self, *_args):
            return self

        def all(self):
            return [row]

    class Database:
        def get(self, *_args):
            return state

        def query(self, *_args):
            return Query()

        def commit(self):
            return None

    CodexPaperJobService()._evaluate_scheduled_health(Database(), row)

    assert state.consecutive_apply_failures == 2
    assert state.paused_at is None


def test_unstarted_job_rebinds_to_the_active_bootstrap_release(monkeypatch):
    from backend.services import codex_add_evals_service

    active_revision = "f" * 40
    monkeypatch.setattr(
        codex_add_evals_service, "_git_revision", lambda: active_revision
    )
    settings = get_settings().model_copy(
        update={
            "codex_jobs_model": "gpt-5.6-sol",
            "codex_jobs_reasoning_effort": "medium",
            "codex_jobs_cli_version": "0.75.0",
        }
    )
    row = SimpleNamespace(
        id=uuid.uuid4(),
        kind="add-evals",
        repository_sha="e" * 40,
        skill_sha256="d" * 64,
        model="older-model",
        reasoning_effort="low",
        codex_cli_version="0.74.0",
        validator_version="older-validator",
        bootstrap_bundle_sha256="a" * 64,
    )
    stored = []
    monkeypatch.setattr(
        codex_add_evals_service,
        "_store_bootstrap_bundle",
        lambda db, revision: stored.append(revision) or "b" * 64,
    )

    CodexPaperJobService._bind_active_release(object(), row, settings)

    assert row.repository_sha == active_revision
    assert row.skill_sha256 != "d" * 64
    assert len(row.skill_sha256) == 64
    assert row.model == "gpt-5.6-sol"
    assert row.reasoning_effort == "medium"
    assert row.codex_cli_version == "0.75.0"
    assert row.validator_version == "scheduled-policy-v1"
    assert stored == [active_revision]
    assert row.bootstrap_bundle_sha256 == "b" * 64


def test_remote_callbacks_identify_the_service_to_cloudflare():
    assert HELPER_USER_AGENT.startswith("PapersWithCode-Curation/")
    runner = Path("jobs/run_paper_curation.py").read_text(encoding="utf-8")
    assert '"User-Agent": USER_AGENT' in runner


def test_remote_runner_uses_codex_075_compatible_non_git_flags():
    runner = Path("jobs/run_paper_curation.py").read_text(encoding="utf-8")
    assert '"--skip-git-repo-check"' in runner
    assert '"--ephemeral"' not in runner


def test_remote_runner_preserves_scoped_callback_token_for_agent_commands():
    runner = Path("jobs/run_paper_curation.py").read_text(encoding="utf-8")
    assert '"shell_environment_policy.ignore_default_excludes=true"' in runner
    assert 'os.environ.pop("OPENAI_API_KEY", None)' in runner


def test_scheduled_enrichment_prompt_is_additive_only():
    runner = Path("jobs/run_paper_curation.py").read_text(encoding="utf-8")

    assert "Scheduled mode is additive only" in runner


def test_remote_runner_checks_markdown_before_both_curation_stages():
    runner = Path("jobs/run_paper_curation.py").read_text(encoding="utf-8")

    preflight = runner.index("preflight = run_url_preflight(context)")
    awaiting_gate = runner.index('preflight.get("awaiting_markdown")', preflight)
    enrich_only = runner.index('if KIND == "enrich-paper":', awaiting_gate)

    assert preflight < awaiting_gate < enrich_only


def test_remote_curation_reads_external_release_pages_as_the_paper():
    skill = " ".join(
        Path(".agents/skills/remote-paper-curation/SKILL.md")
        .read_text(encoding="utf-8")
        .split()
    )

    # Blog-only external papers have no Markdown/PDF; the release page is the
    # paper, so enrichment must still tag tasks and add official Hub repos.
    assert "the `paper_source` document is the paper" in skill
    assert "The missing Markdown or PDF is not missing evidence." in skill
    assert "is the release's own model card" in skill
    assert "do not tag from the title alone" in skill


def test_remote_add_evals_requires_configured_leaderboard_search():
    skill = Path(".agents/skills/remote-paper-curation/SKILL.md").read_text(
        encoding="utf-8"
    )
    runner = Path("jobs/run_paper_curation.py").read_text(encoding="utf-8")
    normalized_skill = " ".join(skill.split())
    normalized_runner = " ".join(runner.split())

    assert "only after running the `leaderboards` command for every" in normalized_skill
    assert "Never use an empty taxonomy result" in normalized_skill
    assert "for every benchmark found across those sources" in normalized_runner
    assert "taxonomy command returns only tasks and methods" in normalized_runner


def test_add_evals_skill_treats_existing_equivalent_rows_as_satisfied():
    skill = Path(".agents/skills/add-evals/SKILL.md").read_text(encoding="utf-8")
    normalized = " ".join(skill.split())

    assert "same introduced model, harness/setup, selected metric" in normalized
    assert "submit an empty `evaluations` array" in normalized
    assert "Do not manufacture `validation_evidence` for unchanged rows" in normalized


def test_codex_endpoint_enqueues_exact_paper(monkeypatch):
    from backend.routers import codex_add_evals

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    paper = SimpleNamespace(
        id=42, source="arxiv", arxiv_id="2601.00001", title="A useful model"
    )

    class Query:
        def filter(self, *_args):
            return self

        def one_or_none(self):
            return paper

    class Database:
        def query(self, _model):
            return Query()

    def fake_enqueue(db, **kwargs):
        assert db is not None
        assert kwargs["kind"] == "add-evals"
        assert kwargs["paper_id"] == 42
        assert kwargs["paper_route"] == "2601.00001"
        assert kwargs["requested_by"] == "niels"
        return _job()

    monkeypatch.setattr(
        codex_add_evals.codex_paper_job_service, "enqueue", fake_enqueue
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[require_hf_admin] = lambda: {"username": "niels"}
    app.dependency_overrides[get_database_session] = lambda: Database()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/codex-add-evals/jobs", json={"paper_id": 42}
        )
    assert response.status_code == 202
    assert response.json()["kind"] == "add-evals"


def test_codex_endpoint_is_hidden_when_jobs_disabled():
    settings = get_settings().model_copy(update={"codex_jobs_enabled": False})
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[require_hf_admin] = lambda: {"username": "niels"}
    app.dependency_overrides[get_database_session] = lambda: SimpleNamespace()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/codex-add-evals/jobs", json={"paper_id": 42}
        )
    assert response.status_code == 404


def test_dedicated_app_exposes_remote_callback_routes():
    paths = {route.path for route in create_codex_add_evals_app().routes}
    assert "/api/v1/admin/codex-add-evals/jobs" in paths
    assert "/api/v1/admin/codex-enrich-paper/jobs" in paths
    assert "/api/v1/admin/codex-curation/jobs" in paths
    assert "/api/v1/admin/codex-curation/jobs/{job_id}/context" in paths
    assert "/api/v1/admin/codex-curation/jobs/{job_id}/leaderboards" in paths
    assert "/api/v1/admin/codex-curation/jobs/{job_id}/thumbnail" in paths
    assert (
        "/api/v1/admin/codex-curation/jobs/benchmark-candidates/{candidate_id}/promote"
        in paths
    )
    assert "/api/v1/chat/models" not in paths


def test_scoped_worker_can_search_configured_leaderboards(monkeypatch):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    inventory = [
        {
            "dataset": {"id": 340, "name": "GenEval", "slug": "geneval"},
            "task": {"id": 19, "name": "Image generation", "slug": "image-generation"},
            "supports_harness": False,
            "metrics": [
                {
                    "id": 101,
                    "name": "GenEval Score",
                    "direction": "higher_is_better",
                    "scale": "0-1",
                    "recent_values": [{"model_name": "Example", "value": "0.90"}],
                }
            ],
        }
    ]
    monkeypatch.setattr(
        codex_curation_callbacks, "_callback_job", lambda *_args: object()
    )
    monkeypatch.setattr(
        codex_curation_callbacks,
        "_leaderboard_inventory",
        lambda _db, query: inventory if query == "GenEval" else [],
    )
    monkeypatch.setattr(codex_curation_callbacks, "_consume_query", lambda *_args: None)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: SimpleNamespace()

    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/admin/codex-curation/jobs/{_job().id}/leaderboards?q=GenEval",
            headers={"Authorization": "Bearer scoped-token"},
        )

    assert response.status_code == 200
    assert response.json()["leaderboards"] == inventory


def test_curation_helper_exposes_leaderboard_search(monkeypatch):
    calls = []
    monkeypatch.setattr(curation_api, "request", lambda path: calls.append(path))
    monkeypatch.setattr(sys, "argv", ["curation_api.py", "leaderboards", "DPG-Bench"])

    curation_api.main()

    assert calls == ["leaderboards?q=DPG-Bench"]


def test_curation_helper_surfaces_callback_validation_detail(monkeypatch):
    monkeypatch.setenv("PWC_CURATION_API_URL", "https://paperswithcode.co/api/v1")
    monkeypatch.setenv("PWC_CURATION_JOB_ID", str(_job().id))
    monkeypatch.setenv("PWC_CURATION_JOB_TOKEN", "scoped-token")
    response = urllib.error.HTTPError(
        "https://paperswithcode.co/api/v1/admin/codex-curation/jobs/job/apply",
        422,
        "Unprocessable Entity",
        {},
        io.BytesIO(
            b'{"detail":"Evaluation metric value 91.9 is outside configured scale 0-1"}'
        ),
    )
    monkeypatch.setattr(
        curation_api.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(response),
    )

    with pytest.raises(RuntimeError, match="outside configured scale 0-1"):
        curation_api.request_json("apply", "POST", {"evaluations": []})


def test_empty_add_evals_apply_is_an_explicit_no_op(monkeypatch):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    row = SimpleNamespace(
        kind="add-evals", status="running", applied_at=None, paper_id=42
    )

    class Database:
        commits = 0

        def commit(self):
            self.commits += 1

    database = Database()
    monkeypatch.setattr(codex_curation_callbacks, "_callback_job", lambda *_args: row)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: database

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/admin/codex-curation/jobs/{_job().id}/apply",
            headers={"Authorization": "Bearer scoped-token"},
            json={"evaluations": []},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "no_changes",
        "evaluations_created": 0,
        "evaluations_updated": 0,
    }
    assert row.applied_at is None
    assert row.submitted_at is not None
    assert database.commits == 1


def test_scoped_worker_can_apply_discovered_evaluation(monkeypatch):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    row = SimpleNamespace(
        kind="add-evals", status="running", applied_at=None, paper_id=42
    )
    created = []

    class Query:
        def filter(self, *_args):
            return self

        def one_or_none(self):
            return None

    class Database:
        commits = 0

        def query(self, _model):
            return Query()

        def commit(self):
            self.commits += 1

    class FakeEvaluationService:
        def __init__(self, _db):
            pass

        def create_evaluation(self, **values):
            created.append(values)

    database = Database()
    monkeypatch.setattr(codex_curation_callbacks, "_callback_job", lambda *_args: row)
    monkeypatch.setattr(
        codex_curation_callbacks, "EvaluationService", FakeEvaluationService
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: database

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/admin/codex-curation/jobs/{_job().id}/apply",
            headers={"Authorization": "Bearer scoped-token"},
            json={
                "evaluations": [
                    {
                        "paper_id": 42,
                        "task_id": 19,
                        "dataset_id": 340,
                        "model_name": "Useful Model",
                        "metrics": {"GenEval Score": 0.9},
                        "best_metric": "GenEval Score",
                        "source_url": "https://arxiv.org/abs/2601.00001",
                    }
                ]
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "applied",
        "evaluations_created": 1,
        "evaluations_updated": 0,
    }
    assert created[0]["dataset_id"] == 340
    assert created[0]["commit"] is False
    assert row.applied_at is not None
    assert database.commits == 1


def test_scoped_enrichment_queues_thumbnail_without_web_process_mutation(monkeypatch):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    row = SimpleNamespace(
        kind="enrich-paper", status="running", applied_at=None, paper_id=42
    )
    paper = SimpleNamespace(thumbnail_url=None, urls_extracted=False)

    class Database:
        commits = 0

        def get(self, _model, paper_id):
            assert paper_id == 42
            return paper

        def commit(self):
            self.commits += 1

    database = Database()
    monkeypatch.setattr(codex_curation_callbacks, "_callback_job", lambda *_args: row)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: database

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/admin/codex-curation/jobs/{_job().id}/apply",
            headers={"Authorization": "Bearer scoped-token"},
            json={
                "enrich": {
                    "regenerate_thumbnail": True,
                    "urls_extracted": True,
                }
            },
        )

    assert response.status_code == 200
    assert response.json()["thumbnail"] | {
        "requested_at": None,
    } == {
        "requested": True,
        "status": "queued",
        "attempt_count": 0,
        "requested_at": None,
        "claimed_at": None,
        "finished_at": None,
        "thumbnail_url": None,
        "previous_dimensions": None,
        "generated_dimensions": None,
        "success": None,
        "warnings": [],
        "error": None,
    }
    assert paper.urls_extracted
    assert row.applied_at is not None
    router_source = Path(codex_curation_callbacks.__file__).read_text()
    assert "regenerate_paper_thumbnail" not in router_source
    assert "ThumbnailService" not in router_source


def test_enrichment_relations_and_thumbnail_enqueue_commit_atomically(monkeypatch):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    row = SimpleNamespace(
        kind="enrich-paper", status="running", applied_at=None, paper_id=42
    )
    paper = SimpleNamespace(thumbnail_url=None, urls_extracted=False)
    calls = []

    class Database:
        commits = 0

        def get(self, _model, _paper_id):
            return paper

        def commit(self):
            self.commits += 1

    class FakeAssociationService:
        def __init__(self, _db, _hydrate):
            pass

        def update_tasks(self, paper_id, values, *, commit):
            calls.append(("tasks", paper_id, values, commit))

        def update_methods(self, paper_id, values, *, commit):
            calls.append(("methods", paper_id, values, commit))

    database = Database()
    monkeypatch.setattr(codex_curation_callbacks, "_callback_job", lambda *_args: row)
    monkeypatch.setattr(
        codex_curation_callbacks, "PaperAssociationService", FakeAssociationService
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: database

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/admin/codex-curation/jobs/{_job().id}/apply",
            headers={"Authorization": "Bearer scoped-token"},
            json={
                "enrich": {
                    "task_ids": [19],
                    "method_ids": [59],
                    "regenerate_thumbnail": True,
                }
            },
        )

    assert response.status_code == 200
    assert calls == [
        ("tasks", 42, [19], False),
        ("methods", 42, [59], False),
    ]
    assert row.thumbnail_status == "queued"
    assert row.submitted_at == row.applied_at
    assert database.commits == 1


def test_late_invalid_enrichment_input_rolls_back_before_enqueue(monkeypatch):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    row = SimpleNamespace(
        kind="enrich-paper", status="running", applied_at=None, paper_id=42
    )
    paper = SimpleNamespace(
        thumbnail_url=None, urls_extracted=False, tasks_changed=False
    )

    class Database:
        commits = 0
        rollbacks = 0

        def get(self, _model, _paper_id):
            return paper

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1
            paper.tasks_changed = False

    class FakeAssociationService:
        def __init__(self, db, _hydrate):
            self.db = db

        def update_tasks(self, _paper_id, _values, *, commit):
            assert commit is False
            paper.tasks_changed = True

        def update_methods(self, _paper_id, _values, *, commit):
            assert commit is False
            raise ValueError("Invalid method IDs: {999}")

    database = Database()
    monkeypatch.setattr(codex_curation_callbacks, "_callback_job", lambda *_args: row)
    monkeypatch.setattr(
        codex_curation_callbacks, "PaperAssociationService", FakeAssociationService
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: database

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            f"/api/v1/admin/codex-curation/jobs/{_job().id}/apply",
            headers={"Authorization": "Bearer scoped-token"},
            json={
                "enrich": {
                    "task_ids": [19],
                    "method_ids": [999],
                    "regenerate_thumbnail": True,
                }
            },
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid method IDs: {999}"}
    assert database.rollbacks == 1
    assert database.commits == 0
    assert paper.tasks_changed is False
    assert not hasattr(row, "thumbnail_status")
    assert not hasattr(row, "submitted_at")


def test_admin_can_list_curation_queue(monkeypatch):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    expected = CodexPaperJobsResponse(
        timestamp=datetime.now(UTC),
        jobs=[_job()],
        summary=CodexPaperJobCounts(total=1, queued=1),
    )

    def fake_list_jobs(db, supplied_settings, *, limit):
        assert db is not None
        assert supplied_settings is settings
        assert limit == 25
        return expected

    monkeypatch.setattr(
        codex_curation_callbacks.codex_paper_job_service, "list_jobs", fake_list_jobs
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[require_hf_admin] = lambda: {"username": "niels"}
    app.dependency_overrides[get_database_session] = lambda: SimpleNamespace()
    with TestClient(app) as client:
        response = client.get("/api/v1/admin/codex-curation/jobs?limit=25")

    assert response.status_code == 200
    assert response.json()["jobs"][0]["paper_id"] == 42
    assert response.json()["summary"]["queued"] == 1


class _ReconcileDb:
    def __init__(self, events, rows):
        self.events = events
        self.rows = rows

    def execute(self, _statement):
        self.events.append("select")
        return SimpleNamespace(
            all=lambda: [(row.id, row.hf_job_id) for row in self.rows]
        )

    def query(self, _model):
        self.events.append("reread")
        query = SimpleNamespace(all=lambda: self.rows)
        query.filter = lambda *_args: query
        return query

    def commit(self):
        self.events.append("commit")


class _ReconcileApi:
    def __init__(self, events, stages):
        self.events = events
        self.stages = stages

    def list_jobs(self, *, namespace):
        self.events.append("list_jobs")
        return [
            SimpleNamespace(id=job_id, status=SimpleNamespace(stage=stage))
            for job_id, stage in self.stages.items()
        ]


def _reconcile_settings():
    return get_settings().model_copy(
        update={"codex_jobs_enabled": True, "codex_jobs_token": "hf-token"}
    )


def test_reconcile_ends_read_transaction_before_listing_hub_jobs():
    events = []
    row = SimpleNamespace(id=uuid.uuid4(), hf_job_id="hf-running", status="running")
    service = CodexPaperJobService(_ReconcileApi(events, {"hf-running": "RUNNING"}))

    service.reconcile(_ReconcileDb(events, [row]), _reconcile_settings())

    assert events == ["select", "commit", "list_jobs"]
    assert row.status == "running"


def test_reconcile_marks_jobs_that_ended_without_a_callback(monkeypatch):
    events = []
    failed = SimpleNamespace(id=uuid.uuid4(), hf_job_id="hf-error", status="running")
    canceled = SimpleNamespace(
        id=uuid.uuid4(), hf_job_id="hf-canceled", status="running"
    )
    service = CodexPaperJobService(
        _ReconcileApi(events, {"hf-error": "ERROR", "hf-canceled": "CANCELED"})
    )
    monkeypatch.setattr(service, "_advance_workflow", lambda *_args: None)
    monkeypatch.setattr(
        service, "dispatch_next", lambda *_args: events.append("dispatch")
    )

    service.reconcile(_ReconcileDb(events, [failed, canceled]), _reconcile_settings())

    assert events == ["select", "commit", "list_jobs", "reread", "commit", "dispatch"]
    assert (failed.status, failed.error) == (
        "failed",
        "Hugging Face Job ended with error.",
    )
    assert canceled.status == "canceled"


def test_polled_reads_share_one_reconcile_per_interval(monkeypatch):
    service = CodexPaperJobService()
    calls = []
    monkeypatch.setattr(service, "reconcile", lambda *_args: calls.append(1))
    clock = iter([100.0, 100.0, 110.0, 131.0, 131.0])
    monkeypatch.setattr(
        "backend.services.codex_add_evals_service.time.monotonic",
        lambda: next(clock),
    )

    service.reconcile_if_due(None, None)
    service.reconcile_if_due(None, None)
    service.reconcile_if_due(None, None)

    assert len(calls) == 2
