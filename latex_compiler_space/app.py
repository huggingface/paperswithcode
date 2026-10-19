"""Stateless, serialized compiler API for one per-job compiler sandbox."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import re
import signal
import stat
import subprocess
import tempfile
import threading
import time
import zipfile
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException, status

from latex_compiler_contract import (
    MAX_SOURCE_BYTES,
    CompilerDiagnostic,
    CompilerEnvelope,
    CompilerJobState,
    CompilerResult,
    CompilerStatus,
    CompileSubmission,
    EnvelopeError,
    SANDBOX_WORKSPACE_ISOLATION_ATTESTATION,
    SANDBOX_WORKSPACE_LIMIT_BYTES,
    validate_qualified_compiler_image,
    validate_public_key,
    validate_result,
    verify_envelope,
)

logger = logging.getLogger(__name__)
_SAFE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,299}$")
_ALLOWED_SUFFIXES = {".tex", ".bib", ".png", ".jpg", ".jpeg", ".pdf"}
_ERROR = re.compile(r"^! (?P<message>.+)$", re.MULTILINE)
_LINE = re.compile(r"^l\.(?P<line>\d+)\s*(?P<message>.*)$", re.MULTILINE)
_WARNING = re.compile(r"^LaTeX Warning: (?P<message>.+)$", re.MULTILINE)
_TEX_SOURCE = re.compile(
    r"\((?P<file>(?:\./)?[A-Za-z0-9][A-Za-z0-9._/-]{0,299}\.(?:tex|bib))(?=[\s)])"
)
ENGINE_VERSION = os.environ.get("PWC_LATEX_COMPILER_ENGINE", "pdfLaTeX")
NETWORK_ISOLATION_ATTESTATION = "sandbox-netns-v1"
WORKSPACE_LIMIT_BYTES = SANDBOX_WORKSPACE_LIMIT_BYTES


class BundleError(ValueError):
    pass


Compiler = Callable[[CompilerEnvelope, bytes], Awaitable[CompilerResult]]


@dataclass
class _Job:
    envelope: CompilerEnvelope
    bundle: bytes
    state: CompilerJobState = CompilerJobState.QUEUED
    result: CompilerResult | None = None

    def status(self) -> CompilerStatus:
        return CompilerStatus(job_id=self.envelope.job_id, state=self.state)

    def has_same_submission(self, envelope: CompilerEnvelope) -> bool:
        return (
            self.envelope.source_digest == envelope.source_digest
            and self.envelope.source_bytes == envelope.source_bytes
            and self.envelope.entrypoint == envelope.entrypoint
            and self.envelope.limits == envelope.limits
            and self.envelope.contract_version == envelope.contract_version
        )


class JobManager:
    """In-memory queue intentionally keeps a single compiler active at a time."""

    def __init__(self, compiler: Compiler, *, compiler_image: str) -> None:
        self.compiler = compiler
        self.compiler_image = compiler_image
        self.jobs: dict[str, _Job] = {}
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.worker: asyncio.Task[None] | None = None
        self.outcomes: dict[str, int] = {
            state.value: 0
            for state in (
                CompilerJobState.SUCCEEDED,
                CompilerJobState.FAILED,
                CompilerJobState.CANCELED,
            )
        }
        self.failure_categories: dict[str, int] = {}
        self.completed_latency_ms: list[int] = []

    async def start(self) -> None:
        self.worker = asyncio.create_task(self._work())

    async def stop(self) -> None:
        shutdown = getattr(self.compiler, "shutdown", None)
        if shutdown is not None:
            shutdown()
        if self.worker is not None:
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass

    async def submit(self, envelope: CompilerEnvelope, bundle: bytes) -> CompilerStatus:
        existing = self.jobs.get(envelope.job_id)
        if existing is not None:
            if not existing.has_same_submission(envelope):
                raise BundleError("Job ID conflicts with an existing submission")
            return existing.status()
        job = _Job(envelope=envelope, bundle=bundle)
        self.jobs[envelope.job_id] = job
        self.queue.put_nowait(envelope.job_id)
        logger.info("latex_compiler_event event=queued")
        return job.status()

    def status(self, job_id: str) -> CompilerStatus | None:
        job = self.jobs.get(job_id)
        return job.status() if job else None

    def result(self, job_id: str) -> CompilerResult | None:
        job = self.jobs.get(job_id)
        return job.result if job else None

    async def cancel(self, job_id: str) -> CompilerStatus | None:
        job = self.jobs.get(job_id)
        if job is None:
            return None
        if job.state in {CompilerJobState.QUEUED, CompilerJobState.COMPILING}:
            was_compiling = job.state == CompilerJobState.COMPILING
            job.state = CompilerJobState.CANCELED
            job.result = CompilerResult.canceled(
                job.envelope,
                compiler_image=self.compiler_image,
                engine_version=ENGINE_VERSION,
            )
            cancel = getattr(self.compiler, "cancel", None)
            if was_compiling and cancel is not None:
                cancel(job_id)
            self._record_result(job.result)
        return job.status()

    async def _work(self) -> None:
        while True:
            job_id = await self.queue.get()
            job = self.jobs[job_id]
            if job.state == CompilerJobState.CANCELED:
                continue
            job.state = CompilerJobState.COMPILING
            try:
                result = await self.compiler(job.envelope, job.bundle)
                validate_result(result, expected=job.envelope)
            except (EnvelopeError, OSError, RuntimeError, ValueError):
                logger.error("latex_compiler_event event=failed category=service_error")
                result = CompilerResult.failed(
                    job.envelope,
                    diagnostics=[
                        CompilerDiagnostic(
                            severity="error", message="The compiler service failed"
                        )
                    ],
                    log_tail="",
                    compiler_image=self.compiler_image,
                    engine_version=ENGINE_VERSION,
                    elapsed_ms=0,
                    failure_category="service_error",
                )
            if job.state != CompilerJobState.CANCELED:
                job.result = result
                job.state = result.state
                self._record_result(result)
                logger.info(
                    "latex_compiler_event event=completed state=%s category=%s",
                    result.state,
                    result.failure_category or "none",
                )

    def metrics(self) -> dict[str, object]:
        """Return a bounded, content-free operational snapshot."""
        latencies = self.completed_latency_ms[-100:]
        return {
            "capacity": 1,
            "queue_depth": self.queue.qsize(),
            "active": sum(
                job.state == CompilerJobState.COMPILING for job in self.jobs.values()
            ),
            "retained_jobs": len(self.jobs),
            "outcomes": self.outcomes.copy(),
            "failure_categories": self.failure_categories.copy(),
            "latency_ms": {
                "count": len(latencies),
                "max": max(latencies, default=0),
                "p50": sorted(latencies)[len(latencies) // 2] if latencies else 0,
            },
        }

    def _record_result(self, result: CompilerResult) -> None:
        self.outcomes[result.state.value] = self.outcomes.get(result.state.value, 0) + 1
        if result.failure_category is not None:
            self.failure_categories[result.failure_category] = (
                self.failure_categories.get(result.failure_category, 0) + 1
            )
        self.completed_latency_ms = (self.completed_latency_ms + [result.elapsed_ms])[
            -100:
        ]


class LatexCompilerRunner:
    """Runs a single constrained latexmk process in a freshly extracted root."""

    def __init__(
        self,
        *,
        compiler_image: str,
        network_isolation_required: bool = False,
    ) -> None:
        self.processes: dict[str, subprocess.Popen[bytes]] = {}
        self._canceled: set[str] = set()
        self._lock = threading.Lock()
        self.compiler_image = compiler_image
        self.network_isolation_required = network_isolation_required

    async def __call__(
        self, envelope: CompilerEnvelope, bundle: bytes
    ) -> CompilerResult:
        return await asyncio.to_thread(self._compile, envelope, bundle)

    def cancel(self, job_id: str) -> None:
        with self._lock:
            self._canceled.add(job_id)
            process = self.processes.get(job_id)
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)

    def shutdown(self) -> None:
        with self._lock:
            job_ids = tuple(self.processes)
        for job_id in job_ids:
            self.cancel(job_id)

    def _is_canceled(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._canceled

    def _compile(self, envelope: CompilerEnvelope, bundle: bytes) -> CompilerResult:
        started_at = time.monotonic()
        try:
            if self._is_canceled(envelope.job_id):
                with self._lock:
                    self._canceled.discard(envelope.job_id)
                return CompilerResult.canceled(
                    envelope,
                    compiler_image=self.compiler_image,
                    engine_version=ENGINE_VERSION,
                )
            with tempfile.TemporaryDirectory(prefix="pwc-latex-") as temporary:
                root = Path(temporary)
                _extract_bundle(bundle, root, envelope)
                workspace_root = root / ".workspace"
                result_root = root / ".results"
                workspace_root.mkdir(mode=0o700)
                result_root.mkdir(mode=0o700)
                process = subprocess.Popen(
                    self._command(
                        envelope,
                        source_root=root,
                        result_root=result_root,
                    ),
                    cwd=root,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                with self._lock:
                    self.processes[envelope.job_id] = process
                    canceled = envelope.job_id in self._canceled
                if canceled:
                    os.killpg(process.pid, signal.SIGKILL)
                try:
                    process.wait(timeout=envelope.limits.timeout_seconds)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    return _failed_result(
                        envelope,
                        _read_tail(
                            result_root / "compiler.log",
                            envelope.limits.max_log_bytes,
                        ),
                        started_at,
                        "Compilation exceeded its time limit",
                        compiler_image=self.compiler_image,
                        failure_category="timeout",
                    )
                finally:
                    with self._lock:
                        self.processes.pop(envelope.job_id, None)
                        canceled = envelope.job_id in self._canceled
                        self._canceled.discard(envelope.job_id)
                if canceled:
                    return CompilerResult.canceled(
                        envelope,
                        compiler_image=self.compiler_image,
                        engine_version=ENGINE_VERSION,
                    )
                log_path = result_root / "compiler.log"
                output = _read_tail(log_path, envelope.limits.max_log_bytes)
                if process.returncode != 0:
                    return _failed_result(
                        envelope,
                        output,
                        started_at,
                        None,
                        compiler_image=self.compiler_image,
                    )
                pdf_path = result_root / "output.pdf"
                if pdf_path.stat().st_size > envelope.limits.max_pdf_bytes:
                    return _failed_result(
                        envelope,
                        output,
                        started_at,
                        "Compiled PDF exceeds its limit",
                        compiler_image=self.compiler_image,
                        failure_category="resource_limit",
                    )
                pdf = pdf_path.read_bytes()
                return CompilerResult.succeeded(
                    envelope,
                    pdf=pdf,
                    log_tail=_log_tail(output, envelope.limits.max_log_bytes),
                    compiler_image=self.compiler_image,
                    engine_version=ENGINE_VERSION,
                    elapsed_ms=_elapsed_ms(started_at),
                    diagnostics=_diagnostics(output),
                )
        except BundleError as error:
            return _failed_result(
                envelope,
                b"",
                started_at,
                str(error),
                compiler_image=self.compiler_image,
                failure_category="invalid_bundle",
            )
        except (OSError, subprocess.SubprocessError):
            return _failed_result(
                envelope,
                b"",
                started_at,
                "Compiler execution failed",
                compiler_image=self.compiler_image,
                failure_category="execution_error",
            )

    def _command(
        self,
        envelope: CompilerEnvelope,
        *,
        source_root: Path | str,
        result_root: Path | str,
    ) -> list[str]:
        command = [
            "prlimit",
            "--cpu=120:120",
            "--as=1073741824:1073741824",
            "--fsize=26214400:26214400",
            "--nofile=64:64",
            "--nproc=16:16",
            "--",
            "latexmk",
            "-norc",
            "-pdf",
            "-bibtex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-no-shell-escape",
            envelope.entrypoint,
        ]
        workspace_root = Path(source_root) / ".workspace"
        return workspace_isolation_command(
            network_isolation=self.network_isolation_required
        ) + [
            "python3",
            "/app/latex_compiler_space/workspace_runner.py",
            "--source-root",
            str(source_root),
            "--workspace-root",
            str(workspace_root),
            "--result-root",
            str(result_root),
            "--entrypoint",
            envelope.entrypoint,
            "--max-source-bytes",
            str(envelope.limits.max_source_bytes),
            "--max-pdf-bytes",
            str(envelope.limits.max_pdf_bytes),
            "--max-log-bytes",
            str(envelope.limits.max_log_bytes),
            "--workspace-limit-bytes",
            str(WORKSPACE_LIMIT_BYTES),
            "--",
            *command,
        ]


def network_isolation_command() -> list[str]:
    """Fail closed into a fresh user/network/PID namespace for each compile."""
    return workspace_isolation_command(network_isolation=True)


def workspace_isolation_command(*, network_isolation: bool) -> list[str]:
    """Create a private user/mount/PID namespace before compiler setup."""
    return [
        "unshare",
        "--user",
        "--map-root-user",
        *(["--net"] if network_isolation else []),
        "--pid",
        "--fork",
        "--mount",
        "--propagation",
        "private",
        "--mount-proc",
        "--",
    ]


def verify_network_isolation() -> None:
    """Prove the compiler child can create a net namespace with no default route."""
    subprocess.run(
        network_isolation_command()
        + [
            "sh",
            "-ceu",
            (
                'if awk \'NR > 1 && $2 == "00000000" { found=1 } '
                "END { exit found ? 0 : 1 }' /proc/net/route; then exit 1; fi; "
                'if awk \'NR > 2 { interface=$1; sub(/:$/, "", interface); '
                'if (interface != "lo") found=1 } END { exit found ? 0 : 1 }\' '
                "/proc/net/dev; then exit 1; fi; "
                "if [ ! -r /proc/net/ipv6_route ]; then exit 1; fi; "
                'if awk \'$1 == "00000000000000000000000000000000" && '
                '$2 == "00" && $10 != "lo" { found=1 } '
                "END { exit found ? 0 : 1 }' "
                "/proc/net/ipv6_route; then exit 1; fi"
            ),
        ],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )


def verify_workspace_quota_isolation() -> None:
    """Prove the required namespace can mount and enforce a bounded tmpfs."""
    subprocess.run(
        workspace_isolation_command(network_isolation=True)
        + [
            "sh",
            "-ceu",
            (
                "workspace=$(mktemp -d); "
                'trap "umount \\"$workspace\\" 2>/dev/null || true; rmdir \\"$workspace\\"" EXIT; '
                'mount -t tmpfs -o size=1048576,mode=0700,nosuid,nodev,noexec tmpfs "$workspace"; '
                'if dd if=/dev/zero of="$workspace/quota" bs=1024 count=1025 status=none 2>/dev/null; then exit 1; fi'
            ),
        ],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )


def create_app(
    *,
    public_key: str,
    compiler: Compiler | None = None,
    qualified_image: str | None = None,
) -> FastAPI:
    qualified_image = qualified_image or os.environ.get(
        "PWC_LATEX_COMPILER_QUALIFIED_IMAGE", ""
    )
    network_isolation_required = (
        os.environ.get("PWC_LATEX_COMPILER_NETWORK_ISOLATION_REQUIRED", "").lower()
        == "true"
    )
    manager = JobManager(
        compiler
        or LatexCompilerRunner(
            compiler_image=qualified_image,
            network_isolation_required=network_isolation_required,
        ),
        compiler_image=qualified_image,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            validate_public_key(public_key)
        except EnvelopeError as error:
            raise RuntimeError("PWC_LATEX_COMPILER_PUBLIC_KEY is required") from error
        try:
            validate_qualified_compiler_image(qualified_image)
        except EnvelopeError as error:
            raise RuntimeError("PWC qualified compiler image is required") from error
        if network_isolation_required:
            try:
                verify_network_isolation()
                verify_workspace_quota_isolation()
            except (OSError, subprocess.SubprocessError) as error:
                raise RuntimeError(
                    "Compiler network isolation is unavailable"
                ) from error
        await manager.start()
        yield
        await manager.stop()

    app = FastAPI(
        title="PwC private LaTeX compiler",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @app.post(
        "/v1/jobs", response_model=CompilerStatus, status_code=status.HTTP_202_ACCEPTED
    )
    async def submit(submission: CompileSubmission) -> CompilerStatus:
        try:
            verify_envelope(submission.envelope, submission.signature, public_key)
            bundle = base64.b64decode(submission.bundle_base64, validate=True)
            if len(bundle) != submission.envelope.source_bytes:
                raise BundleError("Source bundle byte count is invalid")
            if len(bundle) > submission.envelope.limits.max_source_bytes:
                raise BundleError("Source bundle exceeds its limit")
            if hashlib.sha256(bundle).hexdigest() != submission.envelope.source_digest:
                raise BundleError("Source bundle digest is invalid")
            response = await manager.submit(submission.envelope, bundle)
            await asyncio.sleep(0)
            return response
        except EnvelopeError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid compiler request",
            ) from error
        except (ValueError, BundleError) as error:
            code = (
                status.HTTP_409_CONFLICT
                if "conflicts" in str(error)
                else status.HTTP_422_UNPROCESSABLE_ENTITY
            )
            raise HTTPException(
                status_code=code, detail="Invalid compiler bundle"
            ) from error

    @app.get("/v1/jobs/{job_id}", response_model=CompilerStatus)
    async def job_status(job_id: str) -> CompilerStatus:
        response = manager.status(job_id)
        if response is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown compiler job"
            )
        return response

    @app.get("/v1/jobs/{job_id}/result", response_model=CompilerResult)
    async def job_result(job_id: str) -> CompilerResult:
        response = manager.result(job_id)
        if response is None:
            if manager.status(job_id) is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Unknown compiler job"
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Compiler job is not complete",
            )
        return response

    @app.delete("/v1/jobs/{job_id}", response_model=CompilerStatus)
    async def cancel(job_id: str) -> CompilerStatus:
        response = await manager.cancel(job_id)
        if response is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown compiler job"
            )
        return response

    @app.get("/health")
    async def health() -> dict[str, object]:
        if manager.worker is None or manager.worker.done():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Compiler worker is unavailable",
            )
        return {
            "status": "ready",
            "qualified_image": qualified_image,
            "network_isolation": NETWORK_ISOLATION_ATTESTATION,
            "workspace_isolation": SANDBOX_WORKSPACE_ISOLATION_ATTESTATION,
            "workspace_limit_bytes": WORKSPACE_LIMIT_BYTES,
            **manager.metrics(),
        }

    @app.get("/metrics")
    async def metrics() -> dict[str, object]:
        return manager.metrics()

    return app


def _extract_bundle(bundle: bytes, root: Path, envelope: CompilerEnvelope) -> None:
    if len(bundle) > min(envelope.limits.max_source_bytes, MAX_SOURCE_BYTES):
        raise BundleError("Source bundle exceeds its limit")
    try:
        archive = zipfile.ZipFile(BytesIO(bundle))
    except zipfile.BadZipFile as error:
        raise BundleError("Source bundle is not a ZIP archive") from error
    total_bytes = 0
    names: set[str] = set()
    with archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            name = _safe_member_name(member)
            if name in names:
                raise BundleError("Source bundle has duplicate paths")
            names.add(name)
            if len(names) > envelope.limits.max_files:
                raise BundleError("Source bundle has too many files")
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            member_bytes = 0
            with archive.open(member) as source, destination.open("xb") as target:
                while chunk := source.read(64 * 1024):
                    member_bytes += len(chunk)
                    total_bytes += len(chunk)
                    if total_bytes > envelope.limits.max_source_bytes:
                        raise BundleError("Source bundle expands beyond its limit")
                    target.write(chunk)
            if member_bytes != member.file_size:
                raise BundleError("Source bundle member size is invalid")
            if destination.suffix.lower() in {".tex", ".bib"}:
                try:
                    destination.read_text(encoding="utf-8")
                except UnicodeDecodeError as error:
                    raise BundleError("Source bundle text must be UTF-8") from error
    if envelope.entrypoint not in names:
        raise BundleError("Source bundle does not contain its entrypoint")


def _safe_member_name(member: zipfile.ZipInfo) -> str:
    name = member.filename
    path = PurePosixPath(name)
    if (
        not _SAFE_PATH.fullmatch(name)
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.suffix.lower() not in _ALLOWED_SUFFIXES
        or member.flag_bits & 0x1
        or stat.S_ISLNK(member.external_attr >> 16)
    ):
        raise BundleError("Source bundle contains an unsafe file")
    return path.as_posix()


def _compiler_environment(root: Path) -> dict[str, str]:
    home = root / ".home"
    home.mkdir()
    return {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "PATH": "/opt/texlive/bin:/usr/local/bin:/usr/bin:/bin",
        "TEXMFOUTPUT": str(root),
        "openin_any": "p",
        "openout_any": "p",
        "shell_escape": "f",
    }


def _failed_result(
    envelope: CompilerEnvelope,
    output: bytes,
    started_at: float,
    message: str | None,
    *,
    compiler_image: str,
    failure_category: str = "compiler_error",
) -> CompilerResult:
    diagnostics = _diagnostics(output)
    if message is not None:
        diagnostics.insert(0, CompilerDiagnostic(severity="error", message=message))
    if not diagnostics:
        diagnostics = [
            CompilerDiagnostic(severity="error", message="Compilation failed")
        ]
    return CompilerResult.failed(
        envelope,
        diagnostics=diagnostics,
        log_tail=_log_tail(output, envelope.limits.max_log_bytes),
        compiler_image=compiler_image,
        engine_version=ENGINE_VERSION,
        elapsed_ms=_elapsed_ms(started_at),
        failure_category=failure_category,
    )


def _diagnostics(output: bytes) -> list[CompilerDiagnostic]:
    text = output.decode("utf-8", errors="replace")
    errors = [
        CompilerDiagnostic(severity="error", message=match.group("message")[:1000])
        for match in _ERROR.finditer(text)
    ]
    warnings = [
        CompilerDiagnostic(severity="warning", message=match.group("message")[:1000])
        for match in _WARNING.finditer(text)
    ]
    source_file = _diagnostic_source_file(text)
    if errors and source_file is not None:
        errors[0] = errors[0].model_copy(update={"file": source_file})
    line = _LINE.search(text)
    if errors and line:
        errors[0] = errors[0].model_copy(
            update={
                "line": int(line.group("line")),
                "message": line.group("message")[:1000] or errors[0].message,
            }
        )
    return (errors + warnings)[:100]


def _diagnostic_source_file(text: str) -> str | None:
    """Return only a normalized bundle-relative TeX/Bib path from compiler logs."""
    for match in _TEX_SOURCE.finditer(text):
        candidate = match.group("file").removeprefix("./")
        path = PurePosixPath(candidate)
        if (
            _SAFE_PATH.fullmatch(candidate)
            and path.suffix.lower() in {".tex", ".bib"}
            and not path.is_absolute()
            and not any(part in {"", ".", ".."} for part in path.parts)
        ):
            return path.as_posix()
    return None


def _log_tail(output: bytes, maximum: int) -> str:
    return output[-maximum:].decode("utf-8", errors="replace")


def _read_tail(path: Path, maximum: int) -> bytes:
    try:
        with path.open("rb") as log:
            log.seek(0, os.SEEK_END)
            log.seek(max(0, log.tell() - maximum))
            return log.read(maximum)
    except FileNotFoundError:
        return b""


def _elapsed_ms(started_at: float) -> int:
    return min(120_000, int((time.monotonic() - started_at) * 1000))


app = create_app(public_key=os.environ.get("PWC_LATEX_COMPILER_PUBLIC_KEY", ""))
