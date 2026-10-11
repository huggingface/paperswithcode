"""
Organization service for listing organizations and organization-scoped taxonomy.
"""

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_, asc, desc, func
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
from backend.services.sitemap_service import eligible_paper_filter
from backend.services.trending_ranking_service import active_paper_score_components
from backend.config import get_settings
from backend.utils.exceptions import DatabaseError, PaperNotFoundError
from backend.utils.organization_logos import organization_logo_path


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
                rows = rows.filter(DBOrganization.slug.in_(BY_PWC_SLUG))
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
                repo_stats, active_score = active_paper_score_components(
                    self.db, get_settings().trending_ranking_mode
                )
                candidates = (
                    self.db.query(PaperOrganization.organization_id, DBPaper)
                    .join(DBPaper, DBPaper.id == PaperOrganization.paper_id)
                    .outerjoin(repo_stats, repo_stats.c.paper_id == DBPaper.id)
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
                for organization_id, paper in candidates:
                    top_by_org.setdefault(organization_id, paper)

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

    def get_organization(self, slug: str) -> Organization:
        try:
            organization = self._get_organization_by_slug(slug)
            if organization.is_featured:
                for projected in self.get_organizations(featured_only=True).results:
                    if projected.slug == slug:
                        return projected
            return self._organization_to_api(organization)
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

            total_paper_count = (
                self.db.query(func.count(func.distinct(DBPaper.id)))
                .join(PaperOrganization, PaperOrganization.paper_id == DBPaper.id)
                .filter(
                    PaperOrganization.organization_id == organization.id,
                    eligible_paper_filter(),
                )
                .scalar()
                or 0
            )

            area_rows = self.db.query(DBArea).order_by(DBArea.name).all()

            paper_count_col = func.count(
                func.distinct(PaperOrganization.paper_id)
            ).label("paper_count")
            task_rows = (
                self.db.query(DBTask, paper_count_col)
                .outerjoin(
                    PaperTask,
                    DBTask.id == PaperTask.task_id,
                )
                .join(DBPaper, DBPaper.id == PaperTask.paper_id)
                .outerjoin(
                    PaperOrganization,
                    and_(
                        PaperTask.paper_id == PaperOrganization.paper_id,
                        PaperOrganization.organization_id == organization.id,
                    ),
                )
                .filter(eligible_paper_filter())
                .group_by(DBTask.id)
                .order_by(DBTask.name)
                .all()
            )

            tasks_by_area: dict[Optional[int], list[ConferenceTaskSummary]] = {}
            for db_task, paper_count in task_rows:
                if not paper_count:
                    continue
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

            projected_organization = self._organization_to_api(
                organization, paper_count=total_paper_count
            )
            if organization.is_featured:
                projected_organization = next(
                    (
                        item
                        for item in self.get_organizations(featured_only=True).results
                        if item.slug == slug
                    ),
                    projected_organization,
                )
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

            if latest_only:
                query = query.filter(DBPaper.is_latest_version)

            if has_code:
                from backend.services.paper_service import PaperService

                query = PaperService.apply_has_code_filter(query)

            if has_hf_artifacts:
                from backend.services.paper_service import PaperService

                query = PaperService.apply_has_hf_artifacts_filter(query)

            if start_date is not None:
                query = query.filter(DBPaper.date_published >= start_date)
            if end_date is not None:
                query = query.filter(DBPaper.date_published <= end_date)

            if order_by == "trending":
                # Match the home feed: rank by the active trending metric
                # (paper-level composite score or official-repo velocity per
                # PWC_TRENDING_RANKING_MODE). Unscored papers stay in the list
                # but sort after scored papers.
                from backend.services.paper_service import PaperService

                query = PaperService(self.db).apply_scoped_trending_order(query)
            else:
                if order_by == "title":
                    order_field = DBPaper.title
                elif order_by == "citation_count":
                    order_field = DBPaper.citation_count
                else:
                    order_field = DBPaper.date_published

                if order_dir == "desc":
                    query = query.order_by(desc(order_field), desc(DBPaper.id))
                else:
                    query = query.order_by(asc(order_field), asc(DBPaper.id))

            total_count = query.count()
            offset = (page - 1) * page_size
            db_papers = query.offset(offset).limit(page_size).all()

            from backend.services.paper_service import PaperService

            paper_service = PaperService(self.db)
            papers = paper_service.hydrate_cards(
                db_papers, include_resources=include_resources
            )

            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Papers(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=papers,
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
