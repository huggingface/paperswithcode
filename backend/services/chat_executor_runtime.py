"""Activation bridge from durable shard metadata to one executor launch."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import socket
import stat
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    ChatExecutorCell,
    ChatExecutorManifest,
    ChatExecutorRegistration,
    ChatExecutorShard,
)
from backend.services.chat_executor_admission import (
    AdmissionManifest,
    AdmissionSigningKey,
    issue_launch_admission,
)
from backend.services.chat_executor_registry import ChatExecutorRegistry, WorkspaceClaim
from backend.services.chat_executor_transport_circuit import ExecutorTransportCircuit
from backend.services.chat_external_executor_workspace import ExternalExecutorWorkspace
from backend.services.chat_sandbox_executor_channel import (
    ExecutorAttachment,
    PersistentSandboxExecutorChannel,
)
from backend.services.chat_sandbox_provider import ExecutorLaunchBundle, SandboxError
from backend.services.chat_turn_job_repository import TurnLeaseClaim

SessionFactory = Callable[[], Session]


def executor_environment_generation(worker_generation: str) -> int:
    if not worker_generation or len(worker_generation) > 128:
        raise ValueError("Executor worker generation is invalid")
    value = int.from_bytes(
        hashlib.sha256(worker_generation.encode()).digest()[:8], "big"
    ) & (2**63 - 1)
    return value or 1


class ChatExecutorRuntime:
    """Issue generation-bound launch admission from the active durable route."""

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: SessionFactory,
        registry: ChatExecutorRegistry | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.registry = registry or ChatExecutorRegistry()

    async def prepare_launch(self, worker_generation: str) -> ExecutorLaunchBundle:
        return await asyncio.to_thread(self._prepare_launch, worker_generation)

    def route_health_seconds(self, db: Session) -> float | None:
        cell = db.get(ChatExecutorCell, self.settings.chat_executor_cell_id)
        shard = (
            db.get(ChatExecutorShard, cell.active_shard_id)
            if cell is not None and cell.active_shard_id is not None
            else None
        )
        if (
            cell is None
            or shard is None
            or cell.circuit_state != "closed"
            or shard.state != "ready"
        ):
            return None
        path = self._rendezvous_socket(shard.generation)
        self._validate_socket(path)
        request = b'{"kind":"route_health"}'
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(0.25)
            client.connect(str(path))
            client.sendall(len(request).to_bytes(4, "big") + request)
            size = int.from_bytes(self._receive_exact(client, 4), "big")
            if not 0 < size <= 2_048:
                return None
            response = json.loads(self._receive_exact(client, size))
        if not isinstance(response, dict):
            return None
        age_ms = response.get("age_ms")
        if (
            response.get("kind") != "route_health"
            or not isinstance(age_ms, int)
            or isinstance(age_ms, bool)
            or age_ms < 0
        ):
            return None
        return age_ms / 1_000

    async def attach_channel(
        self,
        workspace: ExternalExecutorWorkspace,
        turn_claim: TurnLeaseClaim,
        minimum_remaining_seconds: int,
    ) -> PersistentSandboxExecutorChannel:
        try:
            channel = await self._attach_channel(
                workspace, turn_claim, minimum_remaining_seconds
            )
        except BaseException:
            try:
                await asyncio.to_thread(
                    self._record_attach_result, turn_claim.turn_id, False
                )
            except (RuntimeError, SQLAlchemyError):
                pass
            raise
        try:
            await asyncio.to_thread(
                self._record_attach_result, turn_claim.turn_id, True
            )
        except BaseException:
            await channel.aclose()
            raise
        return channel

    async def _attach_channel(
        self,
        workspace: ExternalExecutorWorkspace,
        turn_claim: TurnLeaseClaim,
        minimum_remaining_seconds: int,
    ) -> PersistentSandboxExecutorChannel:
        if minimum_remaining_seconds != 240:
            raise ValueError("Executor claim lifetime is invalid")
        registration, manifest = await self._wait_for_registration(workspace)
        liveness_nonce = await self._claim_liveness(registration, turn_claim)
        claim = await asyncio.to_thread(
            self._claim_workspace,
            registration,
            turn_claim,
            liveness_nonce,
            minimum_remaining_seconds,
        )
        channel = _RegistryBackedExecutorChannel(
            self._harness_socket(registration.shard_generation),
            session_factory=self.session_factory,
            registry=self.registry,
            claim=claim,
        )
        attachment = ExecutorAttachment(
            environment_id=registration.environment_id,
            environment_generation=registration.environment_generation,
            registration_id=str(registration.id),
            shard_generation=registration.shard_generation,
            stream_id=secrets.token_hex(16),
            protocol_version=manifest.protocol_version,
            schema_digest=manifest.schema_digest,
            authorization_id=secrets.token_hex(16),
            expires_at=int(time.time()) + 2,
            harness_key_id=self.settings.chat_executor_harness_key_id,
            authorization_key_id=self.settings.chat_executor_authorization_key_id,
            environment_noise_key_id=registration.public_key_id,
            environment_public_key=registration.public_noise_key,
        )
        try:
            await channel.attach_environment(attachment)
        except BaseException:
            await channel.settle("executor_transport_unavailable")
            await channel.aclose()
            raise
        return channel

    def _record_attach_result(self, turn_id: uuid.UUID, success: bool) -> None:
        with self.session_factory() as db, db.begin():
            circuit = ExecutorTransportCircuit(environment=self.settings.environment)
            if success:
                circuit.record_success(
                    db, now=datetime.now(UTC), canary_owner=str(turn_id)
                )
            else:
                circuit.record_attach_failure(
                    db, now=datetime.now(UTC), canary_owner=str(turn_id)
                )

    def _prepare_launch(self, worker_generation: str) -> ExecutorLaunchBundle:
        environment_generation = executor_environment_generation(worker_generation)
        try:
            private_key = self._private_key()
            with self.session_factory() as db, db.begin():
                cell = db.get(ChatExecutorCell, self.settings.chat_executor_cell_id)
                shard = (
                    db.get(ChatExecutorShard, cell.active_shard_id)
                    if cell is not None and cell.active_shard_id is not None
                    else None
                )
                manifest = (
                    db.get(ChatExecutorManifest, cell.selected_manifest_digest)
                    if cell is not None and cell.selected_manifest_digest is not None
                    else None
                )
                if (
                    cell is None
                    or shard is None
                    or manifest is None
                    or cell.circuit_state != "closed"
                    or shard.state != "ready"
                    or manifest.qualification_status != "qualified"
                    or manifest.compatibility_state == "incompatible"
                    or manifest.revoked_at is not None
                ):
                    raise RuntimeError("executor route is unavailable")
                signing_key = AdmissionSigningKey(
                    key_id=self.settings.chat_executor_admission_signing_key_id,
                    private_key=private_key,
                    not_before_ms=self.settings.chat_executor_admission_key_not_before_ms,
                    not_after_ms=self.settings.chat_executor_admission_key_not_after_ms,
                )
                admission = issue_launch_admission(
                    db,
                    registry=self.registry,
                    signing_key=signing_key,
                    environment_id=worker_generation,
                    environment_generation=environment_generation,
                    cell_id=cell.cell_id,
                    shard_id=shard.shard_id,
                    shard_database_id=shard.id,
                    shard_generation=shard.generation,
                    key_epoch=cell.key_epoch,
                    lifecycle_class="assigned_idle",
                    manifest=AdmissionManifest(
                        manifest_digest=manifest.digest,
                        image_digest=manifest.image_digest,
                        environment_binary_digest=manifest.environment_binary_digest,
                        daemon_digest=manifest.daemon_digest,
                        source_commit=manifest.source_commit,
                        protocol_version=manifest.protocol_version,
                        schema_digest=manifest.schema_digest,
                        release_id=manifest.release_id,
                        compatibility_expires_at=manifest.compatibility_expires_at,
                    ),
                    remaining_lifetime_ms=(
                        self.settings.chat_persistent_sandbox_lifetime_seconds * 1_000
                    ),
                )
                return ExecutorLaunchBundle(
                    admission,
                    shard_generation=shard.generation,
                    authorization_keys_json=(
                        self.settings.chat_executor_authorization_keys_json
                    ),
                )
        except SandboxError:
            raise
        except Exception as error:
            raise SandboxError(
                "sandbox_executor_admission_unavailable",
                "Sandbox executor admission is unavailable",
            ) from error

    def _private_key(self) -> Ed25519PrivateKey:
        path = Path(self.settings.chat_executor_admission_signing_key_file)
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_mode & 0o077
                or metadata.st_size != 32
                or metadata.st_uid not in {0, os.geteuid()}
            ):
                raise PermissionError("Executor admission credential is unsafe")
            private_bytes = os.read(descriptor, 33)
            if len(private_bytes) != 32:
                raise PermissionError("Executor admission credential is unsafe")
        finally:
            os.close(descriptor)
        return Ed25519PrivateKey.from_private_bytes(private_bytes)

    async def _wait_for_registration(
        self, workspace: ExternalExecutorWorkspace
    ) -> tuple[ChatExecutorRegistration, ChatExecutorManifest]:
        deadline = time.monotonic() + self.settings.chat_worker_ready_timeout_seconds
        environment_generation = executor_environment_generation(
            workspace.worker_generation
        )
        while time.monotonic() < deadline:
            result = await asyncio.to_thread(
                self._registration,
                workspace.worker_generation,
                environment_generation,
            )
            if result is not None:
                return result
            await asyncio.sleep(0.05)
        raise SandboxError(
            "sandbox_executor_registration_timeout",
            "Sandbox executor registration timed out",
        )

    def _registration(
        self, environment_id: str, environment_generation: int
    ) -> tuple[ChatExecutorRegistration, ChatExecutorManifest] | None:
        with self.session_factory() as db:
            registration = (
                db.query(ChatExecutorRegistration)
                .filter_by(
                    environment_id=environment_id,
                    environment_generation=environment_generation,
                    state="ready",
                )
                .one_or_none()
            )
            if registration is None:
                return None
            shard = db.get(ChatExecutorShard, registration.shard_id)
            cell = db.get(ChatExecutorCell, registration.cell_id)
            manifest = db.get(ChatExecutorManifest, registration.manifest_digest)
            if (
                shard is None
                or cell is None
                or manifest is None
                or cell.active_shard_id != shard.id
                or shard.state != "ready"
                or shard.generation != registration.shard_generation
                or cell.selected_manifest_digest != manifest.digest
            ):
                return None
            db.expunge(registration)
            db.expunge(manifest)
            return registration, manifest

    async def _claim_liveness(
        self,
        registration: ChatExecutorRegistration,
        turn_claim: TurnLeaseClaim,
    ) -> str:
        path = self._rendezvous_socket(registration.shard_generation)
        self._validate_socket(path)
        reader, writer = await asyncio.open_unix_connection(path)
        request = json.dumps(
            {
                "kind": "claim_liveness",
                "registration_id": str(registration.id),
                "environment_id": registration.environment_id,
                "environment_generation": registration.environment_generation,
                "shard_generation": registration.shard_generation,
                "turn_id": str(turn_claim.turn_id),
            },
            separators=(",", ":"),
        ).encode()
        try:
            writer.write(len(request).to_bytes(4, "big") + request)
            await writer.drain()
            async with asyncio.timeout(2):
                size = int.from_bytes(await reader.readexactly(4), "big")
                if not 0 < size <= 2_048:
                    raise RuntimeError("Executor liveness response is invalid")
                response = json.loads(await reader.readexactly(size))
        finally:
            writer.close()
            await writer.wait_closed()
        if not isinstance(response, dict):
            raise RuntimeError("Executor liveness response is invalid")
        nonce_digest = response.get("nonce_digest")
        if (
            response.get("kind") != "claim_liveness"
            or not isinstance(nonce_digest, str)
            or len(nonce_digest) != 64
            or any(character not in "0123456789abcdef" for character in nonce_digest)
        ):
            raise RuntimeError("Executor liveness response is invalid")
        return nonce_digest

    def _claim_workspace(
        self,
        registration: ChatExecutorRegistration,
        turn_claim: TurnLeaseClaim,
        liveness_nonce: str,
        ttl_seconds: int,
    ) -> WorkspaceClaim:
        with self.session_factory() as db, db.begin():
            return self.registry.claim_workspace(
                db,
                turn_id=turn_claim.turn_id,
                registration_id=registration.id,
                environment_generation=registration.environment_generation,
                shard_generation=registration.shard_generation,
                liveness_nonce_digest=liveness_nonce,
                claim_generation=turn_claim.lease_generation,
                ttl_seconds=ttl_seconds,
            )

    def _generation_root(self, shard_generation: int) -> Path:
        if shard_generation <= 0:
            raise ValueError("Executor shard generation is invalid")
        return (
            Path("/run/paperswithcode")
            / self.settings.environment
            / str(shard_generation)
        )

    def _rendezvous_socket(self, shard_generation: int) -> Path:
        return self._generation_root(shard_generation) / "chat-executor-rendezvous.sock"

    def _harness_socket(self, shard_generation: int) -> Path:
        return self._generation_root(shard_generation) / "chat-executor-harness.sock"

    @staticmethod
    def _receive_exact(client: socket.socket, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            chunk = client.recv(size - len(result))
            if not chunk:
                raise ConnectionError("Executor rendezvous closed")
            result.extend(chunk)
        return bytes(result)

    @staticmethod
    def _validate_socket(path: Path) -> None:
        metadata = path.stat()
        parent = path.parent.stat()
        trusted_groups = {os.getegid(), *os.getgroups()}
        if (
            not stat.S_ISSOCK(metadata.st_mode)
            or metadata.st_mode & 0o007
            or parent.st_mode & 0o022
            or (
                metadata.st_uid not in {0, os.geteuid()}
                and metadata.st_gid not in trusted_groups
            )
        ):
            raise PermissionError("Executor rendezvous requires a protected socket")


class _RegistryBackedExecutorChannel(PersistentSandboxExecutorChannel):
    def __init__(
        self,
        socket_path: Path,
        *,
        session_factory: SessionFactory,
        registry: ChatExecutorRegistry,
        claim: WorkspaceClaim,
    ) -> None:
        super().__init__(socket_path)
        self.session_factory = session_factory
        self.registry = registry
        self.claim = claim
        self._settled = False

    async def release_workspace(self, context) -> None:
        await super().release_workspace(context)
        await self.settle("completed")

    async def settle(self, terminal_code: str) -> None:
        if self._settled:
            return
        settled = await asyncio.to_thread(self._settle, terminal_code)
        self._settled = self._settled or settled

    def _settle(self, terminal_code: str) -> bool:
        with self.session_factory() as db, db.begin():
            self.registry.settle_claim(
                db,
                turn_id=self.claim.turn_id,
                claim_generation=self.claim.claim_generation,
                settlement_request_id=uuid.uuid4(),
                terminal_code=terminal_code,
            )
        return True

    async def aclose(self) -> None:
        if not self._settled:
            await self.settle("executor_transport_unavailable")
        await super().aclose()
