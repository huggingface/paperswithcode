import json
import os
import subprocess
import threading
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hashlib import sha256

import pytest
import httpx
from sqlalchemy import create_engine, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.database import (
    AutonomousBudgetReservation,
    AutonomousExecutionIntent,
    AutonomousRun,
)
from backend.cli import build_parser
from backend.services.autonomous_capabilities import (
    CAPABILITY_MANIFESTS,
    Capability,
    ResourceKind,
)
from backend.services.autonomous_budget_gateway import (
    AutonomousBudgetGateway,
    GatewayConfigurationError,
)
from backend.services.autonomous_codex_runner import (
    AutonomousCodexRunner,
    CodexRequest,
    ExecutionCancelled,
    ExecutionBudgetExceeded,
    ExecutionOutcome,
    EvidenceRef,
    ModelPricing,
    OutputLimitExceeded,
    SubprocessCodexExecutor,
    SubprocessCredentialBroker,
    VerifiedCredentialReservation,
    codex_result_schema,
)
from backend.services.autonomous_operations_repository import Operator, RunContext
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    BudgetReservationUnavailable,
)
from backend.services.autonomous_prompt_builder import build_codex_envelope
from backend.services.autonomous_digest_service import BudgetDecision, BudgetLimits


NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)
REAL_BROKER_RESERVE = SubprocessCredentialBroker.reserve
REAL_BROKER_RELEASE = SubprocessCredentialBroker.release


def runner_env(**values):
    return {
        "PWC_AUTONOMOUS_CODEX_API_KEY": "dedicated-key",
        "PWC_AUTONOMOUS_CODEX_EXECUTABLE": "/opt/pwc/bin/codex",
        "PWC_AUTONOMOUS_CODEX_BWRAP_EXECUTABLE": "/usr/bin/bwrap",
        "PWC_AUTONOMOUS_CODEX_UPSTREAM_BASE_URL": "https://api.openai.com/v1",
        "PWC_AUTONOMOUS_CODEX_UPSTREAM_HOST_ALLOWLIST": "api.openai.com",
        "PWC_AUTONOMOUS_CODEX_PRICING_REVISION": "pricing-2026-08-28",
        "PWC_AUTONOMOUS_CODEX_LUNA_INPUT_USD_PER_MILLION": "1",
        "PWC_AUTONOMOUS_CODEX_LUNA_CACHED_INPUT_USD_PER_MILLION": "0.1",
        "PWC_AUTONOMOUS_CODEX_LUNA_OUTPUT_USD_PER_MILLION": "2",
        "PWC_AUTONOMOUS_CODEX_TERRA_INPUT_USD_PER_MILLION": "3",
        "PWC_AUTONOMOUS_CODEX_TERRA_CACHED_INPUT_USD_PER_MILLION": "0.3",
        "PWC_AUTONOMOUS_CODEX_TERRA_OUTPUT_USD_PER_MILLION": "6",
        **values,
    }


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    AutonomousRun.__table__.create(engine)
    AutonomousExecutionIntent.__table__.create(engine)
    AutonomousBudgetReservation.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture(autouse=True)
def provider_reservation(monkeypatch):
    monkeypatch.setattr(
        AutonomousOperationsRepository,
        "_database_now",
        staticmethod(lambda _db: NOW),
    )

    def reserve(_broker, value, existing_reservation_id, attestation_context):
        reservation_id = existing_reservation_id or f"run:{value.context.run_id.hex}"
        return VerifiedCredentialReservation(
            api_key="provider-capped-key",
            reservation_id=reservation_id,
            run_id=value.context.run_id,
            provider="openai",
            model_alias=value.model_alias,
            concrete_model=attestation_context.concrete_model,
            reasoning_effort=attestation_context.reasoning_effort,
            limit_usd=value.budget_usd,
            expires_at=NOW + timedelta(hours=3),
            attestation_digest="d" * 64,
            operator=value.context.operator.value,
            manifest_revision=value.context.manifest_revision,
            request_digest=attestation_context.request_digest,
            evidence_digest=attestation_context.evidence_digest,
            pricing_policy_digest=attestation_context.pricing_policy_digest,
            api_base_url=attestation_context.api_base_url,
            credential_scope="responses",
        )

    monkeypatch.setattr(SubprocessCredentialBroker, "reserve", reserve)
    monkeypatch.setattr(
        SubprocessCredentialBroker,
        "release",
        lambda _broker, reservation, usage: min(usage.cost_usd, reservation.limit_usd),
    )


def request(
    *,
    budget: Decimal = Decimal("0.50"),
    operator: Operator = Operator.SUBMISSIONS,
) -> CodexRequest:
    context = RunContext(uuid.uuid4(), operator, False, "manifest-v1")
    identifier = "paper:42"
    evidence_kind = "catalog"
    if operator == Operator.CHAT_RELIABILITY:
        identifier = f"trace:{'b' * 64}"
        evidence_kind = "trace"
    capabilities = tuple(sorted(CAPABILITY_MANIFESTS[operator], key=str))
    return CodexRequest(
        context=context,
        evidence=(EvidenceRef(evidence_kind, identifier, "a" * 64),),
        capabilities=capabilities,
        output_schema=codex_result_schema(capabilities),
        budget_usd=budget,
    )


def completed_output() -> str:
    return json.dumps(
        {
            "status": "completed",
            "proposed_actions": [
                {
                    "capability": Capability.REVIEW_SUBMISSION.value,
                    "resource": {
                        "kind": ResourceKind.PENDING_EDIT.value,
                        "identifier": "7",
                        "exists": True,
                    },
                    "reason_code": "primary_evidence",
                }
            ],
        }
    )


class RecordingExecutor:
    def __init__(self, outcome=None, error=None):
        self.outcome = outcome or ExecutionOutcome(
            returncode=0,
            final_message=completed_output(),
            events_jsonl=(
                '{"type":"turn.completed","usage":{"input_tokens":12,'
                '"cached_input_tokens":2,"output_tokens":4}}\n'
            ),
        )
        self.error = error
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.outcome


def test_envelope_is_deterministic_closed_and_content_free():
    value = request()
    first = build_codex_envelope(value)
    second = build_codex_envelope(value)

    assert first == second
    decoded = json.loads(first)
    assert decoded["run"]["operator"] == "submissions"
    assert decoded["allowed_capabilities"] == sorted(
        capability.value for capability in value.capabilities
    )
    assert "create_task" not in first
    assert decoded["explicit_exclusions"]
    assert decoded["budget_usd"] == "0.50"
    assert decoded["evidence"] == [
        {"kind": "catalog", "identifier": "paper:42", "digest": "a" * 64}
    ]


def test_runner_uses_server_model_sanitized_env_and_argument_array(db):
    executor = RecordingExecutor()
    runner = AutonomousCodexRunner(
        executor=executor,
        environ=runner_env(
            PATH="/untrusted/bin",
            DATABASE_URL="postgresql://secret",
            HF_TOKEN="hf_secret",
        ),
        now=lambda: NOW,
    )

    result = runner.run(request(), db=db)

    assert result.status == "completed"
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 4
    assert result.usage.cost_usd == Decimal("0.0000182")
    call = executor.calls[0]
    assert isinstance(call["command"], list)
    assert call["command"][0:2] == ["/opt/pwc/bin/codex", "exec"]
    assert call["command"][call["command"].index("--model") + 1] == "gpt-6-luna"
    assert 'model_reasoning_effort="medium"' in call["command"]
    assert "shell_environment_policy.inherit=none" in call["command"]
    assert "--skip-git-repo-check" in call["command"]
    assert call["environment"]["OPENAI_API_KEY"] != "provider-capped-key"
    assert call["environment"]["OPENAI_BASE_URL"].startswith("http://127.0.0.1:")
    assert "provider-capped-key" not in json.dumps(call["environment"])
    assert "DATABASE_URL" not in call["environment"]
    assert "HF_TOKEN" not in call["environment"]
    assert call["shell"] is False
    assert call["filesystem_isolation"] is True
    assert call["sandbox_executable"] == "/usr/bin/bwrap"
    assert call["cwd"] == Path("/")
    assert "--cd" in call["command"]
    assert call["command"][call["command"].index("--cd") + 1] == "/workspace"

    row = db.get(AutonomousRun, result.run_id)
    assert row.exit_classification == "completed"
    assert row.input_tokens == 12
    assert row.evidence_digests == ["a" * 64]
    assert row.pricing_revision == "pricing-2026-08-28"
    assert len(row.pricing_policy_digest) == 64
    assert row.pricing_policy_digest != "0" * 64
    assert row.capability_requests == [
        {
            "capability": "review_submission",
            "resource_kind": "pending_edit",
            "resource_identifier": "7",
            "resource_exists": True,
            "reason_code": "primary_evidence",
        }
    ]


@pytest.mark.parametrize(
    ("error", "classification"),
    [
        (subprocess.TimeoutExpired(["codex"], 3), "timeout"),
        (RuntimeError("output_limit"), "output_limit"),
    ],
)
def test_timeout_and_output_limit_fail_without_leaking_error(db, error, classification):
    runner = AutonomousCodexRunner(
        executor=RecordingExecutor(error=error),
        environ=runner_env(),
        now=lambda: NOW,
    )
    result = runner.run(request(), db=db)
    assert result.status == "failed"
    assert result.exit_classification == classification
    assert result.proposed_actions == ()


def test_cancellation_is_persisted_without_starting_codex(db):
    executor = RecordingExecutor()
    runner = AutonomousCodexRunner(
        executor=executor,
        environ=runner_env(),
        now=lambda: NOW,
    )
    result = runner.run(request(), db=db, cancellation_requested=lambda: True)
    assert result.status == "cancelled"
    assert result.exit_classification == "cancelled"
    assert executor.calls == []


def test_budget_exhaustion_discards_proposed_mutations(db):
    runner = AutonomousCodexRunner(
        executor=RecordingExecutor(),
        environ=runner_env(),
        now=lambda: NOW,
    )
    result = runner.run(request(budget=Decimal("0.000001")), db=db)
    assert result.status == "budget_exhausted"
    assert result.proposed_actions == ()
    assert db.get(AutonomousRun, result.run_id).capability_requests == []


def test_cumulative_budget_gate_stops_before_credentials_or_executor(db):
    executor = RecordingExecutor()

    class ExhaustedBudget:
        limits = BudgetLimits(
            Decimal("1"), 1000, Decimal("2"), 2000, Decimal("3"), 3000
        )

        def enforce_before_run(self, _db, **_kwargs):
            return BudgetDecision(
                False,
                "daily_cost_limit",
                True,
                Decimal("2"),
                Decimal("2"),
                1000,
                1000,
            )

    result = AutonomousCodexRunner(
        executor=executor,
        environ=runner_env(),
        now=lambda: NOW,
        cumulative_budget_service=ExhaustedBudget(),
    ).run(request(), db=db)

    assert result.status == "budget_exhausted"
    assert executor.calls == []


def test_provider_reservation_is_durable_before_executor_and_content_free(db):
    value = request()

    class InspectingExecutor(RecordingExecutor):
        def __call__(self, **kwargs):
            intent = db.get(AutonomousExecutionIntent, value.context.run_id)
            row = db.get(AutonomousBudgetReservation, value.context.run_id)
            assert intent is not None
            assert intent.request_digest == AutonomousCodexRunner._request_digest(value)
            assert row is not None
            assert row.limit_usd == value.budget_usd
            assert row.state == "claimed"
            assert "provider-capped-key" not in json.dumps(
                {
                    column.name: getattr(row, column.name)
                    for column in row.__table__.columns
                },
                default=str,
            )
            return super().__call__(**kwargs)

    result = AutonomousCodexRunner(
        executor=InspectingExecutor(), environ=runner_env(), now=lambda: NOW
    ).run(value, db=db)
    row = db.get(AutonomousBudgetReservation, value.context.run_id)
    assert result.status == "completed"
    assert row.released_at.replace(tzinfo=UTC) == NOW
    assert row.state == "released"
    assert row.attestation_digest == "d" * 64
    assert row.request_digest == AutonomousCodexRunner._request_digest(value)
    assert row.credential_scope == "responses"


def test_gateway_start_failure_releases_and_settles_durable_reservation(
    db, monkeypatch
):
    releases = []

    monkeypatch.setattr(
        AutonomousBudgetGateway,
        "create",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("bind failed")),
    )
    monkeypatch.setattr(
        SubprocessCredentialBroker,
        "release",
        lambda _broker, reservation, usage: releases.append(
            (reservation.reservation_id, usage)
        )
        or Decimal("0"),
    )

    value = request()
    result = AutonomousCodexRunner(
        executor=RecordingExecutor(), environ=runner_env(), now=lambda: NOW
    ).run(value, db=db)

    reservation = db.get(AutonomousBudgetReservation, value.context.run_id)
    assert result.exit_classification == "credential_missing"
    assert len(releases) == 1
    assert reservation.state == "released"
    assert reservation.reconciliation_required is False
    assert reservation.released_at.replace(tzinfo=UTC) == NOW


def test_database_rejects_impossible_budget_lifecycle_state(db):
    value = request()
    AutonomousCodexRunner(
        executor=RecordingExecutor(), environ=runner_env(), now=lambda: NOW
    ).run(value, db=db)

    with pytest.raises(IntegrityError):
        db.execute(
            update(AutonomousBudgetReservation)
            .where(AutonomousBudgetReservation.run_id == value.context.run_id)
            .values(cost_upper_bound_usd=value.budget_usd + Decimal("1"))
        )
        db.flush()
    db.rollback()


def test_signed_subprocess_broker_contract_is_verified_and_released(db, tmp_path):
    broker_script = tmp_path / "broker.py"
    broker_script.write_text(
        "#!/usr/bin/env python3\n"
        "import hashlib, hmac, json, sys\n"
        "from datetime import datetime, timedelta, timezone\n"
        "args = dict(zip(sys.argv[2::2], sys.argv[3::2]))\n"
        "if sys.argv[1] == 'release':\n"
        "    print(json.dumps({'cost_usd': '0.000017'}))\n"
        "else:\n"
        "    run_id = args['--run-id']\n"
        "    payload = {\n"
        f"      'expires_at': '{(NOW + timedelta(hours=3)).isoformat()}',\n"
        "      'limit_usd': args['--limit-usd'], 'model_alias': args['--model-alias'],\n"
        "      'concrete_model': args['--concrete-model'],\n"
        "      'reasoning_effort': args['--reasoning-effort'],\n"
        "      'provider': 'openai', 'reservation_id': 'run:' + run_id.replace('-', ''),\n"
        "      'run_id': run_id, 'operator': args['--operator'],\n"
        "      'manifest_revision': args['--manifest-revision'],\n"
        "      'request_digest': args['--request-digest'],\n"
        "      'evidence_digest': args['--evidence-digest'],\n"
        "      'pricing_policy_digest': args['--pricing-policy-digest'],\n"
        "      'api_base_url': args['--api-base-url'],\n"
        "      'credential_scope': args['--credential-scope']}\n"
        "    payload['credential_digest'] = hashlib.sha256(b'short-lived-provider-key').hexdigest()\n"
        "    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))\n"
        "    payload['attestation'] = hmac.new(b'v' * 32, canonical.encode(), hashlib.sha256).hexdigest()\n"
        "    payload['api_key'] = 'short-lived-provider-key'\n"
        "    print(json.dumps(payload))\n",
        encoding="utf-8",
    )
    os.chmod(broker_script, 0o700)

    class ActualBroker:
        def __init__(self, environ):
            self.delegate = SubprocessCredentialBroker(environ=environ, now=lambda: NOW)

        def reserve(self, value, existing, attestation_context):
            return REAL_BROKER_RESERVE(
                self.delegate, value, existing, attestation_context
            )

        def release(self, reservation, usage):
            return REAL_BROKER_RELEASE(self.delegate, reservation, usage)

    environ = runner_env(
        PWC_AUTONOMOUS_CODEX_CREDENTIAL_BROKER=str(broker_script),
        PWC_AUTONOMOUS_CODEX_RESERVATION_VERIFY_KEY="v" * 32,
        PWC_AUTONOMOUS_CODEX_BROKER_TOKEN="broker-token",
    )
    value = request()
    result = AutonomousCodexRunner(
        executor=RecordingExecutor(),
        environ=environ,
        credential_broker=ActualBroker(environ),
        now=lambda: NOW,
    ).run(value, db=db)
    row = db.get(AutonomousBudgetReservation, value.context.run_id)
    assert result.status == "completed"
    assert result.usage.cost_usd == Decimal("0.000017")
    assert row.released_at is not None
    assert "short-lived-provider-key" not in json.dumps(row.__dict__, default=str)


@pytest.mark.parametrize(
    "change",
    [
        {"limit_usd": Decimal("0.51")},
        {"run_id": uuid.UUID(int=0)},
        {"model_alias": "independent_review"},
        {"concrete_model": "unreserved-model"},
        {"reasoning_effort": "high"},
        {"expires_at": NOW + timedelta(minutes=1)},
        {"attestation_digest": "bad"},
        {"api_key": ""},
    ],
)
def test_invalid_provider_reservation_never_invokes_executor(db, change):
    value = request()
    executor = RecordingExecutor()

    class InvalidBroker:
        def reserve(self, _request, _existing, attestation_context):
            valid = VerifiedCredentialReservation(
                api_key="capped",
                reservation_id=f"run:{value.context.run_id.hex}",
                run_id=value.context.run_id,
                provider="openai",
                model_alias="diagnosis",
                concrete_model=attestation_context.concrete_model,
                reasoning_effort=attestation_context.reasoning_effort,
                limit_usd=value.budget_usd,
                expires_at=NOW + timedelta(hours=3),
                attestation_digest="d" * 64,
                operator=value.context.operator.value,
                manifest_revision=value.context.manifest_revision,
                request_digest=attestation_context.request_digest,
                evidence_digest=attestation_context.evidence_digest,
                pricing_policy_digest=attestation_context.pricing_policy_digest,
                api_base_url=attestation_context.api_base_url,
                credential_scope="responses",
            )
            return replace(valid, **change)

        def release(self, _reservation, _usage):
            raise AssertionError("invalid reservations are never released")

    result = AutonomousCodexRunner(
        executor=executor,
        environ=runner_env(),
        credential_broker=InvalidBroker(),
        now=lambda: NOW,
    ).run(value, db=db)
    assert result.exit_classification == "credential_missing"
    assert executor.calls == []


def test_live_budget_claim_prevents_second_model_execution(db):
    value = request()
    repository = AutonomousOperationsRepository(clock=lambda _db: NOW)
    repository.claim_budget_reservation(
        db,
        context=value.context,
        reservation_id=f"run:{value.context.run_id.hex}",
        provider="openai",
        model_alias=value.model_alias,
        limit_usd=value.budget_usd,
        attestation_digest="d" * 64,
        request_digest=AutonomousCodexRunner._request_digest(value),
        endpoint_digest=sha256(
            runner_env()["PWC_AUTONOMOUS_CODEX_UPSTREAM_BASE_URL"].encode()
        ).hexdigest(),
        credential_scope="responses",
        expires_at=NOW + timedelta(hours=3),
        claim_ttl=timedelta(minutes=30),
    )
    db.commit()
    executor = RecordingExecutor()
    with pytest.raises(BudgetReservationUnavailable):
        AutonomousCodexRunner(
            executor=executor,
            environ=runner_env(),
            repository=repository,
            now=lambda: NOW,
        ).run(value, db=db)
    assert executor.calls == []


def test_expired_crash_intent_is_finalized_without_second_model_run(db):
    value = request()
    clock = [NOW]
    repository = AutonomousOperationsRepository(clock=lambda _db: clock[0])
    configured_runner = AutonomousCodexRunner(
        executor=RecordingExecutor(error=AssertionError("must not execute")),
        environ=runner_env(),
        repository=repository,
        now=lambda: clock[0],
    )
    pricing = configured_runner._pricing(value.model_alias)
    request_digest = configured_runner._request_digest(value)
    repository.record_execution_intent(
        db,
        context=value.context,
        request_digest=request_digest,
        evidence_digests=["a" * 64],
        model_alias=value.model_alias,
        budget_usd=value.budget_usd,
        pricing_policy_digest=pricing.policy_digest,
        now=NOW,
    )
    repository.claim_budget_reservation(
        db,
        context=value.context,
        reservation_id=f"run:{value.context.run_id.hex}",
        provider="openai",
        model_alias=value.model_alias,
        limit_usd=value.budget_usd,
        attestation_digest="d" * 64,
        request_digest=request_digest,
        endpoint_digest=sha256(
            runner_env()["PWC_AUTONOMOUS_CODEX_UPSTREAM_BASE_URL"].encode()
        ).hexdigest(),
        credential_scope="responses",
        expires_at=NOW + timedelta(hours=3),
        claim_ttl=timedelta(minutes=1),
    )
    db.commit()
    clock[0] = NOW + timedelta(minutes=2)

    result = configured_runner.run(value, db=db)

    reservation = db.get(AutonomousBudgetReservation, value.context.run_id)
    assert result.exit_classification == "interrupted"
    assert reservation.state == "unknown"
    assert reservation.reconciliation_required is True


def test_crash_before_local_claim_reconciles_idempotent_provider_reservation(db):
    value = request()
    releases = []

    class MustNotReserveAgain:
        limits = BudgetLimits(
            Decimal("1"), 1000, Decimal("2"), 2000, Decimal("3"), 3000
        )

        def enforce_before_run(self, _db, **_kwargs):
            raise AssertionError("durable intent already reserved cumulative budget")

    runner = AutonomousCodexRunner(
        executor=RecordingExecutor(error=AssertionError("must not execute")),
        environ=runner_env(),
        now=lambda: NOW,
        cumulative_budget_service=MustNotReserveAgain(),
    )
    pricing = runner._pricing(value.model_alias)
    runner.repository.record_execution_intent(
        db,
        context=value.context,
        request_digest=runner._request_digest(value),
        evidence_digests=["a" * 64],
        model_alias=value.model_alias,
        budget_usd=value.budget_usd,
        pricing_policy_digest=pricing.policy_digest,
        now=NOW,
    )
    db.commit()
    runner.credential_broker.release = lambda reservation, usage: releases.append(
        (reservation.reservation_id, usage)
    ) or Decimal("0")

    result = runner.run(value, db=db)

    reservation = db.get(AutonomousBudgetReservation, value.context.run_id)
    assert result.exit_classification == "interrupted"
    assert releases[0][0] == f"run:{value.context.run_id.hex}"
    assert reservation.state == "released"


def test_credential_revocation_failure_is_persisted_and_discards_actions(db):
    value = request()

    class RevokeFailureBroker:
        def reserve(self, _request, _existing, attestation_context):
            return VerifiedCredentialReservation(
                api_key="capped",
                reservation_id=f"run:{value.context.run_id.hex}",
                run_id=value.context.run_id,
                provider="openai",
                model_alias=value.model_alias,
                concrete_model=attestation_context.concrete_model,
                reasoning_effort=attestation_context.reasoning_effort,
                limit_usd=value.budget_usd,
                expires_at=NOW + timedelta(hours=3),
                attestation_digest="d" * 64,
                operator=value.context.operator.value,
                manifest_revision=value.context.manifest_revision,
                request_digest=attestation_context.request_digest,
                evidence_digest=attestation_context.evidence_digest,
                pricing_policy_digest=attestation_context.pricing_policy_digest,
                api_base_url=attestation_context.api_base_url,
                credential_scope="responses",
            )

        def release(self, _reservation, _usage):
            raise RuntimeError("provider unavailable")

    result = AutonomousCodexRunner(
        executor=RecordingExecutor(),
        environ=runner_env(),
        credential_broker=RevokeFailureBroker(),
        now=lambda: NOW,
    ).run(value, db=db)
    assert result.status == "failed"
    assert result.exit_classification == "credential_revoke_failed"
    assert result.proposed_actions == ()
    reservation = db.get(AutonomousBudgetReservation, value.context.run_id)
    assert reservation.state == "release_failed"
    assert reservation.reconciliation_required is True
    assert reservation.authoritative_cost_usd == Decimal("0")
    assert reservation.cost_upper_bound_usd > 0


def test_malformed_output_and_secret_text_are_reduced_to_classification(db):
    secret = "sk-never-persist-this-value"
    executor = RecordingExecutor(
        outcome=ExecutionOutcome(
            returncode=0,
            final_message=f"not-json {secret}",
            events_jsonl="",
        )
    )
    runner = AutonomousCodexRunner(
        executor=executor,
        environ=runner_env(),
        now=lambda: NOW,
    )
    result = runner.run(request(), db=db)
    assert result.status == "failed"
    assert result.exit_classification == "malformed_output"
    row = db.get(AutonomousRun, result.run_id)
    assert secret not in json.dumps(row.capability_requests)
    assert secret not in (row.result_digest or "")


def test_existing_run_resumes_without_second_model_call(db):
    value = request()
    first_executor = RecordingExecutor()
    first = AutonomousCodexRunner(
        executor=first_executor,
        environ=runner_env(),
        now=lambda: NOW,
    ).run(value, db=db)
    assert first.proposed_actions, first
    db.commit()
    second_executor = RecordingExecutor(error=AssertionError("must not execute"))
    resumed = AutonomousCodexRunner(
        executor=second_executor,
        environ={},
        now=lambda: NOW,
    ).run(value, db=db)

    assert resumed == first
    assert second_executor.calls == []

    with pytest.raises(ValueError, match="digest mismatch"):
        AutonomousCodexRunner(
            executor=second_executor,
            environ={},
            now=lambda: NOW,
        ).run(replace(value, budget_usd=Decimal("0.40")), db=db)


def test_structured_submission_run_resumes_with_exact_attested_decision(db):
    capabilities = (Capability.REVIEW_SUBMISSION,)
    value = CodexRequest(
        context=RunContext(uuid.uuid4(), Operator.SUBMISSIONS, False, "review-v1"),
        evidence=(EvidenceRef("submission_snapshot", "7", "a" * 64),),
        capabilities=capabilities,
        output_schema=codex_result_schema(capabilities, structured_submission=True),
        budget_usd=Decimal("0.50"),
        evidence_payload={"submissions": [{"id": 7}]},
    )
    output = json.dumps(
        {
            "status": "completed",
            "proposed_actions": [
                {
                    "capability": "review_submission",
                    "resource": {
                        "kind": "pending_edit",
                        "identifier": "7",
                        "exists": True,
                    },
                    "reason_code": "approve",
                    "rationale": "The immutable identifiers resolve.",
                    "evidence": ["submission_snapshot"],
                    "confidence": 0.97,
                    "resolved_payload": {"task_ids": [3]},
                }
            ],
        }
    )
    first = AutonomousCodexRunner(
        executor=RecordingExecutor(
            outcome=ExecutionOutcome(
                0,
                output,
                '{"usage":{"input_tokens":12,"output_tokens":4}}\n',
            )
        ),
        environ=runner_env(),
        now=lambda: NOW,
    ).run(value, db=db)
    assert first.proposed_actions, first
    db.commit()

    no_second_call = RecordingExecutor(error=AssertionError("must resume"))
    resumed = AutonomousCodexRunner(
        executor=no_second_call,
        environ={},
        now=lambda: NOW,
    ).run(value, db=db)

    assert resumed == first
    assert resumed.proposed_actions[0].rationale == (
        "The immutable identifiers resolve."
    )
    assert resumed.proposed_actions[0].resolved_payload == {"task_ids": [3]}
    assert no_second_call.calls == []


def test_forged_capability_or_resource_is_rejected(db):
    output = json.loads(completed_output())
    output["proposed_actions"][0]["capability"] = "create_task"
    runner = AutonomousCodexRunner(
        executor=RecordingExecutor(outcome=ExecutionOutcome(0, json.dumps(output), "")),
        environ=runner_env(),
        now=lambda: NOW,
    )
    result = runner.run(request(), db=db)
    assert result.status == "failed"
    assert result.exit_classification == "malformed_output"


def test_missing_provider_reservation_fails_without_executor(db):
    executor = RecordingExecutor()

    class UnavailableBroker:
        def reserve(self, _request, _existing, _attestation_context):
            raise RuntimeError("broker unavailable")

        def release(self, _reservation, _usage):
            raise AssertionError("missing reservations are never released")

    result = AutonomousCodexRunner(
        executor=executor,
        environ=runner_env(OPENAI_API_KEY="interactive-key-must-not-be-used"),
        credential_broker=UnavailableBroker(),
        now=lambda: NOW,
    ).run(request(), db=db)
    assert result.exit_classification == "credential_missing"
    assert executor.calls == []


def test_missing_codex_binary_is_persisted_as_process_error(db):
    result = AutonomousCodexRunner(
        executor=RecordingExecutor(error=FileNotFoundError("codex")),
        environ=runner_env(),
        now=lambda: NOW,
    ).run(request(), db=db)
    assert result.exit_classification == "process_error"


def test_cost_is_derived_from_versioned_server_pricing(db):
    outcome = ExecutionOutcome(
        0,
        completed_output(),
        '{"usage":{"input_tokens":12,"output_tokens":4}}\n',
    )
    result = AutonomousCodexRunner(
        executor=RecordingExecutor(outcome=outcome),
        environ=runner_env(),
        now=lambda: NOW,
    ).run(request(), db=db)
    assert result.exit_classification == "completed"
    assert result.usage.cost_usd == Decimal("0.000020")


def test_missing_or_nonfinite_pricing_fails_closed_before_executor(db):
    executor = RecordingExecutor()
    for environ in (
        {"PWC_AUTONOMOUS_CODEX_API_KEY": "dedicated-key"},
        runner_env(PWC_AUTONOMOUS_CODEX_LUNA_INPUT_USD_PER_MILLION="Infinity"),
    ):
        result = AutonomousCodexRunner(
            executor=executor, environ=environ, now=lambda: NOW
        ).run(request(), db=db)
        assert result.exit_classification == "configuration_missing"
        db.rollback()
    assert executor.calls == []


def test_malformed_scalar_and_nonfinite_usage_fail_closed(db):
    for events in (
        '{"item":7}\n',
        '{"usage":{"input_tokens":12,"output_tokens":4,"cached_input_tokens":0}}\n'
        '{"usage":{"input_tokens":12,"output_tokens":4,"cached_input_tokens":Infinity}}\n',
    ):
        result = AutonomousCodexRunner(
            executor=RecordingExecutor(
                outcome=ExecutionOutcome(0, completed_output(), events)
            ),
            environ=runner_env(),
            now=lambda: NOW,
        ).run(request(), db=db)
        assert result.exit_classification == "malformed_output"
        db.rollback()


def test_chat_request_requires_opaque_evidence_identifiers():
    value = request(operator=Operator.CHAT_RELIABILITY)
    with pytest.raises(ValueError, match="request"):
        replace(value, evidence=(EvidenceRef("trace", "chat:user-text", "a" * 64),))
    accepted = replace(
        value,
        evidence=(EvidenceRef("trace", f"trace:{'b' * 64}", "a" * 64),),
    )
    assert accepted.evidence[0].identifier.startswith("trace:")


def test_chat_model_output_cannot_encode_user_content_in_resource(db):
    value = request(operator=Operator.CHAT_RELIABILITY)
    output = {
        "status": "completed",
        "proposed_actions": [
            {
                "capability": "switch_chat_provider",
                "resource": {
                    "kind": "chat_provider",
                    "identifier": "user-message-fragment",
                    "exists": True,
                },
                "reason_code": "provider_unhealthy",
            }
        ],
    }
    result = AutonomousCodexRunner(
        executor=RecordingExecutor(
            outcome=ExecutionOutcome(
                0,
                json.dumps(output),
                '{"usage":{"input_tokens":12,"output_tokens":4}}\n',
            )
        ),
        environ=runner_env(),
        now=lambda: NOW,
    ).run(value, db=db)
    assert result.exit_classification == "malformed_output"


def test_schema_and_cli_are_closed_to_server_capabilities():
    capabilities = tuple(sorted(CAPABILITY_MANIFESTS[Operator.CRON_HEALTH], key=str))
    schema = codex_result_schema(capabilities)
    encoded = json.dumps(schema)
    assert "retry_declared_cron" in encoded
    assert "review_submission" not in encoded
    variants = schema["properties"]["proposed_actions"]["items"]["anyOf"]
    assert all(len(variant["properties"]["capability"]) == 1 for variant in variants)

    chat_capabilities = tuple(
        sorted(CAPABILITY_MANIFESTS[Operator.CHAT_RELIABILITY], key=str)
    )
    chat_schema = json.dumps(codex_result_schema(chat_capabilities))
    assert '"fallback"' in chat_schema
    assert '"chat"' in chat_schema

    args = build_parser().parse_args(["autonomous", "run", "cron_health", "--dry-run"])
    assert args.operator == "cron_health"
    assert args.dry_run is True

    with pytest.raises(ValueError, match="request"):
        replace(request(), model_alias="independent_review")
    with pytest.raises(ValueError, match="schema"):
        replace(
            request(),
            output_schema={"type": "object", "description": "chat user content"},
        )


def test_evidence_reference_rejects_secret_like_identifiers():
    with pytest.raises(ValueError, match="evidence"):
        EvidenceRef("trace", "sk-sensitive", "a" * 64)
    with pytest.raises(ValueError, match="request"):
        replace(request(), budget_usd=Decimal("NaN"))


def test_subprocess_executor_enforces_output_bound(tmp_path):
    script = tmp_path / "emit.py"
    script.write_text(
        "#!/usr/bin/env python3\nimport sys\nsys.stdout.write('x' * 5000)\n",
        encoding="utf-8",
    )
    os.chmod(script, 0o700)
    with pytest.raises(OutputLimitExceeded):
        SubprocessCodexExecutor()(
            command=[str(script)],
            environment={"PATH": os.environ["PATH"]},
            cwd=tmp_path,
            input_text="{}",
            output_schema={"type": "object"},
            timeout_seconds=30,
            max_output_bytes=100,
            cancellation_requested=lambda: False,
            budget_exceeded=lambda _: False,
            filesystem_isolation=False,
            sandbox_executable="/usr/bin/bwrap",
            shell=False,
        )


def test_subprocess_executor_hides_host_workspace_with_bubblewrap(tmp_path):
    script = tmp_path / "inspect.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "print('isolated=' + str(Path('/workspace').exists()))\n"
        "print('repo=' + str(Path('/root/.codex/worktrees').exists()))\n"
        "print('proc=' + str(Path('/proc/self/environ').exists()))\n",
        encoding="utf-8",
    )
    os.chmod(script, 0o700)
    outcome = SubprocessCodexExecutor()(
        command=[str(script)],
        environment={"PATH": os.environ["PATH"], "OPENAI_API_KEY": "must-stay-hidden"},
        cwd=Path("/"),
        input_text="{}",
        output_schema={"type": "object"},
        timeout_seconds=30,
        max_output_bytes=1000,
        cancellation_requested=lambda: False,
        budget_exceeded=lambda _: False,
        filesystem_isolation=True,
        sandbox_executable="/usr/bin/bwrap",
        shell=False,
    )
    assert "isolated=True" in outcome.events_jsonl
    assert "repo=False" in outcome.events_jsonl
    assert "proc=False" in outcome.events_jsonl
    assert "must-stay-hidden" not in outcome.events_jsonl


def test_source_repair_mounts_only_declared_files_writable(tmp_path):
    workspace = tmp_path / "candidate"
    allowed = workspace / "backend" / "job.py"
    blocked = workspace / "backend" / "other.py"
    allowed.parent.mkdir(parents=True)
    allowed.write_text("old\n")
    blocked.write_text("keep\n")
    script = tmp_path / "edit.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "Path('/workspace/backend/job.py').write_text('new\\n')\n"
        "try:\n"
        " Path('/workspace/backend/other.py').write_text('bad\\n')\n"
        "except OSError:\n"
        " print('blocked=True')\n",
        encoding="utf-8",
    )
    os.chmod(script, 0o700)
    outcome = SubprocessCodexExecutor()(
        command=[str(script)],
        environment={"PATH": os.environ["PATH"]},
        cwd=Path("/"),
        input_text="{}",
        output_schema={"type": "object"},
        timeout_seconds=30,
        max_output_bytes=1000,
        cancellation_requested=lambda: False,
        budget_exceeded=lambda _: False,
        filesystem_isolation=True,
        sandbox_executable="/usr/bin/bwrap",
        shell=False,
        workspace_path=workspace,
        writable_paths=("backend/job.py",),
    )
    assert "blocked=True" in outcome.events_jsonl
    assert allowed.read_text() == "new\n"
    assert blocked.read_text() == "keep\n"


def test_budget_gateway_caps_each_upstream_call_and_hides_upstream_key():
    received = []
    records = []

    class UpstreamHandler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            assert records and records[-1][1] > 0
            length = int(self.headers["Content-Length"])
            received.append(
                (self.headers["Authorization"], json.loads(self.rfile.read(length)))
            )
            body = json.dumps({"id": "response", "output": []}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *args):
            return

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    pricing = ModelPricing(
        "pricing-v1", "a" * 64, Decimal("1"), Decimal("0.1"), Decimal("2")
    )
    gateway = AutonomousBudgetGateway(
        upstream_base_url=f"http://127.0.0.1:{upstream.server_port}/v1",
        upstream_api_key="real-upstream-key",
        local_api_key="run-scoped-local-key",
        expected_model="fixed",
        expected_reasoning_effort="medium",
        budget_usd=Decimal("0.010"),
        pricing=pricing,
        usage_recorder=lambda usage, upper: records.append((usage, upper)),
        allow_insecure_upstream=True,
    )
    endpoint, local_key = gateway.start()
    try:
        first = httpx.post(
            f"{endpoint}/responses",
            headers={"Authorization": f"Bearer {local_key}"},
            json={
                "model": "fixed",
                "reasoning": {"effort": "medium"},
                "input": "bounded",
                "max_output_tokens": 2000,
            },
        )
        second = httpx.post(
            f"{endpoint}/responses",
            headers={"Authorization": f"Bearer {local_key}"},
            json={
                "model": "fixed",
                "reasoning": {"effort": "medium"},
                "input": "bounded",
                "max_output_tokens": 2000,
            },
        )
    finally:
        usage = gateway.close()
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=5)
    assert first.status_code == 200
    assert second.status_code == 429
    assert received[0][0] == "Bearer real-upstream-key"
    assert received[0][1]["max_output_tokens"] <= 2000
    assert local_key != "real-upstream-key"
    assert usage.cost_usd <= Decimal("0.010")
    assert records[0][1] > 0
    assert records[-1][0].cost_usd == usage.cost_usd


def test_budget_gateway_charges_successful_usage_once():
    gateway = AutonomousBudgetGateway(
        upstream_base_url="http://127.0.0.1:1/v1",
        upstream_api_key="real-upstream-key",
        local_api_key="run-scoped-local-key",
        expected_model="fixed",
        expected_reasoning_effort="medium",
        budget_usd=Decimal("1"),
        pricing=ModelPricing(
            "pricing-v1",
            "a" * 64,
            Decimal("1"),
            Decimal("0.1"),
            Decimal("2"),
        ),
        allow_insecure_upstream=True,
    )

    gateway._reserved = Decimal("0.01")
    gateway._settle(Decimal("0.01"), (100, 20, 4))

    usage = gateway.usage()
    assert usage.input_tokens == 100
    assert usage.output_tokens == 4
    assert usage.cost_usd == Decimal("0.000090")


@pytest.mark.parametrize(
    "override",
    [
        {"model": "unreserved-model"},
        {"previous_response_id": "resp_remote"},
        {"background": True},
        {"service_tier": "priority"},
        {"tools": [{"type": "web_search"}]},
        {"input": [{"type": "input_file", "file_id": "file_remote"}]},
        {"reasoning": {"effort": "high"}},
        {"conversation": "conv_remote"},
        {"prompt": {"id": "pmpt_remote"}},
        {"input": [{"type": "item_reference", "id": "item_remote"}]},
    ],
)
def test_budget_gateway_rejects_cost_expanding_request_features(override):
    gateway = AutonomousBudgetGateway(
        upstream_base_url="http://127.0.0.1:1/v1",
        upstream_api_key="real-upstream-key",
        local_api_key="run-scoped-local-key",
        expected_model="fixed",
        expected_reasoning_effort="medium",
        budget_usd=Decimal("1"),
        pricing=ModelPricing(
            "pricing-v1",
            "a" * 64,
            Decimal("1"),
            Decimal("0.1"),
            Decimal("2"),
        ),
        allow_insecure_upstream=True,
    )
    payload = {
        "model": "fixed",
        "reasoning": {"effort": "medium"},
        "input": "bounded",
        **override,
    }

    with pytest.raises(ValueError, match="reserved scope"):
        gateway._reserve_request(payload, len(json.dumps(payload).encode()))


def test_budget_gateway_requires_exact_reasoning_effort():
    gateway = AutonomousBudgetGateway(
        upstream_base_url="http://127.0.0.1:1/v1",
        upstream_api_key="real-upstream-key",
        local_api_key="run-scoped-local-key",
        expected_model="fixed",
        expected_reasoning_effort="medium",
        budget_usd=Decimal("1"),
        pricing=ModelPricing(
            "pricing-v1",
            "a" * 64,
            Decimal("1"),
            Decimal("0.1"),
            Decimal("2"),
        ),
        allow_insecure_upstream=True,
    )
    payload = {"model": "fixed", "input": "bounded"}

    with pytest.raises(ValueError, match="reserved scope"):
        gateway._reserve_request(payload, len(json.dumps(payload).encode()))


def test_budget_gateway_rejects_cached_input_rate_above_input_rate():
    with pytest.raises(
        GatewayConfigurationError, match="Invalid autonomous budget gateway"
    ):
        AutonomousBudgetGateway(
            upstream_base_url="http://127.0.0.1:1/v1",
            upstream_api_key="real-upstream-key",
            local_api_key="run-scoped-local-key",
            expected_model="fixed",
            expected_reasoning_effort="medium",
            budget_usd=Decimal("1"),
            pricing=ModelPricing(
                "pricing-v1",
                "a" * 64,
                Decimal("1"),
                Decimal("2"),
                Decimal("2"),
            ),
            allow_insecure_upstream=True,
        )


def test_subprocess_executor_cancels_live_process(tmp_path):
    script = tmp_path / "wait.py"
    script.write_text(
        "#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n",
        encoding="utf-8",
    )
    os.chmod(script, 0o700)
    with pytest.raises(ExecutionCancelled):
        SubprocessCodexExecutor()(
            command=[str(script)],
            environment={"PATH": os.environ["PATH"]},
            cwd=tmp_path,
            input_text="{}",
            output_schema={"type": "object"},
            timeout_seconds=30,
            max_output_bytes=1000,
            cancellation_requested=lambda: True,
            budget_exceeded=lambda _: False,
            filesystem_isolation=False,
            sandbox_executable="/usr/bin/bwrap",
            shell=False,
        )


def test_subprocess_executor_terminates_when_live_budget_is_exhausted(tmp_path):
    script = tmp_path / "spend.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, time\n"
        "print(json.dumps({'usage': {'input_tokens': 100, 'output_tokens': 1}}), flush=True)\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    os.chmod(script, 0o700)
    with pytest.raises(ExecutionBudgetExceeded) as raised:
        SubprocessCodexExecutor()(
            command=[str(script)],
            environment={"PATH": os.environ["PATH"]},
            cwd=tmp_path,
            input_text="{}",
            output_schema={"type": "object"},
            timeout_seconds=30,
            max_output_bytes=1000,
            cancellation_requested=lambda: False,
            budget_exceeded=lambda events: '"input_tokens": 100' in events,
            filesystem_isolation=False,
            sandbox_executable="/usr/bin/bwrap",
            shell=False,
        )
    assert '"input_tokens": 100' in raised.value.events_jsonl
