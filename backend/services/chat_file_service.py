"""Files a user attaches to a chat: validation, our private copy, OpenAI copy.

Each upload is stored twice: our copy in a private bucket (so chat-health audits
can see what the model saw) and an OpenAI Files copy (``purpose=user_data``)
that the provider gateway later references by ``file_id``. Both live as long
as the chat session; deleting the file or the chat deletes both.
"""

from __future__ import annotations

import functools
import hashlib
import logging
import re
import tempfile
import unicodedata
import uuid
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ChatMessageRecord, ChatSession, ChatUploadedFile
from backend.services.chat_provider_gateway.user_files import PLACEHOLDER, placeholder
from backend.services.chat_file_probe import FileProbeError, count_pdf_pages, sniff
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    owner_storage_bytes,
)
from backend.services.hf_bucket_filesystem import BucketFileSystem

logger = logging.getLogger(__name__)

OPENAI_FILES_URL = "https://api.openai.com/v1/files"
OPENAI_TIMEOUT_SECONDS = 60
STALE_PENDING_AFTER = timedelta(minutes=15)

# Conservative input-token estimates used to reserve the OpenAI budget for a
# turn that references a file. Calibrate against real usage on staging.
PDF_TEXT_TOKENS_PER_PAGE = 800
PDF_IMAGE_TOKENS_PER_PAGE = {"low": 100, "high": 1_300}
PDF_HIGH_DETAIL_MAX_PAGES = 20
IMAGE_TOKENS = 1_600
TEXT_BYTES_PER_TOKEN = 3


@dataclass(frozen=True)
class FileCleanup:
    """What to delete outside the database once rows are gone."""

    storage_keys: tuple[str, ...] = ()
    openai_file_ids: tuple[str, ...] = ()


class ChatFileStorage(ABC):
    @abstractmethod
    def write(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def read(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class LocalChatFileStorage(ChatFileStorage):
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return path

    def write(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class BucketChatFileStorage(ChatFileStorage):
    def __init__(self, bucket_id: str, token: str | None):
        if not bucket_id:
            raise ValueError("Chat file bucket is not configured")
        self.bucket_id = bucket_id
        self.filesystem = BucketFileSystem(token=token)

    def _path(self, key: str) -> str:
        return f"hf://buckets/{self.bucket_id}/{key}"

    def write(self, key: str, data: bytes) -> None:
        with self.filesystem.open(self._path(key), "wb") as output:
            output.write(data)

    def read(self, key: str) -> bytes:
        with self.filesystem.open(self._path(key), "rb", block_size=0) as handle:
            return handle.read()

    def delete(self, key: str) -> None:
        try:
            self.filesystem.rm(self._path(key))
        except FileNotFoundError:
            pass


@functools.lru_cache(maxsize=4)
def _bucket_storage(bucket_id: str, token: str | None) -> BucketChatFileStorage:
    # One client per process keeps its connections and Xet session warm.
    return BucketChatFileStorage(bucket_id, token)


def chat_file_storage_from_settings(settings: Settings) -> ChatFileStorage:
    if settings.chat_file_storage_backend == "hf_bucket":
        return _bucket_storage(
            settings.chat_file_hf_bucket_id, settings.hf_token or None
        )
    return LocalChatFileStorage(Path(settings.chat_file_local_dir))


def warm_chat_file_storage(settings: Settings) -> None:
    """Open the bucket client at startup so the first upload is not the slow one."""
    if settings.chat_file_storage_backend != "hf_bucket":
        return
    storage = chat_file_storage_from_settings(settings)
    try:
        storage.filesystem.info(storage._path("warmup"))
    except FileNotFoundError:
        pass


class OpenAIFilesClient:
    """The two OpenAI Files API calls chat uploads need."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OpenAI API key is not configured")
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def upload(self, filename: str, data: bytes, media_type: str) -> str:
        response = httpx.post(
            OPENAI_FILES_URL,
            headers=self.headers,
            data={"purpose": "user_data"},
            files={"file": (filename, data, media_type)},
            timeout=OPENAI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()["id"]

    def delete(self, file_id: str) -> None:
        response = httpx.delete(
            f"{OPENAI_FILES_URL}/{file_id}",
            headers=self.headers,
            timeout=OPENAI_TIMEOUT_SECONDS,
        )
        if response.status_code != 404:
            response.raise_for_status()


def safe_filename(filename: str) -> str:
    """Keep a readable display name without paths or control characters."""
    name = Path(filename.replace("\\", "/")).name
    name = "".join(
        character
        for character in unicodedata.normalize("NFC", name)
        if unicodedata.category(character)[0] != "C"
    ).strip()
    return name[:200] or "file"


def estimate_tokens(
    media_type: str, size_bytes: int, page_count: int | None
) -> tuple[int, str | None]:
    """Return (input-token estimate, PDF detail) for one file reference."""
    if media_type == "application/pdf":
        pages = page_count or 1
        detail = "high" if pages <= PDF_HIGH_DETAIL_MAX_PAGES else "low"
        return pages * (
            PDF_TEXT_TOKENS_PER_PAGE + PDF_IMAGE_TOKENS_PER_PAGE[detail]
        ), detail
    if media_type.startswith("image/"):
        return IMAGE_TOKENS, None
    return max(1, size_bytes // TEXT_BYTES_PER_TOKEN), None


def _now() -> datetime:
    return datetime.now(UTC)


USER_FILES_BLOCK = re.compile(r"\A<user_files>\n((?:[^\n]*\n)*?)</user_files>\n")


def prompt_with_files(prompt: str, rows: list[ChatUploadedFile]) -> str:
    """Prefix a turn prompt with one gateway placeholder line per file."""
    if not rows:
        return prompt
    lines = "".join(f"{placeholder(row.id)}\n" for row in rows)
    return f"<user_files>\n{lines}</user_files>\n{prompt}"


def prompt_file_ids(prompt: str | None) -> list[uuid.UUID]:
    """The files a stored turn prompt attached, in order."""
    match = USER_FILES_BLOCK.match(prompt or "")
    if match is None:
        return []
    return [uuid.UUID(found.group(1)) for found in PLACEHOLDER.finditer(match.group(1))]


class ChatFileService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        storage: ChatFileStorage | None = None,
        openai_files: OpenAIFilesClient | None = None,
    ):
        self.db = db
        self.settings = settings
        self._storage = storage
        self._openai_files = openai_files

    @property
    def storage(self) -> ChatFileStorage:
        if self._storage is None:
            self._storage = chat_file_storage_from_settings(self.settings)
        return self._storage

    @property
    def openai_files(self) -> OpenAIFilesClient:
        if self._openai_files is None:
            self._openai_files = OpenAIFilesClient(self.settings.openai_api_key)
        return self._openai_files

    def _owned_session(self, owner: ChatOwner, session_id: uuid.UUID) -> ChatSession:
        session = self.db.scalar(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.hf_user_id == owner.hf_user_id,
            )
        )
        if session is None:
            raise ChatServiceError("session_not_found", 404, "Chat not found")
        return session

    def list_files(
        self, owner: ChatOwner, session_id: uuid.UUID
    ) -> list[ChatUploadedFile]:
        self._owned_session(owner, session_id)
        return list(
            self.db.scalars(
                select(ChatUploadedFile)
                .where(
                    ChatUploadedFile.session_id == session_id,
                    ChatUploadedFile.state == "ready",
                )
                .order_by(ChatUploadedFile.created_at)
            )
        )

    def turn_files(
        self,
        owner: ChatOwner,
        session_id: uuid.UUID | None,
        file_ids: list[uuid.UUID],
    ) -> list[ChatUploadedFile]:
        """Validate the files a new turn attaches; they must be ready in its chat."""
        if not file_ids:
            return []
        if not self.settings.chat_file_uploads_enabled:
            raise ChatServiceError(
                "file_uploads_disabled", 409, "File uploads are not available."
            )
        if session_id is None:
            raise ChatServiceError(
                "file_not_found", 404, "Upload files to this chat before sending."
            )
        session = self._owned_session(owner, session_id)
        if session.selected_model != self.settings.chat_openai_luna_route:
            raise ChatServiceError(
                "file_upload_model_unsupported", 409, "File uploads need GPT-6 Luna"
            )
        wanted = list(dict.fromkeys(file_ids))
        rows = {
            row.id: row
            for row in self.db.scalars(
                select(ChatUploadedFile).where(
                    ChatUploadedFile.session_id == session_id,
                    ChatUploadedFile.id.in_(wanted),
                    ChatUploadedFile.state == "ready",
                )
            )
        }
        if len(rows) != len(wanted):
            raise ChatServiceError(
                "file_not_found",
                404,
                "An attached file is no longer available. Remove it and retry.",
            )
        return [rows[file_id] for file_id in wanted]

    def attachments(
        self, messages: list[ChatMessageRecord]
    ) -> dict[uuid.UUID, list[ChatUploadedFile]]:
        """Files each user message attached, keyed by message id."""
        if not self.settings.chat_file_uploads_enabled:
            return {}
        wanted = {
            message.id: prompt_file_ids(message.effective_prompt)
            for message in messages
            if message.role == "user"
        }
        ids = {file_id for file_ids in wanted.values() for file_id in file_ids}
        if not ids:
            return {}
        rows = {
            row.id: row
            for row in self.db.scalars(
                select(ChatUploadedFile).where(
                    ChatUploadedFile.id.in_(ids), ChatUploadedFile.state == "ready"
                )
            )
        }
        return {
            message_id: [rows[file_id] for file_id in file_ids if file_id in rows]
            for message_id, file_ids in wanted.items()
            if file_ids
        }

    def _lock_owner(self, owner: ChatOwner) -> None:
        """Serialize uploads with turn admission on the owner's quota key."""
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(
                select(
                    func.pg_advisory_xact_lock(
                        func.hashtextextended(f"chat-user:{owner.hf_user_id}", 0)
                    )
                )
            )

    def upload(
        self,
        owner: ChatOwner,
        session_id: uuid.UUID,
        *,
        filename: str,
        data: bytes,
    ) -> ChatUploadedFile:
        """Validate, store both copies, and return the ready row.

        Commits several times on purpose: the pending row must be durable
        before any external write so cleanup can always find what it left.
        """
        if not data:
            raise ChatServiceError("file_empty", 422, "The file is empty")
        if len(data) > self.settings.chat_file_max_bytes:
            raise ChatServiceError("file_too_large", 413, "The file is too large")
        name = safe_filename(filename)
        try:
            kind = sniff(name, data)
            page_count = None
            if kind.media_type == "application/pdf":
                with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary:
                    temporary.write(data)
                    temporary.flush()
                    page_count = count_pdf_pages(Path(temporary.name))
        except FileProbeError as error:
            raise ChatServiceError("file_unsupported", 422, str(error)) from error
        if (
            page_count is not None
            and page_count > self.settings.chat_file_max_pdf_pages
        ):
            raise ChatServiceError(
                "file_too_many_pages", 413, "The PDF has too many pages"
            )
        token_estimate, pdf_detail = estimate_tokens(
            kind.media_type, len(data), page_count
        )

        self._lock_owner(owner)
        session = self.db.scalar(
            select(ChatSession)
            .where(
                ChatSession.id == session_id,
                ChatSession.hf_user_id == owner.hf_user_id,
            )
            .with_for_update()
        )
        if session is None:
            raise ChatServiceError("session_not_found", 404, "Chat not found")
        if session.selected_model != self.settings.chat_openai_luna_route:
            raise ChatServiceError(
                "file_upload_model_unsupported", 409, "File uploads need GPT-6 Luna"
            )
        existing = self.db.scalar(
            select(func.count())
            .select_from(ChatUploadedFile)
            .where(ChatUploadedFile.session_id == session.id)
        )
        if existing >= self.settings.chat_file_max_per_session:
            raise ChatServiceError(
                "file_limit_reached", 409, "This chat has reached its file limit"
            )
        owner_bytes = owner_storage_bytes(self.db, owner.hf_user_id)
        if owner_bytes + len(data) > self.settings.chat_user_byte_limit:
            raise ChatServiceError(
                "chat_storage_quota_exceeded", 409, "Chat storage quota exceeded"
            )

        file_id = uuid.uuid4()
        row = ChatUploadedFile(
            id=file_id,
            session_id=session.id,
            hf_user_id=owner.hf_user_id,
            filename=name,
            media_type=kind.media_type,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            page_count=page_count,
            pdf_detail=pdf_detail,
            token_estimate=token_estimate,
            storage_key=f"chat-files/{session.id}/{file_id}",
            state="pending",
        )
        self.db.add(row)
        self.db.commit()
        storage_key = row.storage_key
        openai_file_id = None
        try:
            # The two copies are independent, so write them at the same time;
            # leaving the block waits for both before either outcome is used.
            with ThreadPoolExecutor(max_workers=2) as pool:
                stored = pool.submit(self.storage.write, storage_key, data)
                uploaded = pool.submit(
                    self.openai_files.upload, name, data, kind.media_type
                )
            if uploaded.exception() is None:
                openai_file_id = uploaded.result()
            failure = stored.exception() or uploaded.exception()
            if failure is not None:
                raise failure
            # Record the OpenAI id at once: it is the only handle that can
            # delete that copy. If the chat was deleted meanwhile, this fails.
            row.openai_file_id = openai_file_id
            row.state = "ready"
            self.db.commit()
        except Exception as error:
            # Either side may have finished while the other failed in any way,
            # so the copies are always removed before the error moves on.
            self.db.rollback()
            self._discard(
                FileCleanup(
                    storage_keys=(storage_key,),
                    openai_file_ids=(openai_file_id,) if openai_file_id else (),
                )
            )
            self.db.execute(
                delete(ChatUploadedFile).where(ChatUploadedFile.id == file_id)
            )
            self.db.commit()
            if isinstance(
                error, (httpx.HTTPError, OSError, ValueError, SQLAlchemyError)
            ):
                raise ChatServiceError(
                    "file_upload_failed", 502, "The file could not be stored; try again"
                ) from error
            raise
        return row

    def delete_file(
        self, owner: ChatOwner, session_id: uuid.UUID, file_id: uuid.UUID
    ) -> None:
        self._owned_session(owner, session_id)
        row = self.db.scalar(
            select(ChatUploadedFile).where(
                ChatUploadedFile.id == file_id,
                ChatUploadedFile.session_id == session_id,
            )
        )
        if row is None:
            raise ChatServiceError("file_not_found", 404, "File not found")
        self._remove(row)

    def remove_stale_pending(self, hf_user_id: str) -> int:
        """Remove this owner's uploads that never finished (crash or timeout)."""
        rows = list(
            self.db.scalars(
                select(ChatUploadedFile).where(
                    ChatUploadedFile.hf_user_id == hf_user_id,
                    ChatUploadedFile.state == "pending",
                    ChatUploadedFile.created_at < _now() - STALE_PENDING_AFTER,
                )
            )
        )
        removed = 0
        for row in rows:
            try:
                self._remove(row)
            except (httpx.HTTPError, OSError, ValueError):
                logger.warning("chat_file_stale_cleanup_failed file_id=%s", row.id)
                continue
            removed += 1
        return removed

    def _discard(self, cleanup: FileCleanup) -> None:
        """Best-effort removal after a failed upload; leftovers are logged."""
        try:
            self.purge(cleanup)
        except (httpx.HTTPError, OSError, ValueError):
            logger.warning(
                "chat_file_discard_failed storage_keys=%s openai_file_ids=%s",
                cleanup.storage_keys,
                cleanup.openai_file_ids,
            )

    def purge(self, cleanup: FileCleanup) -> None:
        """Delete external copies; raises if any deletion fails."""
        for file_id in cleanup.openai_file_ids:
            self.openai_files.delete(file_id)
        for key in cleanup.storage_keys:
            self.storage.delete(key)

    def _remove(self, row: ChatUploadedFile) -> None:
        self.purge(
            FileCleanup(
                storage_keys=(row.storage_key,),
                openai_file_ids=(row.openai_file_id,) if row.openai_file_id else (),
            )
        )
        self.db.delete(row)
