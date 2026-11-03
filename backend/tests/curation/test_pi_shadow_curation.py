"""Pi shadow curation: pairing, frozen context, shadow validation, and diffs."""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import sys
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.config import get_settings
from backend.models.curation import ApplyMutationRequest, EnrichPaperMutation
from backend.models.database import (
    Paper,
    PaperMethod,
    PaperTask,
)
from backend.services import codex_curation_callback_service as callback_module
from backend.services.codex_add_evals_service import (
    PI_CURATOR_COMMAND,
    PI_SHADOW_TRIGGER,
    CodexPaperJobService,
)
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
)
from backend.services.curation_pair_diff import curation_pair_diff
from backend.services.runtime_policies.codex_jobs import (
    validate_codex_jobs_configuration,
)

PI_IMAGE = "cr.hf.co/example/pwc-codex-curator:pi-runner-abc@sha256:" + "a" * 64


def _pi_settings(**overrides):
    return get_settings().model_copy(
        update={
            "codex_jobs_namespace": "example",
            "codex_jobs_token": "jobs-token",
            "codex_jobs_openai_api_key": "openai-key",
            "hf_token": "markdown-token",
            "curation_pi_shadow_sample_rate": 1.0,
            "curation_pi_jobs_image": PI_IMAGE,
            "curation_pi_hf_token": "inference-token",
            **overrides,
        }
    )


def _codex_row(**overrides):
    values = {
        "id": uuid.uuid4(),
        "kind": "enrich-paper",
        "paper_id": 42,
        "paper_route": "2601.00001",
        "paper_title": "Useful Paper",
        "trigger": "hf-daily-cron",
        "retry_of_id": None,
        "runner": "codex",
        "status": "running",
        "cohort_date": None,
        "policy_version": "hf-daily-v1",
        "priority": 10,
        "repository_sha": "b" * 40,
        "skill_sha256": "c" * 64,
        "bootstrap_bundle_sha256": "d" * 64,
        "validator_version": "scheduled-policy-v1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _job(**overrides):
    values = {
        "id": uuid.uuid4(),
        "kind": "enrich-paper",
        "status": "completed",
        "error": None,
        "duration_ms": 1_000,
        "input_tokens": 10,
        "output_tokens": 5,
        "model": "model",
        "proposal": None,
        "context_snapshot": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


# Sampling and dispatch


def test_sampling_is_off_by_default_and_stable_per_paper():
    row = _codex_row()
    assert get_settings().curation_pi_shadow_sample_rate == 0
    assert not CodexPaperJobService._pi_shadow_sampled(get_settings(), row)
    assert CodexPaperJobService._pi_shadow_sampled(_pi_settings(), row)

    half = _pi_settings(curation_pi_shadow_sample_rate=0.5)
    picks = {
        paper_id: CodexPaperJobService._pi_shadow_sampled(
            half, _codex_row(paper_id=paper_id)
        )
        for paper_id in range(400)
    }
    # Both stages of one paper get the same decision.
    assert all(
        CodexPaperJobService._pi_shadow_sampled(
            half, _codex_row(paper_id=paper_id, kind="add-evals")
        )
        == picked
        for paper_id, picked in picks.items()
    )
    assert 150 < sum(picks.values()) < 250


@pytest.mark.parametrize(
    "overrides",
    [
        {"trigger": "admin"},
        {"trigger": "hf-trending-cron"},
        {"kind": "resolve-model-paper"},
        {"retry_of_id": uuid.uuid4()},
        {"paper_id": None},
    ],
)
def test_only_first_attempt_daily_paper_stages_are_paired(overrides):
    assert not CodexPaperJobService._pi_shadow_sampled(
        _pi_settings(), _codex_row(**overrides)
    )


@pytest.mark.parametrize(
    "overrides", [{"curation_pi_jobs_image": ""}, {"curation_pi_hf_token": ""}]
)
def test_pairing_needs_an_image_and_inference_token(overrides):
    assert not CodexPaperJobService._pi_shadow_sampled(
        _pi_settings(**overrides), _codex_row()
    )


class _CountQuery:
    def __init__(self, count):
        self.count = count

    def filter(self, *_args):
        return self

    def scalar(self):
        return self.count


class _PairingDatabase:
    def __init__(self, active=0):
        self.active = active
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, *_args):
        return _CountQuery(self.active)

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_pairing_freezes_the_codex_context_and_launches_a_pi_job(monkeypatch):
    service = CodexPaperJobService()
    dispatched = []
    monkeypatch.setattr(
        service, "_dispatch_row", lambda _db, _settings, row: dispatched.append(row)
    )
    context = {
        "job": {"id": "codex"},
        "retry_feedback": {"error": "previous"},
        "source_candidate": None,
        "paper": {"id": 42, "date_published": date(2026, 1, 2)},
    }
    monkeypatch.setattr(
        CodexCurationCallbackService, "context", lambda _self, _row, _s: dict(context)
    )
    codex = _codex_row()
    db = _PairingDatabase()

    service._pair_pi_shadow(db, _pi_settings(), codex)

    (row,) = db.added
    assert dispatched == [row]
    assert row.runner == "pi"
    assert row.trigger == PI_SHADOW_TRIGGER
    assert row.parent_workflow_id is None
    assert row.paired_job_id == codex.id
    assert row.kind == codex.kind
    assert row.repository_sha == codex.repository_sha
    assert row.model == "deepseek-ai/DeepSeek-V4.1-Flash-1017"
    assert row.reasoning_effort == "high"
    assert row.codex_cli_version == "pi@1.3.0"
    # The snapshot is JSON-ready and holds no job-specific state.
    assert row.context_snapshot == {
        "source_candidate": None,
        "paper": {"id": 42, "date_published": "2026-01-02"},
    }


def test_full_pi_pool_skips_the_pair_instead_of_queueing(monkeypatch):
    service = CodexPaperJobService()
    monkeypatch.setattr(
        service, "_dispatch_row", lambda *_args: pytest.fail("must not dispatch")
    )
    db = _PairingDatabase(active=2)

    service._pair_pi_shadow(db, _pi_settings(), _codex_row())

    assert db.added == []


def test_pairing_failure_never_reaches_the_codex_dispatch(monkeypatch):
    service = CodexPaperJobService()

    def broken_context(_self, _row, _settings):
        raise RuntimeError("catalog unavailable")

    monkeypatch.setattr(CodexCurationCallbackService, "context", broken_context)
    db = _PairingDatabase()

    service._pair_pi_shadow(db, _pi_settings(), _codex_row())

    assert db.added == []
    assert db.rollbacks == 1


def test_pi_job_launches_its_own_image_command_and_inference_token(monkeypatch):
    calls = []

    class Hub:
        def run_job(self, **values):
            calls.append(values)
            return SimpleNamespace(id="hf-job")

    service = CodexPaperJobService()
    monkeypatch.setattr(service, "_api", lambda _settings: Hub())
    settings = _pi_settings()
    row = _codex_row(
        runner="pi",
        trigger=PI_SHADOW_TRIGGER,
        model="deepseek-ai/DeepSeek-V4.1-Flash-1017",
        reasoning_effort="high",
        codex_cli_version="pi@1.3.0",
        candidate_id=None,
    )

    assert service._verified_job_image(None, settings, row) == PI_IMAGE
    service._run_job_with_retry(
        settings=settings, row=row, callback_token="callback", image=PI_IMAGE
    )

    (call,) = calls
    assert call["command"] == ["bash", "-lc", PI_CURATOR_COMMAND]
    assert call["secrets"] == {
        "PWC_CURATION_JOB_TOKEN": "callback",
        "PWC_PAPER_MARKDOWN_HF_TOKEN": "markdown-token",
        "HF_TOKEN": "inference-token",
    }
    assert call["env"]["PWC_CURATION_MODEL"] == "deepseek-ai/DeepSeek-V4.1-Flash-1017"
    assert call["env"]["PWC_CURATION_REASONING_EFFORT"] == "high"
    assert call["env"]["PWC_CURATION_PI_PROVIDER"] == "novita"
    assert call["env"]["PWC_CURATION_PI_BILL_TO"] == "huggingface"
    assert call["env"]["PWC_CURATION_TRIGGER"] == PI_SHADOW_TRIGGER
    assert call["labels"]["runner"] == "pi"


def test_codex_jobs_keep_their_openai_launch(monkeypatch):
    calls = []

    class Hub:
        def run_job(self, **values):
            calls.append(values)
            return SimpleNamespace(id="hf-job")

    service = CodexPaperJobService()
    monkeypatch.setattr(service, "_api", lambda _settings: Hub())
    row = _codex_row(
        model="gpt-6-luna",
        reasoning_effort="medium",
        codex_cli_version="0.75.0",
        candidate_id=None,
    )

    service._run_job_with_retry(
        settings=_pi_settings(), row=row, callback_token="callback", image="image"
    )

    (call,) = calls
    assert call["secrets"]["OPENAI_API_KEY"] == "openai-key"
    assert "HF_TOKEN" not in call["secrets"]
    assert "PWC_CURATION_PI_PROVIDER" not in call["env"]
    assert call["labels"]["runner"] == "codex"


# Frozen context and shadow validation


def test_pi_job_is_served_its_frozen_context():
    snapshot = {"paper": {"id": 42, "tasks": []}, "source_candidate": None}
    row = _codex_row(runner="pi", trigger=PI_SHADOW_TRIGGER, context_snapshot=snapshot)
    job_service = SimpleNamespace(
        serialize=lambda selected, _settings: SimpleNamespace(
            model_dump=lambda mode: {"id": str(selected.id)}
        )
    )
    service = CodexCurationCallbackService(
        SimpleNamespace(), job_service=job_service, association_service=object()
    )

    context = service.context(row, get_settings())

    assert context == {
        **snapshot,
        "job": {"id": str(row.id)},
        "retry_feedback": None,
    }


class _Rows:
    def __init__(self, rows):
        self.rows = rows
        self.ids = []

    def join(self, *_args):
        return self

    def filter(self, *criteria):
        # Task/Method id lookups: every proposed id exists in the catalog.
        values = [
            getattr(getattr(criterion, "right", None), "value", None)
            for criterion in criteria
        ]
        self.ids = [
            item for value in values if isinstance(value, list) for item in value
        ]
        return self

    def count(self):
        return len(self.ids)

    def all(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)


class _LiveCatalog:
    """Catalog after the paired Codex job added task 9 and method 12."""

    def __init__(self):
        self.paper = SimpleNamespace(id=42, project_pages=[])

    def get(self, model, key):
        return self.paper if model is Paper else SimpleNamespace(id=key)

    def query(self, model, *_args):
        if model is PaperTask:
            return _Rows(
                [
                    SimpleNamespace(task_id=3, source="manual"),
                    SimpleNamespace(task_id=9, source="curation"),
                ]
            )
        if model is PaperMethod:
            return _Rows([SimpleNamespace(method_id=12)])
        return _Rows([])


def test_pi_enrichment_is_validated_on_its_snapshot_not_on_codex_writes():
    row = _codex_row(
        runner="pi",
        trigger=PI_SHADOW_TRIGGER,
        trace_status="disabled",
        url_candidates={"complete": True},
        context_snapshot={
            "paper": {"tasks": [{"id": 3}], "methods": [], "repositories": []}
        },
    )
    body = ApplyMutationRequest(
        enrich=EnrichPaperMutation(task_ids=[3, 5], method_ids=[], urls_extracted=True)
    )
    row.proposal = body.model_dump(mode="json")
    service = CodexCurationCallbackService(_LiveCatalog(), association_service=object())

    rebased = service.shadow_validation_body(row, body)

    assert rebased.enrich.task_ids == [3, 5, 9]
    assert rebased.enrich.method_ids == [12]
    assert body.enrich.task_ids == [3, 5]
    # The pre-apply trace holds Pi's own proposal, so compare against that.
    policy = callback_module.CodexCurationCallbackService._validate_scheduled_policy
    with pytest.raises(ValueError, match="cannot remove manual task links"):
        policy(service, row, body)
    result = policy(service, row, rebased, preapply_body=body)
    assert result["policy"] == "scheduled-enrich-v1"


def test_codex_proposals_are_not_rebased():
    body = ApplyMutationRequest(enrich=EnrichPaperMutation(task_ids=[3]))
    service = CodexCurationCallbackService(_LiveCatalog(), association_service=object())

    assert service.shadow_validation_body(_codex_row(), body) is body


# Pair diff


def test_enrich_pair_diff_compares_additions_over_the_snapshot():
    snapshot = {
        "paper": {
            "tasks": [{"id": 1}],
            "methods": [],
            "repositories": [{"url": "https://github.com/a/old"}],
            "project_pages": [],
        }
    }
    codex = _job(
        proposal={
            "enrich": {
                "task_ids": [1, 2, 3],
                "method_ids": [7],
                "repositories": [
                    {"url": "https://github.com/a/old"},
                    {"url": "https://github.com/a/new"},
                ],
            }
        }
    )
    pi = _job(
        status="failed",
        error="Pi exited with status 1.",
        proposal={
            "enrich": {
                "task_ids": [1, 3, 4],
                "repositories": [
                    {"url": "https://github.com/a/old"},
                    {"url": "https://github.com/a/new"},
                ],
            }
        },
        context_snapshot=snapshot,
    )

    diff = curation_pair_diff(codex, pi)

    assert diff["enrich"]["task_ids"] == {
        "both": [3],
        "codex_only": [2],
        "pi_only": [4],
    }
    # Pi left method_ids out, which keeps the current value: no additions.
    assert diff["enrich"]["method_ids"] == {
        "both": [],
        "codex_only": [7],
        "pi_only": [],
    }
    assert diff["enrich"]["repositories"]["both"] == ["https://github.com/a/new"]
    assert diff["disagreements"] == 3
    assert diff["pi"]["status"] == "failed"
    assert diff["both_submitted"] is True
    json.dumps(diff)


def test_evaluation_pair_diff_matches_cells_on_task_dataset_metric():
    def evaluation(dataset_id, metrics, model_name="Model"):
        return {
            "task_id": 19,
            "dataset_id": dataset_id,
            "model_name": model_name,
            "metrics": metrics,
        }

    codex = _job(
        kind="add-evals",
        proposal={
            "evaluations": [
                evaluation(1, {"Accuracy": 86.89, "F1": 70.0}),
                evaluation(2, {"Accuracy": 50.0}),
            ],
            "benchmark_gaps": [{"label": "X"}],
        },
    )
    pi = _job(
        kind="add-evals",
        proposal={
            "evaluations": [
                evaluation(1, {"Accuracy": "86.890", "F1": 0.70}),
                evaluation(3, {"Accuracy": 40.0}),
            ]
        },
    )

    diff = curation_pair_diff(codex, pi)
    evaluations = diff["evaluations"]

    assert [cell["metric"] for cell in evaluations["same"]] == ["Accuracy"]
    assert evaluations["different"] == [
        {
            "task_id": 19,
            "dataset_id": 1,
            "metric": "F1",
            "codex": {"model_name": "Model", "value": 70.0},
            "pi": {"model_name": "Model", "value": 0.7},
        }
    ]
    assert [cell["dataset_id"] for cell in evaluations["codex_only"]] == [2]
    assert [cell["dataset_id"] for cell in evaluations["pi_only"]] == [3]
    assert diff["benchmark_gaps"] == {"codex": 1, "pi": 0}
    assert diff["disagreements"] == 3


def test_pair_diff_is_stored_on_the_pi_job_once_both_are_terminal():
    codex = _job(proposal={"enrich": {"task_ids": [1]}})
    pi = _job(
        runner="pi",
        status="running",
        paired_job_id=codex.id,
        pair_diff=None,
        context_snapshot={"paper": {}},
    )

    class Database:
        def flush(self):
            pass

        def get(self, _model, key):
            assert key == codex.id
            return codex

    CodexPaperJobService._record_pair_diff(Database(), pi)
    assert pi.pair_diff is None

    pi.status = "completed"
    CodexPaperJobService._record_pair_diff(Database(), pi)
    assert pi.pair_diff["enrich"]["task_ids"]["codex_only"] == [1]


def test_unpaired_codex_stages_skip_the_partner_lookup():
    class Database:
        def query(self, *_args):
            pytest.fail("admin stages are never paired")

    CodexPaperJobService._record_pair_diff(
        Database(), _codex_row(trigger="admin", status="completed")
    )


# Configuration


def test_enabled_pi_shadow_requires_a_separate_token_and_pinned_image():
    base = _pi_settings(
        environment="production",
        codex_jobs_enabled=True,
        codex_jobs_api_url="https://paperswithcode.co/api/v1",
        codex_curation_scheduler_enabled=True,
        codex_jobs_image="cr.hf.co/example/codex@sha256:" + "e" * 64,
    )
    validate_codex_jobs_configuration(base)
    for overrides, message in (
        ({"curation_pi_jobs_image": "cr.hf.co/example/pi:latest"}, "immutable Pi"),
        ({"curation_pi_hf_token": ""}, "inference-only"),
        ({"curation_pi_hf_token": "jobs-token"}, "inference-only"),
        ({"curation_pi_hf_token": "markdown-token"}, "inference-only"),
    ):
        with pytest.raises(RuntimeError, match=message):
            validate_codex_jobs_configuration(base.model_copy(update=overrides))


# Runner


@pytest.fixture
def pi_runner(monkeypatch):
    monkeypatch.setenv("PWC_CURATION_API_URL", "https://paperswithcode.co/api/v1")
    monkeypatch.setenv("PWC_CURATION_JOB_ID", str(uuid.uuid4()))
    monkeypatch.setenv("PWC_CURATION_JOB_TOKEN", "test-token")
    monkeypatch.setenv("PWC_CURATION_KIND", "add-evals")
    monkeypatch.setenv("PWC_GIT_SHA", "a" * 40)
    monkeypatch.setenv("PWC_CURATION_MODEL", "deepseek-ai/DeepSeek-V4.1-Flash-1017")
    monkeypatch.setenv("PWC_CURATION_PI_PROVIDER", "novita")
    # The image ships both runners side by side in /runner.
    monkeypatch.syspath_prepend(str(Path("jobs").resolve()))
    for name in ("run_paper_curation", "run_pi_curation"):
        sys.modules.pop(name, None)
    return importlib.import_module("run_pi_curation")


def _message(stop_reason="stop", text="", usage=None):
    return {
        "type": "message_end",
        "message": {
            "role": "assistant",
            "stopReason": stop_reason,
            "content": [{"type": "thinking", "thinking": "..."}]
            + ([{"type": "text", "text": text}] if text else []),
            "usage": usage or {},
        },
    }


def test_runner_sums_per_response_usage_and_reads_the_last_report(pi_runner):
    events = [
        {"type": "message_end", "message": {"role": "user", "content": "go"}},
        _message("toolUse", usage={"input": 100, "cacheRead": 50, "output": 20}),
        {"type": "tool_execution_end", "toolName": "bash"},
        _message("stop", "Applied 2 evaluations.", {"input": 30, "output": 10}),
    ]

    assert pi_runner.usage_totals(events) == {
        "input_tokens": 180,
        "output_tokens": 30,
    }
    assert pi_runner.final_report(events) == "Applied 2 evaluations."
    assert not pi_runner.ended_with_provider_error(events)
    assert pi_runner.ended_with_provider_error(events + [_message("error")])


def test_runner_configures_the_pinned_provider_then_automatic_routing(
    pi_runner, tmp_path, monkeypatch
):
    monkeypatch.setattr(pi_runner, "AGENT_DIR", tmp_path)

    model_ids = pi_runner.write_models_config()

    assert model_ids == [
        "deepseek-ai/DeepSeek-V4.1-Flash-1017:novita",
        "deepseek-ai/DeepSeek-V4.1-Flash-1017",
    ]
    provider = json.loads((tmp_path / "models.json").read_text())["providers"]["pwc-hf"]
    assert provider["baseUrl"] == "https://router.huggingface.co/v1"
    assert provider["apiKey"] == "$HF_TOKEN"
    assert provider["headers"] == {"X-HF-Bill-To": "huggingface"}
    model = provider["models"][0]
    assert model["compat"]["thinkingFormat"] == "deepseek"
    assert model["contextWindow"] == 262_144
    assert model["maxTokens"] == 32_768
    assert model["samplingParams"] == {"temperature": 1.0, "top_p": 1.0}


def test_pi_dockerfile_pins_both_runner_files():
    dockerfile = Path("jobs/Dockerfile.pi-curator").read_text(encoding="utf-8")
    for name in ("run_paper_curation.py", "run_pi_curation.py"):
        digest = hashlib.sha256(Path("jobs", name).read_bytes()).hexdigest()
        assert f'"{digest}"' in dockerfile
    assert "@earendil-works/pi-coding-agent@${PI_CLI_VERSION}" in dockerfile
    assert "ARG PI_CLI_VERSION=1.3.0" in dockerfile
    assert get_settings().curation_pi_cli_version == "1.3.0"


# Callback routes


def test_pi_apply_stays_shadow_even_with_direct_apply_enabled(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.database.connection import get_database_session
    from backend.main import create_app
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(
        update={
            "codex_jobs_enabled": True,
            "codex_curation_direct_apply_enabled": True,
        }
    )
    row = _codex_row(
        runner="pi", trigger=PI_SHADOW_TRIGGER, proposal=None, submitted_at=None
    )
    validated = []

    class Service:
        def _validate_mutation(self, _row, body):
            validated.append(("mutation", body))

        def shadow_validation_body(self, _row, body):
            return body.model_copy(update={"evaluations": []})

        def _validate_scheduled_policy(self, _row, body, *, preapply_body):
            validated.append(("policy", body, preapply_body))
            return {"policy": "scheduled-enrich-v1"}

        def apply(self, *_args, **_kwargs):
            pytest.fail("a Pi shadow job must never apply")

    class Database:
        def commit(self):
            pass

    monkeypatch.setattr(codex_curation_callbacks, "_callback_job", lambda *_a: row)
    monkeypatch.setattr(codex_curation_callbacks, "_service", lambda _db: Service())
    monkeypatch.setattr(
        codex_curation_callbacks,
        "_autonomous_callback_context",
        lambda *_a: pytest.fail("Pi shadow jobs need no autonomous run"),
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: Database()
    proposal = {"enrich": {"task_ids": [3], "method_ids": []}}

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/admin/codex-curation/jobs/{row.id}/apply",
            headers={"Authorization": "Bearer scoped-token"},
            json=proposal,
        )

    assert response.status_code == 200
    assert response.json()["status"] == "shadow"
    assert row.validation_summary == {"policy": "scheduled-enrich-v1", "mode": "shadow"}
    assert row.proposal["enrich"]["task_ids"] == [3]
    (_, policy_body, preapply_body) = validated[1]
    assert policy_body is not preapply_body


def test_admin_retry_refuses_pi_shadow_jobs():
    from fastapi.testclient import TestClient

    from backend.database.connection import get_database_session
    from backend.main import create_app
    from backend.utils.auth import require_hf_admin

    row = _codex_row(runner="pi", trigger=PI_SHADOW_TRIGGER, status="failed")
    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[require_hf_admin] = lambda: {"username": "niels"}
    app.dependency_overrides[get_database_session] = lambda: SimpleNamespace(
        get=lambda _model, _key: row
    )

    with TestClient(app) as client:
        response = client.post(f"/api/v1/admin/codex-curation/jobs/{row.id}/retry")

    assert response.status_code == 409


def test_codex_completion_locks_and_rereads_its_pi_pair():
    codex = _codex_row(status="completed", proposal={"enrich": {"task_ids": [1]}})
    for field in ("error", "duration_ms", "input_tokens", "output_tokens", "model"):
        setattr(codex, field, None)
    pi = _job(
        runner="pi",
        status="running",
        paired_job_id=codex.id,
        pair_diff=None,
        context_snapshot={"paper": {}},
    )
    refreshed = []

    class Query:
        def filter(self, *_args):
            return self

        def first(self):
            return pi

    class Database:
        flushed = False

        def flush(self):
            self.flushed = True

        def query(self, _model):
            assert self.flushed, "pending terminal states must flush first"
            return Query()

        def refresh(self, row, *, with_for_update):
            # A concurrent Pi completion committed while this one waited.
            refreshed.append(with_for_update)
            row.status = "completed"

    CodexPaperJobService._record_pair_diff(Database(), codex)

    assert refreshed == [True]
    assert pi.pair_diff["enrich"]["task_ids"]["codex_only"] == [1]


def test_production_pi_image_pins_the_current_runner_pair():
    from deploy.configure_host_env import production_pi_shadow_values

    values = production_pi_shadow_values()
    runner_digest = hashlib.sha256(
        Path("jobs/run_paper_curation.py").read_bytes()
        + Path("jobs/run_pi_curation.py").read_bytes()
    ).hexdigest()

    assert re.fullmatch(
        rf".+:pi-runner-{runner_digest[:12]}@sha256:[0-9a-f]{{64}}",
        values["PWC_CURATION_PI_JOBS_IMAGE"],
    )
    assert float(values["PWC_CURATION_PI_SHADOW_SAMPLE_RATE"]) == 0.2
    assert "PWC_CURATION_PI_HF_TOKEN" not in values


def test_pi_shadow_row_inserts_beside_its_running_codex_stage():
    """The table's trigger check and one-active-stage index admit the pair."""
    from sqlalchemy import create_engine  # noqa: PLC0415
    from sqlalchemy.dialects.postgresql import JSONB  # noqa: PLC0415
    from sqlalchemy.ext.compiler import compiles  # noqa: PLC0415
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from backend.models.database import PaperCurationJob  # noqa: PLC0415

    @compiles(JSONB, "sqlite")
    def _jsonb_as_json(_element, _compiler, **_kw):
        return "JSON"

    engine = create_engine("sqlite:///:memory:")
    PaperCurationJob.__table__.create(engine)
    stage = {
        "kind": "add-evals",
        "paper_id": 42,
        "policy_version": "hf-daily-v1",
        "requested_by": "hf-daily-cron",
    }
    with Session(engine) as db:
        codex = PaperCurationJob(
            id=uuid.uuid4(), trigger="hf-daily-cron", status="running", **stage
        )
        db.add(codex)
        db.flush()
        db.add(
            PaperCurationJob(
                id=uuid.uuid4(),
                trigger=PI_SHADOW_TRIGGER,
                status="queued",
                runner="pi",
                paired_job_id=codex.id,
                **stage,
            )
        )
        db.flush()
        assert db.query(PaperCurationJob).count() == 2
