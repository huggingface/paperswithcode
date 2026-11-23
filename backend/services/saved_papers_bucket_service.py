"""Persist a user's saved-paper IDs in their Hugging Face Bucket."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError

from backend.services.paper_bucket_service import PaperBucketError, _hub_error

BUCKET_NAME = "pwc-saved-papers"
BOOKMARK_PREFIX = "papers"
MIGRATION_MARKER = "paperswithcode.json"


@dataclass(frozen=True)
class SavedPaperRef:
    paper_id: int
    saved_at: datetime
    title: str | None = None
    arxiv_id: str | None = None
    source_url: str | None = None


def namespace_supports_bucket(username: str) -> bool:
    """Whether a Hub account can own a Bucket; Enterprise managed users (`org:id`) cannot."""
    return ":" not in username


def bucket_id_for(username: str) -> str:
    return f"{username}/{BUCKET_NAME}"


class SavedPapersBucket:
    """Small object-per-bookmark store backed by a user-owned private Bucket."""

    def __init__(self, *, token: str, username: str) -> None:
        self.bucket_id = bucket_id_for(username)
        self.api = HfApi(token=token)

    @staticmethod
    def _path(paper_id: int) -> str:
        return f"{BOOKMARK_PREFIX}/{paper_id}.json"

    @staticmethod
    def _payload(item: SavedPaperRef) -> bytes:
        return json.dumps(
            {
                "paper_id": item.paper_id,
                "title": item.title,
                "arxiv_id": item.arxiv_id,
                "source_url": item.source_url,
                "saved_at": item.saved_at.astimezone(UTC).isoformat(),
                "source": "paperswithcode.co",
            },
            sort_keys=True,
        ).encode("utf-8")

    def initialize(self, load_legacy: Callable[[], list[SavedPaperRef]]) -> None:
        """Copy and verify database bookmarks before marking migration complete."""

        try:
            self.api.create_bucket(self.bucket_id, private=True, exist_ok=True)
            if not self.api.bucket_info(self.bucket_id).private:
                raise PaperBucketError(
                    f"The existing {self.bucket_id} Bucket must be private before "
                    "it can store saved papers."
                )
            root = list(self.api.list_bucket_tree(self.bucket_id, recursive=False))
            if any(item.path == MIGRATION_MARKER for item in root):
                return

            legacy = load_legacy()
            additions = [
                (self._payload(item), self._path(item.paper_id)) for item in legacy
            ]
            if additions:
                self.api.batch_bucket_files(self.bucket_id, add=additions)
                migrated_paths = {
                    item.path
                    for item in self.api.list_bucket_tree(
                        self.bucket_id, prefix=BOOKMARK_PREFIX, recursive=False
                    )
                    if item.type == "file"
                }
                expected_paths = {self._path(item.paper_id) for item in legacy}
                if not expected_paths.issubset(migrated_paths):
                    raise PaperBucketError(
                        "Hugging Face could not verify the saved-paper migration. "
                        "Your database bookmarks were kept unchanged."
                    )
            self.api.batch_bucket_files(
                self.bucket_id,
                add=[
                    (
                        json.dumps(
                            {
                                "schema_version": 1,
                                "description": "Saved papers from paperswithcode.co",
                            },
                            sort_keys=True,
                        ).encode("utf-8"),
                        MIGRATION_MARKER,
                    )
                ],
            )
        except HfHubHTTPError as error:
            raise _hub_error(error) from error
        except RuntimeError as error:
            raise PaperBucketError(
                "Hugging Face could not write the saved-papers Bucket."
            ) from error

    def list(self) -> list[SavedPaperRef]:
        try:
            items = self.api.list_bucket_tree(
                self.bucket_id, prefix=BOOKMARK_PREFIX, recursive=False
            )
            refs: list[SavedPaperRef] = []
            for item in items:
                name = item.path.removeprefix(f"{BOOKMARK_PREFIX}/")
                if item.type != "file" or not name.endswith(".json"):
                    continue
                try:
                    paper_id = int(name.removesuffix(".json"))
                except ValueError:
                    continue
                saved_at = (
                    item.mtime or item.uploaded_at or datetime.min.replace(tzinfo=UTC)
                )
                refs.append(SavedPaperRef(paper_id=paper_id, saved_at=saved_at))
            return sorted(refs, key=lambda item: item.saved_at, reverse=True)
        except HfHubHTTPError as error:
            raise _hub_error(error) from error
        except RuntimeError as error:
            raise PaperBucketError(
                "Hugging Face could not read the saved-papers Bucket."
            ) from error

    def add(
        self,
        paper_id: int,
        *,
        title: str,
        arxiv_id: str | None,
        source_url: str | None,
    ) -> None:
        try:
            item = SavedPaperRef(
                paper_id=paper_id,
                saved_at=datetime.now(UTC),
                title=title,
                arxiv_id=arxiv_id,
                source_url=source_url,
            )
            self.api.batch_bucket_files(
                self.bucket_id,
                add=[(self._payload(item), self._path(paper_id))],
            )
        except HfHubHTTPError as error:
            raise _hub_error(error) from error
        except RuntimeError as error:
            raise PaperBucketError(
                "Hugging Face could not write the saved-papers Bucket."
            ) from error

    def remove(self, paper_id: int) -> None:
        try:
            self.api.batch_bucket_files(self.bucket_id, delete=[self._path(paper_id)])
        except HfHubHTTPError as error:
            raise _hub_error(error) from error
        except RuntimeError as error:
            raise PaperBucketError(
                "Hugging Face could not update the saved-papers Bucket."
            ) from error
