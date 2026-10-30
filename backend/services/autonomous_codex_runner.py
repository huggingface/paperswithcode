"""Bounded Codex execution and durable, content-free result accounting."""

from __future__ import annotations

import json
import hmac
import os
import re
import resource
import signal
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from backend.models.database import AutonomousRun
from backend.services.autonomous_alert_service import send_budget_threshold_alert
from backend.services.autonomous_budget_gateway import (
    AutonomousBudgetGateway,
    GatewayConfigurationError,
)
from backend.services.autonomous_digest_service import AutonomousBudgetService
from backend.services.autonomous_capabilities import (
    CAPABILITY_MANIFESTS,
    CAPABILITY_RESOURCE_KINDS,
    Capability,
    ResourceKind,
    ResourceRef,
)
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    BudgetReservationUnavailable,
    Operator,
    RunContext,
)
from backend.services.autonomous_prompt_builder import (
    build_codex_envelope,
    build_codex_prompt,
)

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CODE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,199}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}$")
_CHAT_EVIDENCE_IDENTIFIER = re.compile(
    r"^(?:aggregate|deployment|incident|trace):[0-9a-f]{64}$"
)
_SECRET_PREFIXES = ("sk-", "hf_", "bearer", "eyj")
_MODEL_ALIASES = {
    "diagnosis": ("gpt-6-luna", "medium"),
    "independent_review": ("gpt-5.6-terra", "high"),
}
_RESULT_STATUSES = {"completed", "rejected"}
_CHAT_REASON_CODES = frozenset(
    {
        "capacity_failure",
        "lifecycle_failure",
        "persistence_failure",
        "provider_auth",
        "provider_billing",
        "provider_quota",
        "provider_unhealthy",
        "restore_primary",
        "review_required",
        "source_failure",
        "stream_failure",
        "synthetic_failure",
    }
)


def _validate_cron_evidence_payload(payload: dict[str, object]) -> None:
    if set(payload) == {"repair_review"}:
        review = payload["repair_review"]
        if not isinstance(review, dict) or set(review) != {
            "base_sha",
            "candidate_id",
            "changed_paths",
            "check_outcomes",
            "patch",
            "patch_digest",
        }:
            raise ValueError("Invalid autonomous evidence payload")
        try:
            uuid.UUID(str(review["candidate_id"]))
        except (TypeError, ValueError):
            raise ValueError("Invalid autonomous evidence payload") from None
        paths = review["changed_paths"]
        checks = review["check_outcomes"]
        if (
            not isinstance(review["base_sha"], str)
            or re.fullmatch(r"[0-9a-f]{40}", review["base_sha"]) is None
            or not isinstance(review["patch_digest"], str)
            or _DIGEST.fullmatch(review["patch_digest"]) is None
            or not isinstance(review["patch"], str)
            or not isinstance(paths, list)
            or not paths
            or len(paths) > 50
            or any(
                not isinstance(path, str)
                or not path
                or len(path) > 255
                or path.startswith("/")
                or ".." in Path(path).parts
                for path in paths
            )
            or not isinstance(checks, list)
            or not checks
            or len(checks) > 50
            or any(
                not isinstance(check, dict)
                or set(check) != {"command", "output_digest"}
                or not isinstance(check["command"], list)
                or not isinstance(check["output_digest"], str)
                or _DIGEST.fullmatch(check["output_digest"]) is None
                for check in checks
            )
        ):
            raise ValueError("Invalid autonomous evidence payload")
        return
    findings = payload.get("findings")
    required = {
        "job_name",
        "plane",
        "contract",
        "state",
        "summary",
        "evidence",
        "observed_at",
        "operator_url",
        "run_url",
    }
    if (
        set(payload) != {"findings"}
        or not isinstance(findings, list)
        or not 1 <= len(findings) <= 100
    ):
        raise ValueError("Invalid autonomous evidence payload")
    for finding in findings:
        if (
            not isinstance(finding, dict)
            or set(finding) != required
            or _CODE.fullmatch(str(finding["job_name"])) is None
            or _CODE.fullmatch(str(finding["contract"])) is None
            or finding["plane"]
            not in {"scheduler", "process_logs", "durable_data", "semantic_outcome"}
            or finding["state"] not in {"healthy", "degraded", "unknown"}
            or not isinstance(finding["summary"], str)
            or len(finding["summary"]) > 256
            or not isinstance(finding["evidence"], dict)
            or not isinstance(finding["observed_at"], str)
            or len(finding["observed_at"]) > 64
            or finding["operator_url"] != "/autonomous-operations?operator=cron"
            or (
                finding["run_url"] is not None
                and (
                    not isinstance(finding["run_url"], str)
                    or not finding["run_url"].startswith(
                        "https://github.com/huggingface/paperswithcode/actions/runs/"
                    )
                )
            )
        ):
            raise ValueError("Invalid autonomous evidence payload")
        encoded = json.dumps(finding["evidence"], sort_keys=True)
        if len(encoded.encode()) > 16_384 or any(
            prefix in encoded.lower() for prefix in _SECRET_PREFIXES
        ):
            raise ValueError("Invalid autonomous evidence payload")


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    kind: str
    identifier: str
    digest: str

    def __post_init__(self) -> None:
        if (
            _CODE.fullmatch(self.kind) is None
            or _IDENTIFIER.fullmatch(self.identifier) is None
            or _DIGEST.fullmatch(self.digest) is None
            or self.kind.startswith(_SECRET_PREFIXES)
            or self.identifier.lower().startswith(_SECRET_PREFIXES)
        ):
            raise ValueError("Invalid autonomous evidence reference")


@dataclass(frozen=True, slots=True)
class ProposedAction:
    capability: Capability
    resource: ResourceRef
    reason_code: str
    rationale: str | None = None
    evidence: tuple[str, ...] = ()
    confidence: float | None = None
    resolved_payload: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class UsageSummary:
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


@dataclass(frozen=True, slots=True)
class ModelPricing:
    revision: str
    policy_digest: str
    input_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal
    output_usd_per_million: Decimal


@dataclass(frozen=True, slots=True)
class VerifiedCredentialReservation:
    api_key: str
    reservation_id: str
    run_id: uuid.UUID
    provider: Literal["openai"]
    model_alias: Literal["diagnosis", "independent_review"]
    concrete_model: str
    reasoning_effort: Literal["medium", "high"]
    limit_usd: Decimal
    expires_at: datetime
    attestation_digest: str
    operator: str
    manifest_revision: str
    request_digest: str
    evidence_digest: str
    pricing_policy_digest: str
    api_base_url: str
    credential_scope: Literal["responses"]


@dataclass(frozen=True, slots=True)
class BudgetAttestationContext:
    request_digest: str
    evidence_digest: str
    pricing_policy_digest: str
    api_base_url: str
    concrete_model: str
    reasoning_effort: Literal["medium", "high"]


@dataclass(frozen=True, slots=True)
class CodexRequest:
    context: RunContext
    evidence: tuple[EvidenceRef, ...]
    capabilities: tuple[Capability, ...]
    output_schema: dict[str, object]
    budget_usd: Decimal
    model_alias: Literal["diagnosis", "independent_review"] = "diagnosis"
    timeout_seconds: int = 1200
    max_output_bytes: int = 2_000_000
    evidence_payload: dict[str, object] | None = None
    workspace_path: Path | None = None
    writable_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        manifest = (
            CAPABILITY_MANIFESTS.get(self.context.operator)
            if isinstance(self.context, RunContext)
            and isinstance(self.context.operator, Operator)
            else None
        )
        if (
            manifest is None
            or not isinstance(self.evidence, tuple)
            or len(self.evidence) > 500
            or any(not isinstance(value, EvidenceRef) for value in self.evidence)
            or not isinstance(self.capabilities, tuple)
            or not self.capabilities
            or len(set(self.capabilities)) != len(self.capabilities)
            or any(
                not isinstance(capability, Capability) or capability not in manifest
                for capability in self.capabilities
            )
            or self.model_alias not in _MODEL_ALIASES
            or (
                self.model_alias == "independent_review"
                and (
                    self.context.operator != Operator.CHAT_RELIABILITY
                    or Capability.REPAIR_CHAT_SOURCE not in self.capabilities
                )
            )
            or not isinstance(self.budget_usd, Decimal)
            or not self.budget_usd.is_finite()
            or not Decimal("0") < self.budget_usd <= Decimal("100")
            or not 30 <= self.timeout_seconds <= 7200
            or not 1024 <= self.max_output_bytes <= 10_000_000
        ):
            raise ValueError("Invalid autonomous Codex request")
        if not isinstance(self.output_schema, dict):
            raise ValueError("Invalid autonomous Codex output schema")
        try:
            encoded_schema = json.dumps(self.output_schema, sort_keys=True)
        except (TypeError, ValueError):
            raise ValueError("Invalid autonomous Codex output schema") from None
        if len(encoded_schema.encode()) > 250_000:
            raise ValueError("Invalid autonomous Codex output schema")
        structured_submission = (
            self.context.operator == Operator.SUBMISSIONS
            and self.evidence_payload is not None
        )
        if self.output_schema != codex_result_schema(
            self.capabilities, structured_submission=structured_submission
        ):
            raise ValueError("Invalid autonomous Codex output schema")
        if self.evidence_payload is not None:
            if self.context.operator not in {
                Operator.SUBMISSIONS,
                Operator.CRON_HEALTH,
            } or not isinstance(self.evidence_payload, dict):
                raise ValueError("Invalid autonomous evidence payload")
            try:
                encoded_evidence = json.dumps(
                    self.evidence_payload, sort_keys=True, separators=(",", ":")
                ).encode()
            except (TypeError, ValueError):
                raise ValueError("Invalid autonomous evidence payload") from None
            if len(encoded_evidence) > 2_000_000:
                raise ValueError("Invalid autonomous evidence payload")
            if self.context.operator == Operator.CRON_HEALTH:
                _validate_cron_evidence_payload(self.evidence_payload)
        if self.context.operator == Operator.CHAT_RELIABILITY and any(
            _CHAT_EVIDENCE_IDENTIFIER.fullmatch(item.identifier) is None
            or item.identifier.partition(":")[0] != item.kind
            for item in self.evidence
        ):
            raise ValueError("Invalid autonomous Codex request")
        if (self.workspace_path is None) != (not self.writable_paths):
            raise ValueError("Invalid autonomous repair workspace")
        if self.workspace_path is not None:
            root = self.workspace_path.resolve()
            if (
                not self.workspace_path.is_absolute()
                or not root.is_dir()
                or self.context.operator
                not in {Operator.CRON_HEALTH, Operator.CHAT_RELIABILITY}
                or not any(
                    capability
                    in {
                        Capability.REPAIR_DECLARED_CRON_SOURCE,
                        Capability.REPAIR_CHAT_SOURCE,
                    }
                    for capability in self.capabilities
                )
                or len(self.writable_paths) > 50
                or len(set(self.writable_paths)) != len(self.writable_paths)
            ):
                raise ValueError("Invalid autonomous repair workspace")
            for value in self.writable_paths:
                relative = Path(value)
                target = (root / relative).resolve()
                if (
                    not value
                    or "\\" in value
                    or relative.is_absolute()
                    or ".." in relative.parts
                    or str(relative) != value
                    or not target.is_file()
                    or root not in target.parents
                    or (root / relative).is_symlink()
                ):
                    raise ValueError("Invalid autonomous repair workspace")


@dataclass(frozen=True, slots=True)
class CodexResult:
    run_id: uuid.UUID
    status: Literal["completed", "rejected", "failed", "budget_exhausted", "cancelled"]
    exit_classification: str
    proposed_actions: tuple[ProposedAction, ...]
    usage: UsageSummary
    result_digest: str


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    returncode: int
    final_message: str
    events_jsonl: str


class OutputLimitExceeded(RuntimeError):
    pass


class ExecutionCancelled(RuntimeError):
    pass


class ExecutionBudgetExceeded(RuntimeError):
    def __init__(self, events_jsonl: str):
        super().__init__("budget_exhausted")
        self.events_jsonl = events_jsonl


Executor = Callable[..., ExecutionOutcome]
CancellationCheck = Callable[[], bool]
BudgetCheck = Callable[[str], bool]


class CredentialBroker(Protocol):
    def reserve(
        self,
        request: CodexRequest,
        existing_reservation_id: str | None,
        attestation_context: BudgetAttestationContext,
    ) -> VerifiedCredentialReservation: ...

    def release(
        self, reservation: VerifiedCredentialReservation, usage: UsageSummary
    ) -> Decimal: ...


class SubprocessCredentialBroker:
    """Obtain a signed, provider-enforced, idempotent per-run credential."""

    def __init__(
        self, *, environ: Mapping[str, str], now: Callable[[], datetime]
    ) -> None:
        self.environ = environ
        self.now = now

    def reserve(
        self,
        request: CodexRequest,
        existing_reservation_id: str | None,
        attestation_context: BudgetAttestationContext,
    ) -> VerifiedCredentialReservation:
        executable = self.environ.get(
            "PWC_AUTONOMOUS_CODEX_CREDENTIAL_BROKER", ""
        ).strip()
        verify_key = self.environ.get(
            "PWC_AUTONOMOUS_CODEX_RESERVATION_VERIFY_KEY", ""
        ).encode()
        broker_token = self.environ.get("PWC_AUTONOMOUS_CODEX_BROKER_TOKEN", "")
        if not executable or not Path(executable).is_absolute() or len(verify_key) < 32:
            raise RuntimeError("Autonomous credential broker is not configured")
        command = [
            executable,
            "reserve",
            "--run-id",
            str(request.context.run_id),
            "--model-alias",
            request.model_alias,
            "--concrete-model",
            attestation_context.concrete_model,
            "--reasoning-effort",
            attestation_context.reasoning_effort,
            "--limit-usd",
            format(request.budget_usd, "f"),
            "--operator",
            request.context.operator.value,
            "--manifest-revision",
            request.context.manifest_revision,
            "--request-digest",
            attestation_context.request_digest,
            "--evidence-digest",
            attestation_context.evidence_digest,
            "--pricing-policy-digest",
            attestation_context.pricing_policy_digest,
            "--api-base-url",
            attestation_context.api_base_url,
            "--credential-scope",
            "responses",
        ]
        if existing_reservation_id is not None:
            command.extend(("--reservation-id", existing_reservation_id))
        outcome = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env={
                "LANG": "C.UTF-8",
                "PATH": "/usr/bin:/bin",
                "PWC_AUTONOMOUS_CODEX_BROKER_TOKEN": broker_token,
            },
        )
        if len(outcome.stdout.encode()) > 64_000:
            raise RuntimeError("Autonomous credential broker output is invalid")
        value = json.loads(outcome.stdout)
        required = {
            "api_key",
            "attestation",
            "credential_digest",
            "credential_scope",
            "api_base_url",
            "evidence_digest",
            "expires_at",
            "limit_usd",
            "model_alias",
            "concrete_model",
            "reasoning_effort",
            "manifest_revision",
            "operator",
            "pricing_policy_digest",
            "provider",
            "reservation_id",
            "run_id",
            "request_digest",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise RuntimeError("Autonomous credential broker output is invalid")
        payload = {
            key: value[key] for key in sorted(required - {"api_key", "attestation"})
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = str(value["attestation"])
        expected = hmac.new(verify_key, canonical.encode(), sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise RuntimeError("Autonomous credential attestation is invalid")
        api_key = str(value["api_key"])
        if not hmac.compare_digest(
            str(value["credential_digest"]), sha256(api_key.encode()).hexdigest()
        ):
            raise RuntimeError("Autonomous credential attestation is invalid")
        return VerifiedCredentialReservation(
            api_key=api_key,
            reservation_id=str(value["reservation_id"]),
            run_id=uuid.UUID(str(value["run_id"])),
            provider=value["provider"],
            model_alias=value["model_alias"],
            concrete_model=str(value["concrete_model"]),
            reasoning_effort=value["reasoning_effort"],
            limit_usd=Decimal(str(value["limit_usd"])),
            expires_at=datetime.fromisoformat(str(value["expires_at"])),
            attestation_digest=sha256(
                f"{canonical}\x1f{signature}".encode()
            ).hexdigest(),
            operator=str(value["operator"]),
            manifest_revision=str(value["manifest_revision"]),
            request_digest=str(value["request_digest"]),
            evidence_digest=str(value["evidence_digest"]),
            pricing_policy_digest=str(value["pricing_policy_digest"]),
            api_base_url=str(value["api_base_url"]),
            credential_scope=value["credential_scope"],
        )

    def release(
        self, reservation: VerifiedCredentialReservation, usage: UsageSummary
    ) -> Decimal:
        executable = self.environ.get(
            "PWC_AUTONOMOUS_CODEX_CREDENTIAL_BROKER", ""
        ).strip()
        if not executable or not Path(executable).is_absolute():
            raise RuntimeError("Autonomous credential broker is not configured")
        outcome = subprocess.run(
            [
                executable,
                "release",
                "--run-id",
                str(reservation.run_id),
                "--reservation-id",
                reservation.reservation_id,
                "--input-tokens",
                str(usage.input_tokens),
                "--output-tokens",
                str(usage.output_tokens),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env={
                "LANG": "C.UTF-8",
                "PATH": "/usr/bin:/bin",
                "PWC_AUTONOMOUS_CODEX_BROKER_TOKEN": self.environ.get(
                    "PWC_AUTONOMOUS_CODEX_BROKER_TOKEN", ""
                ),
            },
        )
        if len(outcome.stdout) > 64_000:
            raise RuntimeError("Autonomous credential release output is invalid")
        value = json.loads(outcome.stdout)
        if not isinstance(value, dict) or set(value) != {"cost_usd"}:
            raise RuntimeError("Autonomous credential release output is invalid")
        cost = Decimal(str(value["cost_usd"]))
        if not cost.is_finite() or not Decimal("0") <= cost <= reservation.limit_usd:
            raise RuntimeError("Autonomous provider billing exceeded its reservation")
        return cost


class SubprocessCodexExecutor:
    """Run Codex with bounded files so stdout cannot consume unbounded memory."""

    def __call__(
        self,
        *,
        command: list[str],
        environment: dict[str, str],
        cwd: Path,
        input_text: str,
        output_schema: dict[str, object],
        timeout_seconds: int,
        max_output_bytes: int,
        cancellation_requested: CancellationCheck,
        budget_exceeded: BudgetCheck,
        filesystem_isolation: bool,
        sandbox_executable: str,
        shell: bool,
        workspace_path: Path | None = None,
        writable_paths: tuple[str, ...] = (),
    ) -> ExecutionOutcome:
        if shell:
            raise ValueError("Autonomous Codex execution cannot use a shell")
        with tempfile.TemporaryDirectory(prefix="pwc-autonomous-codex-") as directory:
            temp = Path(directory)
            schema_path = temp / "output-schema.json"
            prompt_path = temp / "prompt.json"
            final_path = temp / "final.json"
            events_path = temp / "events.jsonl"
            schema_path.write_text(
                json.dumps(output_schema, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            prompt_path.write_text(input_text, encoding="utf-8")
            actual_command = [
                *command,
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(final_path),
                "-",
            ]
            if filesystem_isolation:
                actual_command = self._isolated_command(
                    actual_command,
                    sandbox_executable=sandbox_executable,
                    temporary_directory=temp,
                    workspace_path=workspace_path,
                    writable_paths=writable_paths,
                )
            started = time.monotonic()
            with events_path.open("wb") as events, prompt_path.open("rb") as prompt:
                process = subprocess.Popen(
                    actual_command,
                    stdin=prompt,
                    stdout=events,
                    stderr=subprocess.STDOUT,
                    cwd=cwd,
                    env=environment,
                    shell=False,
                    start_new_session=True,
                    preexec_fn=lambda: resource.setrlimit(
                        resource.RLIMIT_FSIZE,
                        (max_output_bytes, max_output_bytes),
                    ),
                )
                while process.poll() is None:
                    if cancellation_requested():
                        self._terminate(process)
                        raise ExecutionCancelled("cancelled")
                    if time.monotonic() - started > timeout_seconds:
                        self._terminate(process)
                        raise subprocess.TimeoutExpired(actual_command, timeout_seconds)
                    final_size = final_path.stat().st_size if final_path.exists() else 0
                    if events_path.stat().st_size + final_size >= max_output_bytes:
                        self._terminate(process)
                        raise OutputLimitExceeded("output_limit")
                    events.flush()
                    observed = events_path.read_text(encoding="utf-8", errors="replace")
                    if budget_exceeded(observed):
                        self._terminate(process)
                        raise ExecutionBudgetExceeded(observed)
                    time.sleep(0.1)
            if (
                events_path.stat().st_size
                + (final_path.stat().st_size if final_path.exists() else 0)
                >= max_output_bytes
            ):
                raise OutputLimitExceeded("output_limit")
            return ExecutionOutcome(
                returncode=int(process.returncode or 0),
                final_message=(
                    final_path.read_text(encoding="utf-8", errors="replace")
                    if final_path.exists()
                    else ""
                ),
                events_jsonl=events_path.read_text(encoding="utf-8", errors="replace"),
            )

    @staticmethod
    def _isolated_command(
        command: list[str],
        *,
        sandbox_executable: str,
        temporary_directory: Path,
        workspace_path: Path | None = None,
        writable_paths: tuple[str, ...] = (),
    ) -> list[str]:
        """Expose only runtime files and an empty workspace to model tools."""
        isolated_codex = "/pwc-bin/codex"
        isolated = [
            sandbox_executable,
            "--die-with-parent",
            "--new-session",
            "--unshare-all",
            "--share-net",
            "--dev",
            "/dev",
            "--ro-bind",
            "/usr",
            "/usr",
            "--symlink",
            "usr/bin",
            "/bin",
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib64",
            "/lib64",
            "--tmpfs",
            "/tmp",
            "--dir",
            str(temporary_directory),
            "--bind",
            str(temporary_directory),
            str(temporary_directory),
            "--dir",
            "/pwc-bin",
            "--ro-bind",
            command[0],
            isolated_codex,
            "--dir",
            "/tmp/codex-home",
            "--setenv",
            "HOME",
            "/tmp",
            "--setenv",
            "CODEX_HOME",
            "/tmp/codex-home",
        ]
        for path in ("/etc/ssl", "/etc/resolv.conf"):
            if Path(path).exists():
                isolated.extend(("--ro-bind", path, path))
        if workspace_path is None:
            isolated.extend(("--dir", "/workspace"))
        else:
            root = workspace_path.resolve()
            isolated.extend(("--ro-bind", str(root), "/workspace"))
            for relative in writable_paths:
                source = root / relative
                isolated.extend(("--bind", str(source), f"/workspace/{relative}"))
        return [*isolated, "--chdir", "/workspace", "--", isolated_codex, *command[1:]]

    @staticmethod
    def _terminate(process: subprocess.Popen) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=2)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


class AutonomousCodexRunner:
    def __init__(
        self,
        *,
        executor: Executor | None = None,
        environ: Mapping[str, str] | None = None,
        repository: AutonomousOperationsRepository | None = None,
        credential_broker: CredentialBroker | None = None,
        now: Callable[[], datetime] | None = None,
        working_directory: Path | None = None,
        cumulative_budget_service: AutonomousBudgetService | None = None,
    ) -> None:
        self.executor = executor or SubprocessCodexExecutor()
        self.environ = dict(os.environ if environ is None else environ)
        self.repository = repository or AutonomousOperationsRepository()
        self.now = now or (lambda: datetime.now(UTC))
        self.credential_broker = credential_broker or SubprocessCredentialBroker(
            environ=self.environ, now=self.now
        )
        self.working_directory = working_directory or Path("/")
        self.cumulative_budget_service = cumulative_budget_service

    def run(
        self,
        request: CodexRequest,
        *,
        db: Session,
        cancellation_requested: CancellationCheck | None = None,
    ) -> CodexResult:
        cancellation_requested = cancellation_requested or (lambda: False)
        self.repository.lock_run(db, run_id=request.context.run_id)
        existing = db.get(AutonomousRun, request.context.run_id)
        if existing is not None:
            return self._resume(existing, request, db)
        if cancellation_requested():
            return self._finish(request, "cancelled", "cancelled", (), self._zero(), db)
        intent = self.repository.get_execution_intent(db, run_id=request.context.run_id)
        if self.cumulative_budget_service is not None and intent is None:
            budget = self.cumulative_budget_service.enforce_before_run(
                db,
                operator=request.context.operator,
                requested_cost_usd=request.budget_usd,
                requested_tokens=(self.cumulative_budget_service.limits.per_run_tokens),
            )
            if not budget.allowed:
                return self._finish(
                    request,
                    "budget_exhausted",
                    "budget_exhausted",
                    (),
                    self._zero(),
                    db,
                )
        try:
            executable = self._executable()
            sandbox_executable = self._sandbox_executable()
            pricing = self._pricing(request.model_alias)
            upstream_base_url = self._upstream_base_url()
        except (InvalidOperation, KeyError, RuntimeError, ValueError):
            return self._finish(
                request, "failed", "configuration_missing", (), self._zero(), db
            )
        request_digest = self._request_digest(request)
        evidence_digests = sorted({item.digest for item in request.evidence})
        evidence_digest = sha256(
            json.dumps(evidence_digests, separators=(",", ":")).encode()
        ).hexdigest()
        attestation_context = BudgetAttestationContext(
            request_digest=request_digest,
            evidence_digest=evidence_digest,
            pricing_policy_digest=pricing.policy_digest,
            api_base_url=upstream_base_url,
            concrete_model=_MODEL_ALIASES[request.model_alias][0],
            reasoning_effort=_MODEL_ALIASES[request.model_alias][1],
        )
        recovering_unclaimed_intent = False
        if intent is not None:
            if (
                intent.operator != request.context.operator.value
                or intent.dry_run != request.context.dry_run
                or intent.manifest_revision != request.context.manifest_revision
                or intent.request_digest != request_digest
                or intent.evidence_digests != evidence_digests
                or intent.model_alias != request.model_alias
                or Decimal(intent.budget_usd) != request.budget_usd
                or intent.pricing_policy_digest != pricing.policy_digest
            ):
                raise ValueError("Autonomous execution intent mismatch")
            if self.repository.budget_claim_is_active(
                db, run_id=request.context.run_id
            ):
                raise BudgetReservationUnavailable(
                    "Autonomous execution is already active"
                )
            interrupted_reservation = self.repository.get_budget_reservation(
                db, run_id=request.context.run_id
            )
            if interrupted_reservation is None:
                recovering_unclaimed_intent = True
            else:
                interrupted_usage = self._zero()
                if interrupted_reservation.state == "claimed":
                    self.repository.mark_budget_unknown(
                        db, run_id=request.context.run_id
                    )
                elif interrupted_reservation.state == "released":
                    interrupted_usage = UsageSummary(
                        interrupted_reservation.authoritative_input_tokens,
                        interrupted_reservation.authoritative_output_tokens,
                        Decimal(interrupted_reservation.authoritative_cost_usd),
                    )
                return self._finish(
                    request,
                    "failed",
                    "interrupted",
                    (),
                    interrupted_usage,
                    db,
                )
        else:
            self.repository.record_execution_intent(
                db,
                context=request.context,
                request_digest=request_digest,
                evidence_digests=evidence_digests,
                model_alias=request.model_alias,
                budget_usd=request.budget_usd,
                pricing_policy_digest=pricing.policy_digest,
                now=self.now(),
            )
            db.commit()
        durable_reservation = self.repository.get_budget_reservation(
            db, run_id=request.context.run_id
        )
        reservation: VerifiedCredentialReservation | None = None
        claim_id: uuid.UUID | None = None
        gateway: AutonomousBudgetGateway | None = None
        try:
            reservation = self.credential_broker.reserve(
                request,
                durable_reservation.reservation_id
                if durable_reservation is not None
                else f"run:{request.context.run_id.hex}",
                attestation_context,
            )
            self._validate_reservation(request, reservation, attestation_context)
            claim_id = self.repository.claim_budget_reservation(
                db,
                context=request.context,
                reservation_id=reservation.reservation_id,
                provider=reservation.provider,
                model_alias=reservation.model_alias,
                limit_usd=reservation.limit_usd,
                attestation_digest=reservation.attestation_digest,
                request_digest=request_digest,
                endpoint_digest=sha256(upstream_base_url.encode()).hexdigest(),
                credential_scope="responses",
                expires_at=reservation.expires_at,
                claim_ttl=timedelta(seconds=request.timeout_seconds + 300),
            )
            db.commit()
            if recovering_unclaimed_intent:
                billed_cost = self.credential_broker.release(reservation, self._zero())
                if (
                    not isinstance(billed_cost, Decimal)
                    or not billed_cost.is_finite()
                    or not Decimal("0") <= billed_cost <= reservation.limit_usd
                ):
                    raise RuntimeError("Invalid provider billing result")
                return self._finish(
                    request,
                    "failed",
                    "interrupted",
                    (),
                    UsageSummary(0, 0, billed_cost),
                    db,
                    claim_id=claim_id,
                    cost_upper_bound_usd=billed_cost,
                )
            usage_bind = db.get_bind()
            usage_engine = getattr(usage_bind, "engine", usage_bind)

            def record_gateway_usage(gateway_usage, upper_bound):
                if usage_engine.dialect.name != "postgresql":
                    return
                with Session(bind=usage_engine) as usage_db:
                    self.repository.record_budget_usage(
                        usage_db,
                        run_id=request.context.run_id,
                        claim_id=claim_id,
                        input_tokens=gateway_usage.input_tokens,
                        output_tokens=gateway_usage.output_tokens,
                        cost_usd=gateway_usage.cost_usd,
                        cost_upper_bound_usd=upper_bound,
                    )
                    usage_db.commit()

            gateway = AutonomousBudgetGateway.create(
                upstream_base_url=upstream_base_url,
                upstream_api_key=reservation.api_key,
                expected_model=_MODEL_ALIASES[request.model_alias][0],
                expected_reasoning_effort=_MODEL_ALIASES[request.model_alias][1],
                budget_usd=reservation.limit_usd,
                pricing=pricing,
                usage_recorder=record_gateway_usage,
            )
            gateway_base_url, gateway_key = gateway.start()
            environment = self._sanitized_environment(gateway_key, gateway_base_url)
        except BudgetReservationUnavailable:
            db.rollback()
            raise
        except (
            OSError,
            subprocess.SubprocessError,
            RuntimeError,
            TypeError,
            ValueError,
            GatewayConfigurationError,
        ):
            db.rollback()
            if reservation is not None and claim_id is not None:
                usage = self._zero()
                if gateway is not None:
                    try:
                        gateway_usage = gateway.close()
                        usage = UsageSummary(
                            gateway_usage.input_tokens,
                            gateway_usage.output_tokens,
                            gateway_usage.cost_usd,
                        )
                    except (OSError, RuntimeError):
                        pass
                released = True
                classification = "credential_missing"
                try:
                    billed_cost = self.credential_broker.release(reservation, usage)
                    if (
                        not isinstance(billed_cost, Decimal)
                        or not billed_cost.is_finite()
                        or not Decimal("0") <= billed_cost <= reservation.limit_usd
                    ):
                        raise RuntimeError("Invalid provider billing result")
                    usage = UsageSummary(
                        usage.input_tokens, usage.output_tokens, billed_cost
                    )
                except (
                    InvalidOperation,
                    OSError,
                    subprocess.SubprocessError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ):
                    released = False
                    classification = "credential_revoke_failed"
                    usage = UsageSummary(
                        usage.input_tokens, usage.output_tokens, Decimal("0")
                    )
                return self._finish(
                    request,
                    "failed",
                    classification,
                    (),
                    usage,
                    db,
                    claim_id=claim_id,
                    reservation_released=released,
                    cost_upper_bound_usd=usage.cost_usd,
                )
            return self._finish(
                request, "failed", "credential_missing", (), self._zero(), db
            )

        def finish(
            status: str,
            classification: str,
            actions: tuple[ProposedAction, ...],
            usage: UsageSummary,
        ) -> CodexResult:
            gateway_usage = gateway.close()
            released = True
            if gateway_usage.input_tokens or gateway_usage.output_tokens:
                usage = UsageSummary(
                    gateway_usage.input_tokens,
                    gateway_usage.output_tokens,
                    gateway_usage.cost_usd,
                )
            if gateway_usage.cost_usd >= reservation.limit_usd:
                status = "budget_exhausted"
                classification = "budget_exhausted"
                actions = ()
            cost_upper_bound = min(
                reservation.limit_usd,
                max(gateway_usage.cost_usd, usage.cost_usd),
            )
            try:
                billed_cost = self.credential_broker.release(reservation, usage)
                if (
                    not isinstance(billed_cost, Decimal)
                    or not billed_cost.is_finite()
                    or not Decimal("0") <= billed_cost <= reservation.limit_usd
                ):
                    raise RuntimeError("Invalid provider billing result")
                usage = UsageSummary(
                    usage.input_tokens, usage.output_tokens, billed_cost
                )
            except (
                InvalidOperation,
                OSError,
                subprocess.SubprocessError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                released = False
                usage = UsageSummary(
                    usage.input_tokens, usage.output_tokens, Decimal("0")
                )
                status = "failed"
                classification = "credential_revoke_failed"
                actions = ()
            return self._finish(
                request,
                status,
                classification,
                actions,
                usage,
                db,
                claim_id=claim_id,
                reservation_released=released,
                cost_upper_bound_usd=max(cost_upper_bound, usage.cost_usd),
            )

        model, reasoning = _MODEL_ALIASES[request.model_alias]
        command = [
            executable,
            "exec",
            "--json",
            "--ephemeral",
            "--ignore-user-config",
            "--skip-git-repo-check",
            "--color",
            "never",
            "--sandbox",
            "workspace-write" if request.workspace_path is not None else "read-only",
            "--model",
            model,
            "--config",
            f'model_reasoning_effort="{reasoning}"',
            "--config",
            "shell_environment_policy.inherit=none",
            "--config",
            "features.responses_websockets=false",
            "--cd",
            "/workspace",
        ]

        def budget_exceeded(events: tuple[str, ...]) -> bool:
            usage, _usage_found = self._usage(events, pricing)
            return usage.cost_usd > request.budget_usd or (
                self.cumulative_budget_service is not None
                and usage.input_tokens + usage.output_tokens
                > self.cumulative_budget_service.limits.per_run_tokens
            )

        try:
            outcome = self.executor(
                command=command,
                environment=environment,
                cwd=self.working_directory,
                input_text=build_codex_prompt(request),
                output_schema=request.output_schema,
                timeout_seconds=request.timeout_seconds,
                max_output_bytes=request.max_output_bytes,
                cancellation_requested=cancellation_requested,
                budget_exceeded=budget_exceeded,
                filesystem_isolation=True,
                sandbox_executable=sandbox_executable,
                shell=False,
                workspace_path=request.workspace_path,
                writable_paths=request.writable_paths,
            )
        except ExecutionBudgetExceeded as error:
            usage, _ = self._usage(error.events_jsonl, pricing)
            return finish("budget_exhausted", "budget_exhausted", (), usage)
        except subprocess.TimeoutExpired:
            return finish("failed", "timeout", (), self._zero())
        except ExecutionCancelled:
            return finish("cancelled", "cancelled", (), self._zero())
        except OutputLimitExceeded:
            return finish("failed", "output_limit", (), self._zero())
        except (OSError, subprocess.SubprocessError):
            return finish("failed", "process_error", (), self._zero())
        except RuntimeError as error:
            classification = (
                "output_limit" if str(error) == "output_limit" else "process_error"
            )
            return finish("failed", classification, (), self._zero())
        usage, usage_found = self._usage(outcome.events_jsonl, pricing)
        if outcome.returncode != 0:
            return finish("failed", "process_error", (), usage)
        try:
            status, actions = self._parse_result(request, outcome.final_message)
            if not usage_found:
                raise ValueError("usage missing")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return finish("failed", "malformed_output", (), usage)
        if usage.cost_usd > request.budget_usd:
            return finish("budget_exhausted", "budget_exhausted", (), usage)
        return finish(status, status, actions, usage)

    def _sanitized_environment(
        self, credential: str, gateway_base_url: str
    ) -> dict[str, str]:
        credential = credential.strip()
        if not credential:
            raise RuntimeError("Dedicated autonomous Codex credential is missing")
        environment = {
            "PATH": self.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "LANG": self.environ.get("LANG", "C.UTF-8"),
            "OPENAI_API_KEY": credential,
            "OPENAI_BASE_URL": gateway_base_url,
            "CODEX_HOME": self.environ.get(
                "PWC_AUTONOMOUS_CODEX_HOME",
                "/var/lib/paperswithcode/autonomous-codex",
            ),
        }
        for key in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
            if self.environ.get(key):
                environment[key] = self.environ[key]
        return environment

    def _upstream_base_url(self) -> str:
        value = self.environ.get("PWC_AUTONOMOUS_CODEX_UPSTREAM_BASE_URL", "").strip()
        allowed_hosts = {
            host.strip().lower()
            for host in self.environ.get(
                "PWC_AUTONOMOUS_CODEX_UPSTREAM_HOST_ALLOWLIST", ""
            ).split(",")
            if host.strip()
        }
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.hostname.lower() not in allowed_hosts
        ):
            raise RuntimeError("Autonomous Codex upstream is not configured")
        return value

    def _validate_reservation(
        self,
        request: CodexRequest,
        value: VerifiedCredentialReservation,
        attestation_context: BudgetAttestationContext,
    ) -> None:
        now = self.now()
        if (
            not isinstance(value, VerifiedCredentialReservation)
            or not isinstance(value.api_key, str)
            or not value.api_key.strip()
            or _CODE.fullmatch(value.reservation_id) is None
            or len(value.reservation_id) > 128
            or value.reservation_id != f"run:{request.context.run_id.hex}"
            or value.run_id != request.context.run_id
            or value.provider != "openai"
            or value.model_alias != request.model_alias
            or value.concrete_model != attestation_context.concrete_model
            or value.reasoning_effort != attestation_context.reasoning_effort
            or not isinstance(value.limit_usd, Decimal)
            or not value.limit_usd.is_finite()
            or not Decimal("0") < value.limit_usd <= request.budget_usd
            or not isinstance(value.expires_at, datetime)
            or value.expires_at.tzinfo is None
            or value.expires_at < now + timedelta(seconds=request.timeout_seconds + 300)
            or _DIGEST.fullmatch(value.attestation_digest) is None
            or value.operator != request.context.operator.value
            or value.manifest_revision != request.context.manifest_revision
            or value.request_digest != attestation_context.request_digest
            or value.evidence_digest != attestation_context.evidence_digest
            or value.pricing_policy_digest != attestation_context.pricing_policy_digest
            or value.api_base_url != attestation_context.api_base_url
            or value.credential_scope != "responses"
        ):
            raise ValueError("Invalid autonomous credential reservation")

    def _executable(self) -> str:
        value = self.environ.get("PWC_AUTONOMOUS_CODEX_EXECUTABLE", "").strip()
        if not value or not Path(value).is_absolute():
            raise RuntimeError("Autonomous Codex executable is not configured")
        return value

    def _sandbox_executable(self) -> str:
        value = self.environ.get("PWC_AUTONOMOUS_CODEX_BWRAP_EXECUTABLE", "").strip()
        if not value or not Path(value).is_absolute():
            raise RuntimeError("Autonomous Codex sandbox is not configured")
        return value

    def _pricing(self, model_alias: str) -> ModelPricing:
        revision = self.environ.get("PWC_AUTONOMOUS_CODEX_PRICING_REVISION", "").strip()
        if _CODE.fullmatch(revision) is None:
            raise RuntimeError("Autonomous Codex pricing is not configured")
        # Alias names intentionally differ from model slugs; pricing is selected by
        # the same closed server alias that selects the model.
        prefix = (
            "PWC_AUTONOMOUS_CODEX_LUNA"
            if model_alias == "diagnosis"
            else "PWC_AUTONOMOUS_CODEX_TERRA"
        )
        values = [
            Decimal(self.environ[f"{prefix}_{kind}_USD_PER_MILLION"])
            for kind in ("INPUT", "CACHED_INPUT", "OUTPUT")
        ]
        if (
            any(not value.is_finite() or value < 0 for value in values)
            or values[0] <= 0
            or values[2] <= 0
            or values[1] > values[0]
        ):
            raise ValueError("Invalid autonomous Codex pricing")
        canonical = json.dumps(
            {
                "alias": model_alias,
                "cached_input": format(values[1], "f"),
                "input": format(values[0], "f"),
                "output": format(values[2], "f"),
                "revision": revision,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return ModelPricing(revision, sha256(canonical.encode()).hexdigest(), *values)

    @staticmethod
    def _parse_result(
        request: CodexRequest, raw: str
    ) -> tuple[str, tuple[ProposedAction, ...]]:
        value = json.loads(raw)
        if not isinstance(value, dict) or set(value) != {"status", "proposed_actions"}:
            raise ValueError("invalid result")
        status = value["status"]
        if status not in _RESULT_STATUSES or not isinstance(
            value["proposed_actions"], list
        ):
            raise ValueError("invalid result")
        actions = []
        if len(value["proposed_actions"]) > 100:
            raise ValueError("too many actions")
        for item in value["proposed_actions"]:
            if not isinstance(item, dict) or "capability" not in item:
                raise ValueError("invalid action")
            capability = Capability(item["capability"])
            review_keys = {
                "capability",
                "resource",
                "reason_code",
                "rationale",
                "evidence",
                "confidence",
                "resolved_payload",
            }
            ordinary_keys = {"capability", "resource", "reason_code"}
            structured_review = (
                capability == Capability.REVIEW_SUBMISSION
                and request.evidence_payload is not None
            )
            if set(item) != (review_keys if structured_review else ordinary_keys):
                raise ValueError("invalid action")
            resource_value = item["resource"]
            if not isinstance(resource_value, dict) or set(resource_value) != {
                "kind",
                "identifier",
                "exists",
            }:
                raise ValueError("invalid resource")
            if capability not in request.capabilities:
                raise ValueError("capability outside request")
            resource = ResourceRef(
                ResourceKind(resource_value["kind"]),
                resource_value["identifier"],
                resource_value["exists"],
            )
            reason_code = item["reason_code"]
            if (
                resource.kind not in CAPABILITY_RESOURCE_KINDS[capability]
                or not isinstance(reason_code, str)
                or _CODE.fullmatch(reason_code) is None
                or len(reason_code) > 64
            ):
                raise ValueError("invalid action scope")
            if request.context.operator == Operator.CHAT_RELIABILITY:
                allowed_identifiers = {
                    Capability.SWITCH_CHAT_PROVIDER: {"primary", "fallback"},
                    Capability.REPAIR_CHAT_SOURCE: {"chat"},
                }
                if resource.identifier not in allowed_identifiers[capability]:
                    raise ValueError("invalid chat action resource")
                if reason_code not in _CHAT_REASON_CODES:
                    raise ValueError("invalid chat action reason")
            if structured_review:
                rationale = item["rationale"]
                evidence = item["evidence"]
                confidence = item["confidence"]
                resolved_payload = item["resolved_payload"]
                if (
                    reason_code not in {"approve", "reject", "defer"}
                    or resource.kind != ResourceKind.PENDING_EDIT
                    or not resource.exists
                    or not isinstance(rationale, str)
                    or not 1 <= len(rationale) <= 4000
                    or not isinstance(evidence, list)
                    or not 1 <= len(evidence) <= 50
                    or any(
                        not isinstance(value, str) or not 1 <= len(value) <= 255
                        for value in evidence
                    )
                    or isinstance(confidence, bool)
                    or not isinstance(confidence, (int, float))
                    or not 0 <= confidence <= 1
                    or (
                        resolved_payload is not None
                        and not isinstance(resolved_payload, dict)
                    )
                ):
                    raise ValueError("invalid submission review")
                actions.append(
                    ProposedAction(
                        capability,
                        resource,
                        reason_code,
                        rationale,
                        tuple(evidence),
                        float(confidence),
                        resolved_payload,
                    )
                )
            else:
                actions.append(ProposedAction(capability, resource, reason_code))
        if status == "rejected" and actions:
            raise ValueError("rejected result proposed actions")
        return status, tuple(actions)

    @staticmethod
    def _usage(raw: str, pricing: ModelPricing) -> tuple[UsageSummary, bool]:
        input_tokens = 0
        cached_input_tokens = 0
        output_tokens = 0
        tokens_found = False
        for line in raw.splitlines():
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(event, dict):
                continue
            item = event.get("item")
            candidate = event.get("usage") or (
                item.get("usage") if isinstance(item, dict) else None
            )
            if not isinstance(candidate, dict):
                continue
            tokens_found = tokens_found or {
                "input_tokens",
                "output_tokens",
            } <= set(candidate)
            try:
                values = {
                    key: candidate.get(key, 0)
                    for key in (
                        "input_tokens",
                        "cached_input_tokens",
                        "output_tokens",
                    )
                }
                if any(
                    isinstance(value, bool) or not isinstance(value, int) or value < 0
                    for value in values.values()
                ):
                    raise ValueError("invalid usage")
                input_tokens = max(input_tokens, values["input_tokens"])
                cached_input_tokens = max(
                    cached_input_tokens, values["cached_input_tokens"]
                )
                output_tokens = max(output_tokens, values["output_tokens"])
            except (TypeError, ValueError):
                return UsageSummary(0, 0, Decimal("0")), False
        if cached_input_tokens > input_tokens:
            return UsageSummary(0, 0, Decimal("0")), False
        cost = (
            Decimal(input_tokens - cached_input_tokens) * pricing.input_usd_per_million
            + Decimal(cached_input_tokens) * pricing.cached_input_usd_per_million
            + Decimal(output_tokens) * pricing.output_usd_per_million
        ) / Decimal(1_000_000)
        return UsageSummary(input_tokens, output_tokens, cost), tokens_found

    @staticmethod
    def _zero() -> UsageSummary:
        return UsageSummary(0, 0, Decimal("0"))

    def _finish(
        self,
        request: CodexRequest,
        status: str,
        classification: str,
        actions: tuple[ProposedAction, ...],
        usage: UsageSummary,
        db: Session,
        *,
        claim_id: uuid.UUID | None = None,
        reservation_released: bool = True,
        cost_upper_bound_usd: Decimal | None = None,
    ) -> CodexResult:
        try:
            pricing = self._pricing(request.model_alias)
            pricing_revision = pricing.revision
            pricing_policy_digest = pricing.policy_digest
        except (InvalidOperation, KeyError, RuntimeError, ValueError):
            pricing_revision = "unknown"
            pricing_policy_digest = "0" * 64
        reservation = self.repository.get_budget_reservation(
            db, run_id=request.context.run_id
        )
        reservation_digest = (
            reservation.attestation_digest if reservation is not None else "0" * 64
        )
        reservation_limit = (
            Decimal(reservation.limit_usd) if reservation is not None else Decimal("0")
        )
        digest = self._result_digest(
            self._request_digest(request),
            request.context.run_id,
            status,
            classification,
            actions,
            usage,
            pricing_revision,
            pricing_policy_digest,
            reservation_digest,
            reservation_limit,
        )
        result = CodexResult(
            request.context.run_id,
            status,
            classification,
            actions,
            usage,
            digest,
        )
        finished_at = self.now()
        if claim_id is not None:
            self.repository.settle_budget_reservation(
                db,
                run_id=request.context.run_id,
                claim_id=claim_id,
                released=reservation_released,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=usage.cost_usd,
                cost_upper_bound_usd=cost_upper_bound_usd or usage.cost_usd,
                now=finished_at,
            )
        self.repository.append_run(
            db,
            context=request.context,
            status=status,
            now=finished_at,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
            result_digest=digest,
            exit_classification=classification,
            capability_requests=self._capability_requests(actions),
            evidence_digests=sorted({item.digest for item in request.evidence}),
            pricing_revision=pricing_revision,
            pricing_policy_digest=pricing_policy_digest,
        )
        db.commit()
        return result

    @staticmethod
    def _capability_requests(
        actions: tuple[ProposedAction, ...],
    ) -> list[dict[str, object]]:
        requests = []
        for action in actions:
            item: dict[str, object] = {
                "capability": action.capability.value,
                "resource_kind": action.resource.kind.value,
                "resource_identifier": action.resource.identifier,
                "resource_exists": action.resource.exists,
                "reason_code": action.reason_code,
            }
            if action.rationale is not None:
                item.update(
                    {
                        "rationale": action.rationale,
                        "evidence": list(action.evidence),
                        "confidence": action.confidence,
                        "resolved_payload": action.resolved_payload,
                    }
                )
            requests.append(item)
        return requests

    def _resume(
        self, row: AutonomousRun, request: CodexRequest, db: Session
    ) -> CodexResult:
        if (
            row.operator != request.context.operator.value
            or row.dry_run != request.context.dry_run
            or row.manifest_revision != request.context.manifest_revision
            or row.evidence_digests
            != sorted({item.digest for item in request.evidence})
        ):
            raise ValueError("Autonomous run context mismatches durable identity")
        actions = tuple(
            ProposedAction(
                Capability(item["capability"]),
                ResourceRef(
                    ResourceKind(item["resource_kind"]),
                    item["resource_identifier"],
                    item["resource_exists"],
                ),
                item["reason_code"],
                item.get("rationale"),
                tuple(item.get("evidence", ())),
                item.get("confidence"),
                item.get("resolved_payload"),
            )
            for item in row.capability_requests
        )
        usage = UsageSummary(
            int(row.input_tokens), int(row.output_tokens), Decimal(row.cost_usd)
        )
        reservation = self.repository.get_budget_reservation(db, run_id=row.id)
        digest = self._result_digest(
            self._request_digest(request),
            row.id,
            row.status,
            row.exit_classification,
            actions,
            usage,
            row.pricing_revision,
            row.pricing_policy_digest,
            reservation.attestation_digest if reservation is not None else "0" * 64,
            Decimal(reservation.limit_usd) if reservation is not None else Decimal("0"),
        )
        if digest != row.result_digest:
            raise ValueError("Autonomous run result digest mismatch")
        return CodexResult(
            row.id,
            row.status,
            row.exit_classification,
            actions,
            usage,
            digest,
        )

    @staticmethod
    def _result_digest(
        request_digest: str,
        run_id: uuid.UUID,
        status: str,
        classification: str,
        actions: tuple[ProposedAction, ...],
        usage: UsageSummary,
        pricing_revision: str,
        pricing_policy_digest: str,
        reservation_digest: str,
        reservation_limit: Decimal,
    ) -> str:
        value = {
            "actions": [
                {
                    "capability": action.capability.value,
                    "reason_code": action.reason_code,
                    "resource": {
                        "exists": action.resource.exists,
                        "identifier": action.resource.identifier,
                        "kind": action.resource.kind.value,
                    },
                    **(
                        {
                            "rationale": action.rationale,
                            "evidence": list(action.evidence),
                            "confidence": action.confidence,
                            "resolved_payload": action.resolved_payload,
                        }
                        if action.rationale is not None
                        else {}
                    ),
                }
                for action in actions
            ],
            "classification": classification,
            "request_digest": request_digest,
            "run_id": str(run_id),
            "pricing_revision": pricing_revision,
            "pricing_policy_digest": pricing_policy_digest,
            "reservation_digest": reservation_digest,
            "reservation_limit_usd": format(
                reservation_limit.quantize(Decimal("0.000000001")), "f"
            ),
            "status": status,
            "usage": {
                "cost_usd": format(
                    usage.cost_usd.quantize(Decimal("0.000000001")), "f"
                ),
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            },
        }
        return sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _request_digest(request: CodexRequest) -> str:
        value = {
            "envelope": json.loads(build_codex_envelope(request)),
            "max_output_bytes": request.max_output_bytes,
            "model_alias": request.model_alias,
            "timeout_seconds": request.timeout_seconds,
        }
        return sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def run_codex(
    request: CodexRequest,
    *,
    db: Session,
    cancellation_requested: CancellationCheck | None = None,
) -> CodexResult:
    return AutonomousCodexRunner(
        cumulative_budget_service=AutonomousBudgetService(
            on_exhausted=send_budget_threshold_alert
        )
    ).run(request, db=db, cancellation_requested=cancellation_requested)


def codex_result_schema(
    capabilities: tuple[Capability, ...],
    *,
    structured_submission: bool = False,
) -> dict[str, object]:
    action_schemas = []
    for capability in sorted(capabilities, key=str):
        identifier_schema: dict[str, object] = {
            "type": "string",
            "pattern": _IDENTIFIER.pattern,
            "maxLength": 255,
        }
        reason_schema: dict[str, object] = {
            "type": "string",
            "pattern": _CODE.pattern,
            "maxLength": 64,
        }
        if capability == Capability.SWITCH_CHAT_PROVIDER:
            identifier_schema = {"enum": ["fallback", "primary"]}
            reason_schema = {"enum": sorted(_CHAT_REASON_CODES)}
        elif capability == Capability.REPAIR_CHAT_SOURCE:
            identifier_schema = {"const": "chat"}
            reason_schema = {"enum": sorted(_CHAT_REASON_CODES)}
        review_properties = {}
        required = ["capability", "resource", "reason_code"]
        if capability == Capability.REVIEW_SUBMISSION and structured_submission:
            reason_schema = {"enum": ["approve", "reject", "defer"]}
            required.extend(["rationale", "evidence", "confidence", "resolved_payload"])
            review_properties = {
                "rationale": {"type": "string", "minLength": 1, "maxLength": 4000},
                "evidence": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 50,
                    "items": {"type": "string", "minLength": 1, "maxLength": 255},
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "resolved_payload": {"type": ["object", "null"]},
            }
        action_schemas.append(
            {
                "type": "object",
                "additionalProperties": False,
                "required": required,
                "properties": {
                    "capability": {"const": capability.value},
                    "resource": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["kind", "identifier", "exists"],
                        "properties": {
                            "kind": {
                                "enum": sorted(
                                    kind.value
                                    for kind in CAPABILITY_RESOURCE_KINDS[capability]
                                )
                            },
                            "identifier": identifier_schema,
                            "exists": {"type": "boolean"},
                        },
                    },
                    "reason_code": reason_schema,
                    **review_properties,
                },
            }
        )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "proposed_actions"],
        "properties": {
            "status": {"enum": ["completed", "rejected"]},
            "proposed_actions": {
                "type": "array",
                "maxItems": 100,
                "items": {"anyOf": action_schemas},
            },
        },
    }
