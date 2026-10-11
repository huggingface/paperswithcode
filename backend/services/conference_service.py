"""
Conference service for listing conferences and conference-scoped taxonomy.
"""

from datetime import date
from typing import Optional

from sqlalchemy import and_, asc, case, func
from sqlalchemy.orm import Session

from backend.models.conferences import (
    Conference,
    ConferenceAreaWithTasks,
    ConferenceAreasWithTasks,
    ConferenceDeadline,
    ConferenceDeadlines,
    ConferenceTaskSummary,
    Conferences,
)
from backend.models.papers import Papers
from backend.database.conferences_setup.cvpr2026_best_paper_finalist_order import (
    CVPR_2026_BEST_PAPER_FINALIST_ARXIV_ORDER,
)
from backend.models.database import Area as DBArea
from backend.models.database import Conference as DBConference
from backend.models.database import ConferenceDeadline as DBConferenceDeadline
from backend.models.database import Paper as DBPaper
from backend.models.database import PaperConference
from backend.models.database import PaperTask
from backend.models.database import Task as DBTask
from backend.utils.entity_images import entity_image_url
from backend.utils.entity_images import load_entity_image
from backend.utils.exceptions import DatabaseError, PaperNotFoundError
from backend.utils.slug_utils import slugify
from backend.services.catalog_errors import CatalogConflictError, CatalogValidationError
from backend.services.catalog_errors import (
    CatalogNotFoundError,
    CatalogPersistenceError,
)


class ConferenceService:
    """Service layer for conference endpoints."""

    def __init__(self, db: Session):
        self.db = db

    def create_conference(self, *, commit: bool = True, **fields) -> DBConference:
        slug = slugify(fields["name"])
        if len(slug) > 100:
            raise CatalogValidationError("Conference slug would exceed 100 characters")
        if self.db.query(DBConference.id).filter(DBConference.slug == slug).first():
            raise CatalogConflictError(f"Conference with slug '{slug}' already exists")
        row = DBConference(slug=slug, **fields)
        self.db.add(row)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        self.db.refresh(row)
        return row

    def get_image(self, slug: str) -> tuple[bytes, str]:
        result = load_entity_image(self.db, DBConference, slug)
        if result is None:
            raise PaperNotFoundError("Image not available")
        return result

    def lookup_conference(self, slug: str) -> Conference:
        try:
            return self.get_conference(slug)
        except PaperNotFoundError as error:
            raise CatalogNotFoundError(str(error)) from error

    def lookup_conference_papers(self, **kwargs) -> Papers:
        try:
            return self.get_conference_papers(**kwargs)
        except PaperNotFoundError as error:
            raise CatalogNotFoundError(str(error)) from error
        except DatabaseError as error:
            raise CatalogPersistenceError(str(error)) from error

    def _get_conference_by_slug(self, slug: str) -> DBConference:
        conference = (
            self.db.query(DBConference).filter(DBConference.slug == slug).first()
        )
        if not conference:
            raise PaperNotFoundError(f"Conference with slug '{slug}' not found")
        return conference

    def _conference_to_api(
        self,
        db_conference: DBConference,
        paper_count: Optional[int] = None,
        deadlines: Optional[list[DBConferenceDeadline]] = None,
    ) -> Conference:
        if paper_count is None:
            paper_count = (
                self.db.query(func.count(PaperConference.paper_id))
                .filter(PaperConference.conference_id == db_conference.id)
                .scalar()
                or 0
            )

        deadline_models = [
            ConferenceDeadline(
                type=d.deadline_type,
                label=d.label,
                deadline_at=d.deadline_at,
                timezone=d.timezone,
            )
            for d in (deadlines or [])
        ]

        return Conference(
            id=str(db_conference.id),
            name=db_conference.name,
            slug=db_conference.slug,
            short_name=db_conference.short_name,
            year=db_conference.year,
            url=db_conference.url,
            start_date=db_conference.start_date,
            end_date=db_conference.end_date,
            venue=db_conference.venue,
            location=db_conference.location,
            description=db_conference.description,
            image_url=entity_image_url(
                "conferences",
                db_conference.slug,
                db_conference.image_mime_type is not None,
                db_conference.image_url,
                db_conference.updated_at,
            ),
            image_credit=db_conference.image_credit,
            hf_url=db_conference.hf_url,
            paper_count=paper_count,
            tier=db_conference.tier,
            tags=list(db_conference.tags or []),
            country=db_conference.country,
            city=db_conference.city,
            deadlines=deadline_models,
            created_at=db_conference.created_at,
            updated_at=db_conference.updated_at,
        )

    def get_conferences(self) -> Conferences:
        try:
            paper_count_col = func.count(PaperConference.paper_id).label("paper_count")
            rows = (
                self.db.query(DBConference, paper_count_col)
                .outerjoin(
                    PaperConference,
                    DBConference.id == PaperConference.conference_id,
                )
                .group_by(DBConference.id)
                # Only surface conferences with imported papers so the
                # deadline-only rows (no proceedings yet) don't pollute the
                # "browse papers by conference" index.
                .having(func.count(PaperConference.paper_id) > 0)
                .order_by(asc(DBConference.year), DBConference.name)
                .all()
            )

            results = [
                self._conference_to_api(db_conf, paper_count or 0)
                for db_conf, paper_count in rows
            ]
            return Conferences(count=len(results), results=results)
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve conferences: {str(e)}")

    def get_conference_deadlines(self) -> ConferenceDeadlines:
        """Return every conference that has at least one deadline.

        Each conference carries its full deadline list plus the metadata
        (tier, tags, country, city, venue, dates) needed by the
        /ai-deadlines page. Filtering/sorting is done client-side.
        """
        try:
            deadline_rows = (
                self.db.query(DBConferenceDeadline)
                .order_by(DBConferenceDeadline.deadline_at)
                .all()
            )

            deadlines_by_conf: dict[int, list[DBConferenceDeadline]] = {}
            for deadline in deadline_rows:
                deadlines_by_conf.setdefault(deadline.conference_id, []).append(
                    deadline
                )

            if not deadlines_by_conf:
                return ConferenceDeadlines(count=0, results=[])

            conferences = (
                self.db.query(DBConference)
                .filter(DBConference.id.in_(deadlines_by_conf.keys()))
                .all()
            )

            results = [
                self._conference_to_api(
                    conf,
                    paper_count=0,
                    deadlines=deadlines_by_conf.get(conf.id, []),
                )
                for conf in conferences
            ]
            # Order conferences by their earliest deadline so the default
            # (chronological) listing is stable before client-side sorting.
            results.sort(key=lambda c: min(d.deadline_at for d in c.deadlines))
            return ConferenceDeadlines(count=len(results), results=results)
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve conference deadlines: {str(e)}")

    def get_conference(self, slug: str) -> Conference:
        try:
            conference = self._get_conference_by_slug(slug)
            return self._conference_to_api(conference)
        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve conference: {str(e)}")

    OUTSTANDING_AWARDS = ("outstanding", "honorable_mention")
    BEST_PAPER_FINALIST_AWARD = "best_paper_finalist"

    def _count_conference_papers_by_award(
        self, conference: DBConference, awards: tuple[str, ...]
    ) -> int:
        return (
            self.db.query(func.count(PaperConference.paper_id))
            .filter(
                PaperConference.conference_id == conference.id,
                PaperConference.award.in_(awards),
            )
            .scalar()
            or 0
        )

    def _count_conference_papers_by_proceeding(
        self, conference: DBConference, proceeding: str
    ) -> int:
        return (
            self.db.query(func.count(PaperConference.paper_id))
            .join(DBPaper, DBPaper.id == PaperConference.paper_id)
            .filter(
                PaperConference.conference_id == conference.id,
                DBPaper.proceeding == proceeding,
                DBPaper.is_latest_version,
            )
            .scalar()
            or 0
        )

    def get_conference_areas_with_tasks(self, slug: str) -> ConferenceAreasWithTasks:
        try:
            conference = self._get_conference_by_slug(slug)

            total_paper_count = (
                self.db.query(func.count(PaperConference.paper_id))
                .filter(PaperConference.conference_id == conference.id)
                .scalar()
                or 0
            )

            area_rows = self.db.query(DBArea).order_by(DBArea.name).all()

            paper_count_col = func.count(func.distinct(PaperConference.paper_id)).label(
                "paper_count"
            )
            task_rows = (
                self.db.query(DBTask, paper_count_col)
                .outerjoin(
                    PaperTask,
                    DBTask.id == PaperTask.task_id,
                )
                .outerjoin(
                    PaperConference,
                    and_(
                        PaperTask.paper_id == PaperConference.paper_id,
                        PaperConference.conference_id == conference.id,
                    ),
                )
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
                ConferenceAreaWithTasks(
                    id=str(area.id),
                    name=area.name,
                    description=area.description,
                    tasks=tasks_by_area.get(area.id, []),
                )
                for area in area_rows
                if tasks_by_area.get(area.id)
            ]

            return ConferenceAreasWithTasks(
                conference=self._conference_to_api(
                    conference, paper_count=total_paper_count
                ),
                total_paper_count=total_paper_count,
                oral_paper_count=self._count_conference_papers_by_proceeding(
                    conference, f"{conference.name} Oral"
                ),
                spotlight_paper_count=self._count_conference_papers_by_proceeding(
                    conference, f"{conference.name} Spotlight"
                ),
                outstanding_paper_count=self._count_conference_papers_by_award(
                    conference, self.OUTSTANDING_AWARDS
                ),
                best_paper_finalist_paper_count=self._count_conference_papers_by_award(
                    conference, (self.BEST_PAPER_FINALIST_AWARD,)
                ),
                results=results,
            )
        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(
                f"Failed to retrieve conference areas with tasks: {str(e)}"
            )

    def get_conference_papers(
        self,
        slug: str,
        task_slug: Optional[str] = None,
        presentation: Optional[str] = None,
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
            conference = self._get_conference_by_slug(slug)

            query = (
                self.db.query(DBPaper)
                .join(
                    PaperConference,
                    DBPaper.id == PaperConference.paper_id,
                )
                .filter(PaperConference.conference_id == conference.id)
            )

            if task_slug:
                task = self.db.query(DBTask).filter(DBTask.slug == task_slug).first()
                if not task:
                    raise PaperNotFoundError(f"Task with slug '{task_slug}' not found")
                query = query.join(
                    PaperTask,
                    DBPaper.id == PaperTask.paper_id,
                ).filter(PaperTask.task_id == task.id)

            if presentation == "oral":
                query = query.filter(DBPaper.proceeding == f"{conference.name} Oral")
            elif presentation == "spotlight":
                query = query.filter(
                    DBPaper.proceeding == f"{conference.name} Spotlight"
                )
            elif presentation == "outstanding":
                query = query.filter(PaperConference.award.in_(self.OUTSTANDING_AWARDS))
            elif presentation == "best_paper_finalist":
                query = query.filter(
                    PaperConference.award == self.BEST_PAPER_FINALIST_AWARD
                )

            order_override = None
            if presentation in ("outstanding", "best_paper_finalist"):
                if presentation == "outstanding":
                    award_rank = case(
                        (PaperConference.award == "outstanding", 0),
                        (PaperConference.award == "honorable_mention", 1),
                        else_=2,
                    )
                    order_override = (award_rank, asc(DBPaper.title), asc(DBPaper.id))
                elif slug == "cvpr-2026":
                    finalist_rank = case(
                        *[
                            (DBPaper.arxiv_id == arxiv_id, idx)
                            for idx, arxiv_id in enumerate(
                                CVPR_2026_BEST_PAPER_FINALIST_ARXIV_ORDER
                            )
                        ],
                        else_=len(CVPR_2026_BEST_PAPER_FINALIST_ARXIV_ORDER),
                    )
                    order_override = (finalist_rank, asc(DBPaper.id))
                else:
                    order_override = (asc(DBPaper.title), asc(DBPaper.id))
            from backend.services.paper_feed_executor import (
                PaperFeedExecutor,
                SCOPED_ORDERING,
            )
            from backend.services.paper_service import PaperService

            result = PaperFeedExecutor(PaperService(self.db)).execute(
                query,
                page=page,
                page_size=page_size,
                order_by=order_by,
                order_dir=order_dir,
                ordering=SCOPED_ORDERING,
                order_override=order_override,
                latest_only=latest_only,
                has_code=has_code,
                has_hf_artifacts=has_hf_artifacts,
                start_date=start_date,
                end_date=end_date,
                include_resources=include_resources,
            )

            award_by_paper_id: dict[int, Optional[str]] = {}
            if presentation in ("outstanding", "best_paper_finalist"):
                award_filter = (
                    PaperConference.award.in_(self.OUTSTANDING_AWARDS)
                    if presentation == "outstanding"
                    else PaperConference.award == self.BEST_PAPER_FINALIST_AWARD
                )
                award_rows = (
                    self.db.query(PaperConference.paper_id, PaperConference.award)
                    .filter(
                        PaperConference.conference_id == conference.id,
                        PaperConference.paper_id.in_(
                            [int(paper.id) for paper in result.results]
                        ),
                        award_filter,
                    )
                    .all()
                )
                award_by_paper_id = {paper_id: award for paper_id, award in award_rows}

            for paper in result.results:
                if presentation in ("outstanding", "best_paper_finalist"):
                    paper.conference_award = award_by_paper_id.get(int(paper.id))

            return result
        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve conference papers: {str(e)}")
