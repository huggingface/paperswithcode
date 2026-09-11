"""Public, unlisted snapshots of the bounded browser chat projection."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from io import BytesIO

from pydantic import TypeAdapter
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.chat import (
    DISPLAY_BLOCKS_ADAPTER,
    ChatShareDetail,
    PublicChatMessage,
)
from backend.models.database import (
    ChatArtifact,
    ChatArtifactVersion,
    ChatMessageRecord,
    ChatSession,
    ChatShare,
    ChatSharedArtifact,
)
from backend.services.chat_artifact_service import (
    ArtifactError,
    ChatArtifactService,
    StoredArtifactFile,
)
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
)


def _now() -> datetime:
    return datetime.now(UTC)


SNAPSHOT_VERSION = 1
PUBLIC_MESSAGES_ADAPTER = TypeAdapter(list[PublicChatMessage])


def _is_private_paper_block(block: object) -> bool:
    """Fail closed if a private paper block reaches the share projector."""
    return (
        isinstance(block, dict)
        and block.get("kind") == "artifact"
        and block.get("artifact_kind") == "latex_paper"
    )


def _shareable_blocks(row: ChatMessageRecord) -> list[object]:
    return [
        block
        for block in (row.display_blocks or [])
        if not _is_private_paper_block(block)
    ]


def _has_private_paper_block(rows: list[ChatMessageRecord]) -> bool:
    """Treat an unexpected persisted paper event as private rather than public."""

    return any(
        _is_private_paper_block(block)
        for row in rows
        for block in (row.display_blocks or [])
    )


def _failure_message(code: str | None) -> str:
    if code == "provider_error":
        return (
            "The model provider failed before completing the response. "
            "You can edit and retry your question."
        )
    if code == "persistence_error":
        return "The response could not be saved. You can edit and retry your question."
    if code == "transcript_mirror_error":
        return "The conversation could not be saved. Please try again in a new chat."
    return "The response did not complete. You can edit and retry your question."


def _public_blocks(
    row: ChatMessageRecord, shared: dict[str, ChatSharedArtifact]
) -> list[dict]:
    blocks = DISPLAY_BLOCKS_ADAPTER.validate_python(_shareable_blocks(row))
    projection: list[dict] = []
    for block in blocks:
        value = block.model_dump(mode="json", exclude_defaults=True)
        if value["kind"] == "tool" and value["status"] == "running":
            value["status"] = "error"
        if value["kind"] == "app":
            # A share is a browser-local fork.  Do not hand out an owner
            # checkpoint or an App/session correlation capability.
            value["instance_id"] = str(uuid.uuid4())
            value["public_fork"] = True
            value["result"] = {
                "content": value.get("result", {}).get("content", []),
                "structuredContent": {},
                "isError": value.get("result", {}).get("isError", False),
            }
        if value["kind"] == "artifact":
            public = shared.get(value["identifier"])
            if public is None:
                continue
            value = {
                "kind": "artifact",
                "schema_version": 1,
                "scope": "public",
                "public_capability": str(public.capability_id),
                "identifier": public.identifier,
                "version": _shared_version(public),
                "artifact_kind": "posterly",
                "title": public.title,
                "status": "ready",
                "preview_mime": "image/png",
                "gate_status": public.gate_status,
                "total_bytes": _shared_total_bytes(public),
            }
        projection.append(value)
    return projection


def _shared_version(shared: ChatSharedArtifact) -> int:
    return int(shared.canvas.get("source_version", 1))


def _shared_total_bytes(shared: ChatSharedArtifact) -> int:
    return int(shared.canvas.get("total_bytes", 0))


def _public_projection(
    rows: list[ChatMessageRecord], shared: dict[str, ChatSharedArtifact]
) -> list[PublicChatMessage]:
    public_messages: list[PublicChatMessage] = []
    for row in rows:
        if row.role == "assistant":
            public_messages.append(
                PublicChatMessage(
                    id=uuid.uuid4(),
                    role="assistant",
                    content=row.content,
                    display_blocks=_public_blocks(row, shared),
                    citations=row.citations or [],
                    model=row.model,
                    finish_reason=row.finish_reason,
                )
            )
            continue

        public_messages.append(
            PublicChatMessage(
                id=uuid.uuid4(),
                role="user",
                content=row.content,
                paper_mentions=getattr(row, "paper_mentions", None) or [],
                paper_selection=getattr(row, "paper_selection", None),
            )
        )
        if row.status not in {"error", "interrupted"}:
            continue
        interrupted = row.status == "interrupted"
        public_messages.append(
            PublicChatMessage(
                id=uuid.uuid4(),
                role="assistant",
                content="",
                display_blocks=_public_blocks(row, shared),
                model=getattr(row, "model", None),
                display_state="interrupted" if interrupted else "failed",
                finish_reason="stopped" if interrupted else None,
                error=None if interrupted else _failure_message(row.error_code),
            )
        )
    return public_messages


class ChatShareService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.sessions = ChatSessionService(db, settings)
        self.stale_storage_prefixes: set[str] = set()
        self.new_storage_prefixes: set[str] = set()

    def create_or_refresh(self, owner: ChatOwner, session_id: uuid.UUID) -> ChatShare:
        session = self.sessions._owned(owner, session_id, lock=True)
        if (
            getattr(getattr(self.db, "bind", None), "dialect", None) is not None
            and self.db.bind.dialect.name == "postgresql"
        ):
            # Match paper creation's advisory key. A share that starts first
            # is a pre-paper immutable snapshot; a share that starts after a
            # paper insert sees the artifact and fails closed.
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:session))"),
                {"session": f"chat-latex-paper:{session.id}"},
            )
        if session.active_turn_id:
            raise ChatServiceError(
                "session_busy", 409, "Wait for the response to finish before sharing"
            )
        messages = list(
            self.db.execute(
                select(ChatMessageRecord)
                .where(
                    ChatMessageRecord.session_id == session.id,
                    ChatMessageRecord.status.notin_(["superseded", "preparing"]),
                )
                .order_by(ChatMessageRecord.sequence)
            ).scalars()
        )
        if not messages:
            raise ChatServiceError(
                "empty_chat", 409, "Start the conversation before sharing it"
            )
        has_private_paper = self.db.scalar(
            select(ChatArtifact.id)
            .where(
                ChatArtifact.session_id == session.id,
                ChatArtifact.kind == "latex_paper",
            )
            .limit(1)
        )
        if has_private_paper is not None or _has_private_paper_block(messages):
            # Model output in a paper turn can legitimately quote a failed
            # source or diagnostic. Never try to sanitize it for a public
            # snapshot: a paper chat is owner-only for its whole lifecycle.
            raise ChatServiceError(
                "paper_share_disabled",
                409,
                "Chats with private papers cannot be shared",
            )
        share = self.db.execute(
            select(ChatShare).where(ChatShare.chat_session_id == session.id)
        ).scalar_one_or_none()
        if share is None:
            share = ChatShare(
                id=uuid.uuid4(),
                chat_session_id=session.id,
                snapshot_version=SNAPSHOT_VERSION,
                messages=[],
                updated_at=_now(),
            )
            self.db.add(share)
            self.db.flush()
        try:
            shared = self._materialize_artifacts(session, share, messages)
        except ArtifactError as error:
            raise ChatServiceError(
                error.code, 503, "The poster snapshot could not be shared"
            ) from error
        public_messages = _public_projection(messages, shared)
        snapshot = PUBLIC_MESSAGES_ADAPTER.dump_python(
            public_messages, mode="json", exclude_none=True
        )
        share.snapshot_version = SNAPSHOT_VERSION
        share.messages = snapshot
        share.updated_at = _now()
        self.db.flush()
        return share

    def _materialize_artifacts(
        self,
        session: ChatSession,
        share: ChatShare,
        messages: list[ChatMessageRecord],
    ) -> dict[str, ChatSharedArtifact]:
        referenced: dict[str, tuple[int, uuid.UUID]] = {}
        for message in messages:
            for block in _shareable_blocks(message):
                if (
                    isinstance(block, dict)
                    and block.get("kind") == "artifact"
                    and block.get("status") == "ready"
                    and block.get("scope", "owner") == "owner"
                ):
                    try:
                        version_id = uuid.UUID(str(block["version_id"]))
                    except (KeyError, TypeError, ValueError):
                        continue
                    identifier = str(block.get("identifier") or "")
                    version = int(block.get("version") or 0)
                    current = referenced.get(identifier)
                    if identifier and (current is None or version > current[0]):
                        referenced[identifier] = (version, version_id)
        if not referenced:
            for previous in list(getattr(share, "shared_artifacts", ())):
                self.stale_storage_prefixes.add(previous.storage_key)
                self.db.delete(previous)
            return {}
        if (
            not self.sessions.settings.chat_artifact_shared_preview_enabled
            or not self.sessions.settings.chat_artifacts_enabled
        ):
            raise ArtifactError(
                "artifact_share_disabled", "Public poster snapshots are disabled"
            )

        version_ids = [item[1] for item in referenced.values()]
        versions = list(
            self.db.scalars(
                select(ChatArtifactVersion)
                .join(ChatArtifact)
                .where(
                    ChatArtifactVersion.id.in_(version_ids),
                    ChatArtifactVersion.state == "ready",
                    ChatArtifact.session_id == session.id,
                )
            )
        )
        by_id = {item.id: item for item in versions}
        if len(by_id) != len(referenced):
            raise ArtifactError(
                "artifact_not_found", "A referenced poster is unavailable"
            )

        artifacts = ChatArtifactService(self.db, self.sessions.settings)
        for previous in list(getattr(share, "shared_artifacts", ())):
            self.stale_storage_prefixes.add(previous.storage_key)
            self.db.delete(previous)
        # Let the database remove old unique (share, identifier) rows before
        # inserting the replacement snapshot. A later failure rolls this back.
        self.db.flush()
        new_rows: dict[str, ChatSharedArtifact] = {}
        for identifier, (_, version_id) in referenced.items():
            version = by_id[version_id]
            capability = uuid.uuid4()
            prefix = "/".join(
                [
                    self.sessions.settings.chat_artifact_hf_bucket_prefix.strip("/"),
                    "public",
                    str(share.id),
                    str(capability),
                ]
            )
            self.new_storage_prefixes.add(prefix)
            preview_bytes = self._copy_public_file(
                artifacts, version, version.preview_path, prefix
            )
            pdf_path = None
            pdf_bytes = 0
            if version.gate_status != "failed" and version.manifest["downloads"]:
                pdf_path = version.manifest["downloads"][0]["path"]
                pdf_bytes = self._copy_public_file(artifacts, version, pdf_path, prefix)
            artifact = version.artifact
            row = ChatSharedArtifact(
                id=uuid.uuid4(),
                share_id=share.id,
                capability_id=capability,
                source_version_id=version.id,
                identifier=identifier,
                title=artifact.title,
                canvas={
                    **version.manifest["canvas"],
                    "source_version": version.version,
                    "total_bytes": preview_bytes + pdf_bytes,
                },
                gate_status=version.gate_status,
                digest=version.bundle_digest,
                storage_key=prefix,
                preview_path=version.preview_path,
                pdf_path=pdf_path,
            )
            self.db.add(row)
            new_rows[identifier] = row
        self.db.flush()
        return new_rows

    @staticmethod
    def _copy_public_file(
        artifacts: ChatArtifactService,
        version: ChatArtifactVersion,
        path: str,
        prefix: str,
    ) -> int:
        declared = {item["path"]: item for item in version.manifest["files"]}[path]
        data = artifacts.storage.read_file(
            f"{version.storage_key}/{path}", max_bytes=int(declared["bytes"])
        )
        if (
            len(data) != int(declared["bytes"])
            or hashlib.sha256(data).hexdigest() != declared["sha256"]
        ):
            raise ArtifactError(
                "artifact_corrupt", "Stored poster file failed verification"
            )
        artifacts.storage.write_file(f"{prefix}/{path}", BytesIO(data))
        return len(data)

    def read_public_artifact(
        self,
        raw_share_id: str,
        raw_capability_id: str,
        *,
        role: str,
    ) -> StoredArtifactFile:
        try:
            share_id = uuid.UUID(raw_share_id)
            capability_id = uuid.UUID(raw_capability_id)
        except (TypeError, ValueError):
            raise ChatServiceError(
                "share_not_found", 404, "Shared poster not found"
            ) from None
        shared = self.db.scalar(
            select(ChatSharedArtifact).where(
                ChatSharedArtifact.share_id == share_id,
                ChatSharedArtifact.capability_id == capability_id,
            )
        )
        if shared is None:
            raise ChatServiceError("share_not_found", 404, "Shared poster not found")
        if role == "preview":
            path = shared.preview_path
            media_type = "image/png"
        elif role == "pdf" and shared.pdf_path is not None:
            path = shared.pdf_path
            media_type = "application/pdf"
        else:
            raise ChatServiceError("share_not_found", 404, "Shared poster not found")
        data = ChatArtifactService(self.db, self.sessions.settings).storage.read_file(
            f"{shared.storage_key}/{path}",
            max_bytes=self.sessions.settings.chat_artifact_max_pdf_bytes,
        )
        return StoredArtifactFile(
            data=data,
            media_type=media_type,
            filename=path.rsplit("/", 1)[-1],
        )

    def get_public(self, raw_share_id: str) -> ChatShareDetail:
        try:
            share_id = uuid.UUID(raw_share_id)
        except (TypeError, ValueError):
            raise ChatServiceError(
                "share_not_found", 404, "Shared conversation not found"
            ) from None
        share = self.db.execute(
            select(ChatShare).where(ChatShare.id == share_id)
        ).scalar_one_or_none()
        if share is None:
            raise ChatServiceError(
                "share_not_found", 404, "Shared conversation not found"
            )
        try:
            if share.snapshot_version != SNAPSHOT_VERSION:
                raise ValueError("unsupported snapshot version")
            public_messages = PUBLIC_MESSAGES_ADAPTER.validate_python(share.messages)
        except (TypeError, ValueError):
            raise ChatServiceError(
                "share_not_found", 404, "Shared conversation not found"
            ) from None

        model = next(
            (
                message.model
                for message in reversed(public_messages)
                if message.role == "assistant" and message.model
            ),
            None,
        )
        # Snapshots created before model attribution was added do not contain
        # this public-safe field. Keep those existing capability URLs useful.
        if model is None and getattr(share, "chat_session_id", None) is not None:
            model = self.db.scalar(
                select(ChatSession.selected_model).where(
                    ChatSession.id == share.chat_session_id
                )
            )
        choice = next(
            (
                candidate
                for candidate in self.sessions.settings.chat_model_registry
                if candidate["id"] == model
            ),
            None,
        )

        return ChatShareDetail(
            share_id=share.id,
            created_at=share.created_at,
            updated_at=share.updated_at,
            model=model,
            model_label=(
                choice["label"]
                if choice
                else self.sessions.settings.chat_model_labels.get(model, model)
            ),
            model_provider=(
                choice["provider"]
                if choice
                else self.sessions.settings.chat_model_providers.get(model)
            ),
            messages=public_messages,
        )
