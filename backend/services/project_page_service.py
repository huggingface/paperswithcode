"""
Project Page service for business logic and data processing with normalized structure.

This service handles all project page related operations with the new many-to-many
relationship structure, including:
- Fetching project pages with pagination and filtering
- Managing paper-project page relationships via junction table
- Converting database models to API models
- Handling relationship metadata (is_official, source)
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func

from backend.models.database import (
    ProjectPage as DBProjectPage,
    PaperProjectPage as DBPaperProjectPage,
)
from backend.models.papers import (
    ProjectPage,
    ProjectPages,
    PaperProjectPage,
    ProjectPageWithPapers,
    ProjectPageCreateRequest,
    ProjectPageUpdateRequest,
)

from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.services.catalog_errors import CatalogValidationError
from backend.config import get_settings


class ProjectPageService:
    """Service for project page operations with normalized many-to-many support."""

    def __init__(self, db: Session):
        """Initialize the service with a database session."""
        self.db = db
        self.settings = get_settings()

    def get_project_pages(
        self,
        page: int = 1,
        page_size: Optional[int] = None,
        official_only: bool = False,
        source: Optional[str] = None,
        order_by: str = "created_at",
        order_dir: str = "desc",
        include_paper_count: bool = True,
    ) -> ProjectPages:
        """
        Get project pages with pagination and filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of project pages per page
            official_only: Only include project pages that are official for at least one paper
            source: Filter by data source (pwc_archive, ai_extraction, manual, etc.)
            order_by: Field to order by (supports 'paper_count' for number of associated papers)
            order_dir: Order direction (asc/desc)
            include_paper_count: Whether to include paper count in results

        Returns:
            ProjectPages object with pagination info
        """
        if page_size is None:
            page_size = self.settings.default_page_size

        # Ensure page_size doesn't exceed maximum
        page_size = min(page_size, self.settings.max_page_size)

        try:
            # Build base query
            if include_paper_count or order_by == "paper_count":
                # Query with paper count
                query = (
                    self.db.query(
                        DBProjectPage,
                        func.count(DBPaperProjectPage.paper_id).label("paper_count"),
                    )
                    .outerjoin(
                        DBPaperProjectPage,
                        DBProjectPage.id == DBPaperProjectPage.project_page_id,
                    )
                    .group_by(DBProjectPage.id)
                )
            else:
                # Simple query without paper count
                query = self.db.query(DBProjectPage)

            # Apply filters
            if official_only:
                # Filter by is_official field in project_pages table (not junction table)
                query = query.filter(DBProjectPage.is_official)

            if source:
                query = query.filter(DBProjectPage.source == source)

            # Apply ordering
            if order_by == "paper_count" and (
                include_paper_count or order_by == "paper_count"
            ):
                order_field = func.count(DBPaperProjectPage.paper_id)
            else:
                order_field = getattr(DBProjectPage, order_by, DBProjectPage.created_at)

            if order_dir.lower() == "desc":
                query = query.order_by(desc(order_field))
            else:
                query = query.order_by(asc(order_field))

            # Get total count
            if include_paper_count or order_by == "paper_count":
                total_count = query.count()
            else:
                total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            # Convert to API models
            if include_paper_count or order_by == "paper_count":
                api_project_pages = [
                    self._db_project_page_to_api(result[0]) for result in results
                ]
            else:
                api_project_pages = [
                    self._db_project_page_to_api(page) for page in results
                ]

            # Calculate pagination info
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return ProjectPages(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=api_project_pages,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to fetch project pages: {str(e)}")

    def get_project_page_by_id(self, page_id: str) -> ProjectPage:
        """
        Get a specific project page by ID.

        Args:
            page_id: Project page ID

        Returns:
            ProjectPage object

        Raises:
            PaperNotFoundError: If project page not found
        """
        try:
            project_page = (
                self.db.query(DBProjectPage)
                .filter(DBProjectPage.id == int(page_id))
                .first()
            )

            if not project_page:
                raise PaperNotFoundError(f"Project page with ID {page_id} not found")

            return self._db_project_page_to_api(project_page)

        except ValueError:
            raise PaperNotFoundError(f"Invalid project page ID: {page_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to fetch project page: {str(e)}")

    def get_project_pages_for_paper(self, paper_id: str) -> List[ProjectPage]:
        """
        Get all project pages associated with a paper via the junction table.

        Args:
            paper_id: Paper ID

        Returns:
            List of ProjectPage objects
        """
        try:
            # Query using the junction table
            project_pages = (
                self.db.query(DBProjectPage)
                .join(
                    DBPaperProjectPage,
                    DBProjectPage.id == DBPaperProjectPage.project_page_id,
                )
                .filter(DBPaperProjectPage.paper_id == int(paper_id))
                .order_by(desc(DBProjectPage.created_at))
                .all()
            )

            return [self._db_project_page_to_api(page) for page in project_pages]

        except ValueError:
            raise PaperNotFoundError(f"Invalid paper ID: {paper_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to fetch project pages for paper: {str(e)}")

    def get_project_page_with_papers(self, page_id: str) -> ProjectPageWithPapers:
        """
        Get a project page with all associated papers.

        Args:
            page_id: Project page ID

        Returns:
            ProjectPageWithPapers object with project page and associated papers
        """
        try:
            # Get the project page
            project_page = (
                self.db.query(DBProjectPage)
                .filter(DBProjectPage.id == int(page_id))
                .first()
            )

            if not project_page:
                raise PaperNotFoundError(f"Project page with ID {page_id} not found")

            # Get associated papers
            paper_relationships = (
                self.db.query(DBPaperProjectPage)
                .filter(DBPaperProjectPage.project_page_id == int(page_id))
                .all()
            )

            paper_ids = [str(rel.paper_id) for rel in paper_relationships]
            relationships = [
                self._db_paper_project_page_to_api(rel) for rel in paper_relationships
            ]

            return ProjectPageWithPapers(
                project_page=self._db_project_page_to_api(project_page),
                papers=paper_ids,
                relationships=relationships,
            )

        except ValueError:
            raise PaperNotFoundError(f"Invalid project page ID: {page_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to fetch project page with papers: {str(e)}")

    def get_paper_project_page_relationships(
        self, paper_id: Optional[str] = None, project_page_id: Optional[str] = None
    ) -> List[PaperProjectPage]:
        """
        Get paper-project page relationships with optional filtering.

        Args:
            paper_id: Optional paper ID to filter by
            project_page_id: Optional project page ID to filter by

        Returns:
            List of PaperProjectPage relationship objects
        """
        try:
            query = self.db.query(DBPaperProjectPage)

            if paper_id:
                query = query.filter(DBPaperProjectPage.paper_id == int(paper_id))

            if project_page_id:
                query = query.filter(
                    DBPaperProjectPage.project_page_id == int(project_page_id)
                )

            relationships = query.all()
            return [self._db_paper_project_page_to_api(rel) for rel in relationships]

        except ValueError as e:
            raise PaperNotFoundError(f"Invalid ID provided: {str(e)}")
        except Exception as e:
            raise DatabaseError(f"Failed to fetch relationships: {str(e)}")

    def _db_project_page_to_api(self, db_project_page: DBProjectPage) -> ProjectPage:
        """
        Convert database ProjectPage model to API ProjectPage model.

        Args:
            db_project_page: Database project page object

        Returns:
            API ProjectPage object
        """
        return ProjectPage(
            id=str(db_project_page.id),
            url=db_project_page.url,
            is_official=db_project_page.is_official,
            source=db_project_page.source,
            created_at=(
                db_project_page.created_at.date()
                if db_project_page.created_at
                else None
            ),
            updated_at=(
                db_project_page.updated_at.date()
                if db_project_page.updated_at
                else None
            ),
        )

    def _db_paper_project_page_to_api(
        self, db_relationship: DBPaperProjectPage
    ) -> PaperProjectPage:
        """
        Convert database PaperProjectPage model to API PaperProjectPage model.

        Args:
            db_relationship: Database paper-project page relationship object

        Returns:
            API PaperProjectPage object
        """
        return PaperProjectPage(
            paper_id=str(db_relationship.paper_id),
            project_page_id=str(db_relationship.project_page_id),
        )

    def create_or_update_project_page(
        self,
        url: str,
        is_official: bool = True,
        source: str = "unknown",
    ) -> ProjectPage:
        """
        Create a new project page or update existing one.

        Args:
            url: Project page URL (unique identifier)
            is_official: Whether project page is generally official
            source: Data source

        Returns:
            ProjectPage object (created or updated)
        """
        try:
            # Check if project page already exists
            existing_page = (
                self.db.query(DBProjectPage).filter(DBProjectPage.url == url).first()
            )

            if existing_page:
                # Update existing project page
                existing_page.is_official = (
                    is_official or existing_page.is_official
                )  # Keep true if any source says official
                # Don't update source - keep original

                self.db.commit()
                return self._db_project_page_to_api(existing_page)
            else:
                # Create new project page
                new_page = DBProjectPage(
                    url=url,
                    is_official=is_official,
                    source=source,
                )

                self.db.add(new_page)
                self.db.commit()
                return self._db_project_page_to_api(new_page)

        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to create/update project page: {str(e)}")

    def associate_project_page_with_paper(
        self,
        paper_id: str,
        project_page_id: str,
    ) -> PaperProjectPage:
        """
        Associate a project page with a paper.

        Note: The junction table only stores the relationship (paper_id, project_page_id).
        Metadata like is_official and source are stored in the project_pages table.

        Args:
            paper_id: Paper ID
            project_page_id: Project page ID

        Returns:
            PaperProjectPage object

        Raises:
            PaperNotFoundError: If paper or project page not found
            DatabaseError: If database error occurs
        """
        try:
            from backend.models.database import Paper as DBPaper

            # Check if paper exists
            paper = self.db.query(DBPaper).filter(DBPaper.id == int(paper_id)).first()
            if not paper:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

            # Check if project page exists
            project_page = (
                self.db.query(DBProjectPage)
                .filter(DBProjectPage.id == int(project_page_id))
                .first()
            )
            if not project_page:
                raise PaperNotFoundError(
                    f"Project page with ID {project_page_id} not found"
                )

            # Check if association already exists
            existing_association = (
                self.db.query(DBPaperProjectPage)
                .filter(
                    DBPaperProjectPage.paper_id == int(paper_id),
                    DBPaperProjectPage.project_page_id == int(project_page_id),
                )
                .first()
            )

            if existing_association:
                # Association already exists, return it
                # Note: is_official and source are stored in project_pages table, not junction table
                return self._db_paper_project_page_to_api(existing_association)
            else:
                # Create new association (junction table only stores IDs)
                new_association = DBPaperProjectPage(
                    paper_id=int(paper_id),
                    project_page_id=int(project_page_id),
                )

                self.db.add(new_association)
                self.db.commit()
                return self._db_paper_project_page_to_api(new_association)

        except ValueError:
            raise PaperNotFoundError("Invalid paper or project page ID")
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(
                f"Failed to associate project page with paper: {str(e)}"
            )

    def create_project_page_for_paper(
        self,
        paper_id: str,
        url: str,
        is_official: bool = True,
        source: str = "unknown",
        skip_if_official_exists: bool = True,
    ) -> Optional[ProjectPage]:
        """
        Create a project page and associate it with a paper in one operation.

        This is a convenience method that combines create_or_update_project_page
        and associate_project_page_with_paper.

        Args:
            paper_id: Paper ID
            url: Project page URL
            is_official: Whether this project page is official for this paper
            source: Data source
            skip_if_official_exists: Skip if paper already has official project page from priority sources

        Returns:
            ProjectPage object if created/updated, None if skipped

        Raises:
            PaperNotFoundError: If paper not found
            DatabaseError: On database errors
        """
        try:
            # Check if we should skip due to existing official project page
            if skip_if_official_exists:
                existing_official = (
                    self.db.query(DBProjectPage)
                    .join(
                        DBPaperProjectPage,
                        DBProjectPage.id == DBPaperProjectPage.project_page_id,
                    )
                    .filter(
                        DBPaperProjectPage.paper_id == int(paper_id),
                        DBProjectPage.source.in_(["hf_api"]),  # Priority sources
                        DBProjectPage.is_official,
                    )
                    .first()
                )

                if existing_official:
                    return None  # Skip - official project page already exists

            # Create or update the project page
            project_page = self.create_or_update_project_page(
                url=url, is_official=is_official, source=source
            )

            # Associate with paper (junction table only stores IDs)
            self.associate_project_page_with_paper(
                paper_id=paper_id,
                project_page_id=project_page.id,
            )

            return project_page

        except ValueError:
            raise PaperNotFoundError(f"Invalid paper ID: {paper_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to create project page for paper: {str(e)}")

    def create_project_page(self, request: ProjectPageCreateRequest) -> ProjectPage:
        """
        Create a new project page.

        Args:
            request: ProjectPageCreateRequest with url, is_official, source

        Returns:
            Created ProjectPage object

        Raises:
            ValueError: If URL already exists
            DatabaseError: On database errors
        """
        try:
            # Check if URL already exists
            existing = (
                self.db.query(DBProjectPage)
                .filter(DBProjectPage.url == request.url)
                .first()
            )
            if existing:
                raise CatalogValidationError(
                    f"Project page with URL '{request.url}' already exists"
                )

            # Create new project page
            new_page = DBProjectPage(
                url=request.url,
                is_official=request.is_official,
                source=request.source,
            )

            self.db.add(new_page)
            self.db.commit()
            self.db.refresh(new_page)

            return self._db_project_page_to_api(new_page)

        except ValueError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to create project page: {str(e)}")

    def update_project_page(
        self, page_id: str, request: ProjectPageUpdateRequest
    ) -> ProjectPage:
        """
        Update an existing project page.

        Args:
            page_id: Project page ID
            request: ProjectPageUpdateRequest with optional fields to update

        Returns:
            Updated ProjectPage object

        Raises:
            PaperNotFoundError: If project page not found
            DatabaseError: On database errors
        """
        try:
            project_page = (
                self.db.query(DBProjectPage)
                .filter(DBProjectPage.id == int(page_id))
                .first()
            )

            if not project_page:
                raise PaperNotFoundError(f"Project page with ID {page_id} not found")

            # Update fields if provided
            if request.url is not None:
                # Check if new URL already exists for a different project page
                existing = (
                    self.db.query(DBProjectPage)
                    .filter(
                        DBProjectPage.url == request.url,
                        DBProjectPage.id != int(page_id),
                    )
                    .first()
                )
                if existing:
                    raise CatalogValidationError(
                        f"Project page with URL '{request.url}' already exists"
                    )
                project_page.url = request.url

            if request.is_official is not None:
                project_page.is_official = request.is_official

            if request.source is not None:
                project_page.source = request.source

            self.db.commit()
            self.db.refresh(project_page)

            return self._db_project_page_to_api(project_page)

        except ValueError:
            raise
        except PaperNotFoundError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to update project page: {str(e)}")

    def delete_project_page(self, page_id: str) -> None:
        """
        Delete a project page and all its associations.

        Args:
            page_id: Project page ID

        Raises:
            PaperNotFoundError: If project page not found
            DatabaseError: On database errors
        """
        try:
            project_page = (
                self.db.query(DBProjectPage)
                .filter(DBProjectPage.id == int(page_id))
                .first()
            )

            if not project_page:
                raise PaperNotFoundError(f"Project page with ID {page_id} not found")

            # Delete the project page (cascade will handle junction table)
            self.db.delete(project_page)
            self.db.commit()

        except PaperNotFoundError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to delete project page: {str(e)}")
