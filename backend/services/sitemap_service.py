"""Bounded canonical sitemap queries shared with crawlable paper archives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterator, Optional

from sqlalchemy import and_, case, exists, func, or_
from sqlalchemy.orm import Query, Session

from backend.models.database import (
    Author,
    Conference,
    Dataset,
    Evaluation,
    Method,
    Organization,
    PaperAuthor,
    PaperConference,
    PaperMethod,
    PaperOrganization,
    PaperTask,
    Task,
)
from backend.models.database import (
    Paper as DBPaper,
)
from backend.utils.urls import get_paper_route_identifier

PRODUCTION_ORIGIN = "https://paperswithcode.co"
SITEMAP_BUCKET_SIZE = 50_000
SITEMAP_BATCH_SIZE = 1_000
ARCHIVE_PAGE_SIZE = 100

# Sitemaps and archives only need a few narrow columns. Loading whole ``Paper``
# rows pulled the abstract and the full-text search vector along for up to
# ``SITEMAP_BUCKET_SIZE`` papers per shard, which is what grew a production web
# worker past 1 GB while crawlers walked the shards.
SITEMAP_PAPER_COLUMNS = (
    DBPaper.id,
    DBPaper.source,
    DBPaper.arxiv_id,
    DBPaper.date_published,
    DBPaper.created_at,
)
ARCHIVE_PAPER_COLUMNS = (
    DBPaper.id,
    DBPaper.source,
    DBPaper.arxiv_id,
    DBPaper.title,
    DBPaper.date_published,
)


@dataclass(frozen=True)
class SitemapShard:
    year: int
    bucket: int

    @property
    def name(self) -> str:
        return f"{self.year:04d}-{self.bucket}"


@dataclass(frozen=True)
class SitemapPaper:
    route_identifier: str
    lastmod: datetime


@dataclass(frozen=True)
class ArchivePaper:
    route_identifier: str
    title: str
    published: Optional[date]


@dataclass(frozen=True)
class ArchiveLink:
    href: str
    label: str
    suffix: str = ""


@dataclass(frozen=True)
class ArchivePage:
    title: str
    description: str
    heading: str
    canonical_path: str
    papers: tuple[ArchivePaper, ...] = ()
    navigation: tuple[ArchiveLink, ...] = ()
    page: int = 1
    has_next: bool = False

    @property
    def canonical_url(self) -> str:
        suffix = f"?page={self.page}" if self.page > 1 else ""
        return f"{PRODUCTION_ORIGIN}{self.canonical_path}{suffix}"


@dataclass(frozen=True)
class SitemapEntity:
    path: str
    lastmod: datetime


def eligible_paper_filter():
    """One public-eligibility predicate for sitemaps, archives, and reports."""
    return and_(
        DBPaper.is_latest_version,
        func.length(func.trim(DBPaper.title)) > 0,
        func.length(func.trim(func.coalesce(DBPaper.abstract, ""))) > 0,
        or_(
            and_(
                DBPaper.source == "arxiv",
                DBPaper.arxiv_id.is_not(None),
            ),
            and_(
                DBPaper.source == "external",
                DBPaper.source_url.is_not(None),
            ),
        ),
    )


def _year_expression():
    return case(
        (DBPaper.date_published.is_(None), 0),
        else_=func.extract("year", DBPaper.date_published),
    )


class SitemapService:
    def __init__(self, db: Session):
        self.db = db

    def list_shards(self) -> list[SitemapShard]:
        year = _year_expression().label("year")
        bucket = func.floor(DBPaper.id / SITEMAP_BUCKET_SIZE).label("bucket")
        rows = (
            self.db.query(year, bucket)
            .filter(eligible_paper_filter())
            .distinct()
            .order_by(year, bucket)
            .all()
        )
        return [SitemapShard(int(row.year), int(row.bucket)) for row in rows]

    def iter_shard(self, shard: SitemapShard) -> Iterator[SitemapPaper]:
        lower = shard.bucket * SITEMAP_BUCKET_SIZE
        upper = lower + SITEMAP_BUCKET_SIZE
        query = (
            self.db.query(*SITEMAP_PAPER_COLUMNS)
            .filter(
                eligible_paper_filter(),
                DBPaper.id >= lower,
                DBPaper.id < upper,
            )
            .order_by(DBPaper.id)
            .yield_per(SITEMAP_BATCH_SIZE)
        )
        if shard.year:
            query = query.filter(
                DBPaper.date_published >= date(shard.year, 1, 1),
                DBPaper.date_published < date(shard.year + 1, 1, 1),
            )
        else:
            query = query.filter(DBPaper.date_published.is_(None))

        for paper in query:
            published_at = (
                datetime.combine(paper.date_published, time.min, tzinfo=timezone.utc)
                if paper.date_published
                else None
            )
            created_at = paper.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            lastmod = max(value for value in (published_at, created_at) if value)
            yield SitemapPaper(
                route_identifier=get_paper_route_identifier(
                    paper.source, paper.arxiv_id, paper.id
                ),
                lastmod=lastmod,
            )

    def archive_years(self) -> list[tuple[int, int]]:
        year = func.extract("year", DBPaper.date_published).label("year")
        return [
            (int(row.year), int(row.count))
            for row in (
                self.db.query(year, func.count(DBPaper.id).label("count"))
                .filter(
                    eligible_paper_filter(),
                    DBPaper.date_published.is_not(None),
                )
                .group_by(year)
                .order_by(year.desc())
                .all()
            )
        ]

    def archive_query(
        self,
        *,
        recent: bool = False,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> Query:
        query = self.db.query(DBPaper).filter(eligible_paper_filter())
        if recent:
            cutoff = datetime.now(timezone.utc) - timedelta(days=14)
            query = query.filter(
                or_(
                    DBPaper.date_published >= cutoff.date(),
                    DBPaper.created_at >= cutoff,
                )
            )
        elif year is not None:
            start = date(year, month or 1, 1)
            if month == 12:
                end = date(year + 1, 1, 1)
            elif month:
                end = date(year, month + 1, 1)
            else:
                end = date(year + 1, 1, 1)
            query = query.filter(
                DBPaper.date_published >= start,
                DBPaper.date_published < end,
            )
        return query.order_by(
            DBPaper.date_published.desc().nullslast(), DBPaper.id.desc()
        )

    def archive_page(
        self,
        *,
        page: int,
        recent: bool = False,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> tuple[list[ArchivePaper], bool]:
        rows = (
            self.archive_query(recent=recent, year=year, month=month)
            .with_entities(*ARCHIVE_PAPER_COLUMNS)
            .offset((page - 1) * ARCHIVE_PAGE_SIZE)
            .limit(ARCHIVE_PAGE_SIZE + 1)
            .all()
        )
        items = [
            ArchivePaper(
                route_identifier=get_paper_route_identifier(
                    paper.source, paper.arxiv_id, paper.id
                ),
                title=paper.title,
                published=paper.date_published,
            )
            for paper in rows[:ARCHIVE_PAGE_SIZE]
        ]
        return items, len(rows) > ARCHIVE_PAGE_SIZE

    @staticmethod
    def _eligible_relation_exists(relation, relation_entity_column, entity_id):
        return exists().where(
            relation_entity_column == entity_id,
            relation.paper_id == DBPaper.id,
            eligible_paper_filter(),
        )

    def iter_entities(self, kind: str) -> Iterator[SitemapEntity]:
        definitions = {
            "tasks": (Task, PaperTask, PaperTask.task_id, "/tasks/"),
            "methods": (Method, PaperMethod, PaperMethod.method_id, "/methods/"),
            "benchmarks": (
                Dataset,
                Evaluation,
                Evaluation.dataset_id,
                "/benchmark/",
            ),
            "conferences": (
                Conference,
                PaperConference,
                PaperConference.conference_id,
                "/conferences/",
            ),
            "organizations": (
                Organization,
                PaperOrganization,
                PaperOrganization.organization_id,
                "/orgs/",
            ),
        }
        model, relation, relation_entity_column, prefix = definitions[kind]
        query = (
            self.db.query(model.slug, model.updated_at)
            .filter(
                model.slug.is_not(None),
                func.length(func.trim(model.slug)) > 0,
                self._eligible_relation_exists(
                    relation, relation_entity_column, model.id
                ),
            )
            .order_by(model.id)
            .yield_per(SITEMAP_BATCH_SIZE)
        )
        for entity in query:
            updated = entity.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            yield SitemapEntity(f"{prefix}{entity.slug}", updated)

    def list_author_shards(self) -> list[int]:
        bucket = func.floor(Author.id / SITEMAP_BUCKET_SIZE).label("bucket")
        rows = (
            self.db.query(bucket)
            .filter(
                self._eligible_relation_exists(
                    PaperAuthor, PaperAuthor.author_id, Author.id
                )
            )
            .distinct()
            .order_by(bucket)
            .all()
        )
        return [int(row.bucket) for row in rows]

    def iter_author_shard(self, bucket: int) -> Iterator[SitemapEntity]:
        lower = bucket * SITEMAP_BUCKET_SIZE
        upper = lower + SITEMAP_BUCKET_SIZE
        query = (
            self.db.query(Author.id, Author.updated_at)
            .filter(
                Author.id >= lower,
                Author.id < upper,
                self._eligible_relation_exists(
                    PaperAuthor, PaperAuthor.author_id, Author.id
                ),
            )
            .order_by(Author.id)
            .yield_per(SITEMAP_BATCH_SIZE)
        )
        for author in query:
            updated = author.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            yield SitemapEntity(f"/authors/{author.id}", updated)
