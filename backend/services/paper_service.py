"""
Paper service for business logic and data processing.

This service handles all paper-related operations, including:
- Fetching papers with proper URL construction
- Converting database models to API models
- Handling pagination
- Managing paper versions
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_, func, text

from backend.models.database import (
    Paper as DBPaper,
    Author as DBAuthor,
    PaperAuthor,
    Task as DBTask,
    Method as DBMethod,
    PaperTask,
    PaperMethod,
    Repository as DBRepository,
    PaperRepository as DBPaperRepository,
    ProjectPage as DBProjectPage,
    PaperProjectPage as DBPaperProjectPage,
    Dataset as DBDataset,
)
from backend.services.thumbnail_service import (
    build_thumbnail_filename,
    build_thumbnail_url,
)
from backend.models.api import (
    Paper,
    Papers,
    PaperSummary,
    PaperVersion,
    PaperVersions,
    Repository,
    ProjectPage,
    TaskSummary,
    MethodSummary,
    BenchmarkSummary,
    VersionComparison,
    AuthorLink,
)
from backend.utils.urls import (
    get_arxiv_abs_url,
    get_method_source_url,
    get_paper_abs_url,
    get_paper_pdf_url,
    get_paper_url,
)
from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.config import get_settings
from backend.services.semantic_scholar_service import SemanticScholarService


class PaperService:
    """
    Service class for paper-related operations.
    """

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    @staticmethod
    def _convert_db_method_to_summary(
        method: DBMethod, source_paper: Optional[DBPaper] = None
    ) -> MethodSummary:
        return MethodSummary(
            id=str(method.id),
            name=method.name,
            slug=method.slug,
            introduced_year=method.introduced_year,
            source_paper_id=str(method.source_paper_id)
            if method.source_paper_id is not None
            else None,
            source_url=get_method_source_url(method.source_url, source_paper),
            source_title=method.source_title,
            code_snippet_url=method.code_snippet_url,
        )

    def _get_paper_relation_data(
        self, paper_ids: List[int], include_resources: bool = False
    ) -> Dict[str, Dict[int, list]]:
        """
        Load paper relationships in batches for API serialization.
        """
        unique_ids = list(dict.fromkeys(int(paper_id) for paper_id in paper_ids))
        relation_data = {
            "authors": defaultdict(list),
            "author_links": defaultdict(list),
            "tasks": defaultdict(list),
            "methods": defaultdict(list),
            "repositories": defaultdict(list),
            "project_pages": defaultdict(list),
            "introduced_benchmarks": defaultdict(list),
        }

        if not unique_ids:
            return relation_data

        author_rows = (
            self.db.query(PaperAuthor.paper_id, DBAuthor.name, DBAuthor.hf_username)
            .join(DBAuthor, PaperAuthor.author_id == DBAuthor.id)
            .filter(PaperAuthor.paper_id.in_(unique_ids))
            .order_by(PaperAuthor.paper_id, PaperAuthor.author_order)
            .all()
        )
        for paper_id, author_name, hf_username in author_rows:
            relation_data["authors"][paper_id].append(author_name)
            relation_data["author_links"][paper_id].append(
                AuthorLink(name=author_name, hf_username=hf_username)
            )

        task_rows = (
            self.db.query(PaperTask.paper_id, DBTask)
            .join(DBTask, PaperTask.task_id == DBTask.id)
            .filter(PaperTask.paper_id.in_(unique_ids))
            .order_by(PaperTask.paper_id, DBTask.name)
            .all()
        )
        for paper_id, task in task_rows:
            relation_data["tasks"][paper_id].append(
                TaskSummary(id=str(task.id), name=task.name, slug=task.slug)
            )

        method_rows = (
            self.db.query(PaperMethod.paper_id, DBMethod)
            .join(DBMethod, PaperMethod.method_id == DBMethod.id)
            .filter(PaperMethod.paper_id.in_(unique_ids))
            .order_by(PaperMethod.paper_id, DBMethod.name)
            .all()
        )
        source_paper_ids = [
            method.source_paper_id
            for _, method in method_rows
            if method.source_paper_id is not None
        ]
        source_papers_by_id = {}
        if source_paper_ids:
            source_papers_by_id = {
                paper.id: paper
                for paper in self.db.query(DBPaper)
                .filter(DBPaper.id.in_(set(source_paper_ids)))
                .all()
            }
        for paper_id, method in method_rows:
            relation_data["methods"][paper_id].append(
                self._convert_db_method_to_summary(
                    method,
                    source_papers_by_id.get(method.source_paper_id),
                )
            )

        introduced_dataset_rows = (
            self.db.query(DBDataset)
            .filter(DBDataset.introducing_paper_id.in_(unique_ids))
            .order_by(DBDataset.introducing_paper_id, DBDataset.name)
            .all()
        )
        for dataset in introduced_dataset_rows:
            relation_data["introduced_benchmarks"][dataset.introducing_paper_id].append(
                BenchmarkSummary(
                    id=str(dataset.id),
                    name=dataset.name,
                    slug=dataset.slug,
                    full_name=dataset.full_name,
                    introduced_year=dataset.introduced_year,
                )
            )

        if include_resources:
            repository_rows = (
                self.db.query(
                    DBPaperRepository.paper_id,
                    DBPaperRepository.is_official,
                    DBRepository,
                )
                .join(
                    DBRepository,
                    DBPaperRepository.repository_id == DBRepository.id,
                )
                .filter(DBPaperRepository.paper_id.in_(unique_ids))
                .order_by(
                    DBPaperRepository.paper_id,
                    desc(DBPaperRepository.is_official),
                    desc(DBRepository.num_stars),
                )
                .all()
            )
            for paper_id, is_official, repository in repository_rows:
                relation_data["repositories"][paper_id].append(
                    Repository(
                        id=str(repository.id),
                        url=repository.url,
                        owner=repository.owner,
                        name=repository.name,
                        num_stars=repository.num_stars,
                        is_official=is_official,
                        source=repository.source,
                        trending_score=float(repository.trending_score)
                        if repository.trending_score is not None
                        else None,
                        trending_score_updated_at=repository.trending_score_updated_at,
                        created_at=repository.created_at.date()
                        if repository.created_at
                        else None,
                        updated_at=repository.updated_at.date()
                        if repository.updated_at
                        else None,
                    )
                )

            project_page_rows = (
                self.db.query(DBPaperProjectPage.paper_id, DBProjectPage)
                .join(
                    DBProjectPage,
                    DBPaperProjectPage.project_page_id == DBProjectPage.id,
                )
                .filter(DBPaperProjectPage.paper_id.in_(unique_ids))
                .order_by(DBPaperProjectPage.paper_id, desc(DBProjectPage.created_at))
                .all()
            )
            for paper_id, project_page in project_page_rows:
                relation_data["project_pages"][paper_id].append(
                    ProjectPage(
                        id=str(project_page.id),
                        url=project_page.url,
                        is_official=project_page.is_official,
                        source=project_page.source,
                        created_at=project_page.created_at.date()
                        if project_page.created_at
                        else None,
                        updated_at=project_page.updated_at.date()
                        if project_page.updated_at
                        else None,
                    )
                )

        return relation_data

    @staticmethod
    def _get_published_after_for_time_window(
        time_window: str,
        today: Optional[date] = None,
    ) -> Optional[date]:
        """
        Convert public feed time presets into UTC date boundaries.
        """
        current_date = today or datetime.now(timezone.utc).date()

        if time_window == "today":
            return current_date
        if time_window == "week":
            return current_date - timedelta(days=current_date.weekday())
        if time_window == "month":
            return current_date.replace(day=1)
        if time_window == "all_time":
            return None

        raise ValueError(f"Unsupported time window: {time_window}")

    def _convert_db_paper_to_api(
        self,
        db_paper: DBPaper,
        include_resources: bool = False,
        relation_data: Optional[Dict[str, Dict[int, list]]] = None,
    ) -> Paper:
        """
        Convert database paper model to API paper model.

        Args:
            db_paper: Database paper instance
            include_resources: Whether to include repositories and project pages

        Returns:
            API Paper model
        """
        if relation_data is None:
            relation_data = self._get_paper_relation_data(
                [db_paper.id], include_resources=include_resources
            )

        authors = relation_data["authors"].get(db_paper.id, [])
        author_links = relation_data["author_links"].get(db_paper.id, [])

        # Source-aware URL construction. ArXiv rows derive abs/pdf URLs from
        # `arxiv_id` + `version`. External rows use `source_url` for the
        # primary link and have no derived PDF.
        url_abs = get_paper_abs_url(
            db_paper.source,
            db_paper.arxiv_id,
            db_paper.version,
            db_paper.source_url,
        )
        url_pdf = get_paper_pdf_url(
            db_paper.source, db_paper.arxiv_id, db_paper.version
        )

        # External rows may store an explicit captured thumbnail. ArXiv rows
        # continue to derive their stable thumbnail URL from arxiv_id/version.
        thumbnail_url = db_paper.thumbnail_url
        if thumbnail_url is None and db_paper.source == "arxiv" and db_paper.arxiv_id:
            filename = build_thumbnail_filename(
                db_paper.arxiv_id, db_paper.version or "v1"
            )
            thumbnail_url = build_thumbnail_url(filename)

        tasks = relation_data["tasks"].get(db_paper.id) or None
        methods = relation_data["methods"].get(db_paper.id) or None
        introduced_benchmarks = (
            relation_data["introduced_benchmarks"].get(db_paper.id) or None
        )
        repositories = (
            relation_data["repositories"].get(db_paper.id) or None
            if include_resources
            else None
        )
        project_pages = (
            relation_data["project_pages"].get(db_paper.id) or None
            if include_resources
            else None
        )

        # Create the API model
        paper_data = {
            "id": str(db_paper.id),
            "arxiv_id": db_paper.arxiv_id,
            "source": db_paper.source,
            "source_url": db_paper.source_url,
            "url_abs": url_abs,
            "url_pdf": url_pdf,
            "thumbnail_url": thumbnail_url,
            "title": db_paper.title,
            "abstract": db_paper.abstract or "",
            "authors": authors,
            "author_links": author_links,
            "published": db_paper.date_published,
            "conference": db_paper.conference,
            "conference_url_abs": db_paper.conference_url_abs,
            "conference_url_pdf": db_paper.conference_url_pdf,
            "proceeding": db_paper.proceeding,
            "version": db_paper.version,
            "is_latest_version": db_paper.is_latest_version,
            "citation_count": db_paper.citation_count,
            "semantic_scholar_id": db_paper.semantic_scholar_id,
            "citation_updated_at": db_paper.citation_updated_at,
            "primary_category": db_paper.primary_category,
            "all_categories": db_paper.all_categories or [],
            "urls_extracted": db_paper.urls_extracted,
            "hf_models": db_paper.hf_models or [],
            "hf_datasets": db_paper.hf_datasets or [],
            "hf_spaces": db_paper.hf_spaces or [],
            "repositories": repositories,
            "project_pages": project_pages,
            "tasks": tasks,
            "methods": methods,
            "introduced_benchmarks": introduced_benchmarks,
        }

        return Paper(**paper_data)

    def _convert_db_paper_to_summary(self, db_paper: DBPaper) -> PaperSummary:
        """
        Convert database paper model to API paper summary model.

        Args:
            db_paper: Database paper instance

        Returns:
            API PaperSummary model
        """
        # Get authors for this paper - handle case where authors table doesn't exist yet
        authors = []
        try:
            authors_query = (
                self.db.query(DBAuthor)
                .join(PaperAuthor)
                .filter(PaperAuthor.paper_id == db_paper.id)
                .order_by(PaperAuthor.author_order)
            )
            authors = [author.name for author in authors_query.all()]
        except Exception:
            # Authors table doesn't exist yet, use empty list
            authors = []

        # Source-aware URL: ArXiv abs URL for ArXiv rows, source_url for external.
        url_abs = get_paper_abs_url(
            db_paper.source,
            db_paper.arxiv_id,
            db_paper.version,
            db_paper.source_url,
        )

        return PaperSummary(
            id=str(db_paper.id),
            title=db_paper.title,
            arxiv_id=db_paper.arxiv_id,
            source=db_paper.source,
            source_url=db_paper.source_url,
            authors=authors,
            published=db_paper.date_published,
            url_abs=url_abs,
            citation_count=db_paper.citation_count,
        )

    def get_paper_by_id(self, paper_id: int, include_resources: bool = False) -> Paper:
        """
        Get a paper by its database ID.

        Args:
            paper_id: Database paper ID
            include_resources: Whether to include repositories and project pages

        Returns:
            API Paper model

        Raises:
            PaperNotFoundError: If paper is not found
        """
        try:
            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()

            if not db_paper:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

            relation_data = self._get_paper_relation_data(
                [db_paper.id], include_resources=include_resources
            )
            return self._convert_db_paper_to_api(
                db_paper,
                include_resources=include_resources,
                relation_data=relation_data,
            )

        except Exception as e:
            if isinstance(e, PaperNotFoundError):
                raise
            raise DatabaseError(f"Error fetching paper {paper_id}: {str(e)}")

    def get_paper_by_id_or_arxiv(
        self, identifier: str, include_resources: bool = False
    ) -> Paper:
        """
        Resolve a paper by either an ArXiv ID or an internal database ID.

        This is used by the public `/papers/{paper_id}` route so that:
          - `source='arxiv'` rows keep ArXiv-style URLs like `/papers/2504.12516`.
          - `source='external'` rows are addressed by their internal `papers.id`.

        ArXiv lookups are attempted first when the identifier matches the
        ArXiv format. Otherwise the identifier is parsed as an integer ID.
        """
        from backend.utils.urls import validate_arxiv_id

        if validate_arxiv_id(identifier):
            try:
                return self.get_paper_by_arxiv_id(
                    identifier, version=None, include_resources=include_resources
                )
            except PaperNotFoundError:
                # Fall through to internal-ID lookup; external rows or
                # unindexed ArXiv IDs are still addressable that way.
                pass

        try:
            paper_id = int(identifier)
        except (TypeError, ValueError):
            raise PaperNotFoundError(f"No paper found for identifier '{identifier}'")

        return self.get_paper_by_id(paper_id, include_resources=include_resources)

    def get_paper_by_arxiv_id(
        self,
        arxiv_id: str,
        version: Optional[str] = None,
        include_resources: bool = False,
    ) -> Paper:
        """
        Get a paper by ArXiv ID and optional version.

        Args:
            arxiv_id: ArXiv ID
            version: Specific version (if None, gets latest version)
            include_resources: Whether to include repositories and project pages

        Returns:
            API Paper model

        Raises:
            PaperNotFoundError: If paper is not found
        """
        try:
            query = self.db.query(DBPaper).filter(DBPaper.arxiv_id == arxiv_id)

            if version:
                query = query.filter(DBPaper.version == version)
            else:
                # Get latest version
                query = query.filter(DBPaper.is_latest_version)

            db_paper = query.first()

            if not db_paper:
                version_text = f" version {version}" if version else " (latest version)"
                raise PaperNotFoundError(
                    f"Paper with ArXiv ID {arxiv_id}{version_text} not found"
                )

            relation_data = self._get_paper_relation_data(
                [db_paper.id], include_resources=include_resources
            )
            return self._convert_db_paper_to_api(
                db_paper,
                include_resources=include_resources,
                relation_data=relation_data,
            )

        except Exception as e:
            if isinstance(e, PaperNotFoundError):
                raise
            raise DatabaseError(f"Error fetching paper {arxiv_id}: {str(e)}")

    def get_papers(
        self,
        page: int = 1,
        page_size: int = None,
        search: Optional[str] = None,
        published_after: Optional[str] = None,
        published_before: Optional[str] = None,
        conference: Optional[str] = None,
        latest_only: bool = True,
        order_by: str = "trending",
        order_dir: str = "desc",
        time_window: str = "all_time",
        include_resources: bool = False,
    ) -> Papers:
        """
        Get paginated list of papers with optional filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of papers per page
            search: Search term for title/abstract
            published_after: Filter papers published after this date (YYYY-MM-DD)
            published_before: Filter papers published before this date (YYYY-MM-DD)
            conference: Filter by conference
            latest_only: Whether to only include latest versions of papers
            order_by: Field to order by (date_published, citation_count, trending)
            order_dir: Order direction (asc, desc)
            time_window: Feed time window (today, week, month, all_time)

        Returns:
            Paginated Papers response
        """
        try:
            # Set default page size
            if page_size is None:
                page_size = self.settings.default_page_size

            # Limit page size
            page_size = min(page_size, self.settings.max_page_size)

            allowed_order_columns = {
                "date_published": DBPaper.date_published,
                "citation_count": DBPaper.citation_count,
            }
            if order_by not in {*allowed_order_columns.keys(), "trending"}:
                raise ValueError(f"Unsupported order_by: {order_by}")

            if time_window != "all_time":
                published_after = self._get_published_after_for_time_window(time_window)

            # Special handling for trending sort
            if order_by == "trending":
                return self._get_trending_papers(
                    page=page,
                    page_size=page_size,
                    search=search,
                    published_after=published_after,
                    published_before=published_before,
                    conference=conference,
                    latest_only=latest_only,
                    include_resources=include_resources,
                )

            # Build base query
            query = self.db.query(DBPaper)

            # Filter for latest versions only
            if latest_only:
                query = query.filter(DBPaper.is_latest_version)

            # Apply search filter
            if search:
                search_term = f"%{search}%"
                query = query.filter(
                    or_(
                        DBPaper.title.ilike(search_term),
                        DBPaper.abstract.ilike(search_term),
                    )
                )

            # Apply date filters
            if published_after:
                query = query.filter(DBPaper.date_published >= published_after)

            if published_before:
                query = query.filter(DBPaper.date_published <= published_before)

            # Apply conference filter
            if conference:
                query = query.filter(DBPaper.conference.ilike(f"%{conference}%"))

            # Apply ordering
            order_column = allowed_order_columns[order_by]
            if order_dir.lower() == "desc":
                query = query.order_by(desc(order_column))
            else:
                query = query.order_by(asc(order_column))

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            db_papers = query.offset(offset).limit(page_size).all()

            relation_data = self._get_paper_relation_data(
                [paper.id for paper in db_papers], include_resources=include_resources
            )

            # Convert to API models
            api_papers = [
                self._convert_db_paper_to_api(
                    db_paper,
                    include_resources=include_resources,
                    relation_data=relation_data,
                )
                for db_paper in db_papers
            ]

            # Calculate pagination info
            total_pages = (total_count + page_size - 1) // page_size
            next_page = page + 1 if page < total_pages else None
            previous_page = page - 1 if page > 1 else None

            return Papers(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=api_papers,
            )

        except Exception as e:
            raise DatabaseError(f"Error fetching papers: {str(e)}")

    def _get_trending_papers(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        published_after: Optional[str] = None,
        published_before: Optional[str] = None,
        conference: Optional[str] = None,
        latest_only: bool = True,
        include_resources: bool = False,
    ) -> Papers:
        """
        Get papers sorted by official repository trending score.

        This uses the EMA-based trending scores calculated by the hourly CRON job.
        Only repositories marked official for a paper contribute to that paper's
        ranking.

        Args:
            Same as get_papers()

        Returns:
            Paginated Papers response sorted by official repository trending score
        """
        try:
            # Two-step dedup: first pick the best official repo per paper,
            # then ensure each repository contributes at most one paper. When
            # multiple latest papers share the same GitHub repo (e.g. v1/v2
            # papers both flagged latest, or unrelated papers wired to the
            # same code release), we keep only the most recently published
            # paper so the trending feed never shows duplicate repo cards.
            sql_query = text("""
                WITH paper_trending AS (
                    SELECT DISTINCT ON (p.id)
                        p.id as paper_id,
                        p.date_published,
                        r.id as repository_id,
                        r.trending_score,
                        r.num_stars
                    FROM papers p
                    LEFT JOIN paper_repositories pr
                        ON p.id = pr.paper_id
                        AND pr.is_official = TRUE
                    LEFT JOIN repositories r
                        ON pr.repository_id = r.id
                        AND r.trending_score IS NOT NULL
                        AND r.trending_score_updated_at >= (NOW() - INTERVAL '24 hours')
                    WHERE (:search_term IS NOT NULL OR r.id IS NOT NULL)
                        AND (:search_term IS NULL OR p.title ILIKE :search_term OR p.abstract ILIKE :search_term)
                        AND (:published_after IS NULL OR p.date_published >= :published_after)
                        AND (:published_before IS NULL OR p.date_published <= :published_before)
                        AND (:conference IS NULL OR p.conference ILIKE :conference)
                        AND (:latest_only = FALSE OR p.is_latest_version = TRUE)
                    ORDER BY p.id, r.trending_score DESC NULLS LAST, r.num_stars DESC NULLS LAST
                ),
                ranked_by_repo AS (
                    SELECT
                        paper_id,
                        trending_score,
                        num_stars,
                        ROW_NUMBER() OVER (
                            PARTITION BY repository_id
                            ORDER BY date_published DESC NULLS LAST, paper_id DESC
                        ) as repo_paper_rank
                    FROM paper_trending
                )
                SELECT
                    paper_id,
                    COUNT(*) OVER() as total_count
                FROM ranked_by_repo
                WHERE repo_paper_rank = 1
                ORDER BY trending_score DESC NULLS LAST, num_stars DESC
                LIMIT :limit OFFSET :offset
            """)

            # Prepare query parameters
            search_param = f"%{search}%" if search else None
            conference_param = f"%{conference}%" if conference else None

            # Execute the query to get paper IDs
            result = self.db.execute(
                sql_query,
                {
                    "search_term": search_param,
                    "published_after": published_after,
                    "published_before": published_before,
                    "conference": conference_param,
                    "latest_only": latest_only,
                    "limit": page_size,
                    "offset": (page - 1) * page_size,
                },
            ).fetchall()

            if not result:
                # No trending data available yet
                return Papers(
                    count=0,
                    next_page=None,
                    previous_page=None,
                    results=[],
                )

            # Extract paper IDs and total count
            paper_ids = [row[0] for row in result]
            total_count = result[0][1] if result else 0

            papers_by_id = {
                paper.id: paper
                for paper in self.db.query(DBPaper)
                .filter(DBPaper.id.in_(paper_ids))
                .all()
            }
            db_papers = [
                papers_by_id[paper_id]
                for paper_id in paper_ids
                if paper_id in papers_by_id
            ]

            relation_data = self._get_paper_relation_data(
                [paper.id for paper in db_papers], include_resources=include_resources
            )

            # Convert to API models
            api_papers = [
                self._convert_db_paper_to_api(
                    db_paper,
                    include_resources=include_resources,
                    relation_data=relation_data,
                )
                for db_paper in db_papers
            ]

            # Calculate pagination info
            total_pages = (total_count + page_size - 1) // page_size
            next_page = page + 1 if page < total_pages else None
            previous_page = page - 1 if page > 1 else None

            return Papers(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=api_papers,
            )

        except Exception as e:
            raise DatabaseError(f"Error fetching trending papers: {str(e)}")

    def get_paper_versions(self, arxiv_id: str) -> PaperVersions:
        """
        Get all versions of a paper by ArXiv ID.

        Args:
            arxiv_id: ArXiv ID

        Returns:
            PaperVersions with all versions

        Raises:
            PaperNotFoundError: If no versions found
        """
        try:
            db_papers = (
                self.db.query(DBPaper)
                .filter(DBPaper.arxiv_id == arxiv_id)
                .order_by(desc(DBPaper.version))
                .all()
            )

            if not db_papers:
                raise PaperNotFoundError(f"No papers found for ArXiv ID {arxiv_id}")

            versions = []
            for db_paper in db_papers:
                abstract_preview = None
                if db_paper.abstract:
                    abstract_preview = (
                        db_paper.abstract[:200] + "..."
                        if len(db_paper.abstract) > 200
                        else db_paper.abstract
                    )

                version = PaperVersion(
                    id=str(db_paper.id),
                    version=db_paper.version,
                    title=db_paper.title,
                    is_latest=db_paper.is_latest_version,
                    published=db_paper.date_published,
                    url_abs=get_arxiv_abs_url(db_paper.arxiv_id, db_paper.version),
                    paper_url=get_paper_url(db_paper.id, db_paper.arxiv_id),
                    abstract_preview=abstract_preview,
                )
                versions.append(version)

            return PaperVersions(
                arxiv_id=arxiv_id, total_versions=len(versions), versions=versions
            )

        except Exception as e:
            if isinstance(e, PaperNotFoundError):
                raise
            raise DatabaseError(
                f"Error fetching paper versions for {arxiv_id}: {str(e)}"
            )

    def compare_paper_versions(
        self, arxiv_id: str, from_version: str, to_version: str
    ) -> VersionComparison:
        """
        Compare two versions of a paper.

        Args:
            arxiv_id: ArXiv ID
            from_version: Source version
            to_version: Target version

        Returns:
            VersionComparison object

        Raises:
            PaperNotFoundError: If either version is not found
        """
        try:
            # Get both versions
            old_paper = (
                self.db.query(DBPaper)
                .filter(DBPaper.arxiv_id == arxiv_id, DBPaper.version == from_version)
                .first()
            )

            new_paper = (
                self.db.query(DBPaper)
                .filter(DBPaper.arxiv_id == arxiv_id, DBPaper.version == to_version)
                .first()
            )

            if not old_paper:
                raise PaperNotFoundError(
                    f"Paper version {from_version} not found for ArXiv ID {arxiv_id}"
                )

            if not new_paper:
                raise PaperNotFoundError(
                    f"Paper version {to_version} not found for ArXiv ID {arxiv_id}"
                )

            # Calculate time difference
            time_between = None
            if old_paper.created_at and new_paper.created_at:
                time_between = (new_paper.created_at - old_paper.created_at).days

            return VersionComparison(
                from_version=from_version,
                to_version=to_version,
                title_changed=old_paper.title != new_paper.title,
                abstract_changed=old_paper.abstract != new_paper.abstract,
                date_changed=old_paper.date_published != new_paper.date_published,
                time_between_versions=time_between,
            )

        except Exception as e:
            if isinstance(e, PaperNotFoundError):
                raise
            raise DatabaseError(f"Error comparing paper versions: {str(e)}")

    def search_papers(self, query: str, limit: int = 10) -> List[PaperSummary]:
        """
        Fast search for papers ordered primarily by citation count.

        Uses ILIKE queries with citation-based ranking:
        1. All papers matching query (title or abstract)
        2. Sorted by citation count (highest first)
        3. Small relevance boost for title matches

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of paper summaries ordered by citation count and relevance
        """
        try:
            from sqlalchemy import case

            # Create a small relevance boost that doesn't override citation ordering
            # Title matches get a tiny boost (equivalent to ~100 citations)
            relevance_boost = case(
                (
                    DBPaper.title.ilike(query),
                    100,
                ),  # Exact title match - small boost
                (
                    DBPaper.title.ilike(f"%{query}%"),
                    50,
                ),  # Title contains - smaller boost
                else_=0,
            )

            results = (
                self.db.query(DBPaper)
                .filter(
                    or_(
                        DBPaper.title.ilike(query),  # Exact match
                        DBPaper.title.ilike(f"%{query}%"),  # Title contains
                        DBPaper.abstract.ilike(f"%{query}%"),  # Abstract contains
                    )
                )
                .filter(DBPaper.is_latest_version)
                .order_by(
                    desc(
                        DBPaper.citation_count + relevance_boost
                    ),  # Citations first, small boost for title relevance
                    desc(DBPaper.date_published),  # Date as tiebreaker
                )
                .limit(limit)
                .all()
            )

            return [self._convert_db_paper_to_summary(db_paper) for db_paper in results]

        except Exception as e:
            raise DatabaseError(f"Error searching papers: {str(e)}")

    def get_recent_papers(self, limit: int = 10) -> List[PaperSummary]:
        """
        Get recently published papers.

        Args:
            limit: Maximum number of papers to return

        Returns:
            List of recent paper summaries
        """
        try:
            db_papers = (
                self.db.query(DBPaper)
                .filter(DBPaper.is_latest_version)
                .filter(DBPaper.date_published.is_not(None))
                .order_by(desc(DBPaper.date_published))
                .limit(limit)
                .all()
            )

            return [
                self._convert_db_paper_to_summary(db_paper) for db_paper in db_papers
            ]

        except Exception as e:
            raise DatabaseError(f"Error fetching recent papers: {str(e)}")

    def get_paper_stats(self) -> Dict[str, Any]:
        """
        Get statistics about papers in the database.

        Returns:
            Dictionary with paper statistics
        """
        try:
            total_papers = self.db.query(DBPaper).count()
            total_latest = (
                self.db.query(DBPaper).filter(DBPaper.is_latest_version).count()
            )

            # Get papers by year
            year_stats = (
                self.db.query(
                    func.extract("year", DBPaper.date_published).label("year"),
                    func.count(DBPaper.id).label("count"),
                )
                .filter(DBPaper.date_published.is_not(None))
                .filter(DBPaper.is_latest_version)
                .group_by(func.extract("year", DBPaper.date_published))
                .order_by(desc("year"))
                .limit(10)
                .all()
            )

            # Get latest paper date
            latest_paper = (
                self.db.query(DBPaper)
                .filter(DBPaper.date_published.is_not(None))
                .order_by(desc(DBPaper.date_published))
                .first()
            )

            return {
                "total_papers": total_papers,
                "latest_versions_only": total_latest,
                "papers_by_year": [
                    {"year": int(stat.year), "count": stat.count} for stat in year_stats
                ],
                "latest_paper_date": latest_paper.date_published.isoformat()
                if latest_paper
                else None,
            }

        except Exception as e:
            raise DatabaseError(f"Error fetching paper statistics: {str(e)}")

    async def update_citation_counts(self, limit: int = 100) -> Dict[str, Any]:
        """
        Update citation counts for papers using Semantic Scholar API.

        Args:
            limit: Maximum number of papers to update

        Returns:
            Dictionary with update statistics
        """
        try:
            semantic_scholar_service = SemanticScholarService(self.db)
            updated_count = await semantic_scholar_service.batch_update_citation_counts(
                limit
            )

            return {
                "updated_count": updated_count,
                "limit": limit,
                "status": "completed",
            }

        except Exception as e:
            raise DatabaseError(f"Error updating citation counts: {str(e)}")

    async def search_papers_with_semantic_scholar(
        self, query: str, limit: int = 10
    ) -> List[PaperSummary]:
        """
        Enhanced search that also queries Semantic Scholar for highly cited papers.

        This method combines local database search with Semantic Scholar API results
        to ensure highly cited papers are included in search results.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of paper summaries with enhanced citation-based ranking
        """
        try:
            # Get local search results
            local_results = self.search_papers(query, limit)

            # If we have enough results, return them
            if len(local_results) >= limit:
                return local_results

            # Otherwise, supplement with Semantic Scholar search
            semantic_scholar_service = SemanticScholarService(self.db)
            highly_cited = await semantic_scholar_service.get_highly_cited_papers(
                query, limit
            )

            # Try to find these papers in our database
            local_titles = {result.title.lower() for result in local_results}
            supplemental_results = []

            for title, citation_count in highly_cited:
                if (
                    title.lower() not in local_titles
                    and len(local_results) + len(supplemental_results) < limit
                ):
                    # Try to find this paper in our database
                    db_paper = (
                        self.db.query(DBPaper)
                        .filter(DBPaper.title.ilike(f"%{title}%"))
                        .filter(DBPaper.is_latest_version)
                        .first()
                    )

                    if db_paper:
                        # Update citation count if it's higher
                        if citation_count > db_paper.citation_count:
                            db_paper.citation_count = citation_count
                            self.db.commit()

                        supplemental_results.append(
                            self._convert_db_paper_to_summary(db_paper)
                        )

            # Combine and return results
            all_results = local_results + supplemental_results
            return all_results[:limit]

        except Exception:
            # Fall back to local search if Semantic Scholar fails
            return self.search_papers(query, limit)

    def add_paper(self, paper_data: Dict[str, Any]) -> Optional[int]:
        """
        Add a single paper to the database.

        Args:
            paper_data: Dictionary containing paper information with keys:
                - arxiv_id: ArXiv ID (required)
                - title: Paper title (required)
                - abstract: Paper abstract (optional)
                - version: Version string (default: 'v1')
                - date_published: Publication date (optional)
                - conference: Conference name (optional)
                - conference_url_abs: Conference abstract URL (optional)
                - conference_url_pdf: Conference PDF URL (optional)
                - proceeding: Proceeding information (optional)
                - is_latest_version: Whether this is the latest version (default: True)

        Returns:
            Paper ID if successful, None if paper already exists or on error
        """
        try:
            # Check if paper already exists
            existing = (
                self.db.query(DBPaper)
                .filter(
                    DBPaper.arxiv_id == paper_data["arxiv_id"],
                    DBPaper.version == paper_data.get("version", "v1"),
                )
                .first()
            )

            if existing:
                return None  # Paper already exists

            # Create new paper
            db_paper = DBPaper(
                arxiv_id=paper_data["arxiv_id"],
                title=paper_data["title"],
                abstract=paper_data.get("abstract"),
                version=paper_data.get("version", "v1"),
                date_published=paper_data.get("date_published"),
                conference=paper_data.get("conference"),
                conference_url_abs=paper_data.get("conference_url_abs"),
                conference_url_pdf=paper_data.get("conference_url_pdf"),
                proceeding=paper_data.get("proceeding"),
                is_latest_version=paper_data.get("is_latest_version", True),
                citation_count=paper_data.get("citation_count", 0),
                semantic_scholar_id=paper_data.get("semantic_scholar_id"),
                citation_updated_at=paper_data.get("citation_updated_at"),
                primary_category=paper_data.get("primary_category"),
                all_categories=paper_data.get("all_categories"),
                urls_extracted=paper_data.get("urls_extracted", False),
            )

            self.db.add(db_paper)
            self.db.commit()
            self.db.refresh(db_paper)

            return db_paper.id

        except Exception as e:
            self.db.rollback()
            print(f"Error adding paper {paper_data.get('arxiv_id', 'unknown')}: {e}")
            return None

    def add_papers_batch(
        self, papers_data: List[Dict[str, Any]], batch_size: int = 100
    ) -> Dict[str, int]:
        """
        Add multiple papers to the database in batches for better performance.

        Args:
            papers_data: List of paper data dictionaries
            batch_size: Number of papers to process in each batch

        Returns:
            Dictionary with statistics: {'added': count, 'skipped': count, 'errors': count}
        """
        stats = {"added": 0, "skipped": 0, "errors": 0}

        try:
            for i in range(0, len(papers_data), batch_size):
                batch = papers_data[i : i + batch_size]

                # Process batch
                for paper_data in batch:
                    try:
                        paper_id = self.add_paper(paper_data)
                        if paper_id:
                            stats["added"] += 1
                        else:
                            stats["skipped"] += 1
                    except Exception as e:
                        stats["errors"] += 1
                        print(f"Error in batch processing: {e}")

                # Progress report
                if (i + len(batch)) % (batch_size * 10) == 0:
                    print(
                        f"Processed {i + len(batch):,} papers... (added: {stats['added']:,}, skipped: {stats['skipped']:,}, errors: {stats['errors']:,})"
                    )

            return stats

        except Exception as e:
            print(f"Error in batch processing: {e}")
            return stats

    def update_paper_metadata(
        self, paper_id: int, metadata_updates: Dict[str, Any]
    ) -> bool:
        """
        Update paper metadata fields like URLs extracted status, categories, etc.

        Args:
            paper_id: Database paper ID
            metadata_updates: Dictionary of fields to update

        Returns:
            True if successful, False otherwise
        """
        try:
            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
            if not db_paper:
                return False

            # Update allowed metadata fields
            allowed_fields = {
                "urls_extracted",
                "primary_category",
                "all_categories",
                "citation_count",
                "semantic_scholar_id",
                "citation_updated_at",
            }

            for field, value in metadata_updates.items():
                if field in allowed_fields and hasattr(db_paper, field):
                    setattr(db_paper, field, value)

            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            print(f"Error updating paper metadata {paper_id}: {e}")
            return False

    def mark_urls_extracted(self, paper_ids: List[int]) -> int:
        """
        Mark papers as having their URLs extracted.

        Args:
            paper_ids: List of paper IDs to update

        Returns:
            Number of papers successfully updated
        """
        try:
            updated_count = (
                self.db.query(DBPaper)
                .filter(DBPaper.id.in_(paper_ids))
                .update({DBPaper.urls_extracted: True}, synchronize_session=False)
            )
            self.db.commit()
            return updated_count

        except Exception as e:
            self.db.rollback()
            print(f"Error marking URLs as extracted: {e}")
            return 0

    def get_papers_needing_url_extraction(self, limit: int = 100) -> List[DBPaper]:
        """
        Get papers that haven't had their URLs extracted yet.

        Args:
            limit: Maximum number of papers to return

        Returns:
            List of papers needing URL extraction
        """
        try:
            return (
                self.db.query(DBPaper)
                .filter(not DBPaper.urls_extracted)
                .filter(DBPaper.is_latest_version)
                .limit(limit)
                .all()
            )

        except Exception as e:
            print(f"Error fetching papers needing URL extraction: {e}")
            return []

    def get_papers_by_category(
        self, category: str, limit: int = 100, latest_only: bool = True
    ) -> List[PaperSummary]:
        """
        Get papers by ArXiv category.

        Args:
            category: ArXiv category (e.g., "cs.CV", "cs.LG")
            limit: Maximum number of papers to return
            latest_only: Whether to only include latest versions

        Returns:
            List of paper summaries in the category
        """
        try:
            query = self.db.query(DBPaper)

            if latest_only:
                query = query.filter(DBPaper.is_latest_version)

            # Filter by primary category or any category in all_categories
            query = query.filter(
                or_(
                    DBPaper.primary_category == category,
                    DBPaper.all_categories.contains([category]),
                )
            )

            db_papers = query.order_by(desc(DBPaper.date_published)).limit(limit).all()

            return [
                self._convert_db_paper_to_summary(db_paper) for db_paper in db_papers
            ]

        except Exception as e:
            raise DatabaseError(
                f"Error fetching papers by category {category}: {str(e)}"
            )

    def get_papers_needing_citation_update_count(self, threshold_days: int = 7) -> int:
        """
        Get count of papers that need citation updates.

        Args:
            threshold_days: Only count papers older than this many days

        Returns:
            Number of papers needing citation updates
        """
        try:
            from datetime import datetime, timedelta

            threshold_date = datetime.now() - timedelta(days=threshold_days)

            count = (
                self.db.query(DBPaper)
                .filter(DBPaper.is_latest_version)
                .filter(DBPaper.arxiv_id.is_not(None))
                .filter(
                    or_(
                        DBPaper.citation_updated_at.is_(None),
                        DBPaper.citation_updated_at < threshold_date,
                    )
                )
                .count()
            )

            return count

        except Exception as e:
            raise DatabaseError(
                f"Error counting papers needing citation updates: {str(e)}"
            )

    def get_papers_needing_citation_update_chunk(
        self, offset: int, limit: int, threshold_days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Get a chunk of papers that need citation updates with priority ordering.

        Args:
            offset: Offset for pagination
            limit: Maximum number of papers to return
            threshold_days: Only get papers older than this many days

        Returns:
            List of paper dictionaries with citation update information
        """
        try:
            from datetime import datetime, timedelta
            from sqlalchemy import case

            threshold_date = datetime.now() - timedelta(days=threshold_days)

            # Create priority ordering for citation updates
            priority_order = case(
                (
                    DBPaper.citation_updated_at.is_(None),
                    0,
                ),  # Never updated (highest priority)
                (
                    DBPaper.citation_count == 0,
                    1,
                ),  # Zero citations (may have gained citations)
                else_=2,  # Regular refresh
            )

            # Year-based priority for high-citation periods
            year_priority = case(
                (func.extract("year", DBPaper.date_published).between(2019, 2022), 1),
                (func.extract("year", DBPaper.date_published).between(2017, 2018), 2),
                (func.extract("year", DBPaper.date_published).between(2023, 2024), 3),
                else_=4,
            )

            db_papers = (
                self.db.query(DBPaper)
                .filter(DBPaper.is_latest_version)
                .filter(DBPaper.arxiv_id.is_not(None))
                .filter(
                    or_(
                        DBPaper.citation_updated_at.is_(None),
                        DBPaper.citation_updated_at < threshold_date,
                    )
                )
                .order_by(
                    priority_order,
                    year_priority,
                    DBPaper.citation_updated_at.asc().nullsfirst(),
                    DBPaper.id.asc(),
                )
                .offset(offset)
                .limit(limit)
                .all()
            )

            # Convert to dictionaries with priority information
            papers_data = []
            for paper in db_papers:
                priority_type = (
                    "NEVER_UPDATED"
                    if paper.citation_updated_at is None
                    else ("ZERO_CITATIONS" if paper.citation_count == 0 else "REFRESH")
                )

                papers_data.append(
                    {
                        "id": paper.id,
                        "arxiv_id": paper.arxiv_id,
                        "title": paper.title,
                        "citation_count": paper.citation_count or 0,
                        "citation_updated_at": paper.citation_updated_at,
                        "date_published": paper.date_published,
                        "priority_type": priority_type,
                    }
                )

            return papers_data

        except Exception as e:
            raise DatabaseError(
                f"Error fetching papers chunk for citation updates: {str(e)}"
            )

    def update_citation_counts_batch(
        self, citation_updates: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Update citation counts for multiple papers in batch.

        Args:
            citation_updates: List of dictionaries with keys:
                - paper_id: Database paper ID
                - citation_count: New citation count
                - semantic_scholar_id: Semantic Scholar paper ID (optional)
                - success: Whether the update was successful

        Returns:
            Dictionary with update statistics: {'updated': count, 'failed': count}
        """
        try:
            stats = {"updated": 0, "failed": 0}

            for update in citation_updates:
                try:
                    paper_id = update["paper_id"]
                    citation_count = update["citation_count"]
                    semantic_scholar_id = update.get("semantic_scholar_id")
                    success = update.get("success", True)

                    if success and semantic_scholar_id:
                        # Successful update with citation data
                        db_paper = (
                            self.db.query(DBPaper)
                            .filter(DBPaper.id == paper_id)
                            .first()
                        )
                        if db_paper:
                            db_paper.citation_count = citation_count
                            db_paper.semantic_scholar_id = semantic_scholar_id
                            db_paper.citation_updated_at = func.now()
                            db_paper.updated_at = func.now()
                            stats["updated"] += 1
                        else:
                            stats["failed"] += 1
                    else:
                        # Failed update - just mark as processed to avoid re-processing
                        db_paper = (
                            self.db.query(DBPaper)
                            .filter(DBPaper.id == paper_id)
                            .first()
                        )
                        if db_paper:
                            db_paper.citation_updated_at = func.now()
                            db_paper.updated_at = func.now()
                            stats["failed"] += 1
                        else:
                            stats["failed"] += 1

                except Exception as e:
                    print(
                        f"Error updating paper {update.get('paper_id', 'unknown')}: {e}"
                    )
                    stats["failed"] += 1

            self.db.commit()
            return stats

        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Error updating citation counts batch: {str(e)}")

    def get_citation_statistics(self) -> Dict[str, Any]:
        """
        Get citation update statistics for the database.

        Returns:
            Dictionary with citation statistics
        """
        try:
            # Get overall statistics
            total_papers = (
                self.db.query(DBPaper).filter(DBPaper.is_latest_version).count()
            )

            papers_processed = (
                self.db.query(DBPaper)
                .filter(DBPaper.is_latest_version)
                .filter(DBPaper.citation_updated_at.is_not(None))
                .count()
            )

            papers_with_citations = (
                self.db.query(DBPaper)
                .filter(DBPaper.is_latest_version)
                .filter(DBPaper.citation_count > 0)
                .count()
            )

            # Calculate percentages
            processed_pct = (
                (papers_processed / total_papers * 100) if total_papers > 0 else 0
            )
            citations_pct = (
                (papers_with_citations / total_papers * 100) if total_papers > 0 else 0
            )

            return {
                "total_papers": total_papers,
                "papers_processed": papers_processed,
                "papers_with_citations": papers_with_citations,
                "processed_percentage": round(processed_pct, 1),
                "citations_percentage": round(citations_pct, 1),
            }

        except Exception as e:
            raise DatabaseError(f"Error getting citation statistics: {str(e)}")

    def update_paper_tasks(self, paper_id: int, task_ids: List[int]) -> Paper:
        """
        Update the tasks associated with a paper.

        Args:
            paper_id: Database paper ID
            task_ids: List of task IDs to associate with the paper

        Returns:
            Updated Paper object

        Raises:
            PaperNotFoundError: If paper is not found
            DatabaseError: If update fails
        """
        try:
            from backend.models.database import Task as DBTask, PaperTask

            # Verify paper exists
            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
            if not db_paper:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

            # Verify all task IDs exist
            existing_tasks = self.db.query(DBTask).filter(DBTask.id.in_(task_ids)).all()
            existing_task_ids = {task.id for task in existing_tasks}
            invalid_task_ids = set(task_ids) - existing_task_ids
            if invalid_task_ids:
                raise DatabaseError(f"Invalid task IDs: {invalid_task_ids}")

            # Replace all existing paper_tasks associations with the new set.
            # An admin override always wins: every row inserted here is marked
            # source='manual' so the keyword-matcher rebuild pass won't touch it.
            self.db.query(PaperTask).filter(PaperTask.paper_id == paper_id).delete()

            for task_id in task_ids:
                paper_task = PaperTask(
                    paper_id=paper_id, task_id=task_id, source="manual"
                )
                self.db.add(paper_task)

            self.db.commit()

            # Return updated paper
            return self.get_paper_by_id(paper_id, include_resources=True)

        except Exception as e:
            self.db.rollback()
            if isinstance(e, (PaperNotFoundError, DatabaseError)):
                raise
            raise DatabaseError(f"Error updating paper tasks: {str(e)}")

    def update_paper_methods(self, paper_id: int, method_ids: List[int]) -> Paper:
        """
        Update the methods associated with a paper.

        Args:
            paper_id: Database paper ID
            method_ids: List of method IDs to associate with the paper

        Returns:
            Updated Paper object

        Raises:
            PaperNotFoundError: If paper is not found
            DatabaseError: If update fails
        """
        try:
            from backend.models.database import Method as DBMethod, PaperMethod

            # Verify paper exists
            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
            if not db_paper:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

            # Verify all method IDs exist
            existing_methods = (
                self.db.query(DBMethod).filter(DBMethod.id.in_(method_ids)).all()
            )
            existing_method_ids = {method.id for method in existing_methods}
            invalid_method_ids = set(method_ids) - existing_method_ids
            if invalid_method_ids:
                raise DatabaseError(f"Invalid method IDs: {invalid_method_ids}")

            # Delete existing paper_methods associations
            self.db.query(PaperMethod).filter(PaperMethod.paper_id == paper_id).delete()

            # Add new associations
            for method_id in method_ids:
                paper_method = PaperMethod(paper_id=paper_id, method_id=method_id)
                self.db.add(paper_method)

            self.db.commit()

            # Return updated paper
            return self.get_paper_by_id(paper_id, include_resources=True)

        except Exception as e:
            self.db.rollback()
            if isinstance(e, (PaperNotFoundError, DatabaseError)):
                raise
            raise DatabaseError(f"Error updating paper methods: {str(e)}")

    def update_paper_repositories(
        self, paper_id: int, repositories: List[Dict[str, Any]]
    ) -> Paper:
        """
        Update the repositories associated with a paper.

        Creates repositories if they don't exist, and establishes the paper-repository
        associations with the is_official flag.

        Args:
            paper_id: Database paper ID
            repositories: List of dicts with 'url' and 'is_official' keys

        Returns:
            Updated Paper object

        Raises:
            PaperNotFoundError: If paper is not found
            DatabaseError: If update fails
        """
        try:
            from backend.models.database import (
                Repository as DBRepository,
                PaperRepository,
            )
            import re

            # Verify paper exists
            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
            if not db_paper:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

            # Delete existing paper_repositories associations
            self.db.query(PaperRepository).filter(
                PaperRepository.paper_id == paper_id
            ).delete()

            # Process each repository URL
            for repo_data in repositories:
                url = repo_data.get("url", "").strip()
                is_official = repo_data.get("is_official", False)

                if not url:
                    continue

                # Check if repository already exists
                existing_repo = (
                    self.db.query(DBRepository).filter(DBRepository.url == url).first()
                )

                if existing_repo:
                    # Use existing repository
                    repository_id = existing_repo.id
                else:
                    # Create new repository
                    # Extract owner and name from GitHub URL
                    owner = None
                    name = None
                    github_match = re.match(
                        r"https?://github\.com/([^/]+)/([^/]+)(?:/.*)?", url
                    )
                    if github_match:
                        owner = github_match.group(1)
                        name = github_match.group(2)
                        # Remove .git suffix if present
                        if name.endswith(".git"):
                            name = name[:-4]

                    # Create new repository entry
                    new_repo = DBRepository(
                        url=url,
                        owner=owner,
                        name=name,
                        num_stars=0,
                        source="manual",  # Marked as manually added by admin
                    )
                    self.db.add(new_repo)
                    self.db.flush()  # Get the ID without committing
                    repository_id = new_repo.id

                # Create paper-repository association
                paper_repository = PaperRepository(
                    paper_id=paper_id,
                    repository_id=repository_id,
                    is_official=is_official,
                )
                self.db.add(paper_repository)

            self.db.commit()

            # Return updated paper
            return self.get_paper_by_id(paper_id, include_resources=True)

        except Exception as e:
            self.db.rollback()
            if isinstance(e, (PaperNotFoundError, DatabaseError)):
                raise
            raise DatabaseError(f"Error updating paper repositories: {str(e)}")

    def update_paper_project_pages(
        self, paper_id: int, project_pages: List[Dict[str, Any]]
    ) -> Paper:
        """
        Update the project pages associated with a paper.

        Creates project pages if they don't exist, and establishes the paper-project page
        associations.

        Args:
            paper_id: Database paper ID
            project_pages: List of dicts with 'url' and 'is_official' keys

        Returns:
            Updated Paper object

        Raises:
            PaperNotFoundError: If paper is not found
            DatabaseError: If update fails
        """
        try:
            from backend.models.database import (
                ProjectPage as DBProjectPage,
                PaperProjectPage as DBPaperProjectPage,
            )

            # Verify paper exists
            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
            if not db_paper:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

            # Delete existing paper_project_pages associations
            self.db.query(DBPaperProjectPage).filter(
                DBPaperProjectPage.paper_id == paper_id
            ).delete()

            # Process each project page URL
            for page_data in project_pages:
                url = page_data.get("url", "").strip()
                is_official = page_data.get("is_official", False)

                if not url:
                    continue

                # Check if project page already exists
                existing_page = (
                    self.db.query(DBProjectPage)
                    .filter(DBProjectPage.url == url)
                    .first()
                )

                if existing_page:
                    # Use existing project page, update is_official if needed
                    if is_official and not existing_page.is_official:
                        existing_page.is_official = True
                    project_page_id = existing_page.id
                else:
                    # Create new project page
                    new_page = DBProjectPage(
                        url=url,
                        is_official=is_official,
                        source="manual",  # Marked as manually added by admin
                    )
                    self.db.add(new_page)
                    self.db.flush()  # Get the ID without committing
                    project_page_id = new_page.id

                # Create paper-project page association
                paper_project_page = DBPaperProjectPage(
                    paper_id=paper_id,
                    project_page_id=project_page_id,
                )
                self.db.add(paper_project_page)

            self.db.commit()

            # Return updated paper
            return self.get_paper_by_id(paper_id, include_resources=True)

        except Exception as e:
            self.db.rollback()
            if isinstance(e, (PaperNotFoundError, DatabaseError)):
                raise
            raise DatabaseError(f"Error updating paper project pages: {str(e)}")
