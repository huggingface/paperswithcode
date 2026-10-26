#!/usr/bin/env python3
"""Guarded staging-only external Pi shadow activation and rollback helper."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import os
import pwd
import secrets
import stat
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

try:
    from deploy import build_sandbox
    from deploy.external_pi_slot_topology import replica_specs
except ModuleNotFoundError:
    import build_sandbox  # type: ignore[no-redef]
    from external_pi_slot_topology import replica_specs  # type: ignore[no-redef]

APP_ROOT = Path("/srv/paperswithcode")
CONFIG_ROOT = Path("/etc/paperswithcode")

SHADOW_FLAGS = {
    "PWC_CHAT_EXTERNAL_PI_SHADOW_ENABLED",
    "PWC_CHAT_EXTERNAL_PI_SUPERVISOR_ENABLED",
}
INERT_FLAGS = {
    "PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED",
    "PWC_CHAT_REMOTE_WORKSPACE_TOOLS_ENABLED",
    "PWC_CHAT_SANDBOX_EXECUTOR_ENABLED",
    "PWC_CHAT_REMOTE_BASH_ENABLED",
    "PWC_CHAT_REMOTE_READ_ENABLED",
    "PWC_CHAT_LAZY_WORKSPACE_ENABLED",
}
REQUIRED_CASES = {
    "linear_history",
    "branching_history",
    "tool_history",
    "eight_isolated_sessions",
    "capacity_no_queue",
    "restart_after_lease_expiry",
    "stale_generation_fencing",
    "drain_recovery",
    "zero_external_work",
}
TOKEN_KEY = "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN"
REPORT_MAX_AGE_MS = 5 * 60 * 1000
REPORT_MAX_DURATION_MS = 10 * 60 * 1000


class ShadowActivationError(RuntimeError):
    """The operator request did not prove a safe staging shadow transition."""


class ShadowActivationInterrupted(BaseException):
    """A normal process signal interrupted the guarded activation transaction."""

    def __init__(self, signal_number: int):
        super().__init__(
            f"external Pi activation interrupted by signal {signal_number}"
        )
        self.signal_number = signal_number


class ShadowActivationRecoveryRequired(ShadowActivationError):
    """An interrupted partial disable requires an explicit guarded retry."""


def _lifecycle_modules():
    """Load lifecycle modules from either source or installed flat layout."""
    if __package__ in {None, ""}:
        lifecycle = importlib.import_module("external_pi_slot_lifecycle")
        runtime = importlib.import_module("runtime")
    else:
        lifecycle = importlib.import_module("deploy.external_pi_slot_lifecycle")
        runtime = importlib.import_module("deploy.runtime")
    return lifecycle, runtime


@contextlib.contextmanager
def activation_signal_context():
    """Turn normal CLI termination signals into exceptions during the transaction."""
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("activation signal handlers require the main thread")
    watched = (signal.SIGTERM, signal.SIGINT)
    previous = {number: signal.getsignal(number) for number in watched}
    original_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
    interrupted = False

    def interrupt(signal_number, _frame):
        nonlocal interrupted
        if interrupted:
            return
        interrupted = True
        signal.pthread_sigmask(signal.SIG_BLOCK, watched)
        raise ShadowActivationInterrupted(signal_number)

    try:
        for number in watched:
            signal.signal(number, interrupt)
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK, watched)
        try:
            for number, handler in previous.items():
                signal.signal(number, handler)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, original_mask)


@contextlib.contextmanager
def _activation_signals_blocked():
    """Defer normal termination while publishing an already-proven safe state."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    watched = (signal.SIGTERM, signal.SIGINT)
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, watched)
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


@dataclass(frozen=True, slots=True)
class QualificationEvidence:
    worker_id: str
    initial_generation: int
    restarted_generation: int
    recovery_generation: int
    stale_fenced: bool
    drain_recovered: bool
    nonce: str


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ShadowActivationError("protected environment is malformed")
        key, value = line.split("=", 1)
        if not key or key in values:
            raise ShadowActivationError("protected environment is malformed")
        values[key] = value
    return values


def _atomic_write(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _validate_worker_environment(values: dict[str, str]) -> None:
    if set(values) - {TOKEN_KEY, "PWC_CHAT_PWC_MCP_ENABLED"}:
        raise ShadowActivationError(
            "external Pi worker environment has unapproved keys"
        )
    if values.get("PWC_CHAT_PWC_MCP_ENABLED", "false") not in {"true", "false"}:
        raise ShadowActivationError("external Pi MCP flag must be true or false")


def _ensure_worker_environment(path: Path, token: str) -> None:
    existing = _read_env(path)
    _validate_worker_environment(existing)
    existing_token = existing.get(TOKEN_KEY)
    if existing_token and existing_token != token:
        raise ShadowActivationError("external Pi worker token environments disagree")
    if len(token) < 32 or any(character in token for character in "\r\n\0"):
        raise ShadowActivationError("external Pi worker token is invalid")
    existing[TOKEN_KEY] = token
    content = "".join(f"{key}={value}\n" for key, value in sorted(existing.items()))
    _atomic_write(path, content.encode(), 0o640)


@contextlib.contextmanager
def temporary_worker_token_file(token: str, directory: Path):
    if len(token) < 32 or any(character in token for character in "\r\n\0"):
        raise ShadowActivationError("external Pi worker token is invalid")
    descriptor, name = tempfile.mkstemp(
        prefix=".external-pi-shadow-token-", dir=directory
    )
    path = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"{TOKEN_KEY}={token}\n")
            handle.flush()
            os.fsync(handle.fileno())
        yield path
    finally:
        path.unlink(missing_ok=True)


MAX_REPORT_BYTES = 1024 * 1024


def _read_untrusted_report(path: Path) -> bytes:
    """Read a report written by an unprivileged process without following links."""

    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_REPORT_BYTES:
            raise ShadowActivationError("qualification report is not a bounded file")
        return handle.read(MAX_REPORT_BYTES + 1)[:MAX_REPORT_BYTES]


def run_temporary_shadow_qualification(
    *,
    environment: str,
    slot: str,
    release_id: str,
    report_path: Path,
    worker_id: str | None = None,
    start: Callable[[str, str], None] | None = None,
    authenticated: Callable[[str, str, str], int] | None = None,
    qualify: Callable[[QualificationEvidence, Path], None],
    expire_and_restart: Callable[[str, str, str, int], int] | None = None,
    stale_probe: Callable[[str, int, int], bool] | None = None,
    stop: Callable[[str, str, str], None] | None = None,
    leave_recovery_running: bool = False,
) -> QualificationEvidence:
    """Qualify one slot, stopping it unless its final recovery must remain live."""

    if environment != "staging":
        raise ShadowActivationError("temporary shadow qualification is staging-only")
    if slot not in {"blue", "green"}:
        raise ShadowActivationError("temporary shadow qualification slot is invalid")
    resolved_worker_id = worker_id or f"staging-{slot}"
    if not resolved_worker_id.startswith(f"staging-{slot}"):
        raise ShadowActivationError("temporary shadow qualification worker is invalid")
    if start is None or authenticated is None or stop is None:
        lifecycle, _runtime = _lifecycle_modules()
        start = start or lifecycle.start_slot
        authenticated = authenticated or lifecycle.qualify_candidate
        expire_and_restart = (
            expire_and_restart or lifecycle.restart_supervisor_after_lease_expiry
        )
        stop = stop or lifecycle.stop_slot
    if expire_and_restart is None or stale_probe is None:
        raise ShadowActivationError("qualification lifecycle probes are required")
    cleanup_owned = False
    qualified = False
    try:
        cleanup_owned = True
        stop(environment, slot, release_id)
        start(environment, slot)
        initial = authenticated(environment, slot, release_id)
        restarted = expire_and_restart(environment, slot, release_id, initial)
        if restarted <= initial:
            raise ShadowActivationError(
                "lease-expiry restart did not advance generation"
            )
        stale_fenced = stale_probe(resolved_worker_id, initial, restarted)
        if stale_fenced is not True:
            raise ShadowActivationError("stale generation was not durably fenced")
        stop(environment, slot, release_id)
        start(environment, slot)
        recovery = authenticated(environment, slot, release_id)
        if recovery <= restarted:
            raise ShadowActivationError("drain recovery did not advance generation")
        evidence = QualificationEvidence(
            worker_id=resolved_worker_id,
            initial_generation=initial,
            restarted_generation=restarted,
            recovery_generation=recovery,
            stale_fenced=stale_fenced,
            drain_recovered=True,
            nonce=secrets.token_urlsafe(32),
        )
        qualify(evidence, report_path)
        qualified = True
        return evidence
    finally:
        if cleanup_owned and not (qualified and leave_recovery_running):
            stop(environment, slot, release_id)


def _validate_report(
    path: Path,
    release_id: str,
    evidence: QualificationEvidence,
    *,
    now_unix_ms: int | None = None,
) -> None:
    if not path.is_file():
        raise ShadowActivationError("successful qualification report is required")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ShadowActivationError(
            "successful qualification report is invalid"
        ) from error
    if not isinstance(report, dict):
        raise ShadowActivationError("successful qualification report is invalid")
    cases = report.get("cases")
    counts = report.get("external_work_counts")
    now = int(time.time() * 1000) if now_unix_ms is None else now_unix_ms
    if (
        set(report)
        != {
            "release_id",
            "worker_id",
            "worker_generation",
            "qualification_nonce",
            "qualified_at_unix_ms",
            "passed",
            "case_count",
            "duration_ms",
            "external_work_counts",
            "cases",
        }
        or report.get("release_id") != release_id
        or report.get("worker_id") != evidence.worker_id
        or type(report.get("worker_generation")) is not int
        or report["worker_generation"] != evidence.recovery_generation
        or report.get("qualification_nonce") != evidence.nonce
        or type(report.get("qualified_at_unix_ms")) is not int
        or not now - REPORT_MAX_AGE_MS <= report["qualified_at_unix_ms"] <= now + 30_000
        or report.get("passed") is not True
        or type(report.get("case_count")) is not int
        or report["case_count"] != len(REQUIRED_CASES)
        or type(report.get("duration_ms")) is not int
        or not 0 <= report["duration_ms"] <= REPORT_MAX_DURATION_MS
        or not isinstance(cases, list)
        or len(cases) != len(REQUIRED_CASES)
        or not all(
            isinstance(case, dict)
            and set(case) == {"name", "passed", "count", "duration_ms", "failure_code"}
            for case in cases
        )
        or {case.get("name") for case in cases if isinstance(case, dict)}
        != REQUIRED_CASES
        or any(
            case.get("passed") is not True
            or case.get("failure_code") is not None
            or type(case.get("count")) is not int
            or case["count"] < 0
            or type(case.get("duration_ms")) is not int
            or not 0 <= case["duration_ms"] <= REPORT_MAX_DURATION_MS
            for case in cases
            if isinstance(case, dict)
        )
        or not isinstance(counts, dict)
        or set(counts)
        != {
            "shadow_requests",
            "model_calls",
            "tool_calls",
            "provider_calls",
            "modal_calls",
            "billing_events",
        }
        or type(counts.get("shadow_requests")) is not int
        or not 0 < counts["shadow_requests"] <= 1_000_000
        or any(
            type(counts.get(key)) is not int or counts[key] != 0
            for key in (
                "model_calls",
                "tool_calls",
                "provider_calls",
                "modal_calls",
                "billing_events",
            )
        )
    ):
        raise ShadowActivationError("successful qualification is not proven")


def _current_release(app_root: Path) -> tuple[str, str]:
    current = app_root / "environments/staging/current"
    if not current.is_symlink():
        raise ShadowActivationError("exact current release is unavailable")
    try:
        manifest = json.loads(
            (current.resolve(strict=True) / "release.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        raise ShadowActivationError("exact current release is invalid") from error
    release_id, git_sha = manifest.get("release_id"), manifest.get("git_sha")
    if (
        not isinstance(release_id, str)
        or not release_id
        or not isinstance(git_sha, str)
        or len(git_sha) != 40
        or any(character not in "0123456789abcdef" for character in git_sha)
    ):
        raise ShadowActivationError("exact current release is invalid")
    return release_id, git_sha


def refresh_command(environment: str, git_sha: str) -> list[str]:
    return ["pwc-deploy", environment, git_sha, "--refresh-environment"]


def _unit_is_inactive(unit: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "show", "--property=ActiveState", "--value", unit],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0 and result.stdout.strip() in {"inactive", "failed"}


def deactivate_external_pi_slots(
    release_id: str,
    *,
    active_slot: str,
    resolve: Callable[[str, str], object],
    stop: Callable[[str, str, str], None],
    unit_inactive: Callable[[str], bool] = _unit_is_inactive,
) -> None:
    """Prove both exact units inactive for every slot, even if resolution fails."""
    stopped_current = False
    for slot in ("blue", "green"):
        try:
            resolved = resolve("staging", slot)
        except (OSError, ValueError):
            resolved = None
        if resolved is not None:
            stop("staging", slot, resolved.release_id)
            stopped_current |= resolved.release_id == release_id
        supervisor = f"paperswithcode-staging-external-pi@{slot}.service"
        worker = f"paperswithcode-staging-external-pi-worker@{slot}.service"
        if not unit_inactive(supervisor) or not unit_inactive(worker):
            raise ShadowActivationError(f"external Pi {slot} units remain active")
        if slot == active_slot:
            stopped_current = True
    if not stopped_current:
        raise ShadowActivationError("exact current external Pi units were not stopped")


def apply_staging_shadow_activation(
    *,
    environment: str,
    expected_release_id: str,
    report_path: Path,
    enabled: bool,
    app_root: Path = APP_ROOT,
    config_root: Path = CONFIG_ROOT,
    qualify: Callable[[str, str, Path, bool], QualificationEvidence] | None,
    deactivate: Callable[[str, str], None] | None,
    refresh: Callable[[str], None],
) -> dict[str, object]:
    if environment != "staging":
        raise ShadowActivationError("external Pi shadow activation is staging-only")
    current_release_id, git_sha = _current_release(app_root)
    if current_release_id != expected_release_id:
        raise ShadowActivationError("expected release is not the exact current release")
    staging_path = config_root / "staging.env"
    if not staging_path.is_file():
        raise ShadowActivationError("protected staging environment is missing")
    original = staging_path.read_bytes()
    worker_path = config_root / "external-pi-worker.env"
    original_worker = worker_path.read_bytes() if worker_path.is_file() else None
    values = _read_env(staging_path)
    lifecycle_values = {key: values.get(key, "false").lower() for key in SHADOW_FLAGS}
    if (
        set(lifecycle_values.values()) - {"true", "false"}
        or len(set(lifecycle_values.values())) != 1
    ):
        raise ShadowActivationError(
            "shadow and supervisor flags are invalid or disagree"
        )
    if enabled and set(lifecycle_values.values()) != {"false"}:
        raise ShadowActivationError("bootstrap requires shadow lifecycle flags false")
    worker_values = _read_env(worker_path)
    _validate_worker_environment(worker_values)
    staging_token = values.get(TOKEN_KEY, "")
    worker_token = worker_values.get(TOKEN_KEY, "")
    if staging_token and worker_token and staging_token != worker_token:
        raise ShadowActivationError("external Pi worker token environments disagree")
    token = staging_token or worker_token or secrets.token_urlsafe(48)
    values[TOKEN_KEY] = token
    values.update({key: "false" for key in SHADOW_FLAGS})
    values.update({key: "false" for key in INERT_FLAGS})
    rendered = "".join(f"{key}={value}\n" for key, value in sorted(values.items()))
    proven_stopped = False
    refresh_started = False
    refresh_complete = False
    try:
        if not enabled:
            if deactivate is None:
                raise ShadowActivationError(
                    "disabled shadow lifecycle requires integrated proven stop"
                )
            deactivate(current_release_id, git_sha)
            proven_stopped = True
        _ensure_worker_environment(worker_path, token)
        _atomic_write(staging_path, rendered.encode(), 0o640)
        if enabled:
            if qualify is None:
                raise ShadowActivationError(
                    "enabled bootstrap requires an integrated qualification"
                )
            report_path.unlink(missing_ok=True)
            evidence = qualify(current_release_id, git_sha, report_path, False)
            _validate_report(report_path, current_release_id, evidence)
            values.update({key: "true" for key in SHADOW_FLAGS})
            rendered = "".join(
                f"{key}={value}\n" for key, value in sorted(values.items())
            )
            _atomic_write(staging_path, rendered.encode(), 0o640)
        refresh_started = True
        refresh(git_sha)
        refresh_complete = True
        if enabled:
            report_path.unlink(missing_ok=True)
            final_evidence = qualify(current_release_id, git_sha, report_path, True)
            _validate_report(report_path, current_release_id, final_evidence)
    except BaseException as error:
        # A handled termination signal may arrive after refresh side effects but
        # before the call returns and ``refresh_complete`` can be published.
        # Conservatively inspect/drain both slots for that case; ordinary deploy
        # failures retain the deploy command's own pointer/service rollback.
        if enabled and (
            refresh_complete
            or (refresh_started and isinstance(error, ShadowActivationInterrupted))
        ):
            if deactivate is None:
                raise ShadowActivationRecoveryRequired(
                    "final active worker qualification failed while lifecycle "
                    "remains enabled; guarded disable is required"
                ) from error
            with _activation_signals_blocked():
                try:
                    deactivate(current_release_id, git_sha)
                except BaseException as cleanup_error:
                    raise ShadowActivationRecoveryRequired(
                        "final active worker qualification failed and exact-evidence "
                        "deactivation did not complete; guarded disable is required"
                    ) from cleanup_error
                values.update({key: "false" for key in SHADOW_FLAGS})
                rendered = "".join(
                    f"{key}={value}\n" for key, value in sorted(values.items())
                )
                _atomic_write(staging_path, rendered.encode(), 0o640)
                _ensure_worker_environment(worker_path, token)
                try:
                    refresh(git_sha)
                except BaseException as refresh_error:
                    raise ShadowActivationError(
                        "final active worker qualification failed; external Pi units "
                        "were proven stopped and flags remain disabled after refresh failure"
                    ) from refresh_error
            raise
        if not enabled and not proven_stopped:
            _atomic_write(staging_path, original, 0o640)
            if original_worker is None:
                worker_path.unlink(missing_ok=True)
            else:
                _atomic_write(worker_path, original_worker, 0o640)
            raise ShadowActivationRecoveryRequired(
                "external Pi disable was interrupted before all units proved "
                "inactive; prior lifecycle flags were preserved and guarded "
                "disable must be retried"
            ) from error
        if proven_stopped:
            _atomic_write(staging_path, rendered.encode(), 0o640)
            _ensure_worker_environment(worker_path, token)
            if isinstance(error, Exception):
                raise ShadowActivationError(
                    "external Pi units were proven stopped; flags remain disabled "
                    "after refresh failure"
                ) from error
            raise
        _atomic_write(staging_path, original, 0o640)
        if original_worker is None:
            worker_path.unlink(missing_ok=True)
        else:
            _atomic_write(worker_path, original_worker, 0o640)
        raise
    return {"release_id": current_release_id, "enabled": enabled}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("environment", choices=("staging", "production"))
    parser.add_argument("mode", choices=("enable", "disable"))
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--report", type=Path, default=Path("/dev/null"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo")

    def refresh(sha: str) -> None:
        subprocess.run(refresh_command(args.environment, sha), check=True)

    def active_slot() -> str:
        active = APP_ROOT / "environments/staging/active"
        if not active.is_symlink():
            raise ShadowActivationError("staging active slot is unavailable")
        target = active.resolve(strict=False)
        slots = APP_ROOT / "environments/staging/slots"
        slot = next(
            (
                name
                for name in ("blue", "green")
                if target == (slots / name).resolve(strict=False)
            ),
            None,
        )
        if slot is None:
            raise ShadowActivationError("staging active slot is invalid")
        return slot

    def qualify(
        release_id: str,
        _sha: str,
        report_path: Path,
        leave_recovery_running: bool,
    ) -> QualificationEvidence:
        slot = active_slot()
        lifecycle, runtime = _lifecycle_modules()

        token = _read_env(CONFIG_ROOT / "staging.env").get(TOKEN_KEY, "")
        resolved = lifecycle.resolve_external_pi_replicas("staging", slot, token)[0]
        replica = replica_specs("staging", slot, token)[0]
        if replica.worker_id != resolved.worker_id or replica.port != resolved.port:
            raise ShadowActivationError("external Pi replica topology is inconsistent")
        release = (APP_ROOT / "environments/staging/current").resolve(strict=True)
        python = APP_ROOT / "runtimes" / runtime.runtime_id(release) / "bin/python"

        def stale_probe(worker_id: str, stale: int, current: int) -> bool:
            subprocess.run(
                [
                    "systemd-run",
                    "--quiet",
                    "--wait",
                    "--pipe",
                    "--collect",
                    "--uid=pwc-staging",
                    "--gid=pwc-staging",
                    f"--working-directory={release}",
                    "--property=EnvironmentFile=/etc/paperswithcode/staging.env",
                    str(python),
                    "-m",
                    "backend.scripts.qualify_external_pi_registry",
                    "--environment",
                    "staging",
                    "--worker-id",
                    worker_id,
                    "--release-id",
                    release_id,
                    "--stale-generation",
                    str(stale),
                    "--current-generation",
                    str(current),
                ],
                check=True,
            )
            return True

        def command(evidence: QualificationEvidence, destination: Path) -> None:
            # The qualifier is release code: run it as pwc-staging (like the
            # stale probe above), never as root. It gets only its token file
            # and a private directory for its report.
            account = pwd.getpwnam("pwc-staging")
            with (
                temporary_worker_token_file(replica.token, CONFIG_ROOT) as token_file,
                tempfile.TemporaryDirectory(prefix="pwc-shadow-report-") as scratch,
            ):
                os.chown(token_file, account.pw_uid, account.pw_gid)
                os.chown(scratch, account.pw_uid, account.pw_gid)
                report = Path(scratch) / "report.json"
                subprocess.run(
                    build_sandbox.command_as(
                        "pwc-staging",
                        [
                            str(python),
                            "-m",
                            "backend.scripts.qualify_external_pi_shadow",
                            "--environment",
                            "staging",
                            "--app-root",
                            str(APP_ROOT),
                            "--release-dir",
                            str(release),
                            "--worker-url",
                            f"http://127.0.0.1:{resolved.port}",
                            "--worker-id",
                            resolved.worker_id,
                            "--expected-generation",
                            str(evidence.recovery_generation),
                            "--initial-generation",
                            str(evidence.initial_generation),
                            "--restarted-generation",
                            str(evidence.restarted_generation),
                            "--stale-fenced",
                            "--drain-recovered",
                            "--qualification-nonce",
                            evidence.nonce,
                            "--token-file",
                            str(token_file),
                            "--prompt-file",
                            str(resolved.prompt),
                            "--report",
                            str(report),
                        ],
                    ),
                    cwd=release,
                    env={"PATH": os.defpath, "LANG": "C.UTF-8", "HOME": "/nonexistent"},
                    check=True,
                )
                with open(destination, "wb") as handle:
                    handle.write(_read_untrusted_report(report))

        return run_temporary_shadow_qualification(
            environment="staging",
            slot=slot,
            release_id=release_id,
            report_path=report_path,
            worker_id=resolved.worker_id,
            qualify=command,
            stale_probe=stale_probe,
            leave_recovery_running=leave_recovery_running,
        )

    def deactivate(release_id: str, _sha: str) -> None:
        lifecycle, _runtime = _lifecycle_modules()

        deactivate_external_pi_slots(
            release_id,
            active_slot=active_slot(),
            resolve=lifecycle.resolve_external_pi_slot,
            stop=lifecycle.stop_slot,
        )

    with activation_signal_context():
        result = apply_staging_shadow_activation(
            environment=args.environment,
            expected_release_id=args.release_id,
            report_path=args.report,
            enabled=args.mode == "enable",
            qualify=qualify if args.mode == "enable" else None,
            deactivate=deactivate,
            refresh=refresh,
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
