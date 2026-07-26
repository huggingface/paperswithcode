"""Durable Modal sandbox lifecycle and framed worker transport."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import modal
from modal.stream_type import StreamType
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.chat_sandbox_worker.protocol import (
    FRAME_PREFIX,
    ProtocolError,
    WorkerEventValidator,
    decode_frame,
    encode_frame,
)
from backend.chat_sandbox_worker.contract import MODAL_APP_NAME
from backend.chat_sandbox_worker.supervisor import SUPERVISOR_PREFIX
from backend.config import Settings
from backend.database.connection import db_manager
from backend.models.database import ChatSandboxLease, ChatSession
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_runtime_contract import dedicated_gateway_hostname


class SandboxError(RuntimeError):
    def __init__(self, code: str, message: str, *, uncertain: bool = False):
        super().__init__(message)
        self.code = code
        self.uncertain = uncertain


@dataclass(frozen=True)
class WorkerClaim:
    sandbox_id: str
    token_hash: str


@dataclass
class RunningWorker:
    process: object
    request_id: str
    claim: WorkerClaim
    cancel_requested: bool = False


@dataclass(frozen=True)
class StartClaim:
    token_hash: str
    stale_sandbox_id: str | None
    snapshot_id: str | None


async def resolve_modal_image(image_reference: str):
    if image_reference.startswith("im-"):
        return modal.Image.from_id(image_reference)
    return modal.Image.from_name(image_reference)


def sandbox_environment(settings: Settings) -> dict[str, str]:
    return {
        "PWC_CHAT_MAX_TURNS": str(settings.chat_max_turns),
        "PWC_CHAT_MAX_TOOL_CALLS": str(settings.chat_max_tool_calls),
        "PWC_CHAT_MAX_DIRECT_SEARCH_CALLS": str(settings.chat_max_direct_search_calls),
        "PWC_CHAT_TOOL_RESULT_MAX_BYTES": str(settings.chat_tool_result_max_bytes),
        "PWC_CHAT_TURN_TOOL_OUTPUT_MAX_BYTES": str(
            settings.chat_turn_tool_output_max_bytes
        ),
        "PWC_CHAT_BASH_TIMEOUT_SECONDS": str(settings.chat_bash_timeout_seconds),
        "PWC_CHAT_AGENT_TIMEOUT_SECONDS": str(settings.chat_agent_timeout_seconds),
        "PWC_CHAT_SANDBOX_PIDS_MAX": str(settings.chat_sandbox_pids_max),
    }


async def create_isolated_sandbox(
    settings: Settings,
    *,
    name: str,
    tags: dict[str, str],
):
    try:
        gateway_host = dedicated_gateway_hostname(settings.chat_gateway_url)
    except ValueError as error:
        raise SandboxError(
            "gateway_unavailable", "The research gateway is not configured"
        ) from error
    app, image = await asyncio.gather(
        modal.App.lookup.aio(MODAL_APP_NAME, create_if_missing=False),
        resolve_modal_image(settings.chat_modal_image_version),
    )
    return await modal.Sandbox.create.aio(
        "sleep",
        "infinity",
        app=app,
        image=image,
        env=sandbox_environment(settings),
        name=name,
        tags=tags,
        timeout=3600,
        idle_timeout=max(60, settings.chat_sandbox_warm_seconds),
        workdir="/workspace",
        cpu=(settings.chat_sandbox_cpu, settings.chat_sandbox_cpu),
        memory=(
            settings.chat_sandbox_memory_mib,
            settings.chat_sandbox_memory_mib,
        ),
        outbound_domain_allowlist=[gateway_host],
        inbound_cidr_allowlist=[],
        encrypted_ports=[],
        unencrypted_ports=[],
        include_oidc_identity_token=False,
        readiness_probe=modal.sandbox.Probe.with_exec(
            "test", "-x", "/usr/local/bin/pwc"
        ),
    )


class WorkspaceSnapshotProvider:
    """Directory-only snapshots; never capture processes or the full filesystem."""

    supported = True

    def __init__(self, *, ttl_days: int = 30):
        self.ttl_seconds = ttl_days * 24 * 60 * 60

    async def save(self, sandbox, _chat_session_id: uuid.UUID) -> str:
        image = await sandbox.snapshot_directory.aio(
            "/workspace",
            timeout=55,
            ttl=self.ttl_seconds,
        )
        await image.hydrate.aio()
        return image.object_id

    async def restore(self, sandbox, snapshot_id: str) -> None:
        image = modal.Image.from_id(snapshot_id)
        await sandbox.mount_image.aio("/workspace", image)

    async def delete(self, _snapshot_id: str) -> None:
        # Modal Image currently has no early-delete API. Dropping the durable
        # reference revokes application access; provider TTL performs deletion.
        return


class SandboxSessionManager:
    MAINTENANCE_CONCURRENCY = 8

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: Callable[[], Session] | None = None,
        snapshot_provider: WorkspaceSnapshotProvider | None = None,
    ):
        self.settings = settings
        self.session_factory = session_factory or db_manager.session_local
        self.snapshots = snapshot_provider or WorkspaceSnapshotProvider(
            ttl_days=settings.chat_workspace_snapshot_inactivity_days
        )
        self._processes: dict[uuid.UUID, RunningWorker] = {}
        if settings.chat_workspace_snapshots_enabled and not self.snapshots.supported:
            raise SandboxError(
                "snapshot_unsupported",
                "Configured workspace snapshots require a Directory Snapshot provider",
            )

    async def validate_image_reference(self) -> None:
        try:
            await modal.App.lookup.aio(MODAL_APP_NAME, create_if_missing=False)
            await resolve_modal_image(self.settings.chat_modal_image_version)
        except Exception as error:
            raise SandboxError(
                "sandbox_image_unresolved",
                "The pinned sandbox image could not be resolved",
            ) from error

    def _lease(self, db: Session, chat_session_id: uuid.UUID, *, lock: bool):
        query = select(ChatSandboxLease).where(
            ChatSandboxLease.chat_session_id == chat_session_id
        )
        if lock:
            query = query.with_for_update()
        return db.execute(query).scalar_one_or_none()

    @staticmethod
    def _lock_start_claim(db: Session, chat_session_id: uuid.UUID) -> None:
        """Serialize start claims even before the lease row exists."""

        db.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(f"chat-sandbox:{chat_session_id}", 0)
                )
            )
        )

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _claim_start(
        self,
        lease: ChatSandboxLease,
        *,
        creation_token: str,
        now: datetime,
    ) -> StartClaim:
        snapshot_id = None
        if (
            self.settings.chat_workspace_snapshots_enabled
            and lease.workspace_snapshot_id
            and lease.snapshot_image_version == self.settings.chat_modal_image_version
        ):
            snapshot_id = lease.workspace_snapshot_id
        elif lease.workspace_snapshot_id:
            lease.workspace_snapshot_id = None
            lease.snapshot_image_version = None
            lease.snapshot_updated_at = None

        token_hash = self._token_hash(creation_token)
        claim = StartClaim(token_hash, lease.modal_sandbox_id, snapshot_id)
        lease.state = "starting"
        lease.modal_sandbox_id = None
        lease.app_release_id = self.settings.release_id
        lease.image_version = self.settings.chat_modal_image_version
        lease.worker_contract_version = self.settings.chat_worker_contract_version
        lease.lease_token_hash = token_hash
        lease.lease_expires_at = now + timedelta(
            seconds=self.settings.chat_sandbox_ready_timeout_seconds + 15
        )
        lease.failure_code = None
        lease.updated_at = now
        return claim

    @staticmethod
    def _unexpired(lease: ChatSandboxLease, now: datetime) -> bool:
        expires_at = lease.lease_expires_at
        if expires_at is None:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at > now

    def _finish_owned_operation(
        self,
        chat_session_id: uuid.UUID,
        *,
        token_hash: str,
        expected_state: str,
        expected_sandbox_id: str | None,
        state: str,
        failure_code: str | None,
        clear_sandbox: bool,
    ) -> bool:
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            if not (
                lease
                and lease.state == expected_state
                and lease.lease_token_hash == token_hash
                and lease.modal_sandbox_id == expected_sandbox_id
            ):
                return False
            if clear_sandbox:
                lease.modal_sandbox_id = None
            lease.state = state
            lease.failure_code = failure_code
            lease.lease_token_hash = None
            lease.lease_expires_at = None
            lease.updated_at = datetime.now(UTC)
            return True

    async def ensure_ready(
        self, chat_session_id: uuid.UUID
    ) -> tuple[object, int, bool]:
        started = time.perf_counter()
        deadline = time.monotonic() + self.settings.chat_sandbox_ready_timeout_seconds
        claim: StartClaim | None = None
        sandbox_id: str | None = None
        while claim is None and sandbox_id is None:
            creation_token = secrets.token_urlsafe(24)
            now = datetime.now(UTC)
            waiting_for_owner = False
            with self.session_factory() as db, db.begin():
                self._lock_start_claim(db, chat_session_id)
                lease = self._lease(db, chat_session_id, lock=True)
                compatible = bool(
                    lease
                    and lease.image_version == self.settings.chat_modal_image_version
                    and lease.worker_contract_version
                    == self.settings.chat_worker_contract_version
                )
                if (
                    lease
                    and compatible
                    and lease.modal_sandbox_id
                    and lease.state in {"ready", "idle", "busy"}
                ):
                    sandbox_id = lease.modal_sandbox_id
                elif (
                    lease
                    and compatible
                    and lease.state == "starting"
                    and lease.lease_token_hash
                    and self._unexpired(lease, now)
                ):
                    waiting_for_owner = True
                elif lease is None:
                    token_hash = self._token_hash(creation_token)
                    lease = ChatSandboxLease(
                        chat_session_id=chat_session_id,
                        app_release_id=self.settings.release_id,
                        image_version=self.settings.chat_modal_image_version,
                        worker_contract_version=self.settings.chat_worker_contract_version,
                        state="starting",
                        lease_token_hash=token_hash,
                        lease_expires_at=now
                        + timedelta(
                            seconds=self.settings.chat_sandbox_ready_timeout_seconds
                            + 15
                        ),
                        last_activity_at=now,
                    )
                    db.add(lease)
                    claim = StartClaim(token_hash, None, None)
                else:
                    claim = self._claim_start(
                        lease, creation_token=creation_token, now=now
                    )
            if waiting_for_owner:
                if time.monotonic() >= deadline:
                    raise SandboxError(
                        "sandbox_timeout", "Secure workspace startup timed out"
                    )
                await asyncio.sleep(0.05)

        if claim and claim.stale_sandbox_id:
            try:
                stale = await modal.Sandbox.from_id.aio(claim.stale_sandbox_id)
                await stale.terminate.aio(wait=False)
            except Exception:
                pass
        await self.enforce_warm_cap()

        if sandbox_id:
            try:
                sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
                if await sandbox.poll.aio() is None:
                    probe = await sandbox.exec.aio(
                        "test", "-x", "/usr/local/bin/pwc", timeout=5
                    )
                    await probe.wait.aio()
                    if probe.returncode == 0:
                        return (
                            sandbox,
                            round((time.perf_counter() - started) * 1000),
                            False,
                        )
            except Exception:
                pass
            with self.session_factory() as db, db.begin():
                lease = self._lease(db, chat_session_id, lock=True)
                if (
                    lease
                    and lease.modal_sandbox_id == sandbox_id
                    and lease.state in {"ready", "idle", "busy"}
                ):
                    claim = self._claim_start(
                        lease,
                        creation_token=secrets.token_urlsafe(24),
                        now=datetime.now(UTC),
                    )
            if claim is None:
                return await self.ensure_ready(chat_session_id)

        assert claim is not None
        try:
            async with asyncio.timeout(
                self.settings.chat_sandbox_ready_timeout_seconds
            ):
                sandbox = await create_isolated_sandbox(
                    self.settings,
                    name=f"chat-{chat_session_id}",
                    tags={
                        "chat_session_hash": hashlib.sha256(
                            str(chat_session_id).encode()
                        ).hexdigest()[:16],
                        "release": self.settings.release_id,
                        "image": self.settings.chat_modal_image_version,
                    },
                )
                if claim.snapshot_id:
                    try:
                        await self.snapshots.restore(sandbox, claim.snapshot_id)
                    except Exception:
                        with self.session_factory() as db, db.begin():
                            lease = self._lease(db, chat_session_id, lock=True)
                            if (
                                lease
                                and lease.state == "starting"
                                and lease.lease_token_hash == claim.token_hash
                            ):
                                lease.workspace_snapshot_id = None
                                lease.snapshot_image_version = None
                                lease.snapshot_updated_at = None
        except TimeoutError as error:
            self._mark_start_failed(
                chat_session_id, claim.token_hash, "sandbox_timeout"
            )
            raise SandboxError(
                "sandbox_timeout", "Secure workspace startup timed out"
            ) from error
        except Exception as error:
            self._mark_start_failed(
                chat_session_id, claim.token_hash, "sandbox_start_failed"
            )
            raise SandboxError(
                "sandbox_start_failed", "Secure workspace startup failed"
            ) from error

        sandbox_id = sandbox.object_id
        landed = False
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            if (
                lease
                and lease.state == "starting"
                and lease.lease_token_hash == claim.token_hash
                and lease.modal_sandbox_id is None
            ):
                lease.modal_sandbox_id = sandbox_id
                lease.state = "ready"
                lease.lease_token_hash = None
                lease.lease_expires_at = None
                lease.last_activity_at = datetime.now(UTC)
                lease.workspace_dirty = False
                lease.updated_at = datetime.now(UTC)
                landed = True
        if not landed:
            await sandbox.terminate.aio(wait=False)
            raise SandboxError(
                "sandbox_start_failed", "Secure workspace ownership changed"
            )
        return sandbox, round((time.perf_counter() - started) * 1000), True

    def _mark_start_failed(
        self, chat_session_id: uuid.UUID, token_hash: str, code: str
    ) -> bool:
        return self._finish_owned_operation(
            chat_session_id,
            token_hash=token_hash,
            expected_state="starting",
            expected_sandbox_id=None,
            state="failed",
            failure_code=code,
            clear_sandbox=False,
        )

    def _claim_worker(self, chat_session_id: uuid.UUID, sandbox_id: str) -> WorkerClaim:
        claim = WorkerClaim(
            sandbox_id=sandbox_id,
            token_hash=self._token_hash(secrets.token_urlsafe(24)),
        )
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            if not (
                lease
                and lease.state in {"ready", "idle"}
                and lease.modal_sandbox_id == claim.sandbox_id
                and lease.lease_token_hash is None
            ):
                raise SandboxError("sandbox_lost", "Secure workspace is unavailable")
            lease.state = "busy"
            lease.lease_token_hash = claim.token_hash
            lease.lease_expires_at = None
            lease.last_activity_at = datetime.now(UTC)
            lease.updated_at = datetime.now(UTC)
        return claim

    def _release_worker(self, chat_session_id: uuid.UUID, claim: WorkerClaim) -> bool:
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            if not (
                lease
                and lease.state == "busy"
                and lease.modal_sandbox_id == claim.sandbox_id
                and lease.lease_token_hash == claim.token_hash
            ):
                return False
            lease.state = "idle"
            lease.lease_token_hash = None
            lease.lease_expires_at = None
            lease.last_activity_at = datetime.now(UTC)
            # A completed turn may have changed /workspace through arbitrary
            # Bash, so conservatively mark it dirty.
            lease.workspace_dirty = True
            lease.updated_at = datetime.now(UTC)
            return True

    async def _terminate_worker(
        self,
        chat_session_id: uuid.UUID,
        claim: WorkerClaim,
        *,
        failure_code: str,
    ) -> bool:
        termination_token_hash = self._token_hash(secrets.token_urlsafe(24))
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            if not (
                lease
                and lease.state == "busy"
                and lease.modal_sandbox_id == claim.sandbox_id
                and lease.lease_token_hash == claim.token_hash
            ):
                return False
            lease.state = "terminating"
            lease.failure_code = failure_code
            lease.lease_token_hash = termination_token_hash
            lease.lease_expires_at = datetime.now(UTC) + timedelta(
                seconds=self.settings.chat_sandbox_ready_timeout_seconds + 15
            )
            lease.updated_at = datetime.now(UTC)
        await self._terminate_owned_sandbox(
            chat_session_id,
            sandbox_id=claim.sandbox_id,
            token_hash=termination_token_hash,
            failure_code=failure_code,
        )
        return True

    async def run_turn(
        self,
        *,
        chat_session_id: uuid.UUID,
        turn_id: uuid.UUID,
        request_id: str,
        prompt: str,
        model: str,
        resume: str | None,
        capability: IssuedCapability,
    ) -> AsyncIterator[dict]:
        yield {"type": "sandbox_start", "session_id": str(chat_session_id)}
        sandbox, cold_start_ms, _created = await self.ensure_ready(chat_session_id)
        yield {
            "type": "sandbox_ready",
            "session_id": str(chat_session_id),
            "cold_start_ms": cold_start_ms,
        }
        claim = self._claim_worker(chat_session_id, sandbox.object_id)
        running_worker: RunningWorker | None = None
        stderr_task: asyncio.Task | None = None
        buffer = b""
        terminal = False
        validator = WorkerEventValidator()
        try:
            process = await sandbox.exec.aio(
                "python",
                "-m",
                "backend.chat_sandbox_worker.supervisor",
                stdout=StreamType.PIPE,
                stderr=StreamType.PIPE,
                timeout=round(self.settings.chat_agent_timeout_seconds + 15),
                workdir="/workspace",
                text=False,
            )
            running_worker = RunningWorker(process, request_id, claim)
            self._processes[turn_id] = running_worker
            launch = {
                "capability": capability.token,
                "gateway_url": self.settings.chat_gateway_url,
                "session_id": str(chat_session_id),
                "turn_id": str(turn_id),
            }
            run = {
                "v": 1,
                "type": "run_turn",
                "request_id": request_id,
                "chat_session_id": str(chat_session_id),
                "prompt": prompt,
                "model": model,
                "resume": resume,
            }
            process.stdin.write(
                SUPERVISOR_PREFIX
                + json.dumps(launch, separators=(",", ":")).encode()
                + b"\n"
                + encode_frame(run)
            )
            await process.stdin.drain.aio()

            async def drain_stderr() -> None:
                async for _chunk in process.stderr:
                    pass

            stderr_task = asyncio.create_task(drain_stderr())
            async with asyncio.timeout(self.settings.chat_agent_timeout_seconds):
                async for chunk in process.stdout:
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if not line:
                            continue
                        if not line.startswith(FRAME_PREFIX.encode()):
                            continue
                        event = decode_frame(line)
                        if event.get("request_id") != request_id:
                            raise ProtocolError("Uncorrelated worker frame")
                        validator.accept(
                            event,
                            allow_terminal_less_stop=running_worker.cancel_requested,
                        )
                        if event["type"] == "worker_done":
                            terminal = True
                            continue
                        yield {
                            key: value
                            for key, value in event.items()
                            if key not in {"v", "request_id"}
                        }
                await process.wait.aio()
            if not terminal:
                raise SandboxError(
                    "sandbox_worker_failed",
                    "The secure workspace worker ended unexpectedly",
                    uncertain=True,
                )
        except TimeoutError as error:
            raise SandboxError(
                "sandbox_timeout", "The research run timed out", uncertain=True
            ) from error
        except ProtocolError as error:
            raise SandboxError(
                "sandbox_worker_failed", "The worker protocol failed", uncertain=True
            ) from error
        finally:
            if stderr_task:
                stderr_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await stderr_task
            self._processes.pop(turn_id, None)
            if not terminal:
                await self._terminate_worker(
                    chat_session_id,
                    claim,
                    failure_code="sandbox_worker_failed",
                )
            elif self._release_worker(chat_session_id, claim):
                await self.enforce_warm_cap()

    async def cancel(self, chat_session_id: uuid.UUID, turn_id: uuid.UUID) -> bool:
        running = self._processes.get(turn_id)
        if running is None:
            return False
        running.cancel_requested = True
        process = running.process
        process.stdin.write(
            encode_frame(
                {
                    "v": 1,
                    "type": "cancel",
                    "request_id": running.request_id,
                }
            )
        )
        await process.stdin.drain.aio()
        try:
            async with asyncio.timeout(self.settings.chat_cancel_grace_seconds):
                await process.wait.aio()
        except TimeoutError:
            await self._terminate_worker(
                chat_session_id,
                running.claim,
                failure_code="cancel_timeout",
            )
        return True

    async def terminate(
        self, chat_session_id: uuid.UUID, *, failure_code: str | None = None
    ) -> None:
        sandbox_id: str | None = None
        token_hash: str | None = None
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            if lease:
                sandbox_id = lease.modal_sandbox_id
                token_hash = self._token_hash(secrets.token_urlsafe(24))
                lease.state = "terminating"
                lease.failure_code = failure_code
                lease.lease_token_hash = token_hash
                lease.lease_expires_at = datetime.now(UTC) + timedelta(
                    seconds=self.settings.chat_sandbox_ready_timeout_seconds + 15
                )
        if token_hash:
            await self._terminate_owned_sandbox(
                chat_session_id,
                sandbox_id=sandbox_id,
                token_hash=token_hash,
                failure_code=failure_code,
            )

    async def _terminate_owned_sandbox(
        self,
        chat_session_id: uuid.UUID,
        *,
        sandbox_id: str | None,
        token_hash: str,
        failure_code: str | None,
    ) -> None:
        if sandbox_id:
            try:
                sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
                await sandbox.terminate.aio(wait=False)
            except Exception:
                pass
        self._finish_owned_operation(
            chat_session_id,
            token_hash=token_hash,
            expected_state="terminating",
            expected_sandbox_id=sandbox_id,
            state="failed" if failure_code else "terminated",
            failure_code=failure_code,
            clear_sandbox=True,
        )

    async def cleanup_deleted(
        self, sandbox_id: str | None, snapshot_id: str | None
    ) -> None:
        if sandbox_id:
            try:
                sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
                await sandbox.terminate.aio(wait=False)
            except Exception:
                pass
        if snapshot_id:
            await self.snapshots.delete(snapshot_id)

    async def reap_idle(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(
            seconds=self.settings.chat_sandbox_warm_seconds
        )
        with self.session_factory() as db:
            ids = list(
                db.execute(
                    select(ChatSandboxLease.chat_session_id)
                    .where(
                        ChatSandboxLease.state == "idle",
                        ChatSandboxLease.last_activity_at < cutoff,
                    )
                    .order_by(ChatSandboxLease.last_activity_at)
                ).scalars()
            )
        return await self._terminate_many(ids)

    async def _terminate_many(self, chat_session_ids: list[uuid.UUID]) -> int:
        semaphore = asyncio.Semaphore(self.MAINTENANCE_CONCURRENCY)

        async def terminate_one(chat_session_id: uuid.UUID) -> bool:
            async with semaphore:
                return await self.snapshot_and_terminate(chat_session_id)

        results = await asyncio.gather(
            *(terminate_one(session_id) for session_id in chat_session_ids)
        )
        return sum(results)

    async def snapshot_and_terminate(self, chat_session_id: uuid.UUID) -> bool:
        token_hash = self._token_hash(secrets.token_urlsafe(24))
        with self.session_factory() as db, db.begin():
            lease = self._lease(db, chat_session_id, lock=True)
            if lease is None or lease.state != "idle" or not lease.modal_sandbox_id:
                return False
            sandbox_id = lease.modal_sandbox_id
            should_snapshot = bool(
                self.settings.chat_workspace_snapshots_enabled and lease.workspace_dirty
            )
            lease.state = "terminating"
            lease.lease_token_hash = token_hash
            lease.lease_expires_at = datetime.now(UTC) + timedelta(
                seconds=self.settings.chat_sandbox_ready_timeout_seconds + 15
            )
        if should_snapshot and sandbox_id:
            try:
                sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
                snapshot_id = await self.snapshots.save(sandbox, chat_session_id)
                with self.session_factory() as db, db.begin():
                    lease = self._lease(db, chat_session_id, lock=True)
                    if (
                        lease
                        and lease.state == "terminating"
                        and lease.modal_sandbox_id == sandbox_id
                        and lease.lease_token_hash == token_hash
                    ):
                        lease.workspace_snapshot_id = snapshot_id
                        lease.snapshot_image_version = (
                            self.settings.chat_modal_image_version
                        )
                        lease.snapshot_updated_at = datetime.now(UTC)
                        lease.workspace_dirty = False
            except Exception:
                # Workspace continuity is recoverable; the transcript remains
                # authoritative and the next sandbox safely starts empty.
                pass
        try:
            sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
            await sandbox.terminate.aio(wait=False)
        except Exception:
            pass
        self._finish_owned_operation(
            chat_session_id,
            token_hash=token_hash,
            expected_state="terminating",
            expected_sandbox_id=sandbox_id,
            state="terminated",
            failure_code=None,
            clear_sandbox=True,
        )
        return True

    async def enforce_warm_cap(self) -> int:
        with self.session_factory() as db:
            counted = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxLease)
                    .where(
                        ChatSandboxLease.state.in_(
                            [
                                "starting",
                                "ready",
                                "idle",
                                "terminating",
                            ]
                        )
                    )
                )
                or 0
            )
            idle = list(
                db.execute(
                    select(ChatSandboxLease.chat_session_id)
                    .where(ChatSandboxLease.state == "idle")
                    .order_by(ChatSandboxLease.last_activity_at.desc())
                ).scalars()
            )
        excess = max(0, counted - self.settings.chat_sandbox_max_warm)
        evict = list(reversed(idle[-excess:])) if excess else []
        return await self._terminate_many(evict)

    async def reconcile(self) -> int:
        """Converge expired creations and provider-lost sandbox leases."""

        with self.session_factory() as db:
            candidates = list(
                db.execute(
                    select(
                        ChatSandboxLease.chat_session_id,
                        ChatSandboxLease.modal_sandbox_id,
                        ChatSandboxLease.state,
                        ChatSandboxLease.lease_token_hash,
                    ).where(
                        (ChatSandboxLease.state == "starting")
                        & (
                            ChatSandboxLease.lease_expires_at.is_(None)
                            | (ChatSandboxLease.lease_expires_at < datetime.now(UTC))
                        )
                        | ChatSandboxLease.state.in_(["ready", "idle"])
                    )
                ).all()
            )
        repaired = 0
        for session_id, sandbox_id, state, token_hash in candidates:
            if state == "starting":
                if token_hash and self._mark_start_failed(
                    session_id, token_hash, "sandbox_start_failed"
                ):
                    repaired += 1
                continue
            if not sandbox_id:
                with self.session_factory() as db, db.begin():
                    lease = self._lease(db, session_id, lock=True)
                    if (
                        lease
                        and lease.state == state
                        and lease.modal_sandbox_id is None
                    ):
                        lease.state = "failed"
                        lease.failure_code = "sandbox_lost"
                        lease.updated_at = datetime.now(UTC)
                        repaired += 1
                continue
            try:
                sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
                alive = await sandbox.poll.aio() is None
            except Exception:
                alive = False
            if not alive:
                with self.session_factory() as db, db.begin():
                    lease = self._lease(db, session_id, lock=True)
                    if (
                        lease
                        and lease.state == state
                        and lease.modal_sandbox_id == sandbox_id
                    ):
                        lease.modal_sandbox_id = None
                        lease.state = "failed"
                        lease.failure_code = "sandbox_lost"
                        lease.updated_at = datetime.now(UTC)
                        repaired += 1
        return repaired

    async def expire_inactive_snapshots(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(
            days=self.settings.chat_workspace_snapshot_inactivity_days
        )
        with self.session_factory() as db:
            rows = list(
                db.execute(
                    select(
                        ChatSandboxLease.chat_session_id,
                        ChatSandboxLease.workspace_snapshot_id,
                    )
                    .join(
                        ChatSession,
                        ChatSession.id == ChatSandboxLease.chat_session_id,
                    )
                    .where(
                        ChatSandboxLease.workspace_snapshot_id.is_not(None),
                        ChatSession.updated_at < cutoff,
                    )
                ).all()
            )
        expired = 0
        for session_id, snapshot_id in rows:
            if snapshot_id:
                await self.snapshots.delete(snapshot_id)
            with self.session_factory() as db, db.begin():
                lease = self._lease(db, session_id, lock=True)
                if lease and lease.workspace_snapshot_id == snapshot_id:
                    lease.workspace_snapshot_id = None
                    lease.snapshot_image_version = None
                    lease.snapshot_updated_at = None
                    expired += 1
        return expired
