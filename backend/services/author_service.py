"""
Author service for handling author-related business logic.

This service provides methods for retrieving and managing author data,
including pagination, filtering, and paper relationships.
"""

import re
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, or_

from backend.models.database import (
    Author as DBAuthor,
    AuthorAlias,
    Paper as DBPaper,
    PaperAuthor,
)
from backend.models.papers import (
    Author,
    Authors,
    Papers,
)
from backend.utils.exceptions import PaperNotFoundError, DatabaseError


def normalize_arxiv_author_name(full_name: str) -> str:
    """Normalize an author name returned by arXiv without runtime side effects."""
    if not full_name or not full_name.strip():
        return "Unknown Author"

    name = re.sub(r"\s+", " ", full_name.strip())
    name = re.sub(r"^\(.*?\)\s*", "", name)
    return re.sub(r"\s*\(.*?\)$", "", name)


def has_hf_account():
    """SQL condition: the author row is linked to a Hugging Face account."""
    return or_(DBAuthor.hf_id.isnot(None), DBAuthor.hf_username.isnot(None))


def get_or_create_author_by_name(db: Session, name: str) -> DBAuthor:
    """Return the name-only author with this name, ignoring case, or create it.

    "Tom Aarsen" and "Tom AARSEN" are the same author, and an exact spelling
    wins. Rows linked to a Hugging Face account are never matched by name: they
    hold only the papers their account claimed, so a namesake's papers cannot
    land on someone else's profile.
    """
    author = (
        db.query(DBAuthor)
        .filter(func.lower(DBAuthor.name) == name.lower(), ~has_hf_account())
        .order_by(DBAuthor.name != name, DBAuthor.id)
        .first()
    )
    if author is None:
        author = DBAuthor(name=name)
        db.add(author)
        db.flush()
    return author


class AuthorService:
    """Service class for author-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def _resolve_author_id(self, author_id: str) -> int:
        """Map an author ID merged into another author to the surviving ID."""
        requested_id = int(author_id)
        merged_into = (
            self.db.query(AuthorAlias.author_id)
            .filter(AuthorAlias.alias_id == requested_id)
            .scalar()
        )
        return merged_into or requested_id

    def get_authors(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        hf_users_only: bool = False,
        order_by: str = "paper_count",
        order_dir: str = "desc",
    ) -> Authors:
        """
        Get a paginated list of authors with optional filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of authors per page
            search: Search term for author name
            hf_users_only: Filter to only Hugging Face users
            order_by: Field to order by (name, paper_count, created_at)
            order_dir: Order direction (asc, desc)

        Returns:
            Authors object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Base query with paper count
            query = (
                self.db.query(
                    DBAuthor, func.count(PaperAuthor.paper_id).label("paper_count")
                )
                .outerjoin(PaperAuthor, DBAuthor.id == PaperAuthor.author_id)
                .group_by(DBAuthor.id)
            )

            # Apply filters
            if search:
                query = query.filter(DBAuthor.name.ilike(f"%{search}%"))

            if hf_users_only:
                query = query.filter(DBAuthor.hf_username.isnot(None))

            # Apply ordering
            if order_by == "paper_count":
                order_field = func.count(PaperAuthor.paper_id)
            elif order_by == "name":
                order_field = DBAuthor.name
            elif order_by == "created_at":
                order_field = DBAuthor.created_at
            else:
                order_field = func.count(PaperAuthor.paper_id)  # Default to paper_count

            if order_dir == "desc":
                query = query.order_by(desc(order_field))
            else:
                query = query.order_by(asc(order_field))

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            # Convert to API models
            authors = []
            for db_author, paper_count in results:
                author_dict = {
                    "id": str(db_author.id),
                    "full_name": db_author.name,  # API model uses 'full_name', DB uses 'name'
                    "hf_username": db_author.hf_username,
                    "hf_id": db_author.hf_id,
                    "hf_avatar_url": db_author.hf_avatar_url,
                    "hf_status": db_author.hf_status,
                    "hf_is_pro": db_author.hf_is_pro or False,
                    "paper_count": paper_count or 0,
                }
                authors.append(Author(**author_dict))

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Authors(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=authors,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve authors: {str(e)}")

    def get_author_by_id(self, author_id: str) -> Author:
        """
        Get a specific author by ID.

        Args:
            author_id: The author ID

        Returns:
            Author object

        Raises:
            PaperNotFoundError: If author not found
            DatabaseError: If database query fails
        """
        try:
            # Query with paper count
            result = (
                self.db.query(
                    DBAuthor, func.count(PaperAuthor.paper_id).label("paper_count")
                )
                .outerjoin(PaperAuthor, DBAuthor.id == PaperAuthor.author_id)
                .filter(DBAuthor.id == self._resolve_author_id(author_id))
                .group_by(DBAuthor.id)
                .first()
            )

            if not result:
                raise PaperNotFoundError(f"Author with ID {author_id} not found")

            db_author, paper_count = result

            author_dict = {
                "id": str(db_author.id),
                "full_name": db_author.name,
                "hf_username": db_author.hf_username,
                "hf_id": db_author.hf_id,
                "hf_avatar_url": db_author.hf_avatar_url,
                "hf_status": db_author.hf_status,
                "hf_is_pro": db_author.hf_is_pro or False,
                "paper_count": paper_count or 0,
            }

            return Author(**author_dict)

        except PaperNotFoundError:
            raise
        except ValueError:
            raise PaperNotFoundError(f"Invalid author ID: {author_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve author: {str(e)}")

    def get_author_papers(
        self,
        author_id: str,
        page: int = 1,
        page_size: int = 50,
        latest_only: bool = True,
        order_by: str = "date_published",
        order_dir: str = "desc",
    ) -> Papers:
        """
        Get papers by a specific author.

        Args:
            author_id: The author ID
            page: Page number (1-based)
            page_size: Number of papers per page
            latest_only: Whether to only include latest versions
            order_by: Field to order by
            order_dir: Order direction (asc, desc)

        Returns:
            Papers object with pagination info and results

        Raises:
            PaperNotFoundError: If author not found
            DatabaseError: If database query fails
        """
        try:
            resolved_id = self._resolve_author_id(author_id)
            author_exists = (
                self.db.query(DBAuthor).filter(DBAuthor.id == resolved_id).first()
            )

            if not author_exists:
                raise PaperNotFoundError(f"Author with ID {author_id} not found")

            # Base query for papers by author
            query = (
                self.db.query(DBPaper)
                .join(PaperAuthor, DBPaper.id == PaperAuthor.paper_id)
                .filter(PaperAuthor.author_id == resolved_id)
            )

            # Apply latest version filter
            if latest_only:
                query = query.filter(DBPaper.is_latest_version)

            # Apply ordering
            if order_by == "date_published":
                order_field = DBPaper.date_published
            elif order_by == "title":
                order_field = DBPaper.title
            elif order_by == "citation_count":
                order_field = DBPaper.citation_count
            else:
                order_field = DBPaper.date_published

            if order_dir == "desc":
                query = query.order_by(desc(order_field))
            else:
                query = query.order_by(asc(order_field))

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            db_papers = query.offset(offset).limit(page_size).all()

            # Convert to API models
            from backend.services.paper_service import PaperService

            paper_service = PaperService(self.db)
            papers = paper_service.hydrate_cards(db_papers, include_resources=False)

            # Calculate pagination
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
        except ValueError:
            raise PaperNotFoundError(f"Invalid author ID: {author_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve author papers: {str(e)}")

    def search_authors(
        self,
        query: str,
        page: int = 1,
        page_size: int = 50,
        hf_users_only: bool = False,
    ) -> Authors:
        """
        Search authors by name with full-text search capabilities.

        Args:
            query: Search query
            page: Page number (1-based)
            page_size: Number of authors per page
            hf_users_only: Filter to only Hugging Face users

        Returns:
            Authors object with search results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Use ILIKE for case-insensitive search
            search_query = (
                self.db.query(
                    DBAuthor, func.count(PaperAuthor.paper_id).label("paper_count")
                )
                .outerjoin(PaperAuthor, DBAuthor.id == PaperAuthor.author_id)
                .filter(
                    or_(
                        DBAuthor.name.ilike(f"%{query}%"),
                        DBAuthor.hf_username.ilike(f"%{query}%"),
                    )
                )
                .group_by(DBAuthor.id)
            )

            if hf_users_only:
                search_query = search_query.filter(DBAuthor.hf_username.isnot(None))

            # Order by relevance (exact matches first, then by paper count)
            search_query = search_query.order_by(desc(func.count(PaperAuthor.paper_id)))

            # Get total count
            total_count = search_query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            results = search_query.offset(offset).limit(page_size).all()

            # Convert to API models
            authors = []
            for db_author, paper_count in results:
                author_dict = {
                    "id": str(db_author.id),
                    "full_name": db_author.name,  # API model uses 'full_name', DB uses 'name'
                    "hf_username": db_author.hf_username,
                    "hf_id": db_author.hf_id,
                    "hf_avatar_url": db_author.hf_avatar_url,
                    "hf_status": db_author.hf_status,
                    "hf_is_pro": db_author.hf_is_pro or False,
                    "paper_count": paper_count or 0,
                }
                authors.append(Author(**author_dict))

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Authors(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=authors,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to search authors: {str(e)}")
