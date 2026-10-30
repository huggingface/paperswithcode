"""
Method service for handling method-related business logic.

This service provides methods for retrieving and managing AI/ML method data,
including pagination, filtering, and paper associations.
"""

from datetime import UTC, date, datetime, timedelta
import time
from typing import Optional, List
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func, desc, asc, or_, case, literal
from sqlalchemy.exc import SQLAlchemyError

from backend.models.database import (
    Method as DBMethod,
    Paper as DBPaper,
    PaperMethod,
)
from backend.models.taxonomy import (
    Method,
    MethodIndex,
    MethodIndexEntry,
    Methods,
    TrendingMethod,
    TrendingMethods,
)
from backend.utils.entity_images import entity_image_url
from backend.utils.entity_images import load_entity_image
from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.utils.urls import get_method_source_url
from backend.utils.slug_utils import slugify
from backend.services.share_lift import rank_by_share_lift
from backend.services.catalog_errors import (
    CatalogConflictError,
    CatalogNotFoundError,
)
from backend.services.entity_search import (
    DETERMINISTIC_CANDIDATE_LIMIT,
    FUZZY_CANDIDATE_LIMIT,
    EntitySearchCandidate,
    EntitySearchKind,
    choose_fuzzy_winner,
    deterministic_match,
    empty_page,
    postgres_fuzzy_ordering,
    postgres_search_expressions,
    prepare_entity_search,
)


# The methods directory asks for the same ranking on every visit, and papers
# arrive in daily imports, so a short shared cache keeps it current.
TRENDING_METHODS_TTL_SECONDS = 600
_trending_methods_cache: dict[tuple, tuple[float, TrendingMethods]] = {}


class MethodService:
    """Service class for method-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_method(self, identifier: str) -> Method:
        operation = (
            self.get_method_by_id if identifier.isdigit() else self.get_method_by_name
        )
        return operation(identifier)

    def create_method(self, *, commit: bool = True, **fields) -> DBMethod:
        slug = slugify(fields["name"])
        if self.db.query(DBMethod.id).filter(DBMethod.slug == slug).first():
            raise CatalogConflictError(f"Method with slug '{slug}' already exists")
        row = DBMethod(slug=slug, **fields)
        self.db.add(row)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        self.db.refresh(row)
        return row

    def get_image(self, identifier: str) -> tuple[bytes, str]:
        result = load_entity_image(self.db, DBMethod, identifier)
        if result is None:
            raise CatalogNotFoundError("Image not available")
        return result

    @staticmethod
    def _convert_db_method_to_api(
        db_method: DBMethod,
        paper_count: Optional[int] = None,
        recent_paper_count: Optional[int] = None,
        baseline_paper_count: Optional[int] = None,
        *,
        recent_days: int = 90,
        baseline_days: int = 180,
    ) -> Method:
        recent = int(recent_paper_count) if recent_paper_count is not None else None
        baseline = (
            int(baseline_paper_count) if baseline_paper_count is not None else None
        )
        recent_velocity = recent * 30.0 / recent_days if recent is not None else None
        baseline_velocity = (
            baseline * 30.0 / baseline_days if baseline is not None else None
        )
        return Method(
            id=str(db_method.id),
            name=db_method.name,
            slug=db_method.slug,
            full_name=db_method.full_name,
            description=db_method.description,
            keywords=db_method.keywords,
            area_id=str(db_method.area_id) if db_method.area_id else None,
            introduced_year=db_method.introduced_year,
            source_paper_id=(
                str(db_method.source_paper_id)
                if db_method.source_paper_id is not None
                else None
            ),
            source_url=get_method_source_url(
                db_method.source_url, db_method.source_paper
            ),
            source_title=db_method.source_title,
            code_snippet_url=db_method.code_snippet_url,
            image_url=entity_image_url(
                "methods",
                db_method.slug,
                db_method.image_mime_type is not None,
                db_method.image_url,
                db_method.updated_at,
            ),
            image_credit=db_method.image_credit,
            collection_name=db_method.collection_name,
            collection_description=db_method.collection_description,
            collection_parent=db_method.collection_parent,
            paper_count=paper_count,
            recent_paper_count=recent,
            baseline_paper_count=baseline,
            trend_score=(
                round(recent_velocity, 4) if recent_velocity is not None else None
            ),
            rate_change=(
                round(recent_velocity / baseline_velocity, 4)
                if recent_velocity is not None and baseline_velocity
                else None
            ),
            created_at=db_method.created_at,
            updated_at=db_method.updated_at,
        )

    def get_methods(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        name: Optional[str] = None,
        full_name: Optional[str] = None,
        introduced_year: Optional[int] = None,
        area_id: Optional[int] = None,
        exclude_id: Optional[int] = None,
        order_by: str = "name",
        order_dir: str = "asc",
        include_trends: bool = False,
        recent_days: int = 90,
        baseline_days: int = 180,
        today: Optional[date] = None,
        _method_ids: Optional[List[int]] = None,
        _count_override: Optional[int] = None,
    ) -> Methods:
        """
        Get a paginated list of AI/ML methods with optional filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of methods per page
            search: Name-only navigational method search
            name: Filter by partial method name match
            full_name: Filter by partial full name match
            introduced_year: Filter by year introduced
            order_by: Field to order by
                (name, full_name, introduced_year, created_at, paper_count,
                trend_score)
            order_dir: Order direction (asc, desc)
            include_trends: Include recent and baseline paper-usage activity
            recent_days: Length of the recent method-usage window
            baseline_days: Length of the preceding comparison window
            today: Optional reproducible endpoint for the usage windows

        Returns:
            Methods object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        if search is not None:
            return self.search_methods(
                query=search,
                page=page,
                page_size=page_size,
                include_trends=include_trends,
            )

        try:
            include_trends = include_trends or order_by == "trend_score"
            generated_on = today or datetime.now(UTC).date()
            recent_start = generated_on - timedelta(days=recent_days)
            baseline_start = recent_start - timedelta(days=baseline_days)
            paper_count_subq = (
                self.db.query(
                    PaperMethod.method_id.label("method_id"),
                    func.count(PaperMethod.paper_id).label("paper_count"),
                )
                .group_by(PaperMethod.method_id)
                .subquery()
            )
            paper_count_col = func.coalesce(paper_count_subq.c.paper_count, 0).label(
                "paper_count"
            )
            activity_subq = None
            if include_trends:
                in_recent = and_(
                    DBPaper.date_published > recent_start,
                    DBPaper.date_published <= generated_on,
                )
                in_baseline = and_(
                    DBPaper.date_published > baseline_start,
                    DBPaper.date_published <= recent_start,
                )
                recent_count = func.count(case((in_recent, DBPaper.id), else_=None))
                baseline_count = func.count(case((in_baseline, DBPaper.id), else_=None))
                activity_subq = (
                    self.db.query(
                        PaperMethod.method_id.label("method_id"),
                        recent_count.label("recent_paper_count"),
                        baseline_count.label("baseline_paper_count"),
                    )
                    .join(
                        DBPaper,
                        and_(
                            DBPaper.id == PaperMethod.paper_id,
                            DBPaper.is_latest_version,
                        ),
                    )
                    .filter(
                        DBPaper.date_published > baseline_start,
                        DBPaper.date_published <= generated_on,
                    )
                    .group_by(PaperMethod.method_id)
                    .subquery()
                )
                recent_count_col = func.coalesce(
                    activity_subq.c.recent_paper_count, 0
                ).label("recent_paper_count")
                baseline_count_col = func.coalesce(
                    activity_subq.c.baseline_paper_count, 0
                ).label("baseline_paper_count")
            else:
                recent_count_col = literal(None).label("recent_paper_count")
                baseline_count_col = literal(None).label("baseline_paper_count")
            query = (
                self.db.query(
                    DBMethod,
                    paper_count_col,
                    recent_count_col,
                    baseline_count_col,
                )
                .options(joinedload(DBMethod.source_paper))
                .outerjoin(
                    paper_count_subq, DBMethod.id == paper_count_subq.c.method_id
                )
            )
            if activity_subq is not None:
                query = query.outerjoin(
                    activity_subq, DBMethod.id == activity_subq.c.method_id
                )

            if _method_ids is not None:
                query = query.filter(DBMethod.id.in_(_method_ids))

            if name:
                query = query.filter(DBMethod.name.ilike(f"%{name}%"))

            if full_name:
                query = query.filter(DBMethod.full_name.ilike(f"%{full_name}%"))

            if introduced_year is not None:
                query = query.filter(DBMethod.introduced_year == introduced_year)

            if area_id is not None:
                query = query.filter(DBMethod.area_id == area_id)

            if exclude_id is not None:
                query = query.filter(DBMethod.id != exclude_id)

            if order_by == "name":
                order_field = DBMethod.name
            elif order_by == "full_name":
                order_field = DBMethod.full_name
            elif order_by == "introduced_year":
                order_field = DBMethod.introduced_year
            elif order_by == "created_at":
                order_field = DBMethod.created_at
            elif order_by == "paper_count":
                order_field = paper_count_col
            elif order_by == "trend_score":
                order_field = recent_count_col
            else:
                order_field = DBMethod.name

            if order_dir == "desc":
                query = query.order_by(desc(order_field))
            else:
                query = query.order_by(asc(order_field))

            total_count = (
                _count_override if _count_override is not None else query.count()
            )

            offset = (page - 1) * page_size
            rows = query.offset(offset).limit(page_size).all()

            methods = [
                self._convert_db_method_to_api(
                    db_method,
                    paper_count or 0,
                    recent_papers,
                    baseline_papers,
                    recent_days=recent_days,
                    baseline_days=baseline_days,
                )
                for db_method, paper_count, recent_papers, baseline_papers in rows
            ]

            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Methods(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=methods,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve methods: {str(e)}")

    def get_method_index(
        self,
        *,
        recent_days: int = 90,
        today: Optional[date] = None,
    ) -> MethodIndex:
        """Return only the fields rendered by the public methods directory."""
        generated_on = today or datetime.now(UTC).date()
        recent_start = generated_on - timedelta(days=recent_days)
        paper_counts = (
            self.db.query(
                PaperMethod.method_id.label("method_id"),
                func.count(PaperMethod.paper_id).label("paper_count"),
            )
            .group_by(PaperMethod.method_id)
            .subquery()
        )
        recent_counts = (
            self.db.query(
                PaperMethod.method_id.label("method_id"),
                func.count(DBPaper.id).label("recent_paper_count"),
            )
            .join(
                DBPaper,
                and_(
                    DBPaper.id == PaperMethod.paper_id,
                    DBPaper.is_latest_version,
                ),
            )
            .filter(
                DBPaper.date_published > recent_start,
                DBPaper.date_published <= generated_on,
            )
            .group_by(PaperMethod.method_id)
            .subquery()
        )
        paper_count = func.coalesce(paper_counts.c.paper_count, 0)
        recent_count = func.coalesce(recent_counts.c.recent_paper_count, 0)
        try:
            rows = (
                self.db.query(
                    DBMethod.id,
                    DBMethod.name,
                    DBMethod.slug,
                    DBMethod.area_id,
                    DBMethod.introduced_year,
                    paper_count.label("paper_count"),
                    recent_count.label("recent_paper_count"),
                )
                .outerjoin(paper_counts, paper_counts.c.method_id == DBMethod.id)
                .outerjoin(recent_counts, recent_counts.c.method_id == DBMethod.id)
                .order_by(desc(recent_count), desc(paper_count), asc(DBMethod.name))
                .all()
            )
        except SQLAlchemyError as error:
            raise DatabaseError(f"Failed to retrieve method index: {error}") from error
        results = [
            MethodIndexEntry(
                id=method_id,
                name=name,
                slug=slug,
                area_id=area_id,
                introduced_year=introduced_year,
                paper_count=int(total),
                trend_score=round(int(recent) * 30.0 / recent_days, 4),
            )
            for (
                method_id,
                name,
                slug,
                area_id,
                introduced_year,
                total,
                recent,
            ) in rows
        ]
        return MethodIndex(count=len(results), results=results)

    def get_trending_methods(
        self,
        *,
        limit: int = 24,
        recent_days: int = 30,
        baseline_days: int = 180,
        min_recent_papers: int = 10,
        min_baseline_papers: int = 10,
        min_share_lift: float = 1.0,
        today: Optional[date] = None,
    ) -> TrendingMethods:
        """Return methods over-indexed in recent papers, briefly cached on PostgreSQL."""
        args = (
            limit,
            recent_days,
            baseline_days,
            min_recent_papers,
            min_baseline_papers,
            min_share_lift,
            today or datetime.now(UTC).date(),
        )
        bind = self.db.get_bind()
        if bind.dialect.name != "postgresql":
            return self._compute_trending_methods(*args)
        key = (str(bind.url), *args)
        cached = _trending_methods_cache.get(key)
        now = time.monotonic()
        if cached and now - cached[0] < TRENDING_METHODS_TTL_SECONDS:
            return cached[1]
        result = self._compute_trending_methods(*args)
        if len(_trending_methods_cache) >= 256:
            _trending_methods_cache.clear()
        _trending_methods_cache[key] = (now, result)
        return result

    def _compute_trending_methods(
        self,
        limit: int,
        recent_days: int,
        baseline_days: int,
        min_recent_papers: int,
        min_baseline_papers: int,
        min_share_lift: float,
        today: date,
    ) -> TrendingMethods:
        try:
            rows = rank_by_share_lift(
                self.db,
                DBMethod,
                PaperMethod.method_id,
                PaperMethod.paper_id,
                limit=limit,
                recent_days=recent_days,
                baseline_days=baseline_days,
                min_recent_papers=min_recent_papers,
                min_baseline_papers=min_baseline_papers,
                min_share_lift=min_share_lift,
                today=today,
            )
        except SQLAlchemyError as error:
            raise DatabaseError(
                f"Failed to compute trending methods: {error}"
            ) from error
        return TrendingMethods(
            results=[
                TrendingMethod(
                    id=row.entity.id,
                    name=row.entity.name,
                    full_name=row.entity.full_name,
                    slug=row.entity.slug,
                    area_id=row.entity.area_id,
                    introduced_year=row.entity.introduced_year,
                    recent_paper_count=row.recent_paper_count,
                    baseline_paper_count=row.baseline_paper_count,
                    share_lift=row.share_lift,
                    trend_score=row.trend_score,
                )
                for row in rows
            ],
            recent_days=recent_days,
            baseline_days=baseline_days,
        )

    def get_method_by_id(self, method_id: str) -> Method:
        """
        Get a specific AI/ML method by ID.

        Args:
            method_id: The method ID

        Returns:
            Method object

        Raises:
            PaperNotFoundError: If method not found
            DatabaseError: If database query fails
        """
        try:
            # Convert string ID to integer
            method_id_int = int(method_id)

            # Query the database
            db_method = (
                self.db.query(DBMethod)
                .options(joinedload(DBMethod.source_paper))
                .filter(DBMethod.id == method_id_int)
                .first()
            )

            if not db_method:
                raise PaperNotFoundError(f"Method with ID {method_id} not found")

            # Get paper count for this method
            paper_count = (
                self.db.query(func.count(PaperMethod.paper_id))
                .filter(PaperMethod.method_id == db_method.id)
                .scalar()
                or 0
            )

            return self._convert_db_method_to_api(db_method, paper_count)

        except ValueError:
            raise PaperNotFoundError(f"Invalid method ID: {method_id}")
        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve method: {str(e)}")

    def get_method_by_name(self, method_name: str) -> Method:
        """
        Get a specific AI/ML method by name or slug.

        Args:
            method_name: The method name or slug (case-insensitive exact match)

        Returns:
            Method object

        Raises:
            PaperNotFoundError: If method not found
            DatabaseError: If database query fails
        """
        try:
            # Try to find by slug first (preferred), then fall back to name
            db_method = (
                self.db.query(DBMethod)
                .options(joinedload(DBMethod.source_paper))
                .filter(
                    or_(
                        DBMethod.slug == method_name.lower(),
                        func.lower(DBMethod.name) == method_name.lower(),
                    )
                )
                .first()
            )

            if not db_method:
                raise PaperNotFoundError(f"Method '{method_name}' not found")

            # Get paper count for this method
            paper_count = (
                self.db.query(func.count(PaperMethod.paper_id))
                .filter(PaperMethod.method_id == db_method.id)
                .scalar()
                or 0
            )

            return self._convert_db_method_to_api(db_method, paper_count)

        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve method: {str(e)}")

    def get_methods_for_paper(
        self,
        paper_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> Methods:
        """
        Get all methods associated with a specific paper.

        Args:
            paper_id: The paper ID
            page: Page number (1-based)
            page_size: Number of methods per page

        Returns:
            Methods object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Base query with join to paper_methods
            query = (
                self.db.query(DBMethod)
                .options(joinedload(DBMethod.source_paper))
                .join(PaperMethod, PaperMethod.method_id == DBMethod.id)
                .filter(PaperMethod.paper_id == paper_id)
                .order_by(DBMethod.name)
            )

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            # Convert to API models
            methods = []
            for db_method in results:
                # Get paper count for this method
                paper_count = (
                    self.db.query(func.count(PaperMethod.paper_id))
                    .filter(PaperMethod.method_id == db_method.id)
                    .scalar()
                    or 0
                )

                methods.append(self._convert_db_method_to_api(db_method, paper_count))

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Methods(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=methods,
            )

        except Exception as e:
            raise DatabaseError(
                f"Failed to retrieve methods for paper {paper_id}: {str(e)}"
            )

    def search_methods(
        self,
        query: str,
        page: int = 1,
        page_size: int = 50,
        include_trends: bool = False,
    ) -> Methods:
        """Search displayed method names with deterministic and typo lanes.

        Args:
            query: Search query string
            page: Page number (1-based)
            page_size: Number of methods per page
            include_trends: Include recent and baseline paper-usage activity

        Returns:
            Methods object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        terms = prepare_entity_search(query, EntitySearchKind.METHOD)
        if not terms.usable:
            return empty_page(Methods)

        candidates = self._method_search_candidates(terms)
        if not candidates:
            return empty_page(Methods)

        trend = self._method_search_trends(
            [candidate.entity_id for candidate in candidates]
        )
        candidates.sort(
            key=lambda candidate: (
                candidate.tier,
                -candidate.relevance,
                -trend.get(candidate.entity_id, (0.0, 0))[0],
                -trend.get(candidate.entity_id, (0.0, 0))[1],
                candidate.name.casefold(),
                candidate.entity_id,
            )
        )

        offset = (page - 1) * page_size
        page_candidates = candidates[offset : offset + page_size]
        page_ids = [candidate.entity_id for candidate in page_candidates]
        response = self.get_methods(
            page=1,
            page_size=max(1, len(page_ids)),
            include_trends=include_trends,
            _method_ids=page_ids,
            _count_override=len(candidates),
        )
        by_id = {int(method.id): method for method in response.results}
        response.results = [
            by_id[entity_id] for entity_id in page_ids if entity_id in by_id
        ]
        response.next_page = page + 1 if offset + page_size < len(candidates) else None
        response.previous_page = page - 1 if page > 1 else None
        return response

    def _method_search_candidates(self, terms) -> List[EntitySearchCandidate]:
        base = self.db.query(DBMethod)
        if self.db.bind.dialect.name != "postgresql":
            methods = base.all()
            candidates = []
            for method in methods:
                match = deterministic_match(
                    terms,
                    name=method.name,
                    slug=method.slug,
                    full_name=method.full_name,
                )
                if match:
                    candidates.append(
                        EntitySearchCandidate(
                            int(method.id), method.name, match[0], match[1]
                        )
                    )
            candidates.sort(
                key=lambda candidate: (
                    candidate.tier,
                    -candidate.relevance,
                    candidate.name.casefold(),
                    candidate.entity_id,
                )
            )
            if candidates:
                return candidates[:DETERMINISTIC_CANDIDATE_LIMIT]
            fuzzy_rows = [(int(method.id), method.name, 0.0) for method in methods]
        else:
            predicate, tier, relevance = postgres_search_expressions(
                DBMethod, terms, full_name=DBMethod.full_name
            )
            rows = (
                base.with_entities(
                    DBMethod.id,
                    DBMethod.name,
                    tier.label("tier"),
                    relevance.label("relevance"),
                )
                .filter(predicate)
                .order_by(
                    asc(tier),
                    desc(relevance),
                    asc(DBMethod.name),
                    asc(DBMethod.id),
                )
                .limit(DETERMINISTIC_CANDIDATE_LIMIT)
                .all()
            )
            if rows:
                return [
                    EntitySearchCandidate(
                        int(entity_id), name, int(match_tier), float(rank or 0.0)
                    )
                    for entity_id, name, match_tier, rank in rows
                ]
            if terms.identity_only or len("".join(terms.tokens)) < 4:
                return []
            distance, similarity = postgres_fuzzy_ordering(
                DBMethod.name, terms.normalized
            )
            fuzzy_rows = (
                base.with_entities(DBMethod.id, DBMethod.name, similarity)
                .order_by(distance, asc(DBMethod.id))
                .limit(FUZZY_CANDIDATE_LIMIT)
                .all()
            )

        if terms.identity_only or len("".join(terms.tokens)) < 4:
            return []
        winner = choose_fuzzy_winner(terms.normalized, list(fuzzy_rows))
        return [winner] if winner else []

    def _method_search_trends(
        self, method_ids: List[int]
    ) -> dict[int, tuple[float, int]]:
        if not method_ids:
            return {}
        today = datetime.now(UTC).date()
        recent_start = today - timedelta(days=90)
        recent_rows = (
            self.db.query(
                PaperMethod.method_id,
                func.count(func.distinct(DBPaper.id)),
            )
            .join(
                DBPaper,
                (DBPaper.id == PaperMethod.paper_id) & DBPaper.is_latest_version,
            )
            .filter(
                PaperMethod.method_id.in_(method_ids),
                DBPaper.date_published > recent_start,
                DBPaper.date_published <= today,
            )
            .group_by(PaperMethod.method_id)
            .all()
        )
        all_time_rows = (
            self.db.query(PaperMethod.method_id, func.count(PaperMethod.paper_id))
            .filter(PaperMethod.method_id.in_(method_ids))
            .group_by(PaperMethod.method_id)
            .all()
        )
        recent = {
            int(method_id): float(count or 0) / 3.0 for method_id, count in recent_rows
        }
        all_time = {
            int(method_id): int(count or 0) for method_id, count in all_time_rows
        }
        return {
            method_id: (recent.get(method_id, 0.0), all_time.get(method_id, 0))
            for method_id in method_ids
        }

    def get_method_papers(
        self,
        method_id: str,
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
        repository_limit: Optional[int] = None,
    ):
        """
        Get papers associated with a specific method.

        Args:
            method_id: The method ID or name
            page: Page number (1-based)
            page_size: Number of papers per page
            latest_only: Whether to only include latest versions
            order_by: Field to order by (date_published, title, citation_count, trending)
            order_dir: Order direction (asc, desc); ignored for trending which is always desc
            include_resources: Whether to include repositories and methods
            repository_limit: Max repositories per paper when including resources

        Returns:
            Papers object with pagination info and results

        Raises:
            PaperNotFoundError: If method not found
            DatabaseError: If database query fails
        """
        try:
            from backend.models.database import Paper as DBPaper

            # Get method to verify it exists - try by ID first, then by slug/name
            method = None
            if method_id.isdigit():
                method_id_int = int(method_id)
                method = (
                    self.db.query(DBMethod).filter(DBMethod.id == method_id_int).first()
                )

            # If not found by ID or not numeric, try by slug first, then name
            if not method:
                method = (
                    self.db.query(DBMethod)
                    .filter(
                        or_(
                            DBMethod.slug == method_id.lower(),
                            func.lower(DBMethod.name) == method_id.lower(),
                        )
                    )
                    .first()
                )

            if not method:
                raise PaperNotFoundError(f"Method '{method_id}' not found")

            # Base query for papers with this method
            query = (
                self.db.query(DBPaper)
                .join(PaperMethod, DBPaper.id == PaperMethod.paper_id)
                .filter(PaperMethod.method_id == method.id)
            )

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
                repository_limit=repository_limit,
            )

        except PaperNotFoundError:
            raise
        except ValueError:
            raise PaperNotFoundError(f"Invalid method ID: {method_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to get papers for method: {str(e)}")

    def add_keywords(self, method_id: str, keywords: List[str]) -> Method:
        """
        Add keywords to a method (appends to existing keywords).

        Args:
            method_id: The method ID or name
            keywords: List of keywords to add

        Returns:
            Updated Method object

        Raises:
            PaperNotFoundError: If method not found
            DatabaseError: If database operation fails
        """
        try:
            # Get method - try by ID first, then by name/slug
            method = None
            if method_id.isdigit():
                method = (
                    self.db.query(DBMethod)
                    .filter(DBMethod.id == int(method_id))
                    .first()
                )

            if not method:
                method = (
                    self.db.query(DBMethod)
                    .filter(
                        or_(
                            DBMethod.slug == method_id.lower(),
                            func.lower(DBMethod.name) == method_id.lower(),
                        )
                    )
                    .first()
                )

            if not method:
                raise PaperNotFoundError(f"Method '{method_id}' not found")

            # Parse existing keywords
            existing_keywords = []
            if method.keywords:
                existing_keywords = [kw.strip() for kw in method.keywords.split(",")]

            # Add new keywords (avoid duplicates)
            for keyword in keywords:
                keyword = keyword.strip()
                if keyword and keyword not in existing_keywords:
                    existing_keywords.append(keyword)

            # Update keywords
            method.keywords = ", ".join(existing_keywords)
            self.db.commit()
            self.db.refresh(method)

            # Return updated method
            return self.get_method_by_id(str(method.id))

        except PaperNotFoundError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to add keywords to method: {str(e)}")

    def remove_keywords(self, method_id: str, keywords: List[str]) -> Method:
        """
        Remove specific keywords from a method.

        Args:
            method_id: The method ID or name
            keywords: List of keywords to remove

        Returns:
            Updated Method object

        Raises:
            PaperNotFoundError: If method not found
            DatabaseError: If database operation fails
        """
        try:
            # Get method - try by ID first, then by name/slug
            method = None
            if method_id.isdigit():
                method = (
                    self.db.query(DBMethod)
                    .filter(DBMethod.id == int(method_id))
                    .first()
                )

            if not method:
                method = (
                    self.db.query(DBMethod)
                    .filter(
                        or_(
                            DBMethod.slug == method_id.lower(),
                            func.lower(DBMethod.name) == method_id.lower(),
                        )
                    )
                    .first()
                )

            if not method:
                raise PaperNotFoundError(f"Method '{method_id}' not found")

            # Parse existing keywords
            existing_keywords = []
            if method.keywords:
                existing_keywords = [kw.strip() for kw in method.keywords.split(",")]

            # Remove specified keywords
            keywords_to_remove = [kw.strip().lower() for kw in keywords]
            existing_keywords = [
                kw for kw in existing_keywords if kw.lower() not in keywords_to_remove
            ]

            # Update keywords
            method.keywords = (
                ", ".join(existing_keywords) if existing_keywords else None
            )
            self.db.commit()
            self.db.refresh(method)

            # Return updated method
            return self.get_method_by_id(str(method.id))

        except PaperNotFoundError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to remove keywords from method: {str(e)}")

    def replace_keywords(self, method_id: str, keywords: List[str]) -> Method:
        """
        Replace all keywords for a method.

        Args:
            method_id: The method ID or name
            keywords: List of keywords to set (replaces all existing keywords)

        Returns:
            Updated Method object

        Raises:
            PaperNotFoundError: If method not found
            DatabaseError: If database operation fails
        """
        try:
            # Get method - try by ID first, then by name/slug
            method = None
            if method_id.isdigit():
                method = (
                    self.db.query(DBMethod)
                    .filter(DBMethod.id == int(method_id))
                    .first()
                )

            if not method:
                method = (
                    self.db.query(DBMethod)
                    .filter(
                        or_(
                            DBMethod.slug == method_id.lower(),
                            func.lower(DBMethod.name) == method_id.lower(),
                        )
                    )
                    .first()
                )

            if not method:
                raise PaperNotFoundError(f"Method '{method_id}' not found")

            # Set new keywords
            cleaned_keywords = [kw.strip() for kw in keywords if kw.strip()]
            method.keywords = ", ".join(cleaned_keywords) if cleaned_keywords else None
            self.db.commit()
            self.db.refresh(method)

            # Return updated method
            return self.get_method_by_id(str(method.id))

        except PaperNotFoundError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to replace keywords for method: {str(e)}")
