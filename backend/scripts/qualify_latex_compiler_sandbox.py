"""Run content-free staging qualification through the per-job Sandbox transport.

The command sends only fixed synthetic fixtures and prints case names, terminal
outcomes, and elapsed milliseconds. It never prints manuscript bytes,
diagnostics, provider handles, URLs, envelopes, or credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import httpx

from backend.config import Settings, get_settings
from backend.scripts.qualify_latex_compiler_space import (
    QualificationCase,
    qualification_cases,
    report,
)
from backend.services.latex_compiler_service import (
    LatexCompilerTransport,
    compiler_transport_from_settings,
)
from latex_compiler_contract import (
    CompilerJobState,
    EnvelopeError,
    validate_staging_sandbox_compiler_identity,
)

CONFIRMATION = "QUALIFY_PRIVATE_LATEX_COMPILER_SANDBOX"
POLL_SECONDS = 0.5
EVIDENCE_PATH = Path(
    "/var/lib/paperswithcode/staging/latex-compiler-qualification.json"
)
_CANCELLATION_BUNDLE = qualification_cases()[0].bundle
_OPERATIONAL_CHECKS = ("health", "metrics", "image-isolation")
_RECOVERY_CHECKS = ("restart", "reconciliation")


class SandboxQualificationTransport(LatexCompilerTransport, Protocol):
    """Additional content-free observations exposed only by the Sandbox client."""

    image: str

    def health(self, job_id: str) -> dict[str, object]: ...

    def metrics(self, job_id: str) -> dict[str, object]: ...

    def isolation(self, job_id: str) -> dict[str, object]: ...

    def reconnect_after_restart(
        self,
        *,
        job_id: str,
        provider_job_id: str,
        bundle: bytes,
        entrypoint: str,
    ): ...


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _check(name: str, *, expected: str = "passed") -> QualificationCase:
    return QualificationCase(name=name, bundle=b"", expected=expected)


def run_case(
    case: QualificationCase, compiler: LatexCompilerTransport
) -> tuple[str, int]:
    """Submit one fixed synthetic case without printing its source or handle."""
    job_id = str(uuid.uuid4())
    started = time.monotonic()
    try:
        status = compiler.submit(
            job_id=job_id, bundle=case.bundle, entrypoint="main.tex"
        )
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 422:
            return "rejected", _elapsed_ms(started)
        raise
    deadline = time.monotonic() + 135
    while time.monotonic() < deadline:
        if status.state in {
            CompilerJobState.SUCCEEDED,
            CompilerJobState.FAILED,
            CompilerJobState.CANCELED,
        }:
            # Read and validate the terminal response so the disposable VM is
            # released by the transport. Do not expose its content.
            compiler.result(job_id)
            return status.state.value, _elapsed_ms(started)
        time.sleep(POLL_SECONDS)
        status = compiler.status(job_id)
    try:
        compiler.cancel(job_id)
    except (httpx.HTTPError, RuntimeError):
        pass
    return "timeout", _elapsed_ms(started)


def run_cancellation_case(compiler: LatexCompilerTransport) -> tuple[str, int]:
    """Exercise immediate, idempotent disposal using an empty synthetic archive."""
    job_id = str(uuid.uuid4())
    started = time.monotonic()
    compiler.submit(job_id=job_id, bundle=_CANCELLATION_BUNDLE, entrypoint="main.tex")
    status = compiler.cancel(job_id)
    return status.state.value, _elapsed_ms(started)


def run_operational_checks(
    compiler: SandboxQualificationTransport,
) -> list[tuple[QualificationCase, str, int]]:
    """Check the content-free health, metrics, and per-job isolation snapshots."""
    job_id = str(uuid.uuid4())
    started = time.monotonic()
    outcomes = {name: "failed" for name in _OPERATIONAL_CHECKS}
    try:
        compiler.submit(
            job_id=job_id, bundle=_CANCELLATION_BUNDLE, entrypoint="main.tex"
        )
        health = compiler.health(job_id)
        metrics = compiler.metrics(job_id)
        isolation = compiler.isolation(job_id)
        outcomes["health"] = (
            "passed"
            if health.get("status") == "ready"
            and health.get("qualified_image") == compiler.image
            and health.get("network_isolation") == "sandbox-netns-v1"
            else "failed"
        )
        outcomes["metrics"] = (
            "passed"
            if {
                "capacity",
                "queue_depth",
                "active",
                "retained_jobs",
                "outcomes",
                "failure_categories",
                "latency_ms",
            }
            <= metrics.keys()
            else "failed"
        )
        outcomes["image-isolation"] = (
            "passed"
            if isolation
            == {
                "image": compiler.image,
                "forward_hf_token": False,
                "secrets": False,
                "volumes": False,
                "network_isolation": "sandbox-netns-v1",
            }
            else "failed"
        )
    except (httpx.HTTPError, RuntimeError, ValueError):
        pass
    finally:
        try:
            compiler.cancel(job_id)
        except (httpx.HTTPError, RuntimeError):
            pass
    elapsed = _elapsed_ms(started)
    return [(_check(name), outcomes[name], elapsed) for name in _OPERATIONAL_CHECKS]


def run_restart_reconciliation_checks(
    compiler: SandboxQualificationTransport,
) -> list[tuple[QualificationCase, str, int]]:
    """Exercise the same reconnect operation used after a backend restart."""
    job_id = str(uuid.uuid4())
    started = time.monotonic()
    outcomes = {name: "failed" for name in _RECOVERY_CHECKS}
    try:
        submitted = compiler.submit(
            job_id=job_id, bundle=_CANCELLATION_BUNDLE, entrypoint="main.tex"
        )
        provider_job_id = submitted.provider_job_id
        if provider_job_id:
            restarted = compiler.reconnect_after_restart(
                job_id=job_id,
                provider_job_id=provider_job_id,
                bundle=_CANCELLATION_BUNDLE,
                entrypoint="main.tex",
            )
            outcomes["restart"] = (
                "passed" if restarted.provider_job_id == provider_job_id else "failed"
            )
            reconciled = compiler.status(job_id)
            outcomes["reconciliation"] = (
                "passed"
                if outcomes["restart"] == "passed"
                and reconciled.job_id == job_id
                and reconciled.provider_job_id == provider_job_id
                else "failed"
            )
    except (AttributeError, httpx.HTTPError, RuntimeError, ValueError):
        pass
    finally:
        try:
            compiler.cancel(job_id)
        except (httpx.HTTPError, RuntimeError):
            pass
    elapsed = _elapsed_ms(started)
    return [(_check(name), outcomes[name], elapsed) for name in _RECOVERY_CHECKS]


def validate_settings(settings: Settings) -> None:
    """Ensure qualification cannot become accidental user-facing compiler work."""
    if settings.environment != "staging":
        raise RuntimeError("Qualification requires PWC_ENVIRONMENT=staging")
    if not settings.chat_latex_compiler_qualification_mode:
        raise RuntimeError("LaTeX Sandbox qualification mode is disabled")
    if settings.chat_latex_compiler_jobs_enabled or settings.chat_latex_paper_enabled:
        raise RuntimeError(
            "Keep paper and compiler job admission disabled for qualification"
        )
    if (
        settings.chat_artifacts_enabled
        or settings.chat_artifact_shared_preview_enabled
        or settings.chat_posterly_enabled
    ):
        raise RuntimeError(
            "Keep all user-facing artifact features disabled for qualification"
        )
    if (
        settings.chat_artifact_storage_backend != "hf_bucket"
        or not settings.chat_artifact_hf_bucket_id
    ):
        raise RuntimeError("Qualification requires the private artifact store")
    try:
        validate_staging_sandbox_compiler_identity(
            settings.chat_latex_compiler_hf_sandbox_image,
            settings.chat_latex_compiler_hf_sandbox_namespace,
        )
    except EnvelopeError as error:
        raise RuntimeError(
            "Qualification requires an immutable Sandbox image"
        ) from error


def qualification_evidence(
    results: Sequence[tuple[QualificationCase, str, int]], *, image: str
) -> dict[str, object]:
    """Build the host-gated evidence without source, logs, IDs, or credentials."""
    summary = report(list(results))
    outcomes = {case.name: outcome == case.expected for case, outcome, _ in results}
    hostile_names = {case.name for case in qualification_cases()}
    checks = {
        "hostile_input": all(outcomes.get(name, False) for name in hostile_names),
        "cancellation": outcomes.get("cancellation", False),
        "health": outcomes.get("health", False),
        "metrics": outcomes.get("metrics", False),
        "image_isolation": outcomes.get("image-isolation", False),
        "restart": outcomes.get("restart", False),
        "reconciliation": outcomes.get("reconciliation", False),
    }
    return {
        "schema_version": 1,
        "environment": "staging",
        "compiler_image": image,
        "passed": summary["passed"],
        "total": summary["total"],
        "checks": checks,
    }


def _require_root_evidence_writer() -> None:
    if os.geteuid() != 0:
        raise PermissionError("Qualification evidence must be written by root")


def _require_trusted_evidence_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory_stat = path.parent.lstat()
    if (
        not stat.S_ISDIR(directory_stat.st_mode)
        or directory_stat.st_uid != 0
        or stat.S_IMODE(directory_stat.st_mode) & 0o077
    ):
        raise PermissionError("Qualification evidence directory is not root-only")


def write_qualification_evidence(
    payload: dict[str, object], path: Path = EVIDENCE_PATH
) -> None:
    """Atomically replace root-owned qualification evidence with mode 0600."""
    _require_root_evidence_writer()
    _require_trusted_evidence_directory(path)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as evidence:
            evidence.write(encoded)
            evidence.flush()
            os.fsync(evidence.fileno())
        os.replace(temporary, path)
        evidence_stat = path.lstat()
        if (
            not stat.S_ISREG(evidence_stat.st_mode)
            or stat.S_IMODE(evidence_stat.st_mode) != 0o600
            or evidence_stat.st_uid != 0
            or evidence_stat.st_nlink != 1
        ):
            raise PermissionError("Qualification evidence ownership is not trusted")
    finally:
        temporary.unlink(missing_ok=True)


def invalidate_qualification_evidence(path: Path = EVIDENCE_PATH) -> None:
    """Remove prior approval before a full rerun can leave stale passing evidence."""
    _require_root_evidence_writer()
    _require_trusted_evidence_directory(path)
    path.unlink(missing_ok=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--evidence-path", type=Path, default=EVIDENCE_PATH)
    parser.add_argument("--no-write-evidence", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"Pass --confirm {CONFIRMATION}")
    settings: Settings = get_settings()
    try:
        validate_settings(settings)
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    if not args.case and not args.no_write_evidence:
        try:
            invalidate_qualification_evidence(args.evidence_path)
        except OSError:
            raise SystemExit("Sandbox qualification evidence is unavailable") from None
    try:
        compiler = compiler_transport_from_settings(settings)
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    selected = [
        case
        for case in qualification_cases()
        if not args.case or case.name in args.case
    ]
    if not selected or (args.case and len(selected) != len(set(args.case))):
        raise SystemExit("Select one or more known qualification cases")
    try:
        results = [(case, *run_case(case, compiler)) for case in selected]
        if not args.case:
            results.append(
                (
                    _check("cancellation", expected="canceled"),
                    *run_cancellation_case(compiler),
                )
            )
            results.extend(run_operational_checks(compiler))
            results.extend(run_restart_reconciliation_checks(compiler))
    except (EnvelopeError, httpx.HTTPError, OSError, RuntimeError):
        raise SystemExit("Sandbox qualification failed") from None
    payload = report(results)
    if not args.case and not args.no_write_evidence:
        try:
            write_qualification_evidence(
                qualification_evidence(results, image=compiler.image),
                args.evidence_path,
            )
        except OSError:
            raise SystemExit("Sandbox qualification evidence write failed") from None
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["passed"] == payload["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
