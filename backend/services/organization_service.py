"""
Organization service for listing organizations and organization-scoped taxonomy.
"""

import threading
import time
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import Float, and_, cast, desc, func, or_
from sqlalchemy.orm import Session

from backend.database.organizations_setup.organizations import BY_PWC_SLUG
from backend.models.conferences import ConferenceTaskSummary
from backend.models.organizations import (
    Organization,
    OrganizationAreaWithTasks,
    OrganizationAreasWithTasks,
    OrganizationContributionDay,
    OrganizationContributions,
    OrganizationTopPaper,
    Organizations,
)
from backend.models.papers import Papers
from backend.models.database import Area as DBArea
from backend.models.database import Organization as DBOrganization
from backend.models.database import Paper as DBPaper
from backend.models.database import PaperOrganization
from backend.models.database import PaperTask
from backend.models.database import Task as DBTask
from backend.models.database import OrganizationTrendingHistory
from backend.services.organization_trending_service import AUTO_FEATURE_MIN_PAPERS
from backend.services.sitemap_service import eligible_paper_filter
from backend.services.trending_ranking_service import (
    active_paper_score_components,
    correlated_paper_score_expressions,
)
from backend.config import get_settings
from backend.utils.exceptions import DatabaseError, PaperNotFoundError
from backend.utils.organization_logos import organization_logo_path


# The public directory builds ~200 cards with a top paper each (~2 s), and
# featuring and trending change once a day. Each worker keeps its cards and,
# once they are older than the TTL, serves them while one background thread
# rebuilds them, so only a worker's very first request waits for the query.
ORGANIZATION_INDEX_TTL_SECONDS = 600
_organization_index_cache: dict[str, tuple[float, Organizations]] = {}
_organization_index_refreshing: set[str] = set()
_organization_index_lock = threading.Lock()


def _refresh_organization_index(bind, key: str) -> None:
    try:
        with Session(bind=bind) as db:
            result = OrganizationService(db).get_organizations(curated_only=True)
        _organization_index_cache[key] = (time.monotonic(), result)
    finally:
        with _organization_index_lock:
            _organization_index_refreshing.discard(key)


class OrganizationService:
    """Service layer for organization endpoints."""

    def __init__(self, db: Session):
        self.db = db

    def _get_organization_by_slug(self, slug: str) -> DBOrganization:
        organization = (
            self.db.query(DBOrganization).filter(DBOrganization.slug == slug).first()
        )
        if not organization:
            raise PaperNotFoundError(f"Organization with slug '{slug}' not found")
        return organization

    def get_logo(self, slug: str) -> tuple[bytes, str]:
        """Return stored logo bytes and MIME type for a public logo route."""
        organization = self._get_organization_by_slug(slug)
        if organization.logo_data is None or organization.logo_mime_type is None:
            raise PaperNotFoundError("Logo not available")
        return organization.logo_data, organization.logo_mime_type

    def _organization_to_api(
        self,
        db_org: DBOrganization,
        paper_count: Optional[int] = None,
        *,
        trending_rank: Optional[int] = None,
        top_paper: Optional[DBPaper] = None,
        first_year: Optional[int] = None,
        latest_year: Optional[int] = None,
    ) -> Organization:
        if paper_count is None:
            paper_count = (
                self.db.query(func.count(PaperOrganization.paper_id))
                .join(DBPaper, DBPaper.id == PaperOrganization.paper_id)
                .filter(
                    PaperOrganization.organization_id == db_org.id,
                    eligible_paper_filter(),
                )
                .scalar()
                or 0
            )

        return Organization(
            id=str(db_org.id),
            name=db_org.name,
            slug=db_org.slug,
            hf_slug=db_org.hf_slug,
            hf_url=db_org.hf_url,
            logo_url=self.logo_url(db_org),
            website_url=db_org.website_url,
            github_url=db_org.github_url,
            description=db_org.description,
            paper_count=paper_count,
            is_featured=db_org.is_featured,
            display_order=db_org.display_order,
            organization_trending_score=(
                float(db_org.trending_score)
                if db_org.trending_score is not None
                else None
            ),
            trending_rank=trending_rank,
            top_trending_paper=(
                OrganizationTopPaper(
                    id=str(top_paper.id),
                    arxiv_id=top_paper.arxiv_id,
                    title=top_paper.title,
                )
                if top_paper is not None
                else None
            ),
            first_paper_year=first_year,
            latest_paper_year=latest_year,
            created_at=db_org.created_at,
            updated_at=db_org.updated_at,
        )

    def get_organization_index(self) -> Organizations:
        """Return the public directory cards, cached and refreshed on PostgreSQL."""
        bind = self.db.get_bind()
        if bind.dialect.name != "postgresql":
            return self.get_organizations(curated_only=True)
        key = str(bind.url)
        cached = _organization_index_cache.get(key)
        now = time.monotonic()
        if cached is None:
            result = self.get_organizations(curated_only=True)
            _organization_index_cache[key] = (now, result)
            return result
        if now - cached[0] >= ORGANIZATION_INDEX_TTL_SECONDS:
            with _organization_index_lock:
                start = key not in _organization_index_refreshing
                _organization_index_refreshing.add(key)
            if start:
                threading.Thread(
                    target=_refresh_organization_index,
                    args=(bind, key),
                    name="organization-index-refresh",
                    daemon=True,
                ).start()
        return cached[1]

    def get_organizations(
        self,
        featured_only: bool = False,
        *,
        curated_only: bool = False,
    ) -> Organizations:
        try:
            paper_count_col = func.count(func.distinct(DBPaper.id)).label("paper_count")
            first_year_col = func.min(
                func.extract("year", DBPaper.date_published)
            ).label("first_year")
            latest_year_col = func.max(
                func.extract("year", DBPaper.date_published)
            ).label("latest_year")
            latest_snapshot_dates = (
                self.db.query(
                    OrganizationTrendingHistory.organization_id.label(
                        "organization_id"
                    ),
                    func.max(OrganizationTrendingHistory.snapshot_date).label(
                        "snapshot_date"
                    ),
                )
                .group_by(OrganizationTrendingHistory.organization_id)
                .subquery()
            )
            rows = (
                self.db.query(
                    DBOrganization,
                    paper_count_col,
                    first_year_col,
                    latest_year_col,
                    OrganizationTrendingHistory.raw_score,
                )
                .outerjoin(
                    PaperOrganization,
                    DBOrganization.id == PaperOrganization.organization_id,
                )
                .outerjoin(
                    DBPaper,
                    and_(
                        DBPaper.id == PaperOrganization.paper_id,
                        eligible_paper_filter(),
                    ),
                )
                .outerjoin(
                    latest_snapshot_dates,
                    latest_snapshot_dates.c.organization_id == DBOrganization.id,
                )
                .outerjoin(
                    OrganizationTrendingHistory,
                    and_(
                        OrganizationTrendingHistory.organization_id
                        == latest_snapshot_dates.c.organization_id,
                        OrganizationTrendingHistory.snapshot_date
                        == latest_snapshot_dates.c.snapshot_date,
                    ),
                )
                .group_by(DBOrganization.id, OrganizationTrendingHistory.raw_score)
            )
            if curated_only:
                # The reviewed manifest plus every org established enough to be
                # auto-featured, so backfilled institutions reach the directory.
                rows = rows.having(
                    or_(
                        DBOrganization.slug.in_(BY_PWC_SLUG),
                        paper_count_col >= AUTO_FEATURE_MIN_PAPERS,
                    )
                )
            if featured_only or curated_only:
                rows = rows.filter(DBOrganization.is_featured.is_(True)).order_by(
                    desc(func.coalesce(DBOrganization.trending_score, 0.0)),
                    desc(func.coalesce(OrganizationTrendingHistory.raw_score, 0.0)),
                    desc(paper_count_col),
                    DBOrganization.display_order,
                    DBOrganization.name,
                )
            else:
                rows = rows.order_by(desc(paper_count_col), DBOrganization.name)
            rows = rows.all()

            top_by_org: dict[int, DBPaper] = {}
            if rows:
                org_ids = [row[0].id for row in rows]
                active_score, _max_stars = correlated_paper_score_expressions(
                    get_settings().trending_ranking_mode
                )
                # Rank ids only, then load just each organization's top paper
                # instead of every eligible paper row.
                candidates = (
                    self.db.query(PaperOrganization.organization_id, DBPaper.id)
                    .join(DBPaper, DBPaper.id == PaperOrganization.paper_id)
                    .filter(
                        PaperOrganization.organization_id.in_(org_ids),
                        eligible_paper_filter(),
                    )
                    .order_by(
                        PaperOrganization.organization_id,
                        desc(active_score),
                        desc(DBPaper.date_published),
                        desc(DBPaper.id),
                    )
                    .all()
                )
                top_paper_ids: dict[int, int] = {}
                for organization_id, paper_id in candidates:
                    top_paper_ids.setdefault(organization_id, paper_id)
                papers = {
                    paper.id: paper
                    for paper in self.db.query(DBPaper).filter(
                        DBPaper.id.in_(top_paper_ids.values())
                    )
                }
                top_by_org = {
                    organization_id: papers[paper_id]
                    for organization_id, paper_id in top_paper_ids.items()
                }

            results = [
                self._organization_to_api(
                    db_org,
                    paper_count or 0,
                    trending_rank=(index if featured_only else None),
                    top_paper=top_by_org.get(db_org.id),
                    first_year=int(first_year) if first_year is not None else None,
                    latest_year=int(latest_year) if latest_year is not None else None,
                )
                for index, (
                    db_org,
                    paper_count,
                    first_year,
                    latest_year,
                    _,
                ) in enumerate(rows, start=1)
            ]
            return Organizations(count=len(results), results=results)
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve organizations: {str(e)}")

    def _project_organization(self, organization: DBOrganization) -> Organization:
        """Project one organization with the fields its featured card exposes.

        Featured organizations also carry their trending rank and top paper,
        computed for this organization alone rather than for the whole list.
        """
        paper_count, first_year, latest_year = (
            self.db.query(
                func.count(func.distinct(DBPaper.id)),
                func.min(func.extract("year", DBPaper.date_published)),
                func.max(func.extract("year", DBPaper.date_published)),
            )
            .join(PaperOrganization, PaperOrganization.paper_id == DBPaper.id)
            .filter(
                PaperOrganization.organization_id == organization.id,
                eligible_paper_filter(),
            )
            .one()
        )
        paper_count = paper_count or 0
        if not organization.is_featured:
            return self._organization_to_api(organization, paper_count)

        repo_stats, active_score = active_paper_score_components(
            self.db, get_settings().trending_ranking_mode
        )
        top_paper = (
            self.db.query(DBPaper)
            .join(PaperOrganization, PaperOrganization.paper_id == DBPaper.id)
            .outerjoin(repo_stats, repo_stats.c.paper_id == DBPaper.id)
            .filter(
                PaperOrganization.organization_id == organization.id,
                eligible_paper_filter(),
            )
            .order_by(
                desc(active_score),
                desc(DBPaper.date_published),
                desc(DBPaper.id),
            )
            .first()
        )
        return self._organization_to_api(
            organization,
            paper_count,
            trending_rank=self._featured_trending_rank(organization),
            top_paper=top_paper,
            first_year=int(first_year) if first_year is not None else None,
            latest_year=int(latest_year) if latest_year is not None else None,
        )

    def _featured_trending_rank(self, organization: DBOrganization) -> int:
        """Position of a featured organization in the featured-list ordering.

        Organizations ahead on trending score or latest raw score are counted
        directly. Only exact ties fall through to the paper-count, display-order
        and name tiebreakers, which need per-organization paper counts. Scores
        are compared as floats, matching the featured-list ORDER BY.
        """
        latest_snapshot_dates = (
            self.db.query(
                OrganizationTrendingHistory.organization_id.label("organization_id"),
                func.max(OrganizationTrendingHistory.snapshot_date).label(
                    "snapshot_date"
                ),
            )
            .group_by(OrganizationTrendingHistory.organization_id)
            .subquery()
        )
        featured = (
            self.db.query(
                DBOrganization.id.label("id"),
                cast(func.coalesce(DBOrganization.trending_score, 0.0), Float).label(
                    "score"
                ),
                cast(
                    func.coalesce(OrganizationTrendingHistory.raw_score, 0.0), Float
                ).label("raw_score"),
            )
            .outerjoin(
                latest_snapshot_dates,
                latest_snapshot_dates.c.organization_id == DBOrganization.id,
            )
            .outerjoin(
                OrganizationTrendingHistory,
                and_(
                    OrganizationTrendingHistory.organization_id
                    == latest_snapshot_dates.c.organization_id,
                    OrganizationTrendingHistory.snapshot_date
                    == latest_snapshot_dates.c.snapshot_date,
                ),
            )
            .filter(DBOrganization.is_featured.is_(True))
            .subquery()
        )
        own = (
            self.db.query(featured.c.score, featured.c.raw_score)
            .filter(featured.c.id == organization.id)
            .one()
        )
        ahead = (
            self.db.query(func.count())
            .select_from(featured)
            .filter(
                or_(
                    featured.c.score > own.score,
                    and_(
                        featured.c.score == own.score,
                        featured.c.raw_score > own.raw_score,
                    ),
                )
            )
            .scalar()
        )
        tied_ids = [
            row.id
            for row in self.db.query(featured.c.id).filter(
                featured.c.score == own.score,
                featured.c.raw_score == own.raw_score,
            )
        ]
        if len(tied_ids) > 1:
            paper_count_col = func.count(func.distinct(DBPaper.id))
            tied_ids = [
                row.id
                for row in self.db.query(DBOrganization.id)
                .outerjoin(
                    PaperOrganization,
                    DBOrganization.id == PaperOrganization.organization_id,
                )
                .outerjoin(
                    DBPaper,
                    and_(
                        DBPaper.id == PaperOrganization.paper_id,
                        eligible_paper_filter(),
                    ),
                )
                .filter(DBOrganization.id.in_(tied_ids))
                .group_by(DBOrganization.id)
                .order_by(
                    desc(paper_count_col),
                    DBOrganization.display_order,
                    DBOrganization.name,
                )
            ]
        return ahead + 1 + tied_ids.index(organization.id)

    def get_organization(self, slug: str) -> Organization:
        try:
            return self._project_organization(self._get_organization_by_slug(slug))
        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve organization: {str(e)}")

    def get_organization_contributions(self, slug: str) -> OrganizationContributions:
        """Return daily eligible-paper counts for the trailing 365 days."""
        try:
            organization = self._get_organization_by_slug(slug)
            end_date = date.today()
            start_date = end_date - timedelta(days=364)
            rows = (
                self.db.query(
                    DBPaper.date_published,
                    func.count(func.distinct(DBPaper.id)).label("paper_count"),
                )
                .join(
                    PaperOrganization,
                    DBPaper.id == PaperOrganization.paper_id,
                )
                .filter(
                    PaperOrganization.organization_id == organization.id,
                    DBPaper.date_published.between(start_date, end_date),
                    eligible_paper_filter(),
                )
                .group_by(DBPaper.date_published)
                .order_by(DBPaper.date_published)
                .all()
            )
            results = [
                OrganizationContributionDay(
                    date=published_date,
                    paper_count=paper_count,
                )
                for published_date, paper_count in rows
            ]
            return OrganizationContributions(
                start_date=start_date,
                end_date=end_date,
                total_count=sum(item.paper_count for item in results),
                results=results,
            )
        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(
                f"Failed to retrieve organization contributions: {str(e)}"
            )

    def get_organization_areas_with_tasks(
        self, slug: str
    ) -> OrganizationAreasWithTasks:
        try:
            organization = self._get_organization_by_slug(slug)
            projected_organization = self._project_organization(organization)
            total_paper_count = projected_organization.paper_count or 0

            area_rows = self.db.query(DBArea).order_by(DBArea.name).all()

            paper_count_col = func.count(
                func.distinct(PaperOrganization.paper_id)
            ).label("paper_count")
            task_rows = (
                self.db.query(DBTask, paper_count_col)
                .join(PaperTask, DBTask.id == PaperTask.task_id)
                .join(
                    PaperOrganization,
                    and_(
                        PaperTask.paper_id == PaperOrganization.paper_id,
                        PaperOrganization.organization_id == organization.id,
                    ),
                )
                .join(DBPaper, DBPaper.id == PaperTask.paper_id)
                .filter(eligible_paper_filter())
                .group_by(DBTask.id)
                .order_by(DBTask.name)
                .all()
            )

            tasks_by_area: dict[Optional[int], list[ConferenceTaskSummary]] = {}
            for db_task, paper_count in task_rows:
                summary = ConferenceTaskSummary(
                    id=str(db_task.id),
                    name=db_task.name,
                    slug=db_task.slug,
                    paper_count=paper_count or 0,
                )
                tasks_by_area.setdefault(db_task.area_id, []).append(summary)

            results = [
                OrganizationAreaWithTasks(
                    id=str(area.id),
                    name=area.name,
                    description=area.description,
                    tasks=tasks_by_area.get(area.id, []),
                )
                for area in area_rows
                if tasks_by_area.get(area.id)
            ]

            return OrganizationAreasWithTasks(
                organization=projected_organization,
                total_paper_count=total_paper_count,
                results=results,
            )
        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(
                f"Failed to retrieve organization areas with tasks: {str(e)}"
            )

    def get_organization_papers(
        self,
        slug: str,
        task_slug: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        latest_only: bool = True,
        order_by: str = "date_published",
        order_dir: str = "desc",
        include_resources: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Papers:
        try:
            organization = self._get_organization_by_slug(slug)

            query = (
                self.db.query(DBPaper)
                .join(
                    PaperOrganization,
                    DBPaper.id == PaperOrganization.paper_id,
                )
                .filter(PaperOrganization.organization_id == organization.id)
            )

            if task_slug:
                task = self.db.query(DBTask).filter(DBTask.slug == task_slug).first()
                if not task:
                    raise PaperNotFoundError(f"Task with slug '{task_slug}' not found")
                query = query.join(
                    PaperTask,
                    DBPaper.id == PaperTask.paper_id,
                ).filter(PaperTask.task_id == task.id)

            from backend.services.paper_feed_executor import (
                PaperFeedExecutor,
                SCOPED_ORDERING,
            )
            from backend.services.paper_service import PaperService

            return PaperFeedExecutor(PaperService(self.db)).execute(
                query,
                page=page,
                page_size=page_size,
                order_by=order_by,
                order_dir=order_dir,
                ordering=SCOPED_ORDERING,
                latest_only=latest_only,
                has_code=has_code,
                has_hf_artifacts=has_hf_artifacts,
                start_date=start_date,
                end_date=end_date,
                include_resources=include_resources,
            )

        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve organization papers: {str(e)}")

    @staticmethod
    def logo_url(db_org: DBOrganization) -> Optional[str]:
        if db_org.logo_mime_type:
            return (
                organization_logo_path(
                    db_org.slug,
                    db_org.logo_mime_type,
                    db_org.logo_sha256,
                )
                or f"/api/v1/organizations/{db_org.slug}/logo"
            )
        return db_org.logo_url
