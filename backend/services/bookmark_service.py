"""Read, project, and mutate a user's saved papers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import desc, func, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.papers import Paper as ApiPaper
from backend.models.database import Paper as DBPaper
from backend.models.database import UserBookmark, UserPreference
from backend.services.hf_inference_billing_service import decrypt_oauth_credential
from backend.services.paper_bucket_service import PaperBucketError
from backend.services.paper_service import PaperService
from backend.services.saved_papers_bucket_service import (
    SavedPaperRef,
    SavedPapersBucket,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BookmarkRefListing:
    refs: tuple[SavedPaperRef, ...]
    bucket_connected: bool


@dataclass(frozen=True)
class SavedTaskProjection:
    id: int | None
    slug: str | None
    name: str
    papers: tuple[ApiPaper, ...]


@dataclass(frozen=True)
class SavedAreaProjection:
    id: int | None
    name: str
    tasks: tuple[SavedTaskProjection, ...]


@dataclass(frozen=True)
class SavedPapersProjection:
    count: int
    areas: tuple[SavedAreaProjection, ...]
    bucket_connected: bool
    bucket_migrated: bool


@dataclass(frozen=True)
class _PrimaryTask:
    id: int | None
    slug: str | None
    name: str | None
    area_id: int | None
    area_name: str | None


@dataclass
class _SavedTaskBuilder:
    id: int | None
    slug: str | None
    name: str
    papers: list[ApiPaper] = field(default_factory=list)


@dataclass
class _SavedAreaBuilder:
    id: int | None
    name: str
    tasks: dict[int | None, _SavedTaskBuilder] = field(default_factory=dict)


class BookmarkPaperNotFoundError(LookupError):
    """The requested paper does not exist."""


class BookmarkService:
    """Own saved-paper source selection, projection, and mutation ordering."""

    def __init__(self, db: Session):
        self.db = db

    def load_legacy_refs(self, username: str) -> list[SavedPaperRef]:
        rows = (
            self.db.query(
                UserBookmark.paper_id,
                UserBookmark.created_at,
                DBPaper.title,
                DBPaper.arxiv_id,
                DBPaper.source_url,
            )
            .join(DBPaper, DBPaper.id == UserBookmark.paper_id)
            .filter(UserBookmark.hf_username == username)
            .order_by(desc(UserBookmark.created_at))
            .all()
        )
        return [
            SavedPaperRef(
                paper_id=int(row[0]),
                saved_at=row[1],
                title=row[2],
                arxiv_id=row[3],
                source_url=row[4],
            )
            for row in rows
        ]

    def initialize_bucket(
        self,
        *,
        encrypted_credential: str | None,
        hf_user_id: str,
        username: str,
    ) -> SavedPapersBucket | None:
        credential = (
            decrypt_oauth_credential(
                encrypted_credential,
                hf_user_id,
                get_settings(),
            )
            if encrypted_credential
            else None
        )
        if credential is None:
            return None

        store = SavedPapersBucket(token=credential.token, username=username)
        store.initialize(lambda: self.load_legacy_refs(username))
        return store

    def bucket_migrated(self, username: str) -> bool:
        """Whether any device has already read this user's saved-papers Bucket."""
        migrated_at = (
            self.db.query(UserPreference.saved_papers_bucket_migrated_at)
            .filter(UserPreference.hf_username == username)
            .scalar()
        )
        return migrated_at is not None

    def record_bucket_migration(self, username: str) -> None:
        """Remember the migration on the account, writing only the first time."""
        if self.bucket_migrated(username):
            return
        # Upsert because the IDs and listing endpoints often run concurrently.
        self.db.execute(
            insert(UserPreference)
            .values(hf_username=username, saved_papers_bucket_migrated_at=func.now())
            .on_conflict_do_update(
                index_elements=[UserPreference.hf_username],
                set_={"saved_papers_bucket_migrated_at": func.now()},
                where=UserPreference.saved_papers_bucket_migrated_at.is_(None),
            )
        )
        self.db.commit()

    def list_refs(
        self,
        *,
        encrypted_credential: str | None,
        hf_user_id: str,
        username: str,
    ) -> BookmarkRefListing:
        # Preserve the database fallback eagerly, including for connected Buckets.
        legacy = self.load_legacy_refs(username)
        try:
            store = self.initialize_bucket(
                encrypted_credential=encrypted_credential,
                hf_user_id=hf_user_id,
                username=username,
            )
            if store is None:
                return BookmarkRefListing(tuple(legacy), False)
            refs = tuple(store.list())
        except PaperBucketError as error:
            logger.warning(
                "Falling back to database bookmarks for %s: %s",
                username,
                error,
            )
            return BookmarkRefListing(tuple(legacy), False)
        self.record_bucket_migration(username)
        return BookmarkRefListing(refs, True)

    def list_grouped(
        self,
        *,
        encrypted_credential: str | None,
        hf_user_id: str,
        username: str,
    ) -> SavedPapersProjection:
        listing = self.list_refs(
            encrypted_credential=encrypted_credential,
            hf_user_id=hf_user_id,
            username=username,
        )
        bucket_migrated = listing.bucket_connected or self.bucket_migrated(username)
        paper_ids = [item.paper_id for item in listing.refs]
        if not paper_ids:
            return SavedPapersProjection(
                count=0,
                areas=(),
                bucket_connected=listing.bucket_connected,
                bucket_migrated=bucket_migrated,
            )

        db_papers = self.db.query(DBPaper).filter(DBPaper.id.in_(paper_ids)).all()
        paper_by_id = {int(paper.id): paper for paper in db_papers}
        ordered_papers = [
            paper_by_id[paper_id] for paper_id in paper_ids if paper_id in paper_by_id
        ]

        primary_rows = self.db.execute(
            text(
                """
                SELECT pt.paper_id,
                       t.id   AS task_id,
                       t.slug AS task_slug,
                       t.name AS task_name,
                       a.id   AS area_id,
                       a.name AS area_name
                FROM paper_tasks pt
                JOIN tasks t ON t.id = pt.task_id
                LEFT JOIN areas a ON a.id = t.area_id
                WHERE pt.paper_id = ANY(:paper_ids)
                  AND pt.task_id = (
                      SELECT MIN(pt2.task_id)
                      FROM paper_tasks pt2
                      WHERE pt2.paper_id = pt.paper_id
                  )
                """
            ),
            {"paper_ids": paper_ids},
        ).fetchall()
        primary_by_paper = {
            int(row[0]): _PrimaryTask(
                id=int(row[1]) if row[1] is not None else None,
                slug=row[2],
                name=row[3],
                area_id=int(row[4]) if row[4] is not None else None,
                area_name=row[5],
            )
            for row in primary_rows
        }

        api_papers = {
            int(paper.id): paper
            for paper in PaperService(self.db).hydrate_cards(
                ordered_papers,
                include_resources=False,
            )
        }
        areas: dict[int | None, _SavedAreaBuilder] = {}

        for db_paper in ordered_papers:
            primary = primary_by_paper.get(int(db_paper.id))
            if primary is None:
                task_id, task_slug, task_name = None, None, "Untagged"
                area_id, area_name = None, "Other"
            else:
                task_id, task_slug, task_name = primary.id, primary.slug, primary.name
                area_id, area_name = primary.area_id, primary.area_name
                if area_id is None:
                    area_name = "Other"
                if task_id is None:
                    task_name = "Untagged"

            area = areas.get(area_id)
            if area is None:
                area = _SavedAreaBuilder(
                    id=area_id,
                    name=area_name or "Other",
                )
                areas[area_id] = area

            task = area.tasks.get(task_id)
            if task is None:
                task = _SavedTaskBuilder(
                    id=task_id,
                    slug=task_slug,
                    name=task_name or "Untagged",
                )
                area.tasks[task_id] = task

            task.papers.append(api_papers[int(db_paper.id)])

        return SavedPapersProjection(
            count=len(api_papers),
            areas=tuple(
                SavedAreaProjection(
                    id=area.id,
                    name=area.name,
                    tasks=tuple(
                        SavedTaskProjection(
                            id=task.id,
                            slug=task.slug,
                            name=task.name,
                            papers=tuple(task.papers),
                        )
                        for task in area.tasks.values()
                    ),
                )
                for area in areas.values()
            ),
            bucket_connected=listing.bucket_connected,
            bucket_migrated=bucket_migrated,
        )

    def _require_bucket(
        self,
        *,
        encrypted_credential: str | None,
        hf_user_id: str,
        username: str,
    ) -> SavedPapersBucket:
        store = self.initialize_bucket(
            encrypted_credential=encrypted_credential,
            hf_user_id=hf_user_id,
            username=username,
        )
        if store is None:
            raise PaperBucketError(
                "Authorize Papers With Code to manage your saved-papers Bucket.",
                authorization_required=True,
            )
        return store

    def add_bookmark(
        self,
        *,
        paper_id: int,
        encrypted_credential: str | None,
        hf_user_id: str,
        username: str,
    ) -> None:
        """Add a Bucket bookmark, then create its database compatibility mirror."""
        paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
        if paper is None:
            raise BookmarkPaperNotFoundError

        store = self._require_bucket(
            encrypted_credential=encrypted_credential,
            hf_user_id=hf_user_id,
            username=username,
        )
        store.add(
            paper_id,
            title=paper.title,
            arxiv_id=paper.arxiv_id,
            source_url=paper.source_url,
        )

        existing = (
            self.db.query(UserBookmark)
            .filter(
                UserBookmark.hf_username == username,
                UserBookmark.paper_id == paper_id,
            )
            .first()
        )
        if existing is None:
            self.db.add(UserBookmark(hf_username=username, paper_id=paper_id))
            self.db.commit()

    def remove_bookmark(
        self,
        *,
        paper_id: int,
        encrypted_credential: str | None,
        hf_user_id: str,
        username: str,
    ) -> None:
        """Remove a Bucket bookmark, then delete its database compatibility mirror."""
        store = self._require_bucket(
            encrypted_credential=encrypted_credential,
            hf_user_id=hf_user_id,
            username=username,
        )
        store.remove(paper_id)
        self.db.query(UserBookmark).filter(
            UserBookmark.hf_username == username,
            UserBookmark.paper_id == paper_id,
        ).delete(synchronize_session=False)
        self.db.commit()
