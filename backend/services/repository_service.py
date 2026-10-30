"""
Repository service for business logic and data processing.

This service handles all repository related operations with
the new many-to-many relationship structure, including:
- Fetching repositories with pagination and filtering
- Managing paper-repository relationships
- Converting database models to API models
- Managing repository metadata (stars, owner, etc.)
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func, case
import logging

from backend.models.database import (
    Repository as DBRepository,
    PaperRepository as DBPaperRepository,
    Paper as DBPaper,
)
from backend.models.papers import (
    Repository,
    Repositories,
    PaperRepository,
    RepositoryStarHistory,
    RepositoryStarHistoryList,
)

from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.utils.github_utils import normalize_github_url, parse_github_url
from backend.config import get_settings

logger = logging.getLogger(__name__)


def find_repository_by_url(session: Session, url: str) -> Optional[DBRepository]:
    """Find a repository row, matching GitHub URLs case-insensitively."""
    normalized = normalize_github_url(url)
    lookup_url = normalized or url.strip()
    if not lookup_url:
        return None

    if "github.com" in lookup_url.lower():
        return (
            session.query(DBRepository)
            .filter(func.lower(DBRepository.url) == lookup_url.lower())
            .order_by(DBRepository.id)
            .first()
        )

    return session.query(DBRepository).filter(DBRepository.url == lookup_url).first()


class RepositoryService:
    """Service for repository operations with many-to-many support."""

    def __init__(self, db: Session):
        """Initialize the service with a database session."""
        self.db = db
        self.settings = get_settings()

    def get_repositories(
        self,
        page: int = 1,
        page_size: Optional[int] = None,
        owner: Optional[str] = None,
        official_only: bool = False,
        min_stars: Optional[int] = None,
        source: Optional[str] = None,
        order_by: str = "num_stars",
        order_dir: str = "desc",
        include_paper_count: bool = True,
    ) -> Repositories:
        """
        Get repositories with pagination and filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of repositories per page
            owner: Filter by repository owner
            official_only: Only include repositories that are official for at least one paper
            min_stars: Minimum number of stars
            source: Filter by data source (pwc_archive, ai_extraction, manual, etc.)
            order_by: Field to order by (supports 'paper_count' for number of associated papers)
            order_dir: Order direction (asc/desc)
            include_paper_count: Whether to include paper count in results

        Returns:
            Repositories object with pagination info
        """
        if page_size is None:
            page_size = self.settings.default_page_size

        # Ensure page_size doesn't exceed maximum
        page_size = min(page_size, self.settings.max_page_size)

        try:
            # Build base query with optional paper count
            if include_paper_count or order_by == "paper_count":
                # Join with paper_repositories to get paper count
                query = (
                    self.db.query(
                        DBRepository,
                        func.count(DBPaperRepository.paper_id).label("paper_count"),
                    )
                    .outerjoin(DBPaperRepository)
                    .group_by(DBRepository.id)
                )
            else:
                query = self.db.query(DBRepository)

            # Apply filters
            if owner:
                if include_paper_count or order_by == "paper_count":
                    query = query.filter(DBRepository.owner.ilike(f"%{owner}%"))
                else:
                    query = query.filter(DBRepository.owner.ilike(f"%{owner}%"))

            if official_only:
                # Filter repositories that are official for at least one paper
                if include_paper_count or order_by == "paper_count":
                    query = query.having(func.bool_or(DBPaperRepository.is_official))
                else:
                    # Need to join with paper_repositories for this filter
                    query = (
                        query.join(DBPaperRepository)
                        .filter(DBPaperRepository.is_official)
                        .distinct()
                    )

            if min_stars is not None:
                query = query.filter(DBRepository.num_stars >= min_stars)

            if source:
                query = query.filter(DBRepository.source == source)

            # Apply ordering
            if order_by == "paper_count":
                if not (include_paper_count or order_by == "paper_count"):
                    # Need to add paper count to query
                    query = (
                        self.db.query(
                            DBRepository,
                            func.count(DBPaperRepository.paper_id).label("paper_count"),
                        )
                        .outerjoin(DBPaperRepository)
                        .group_by(DBRepository.id)
                    )

                if order_dir.lower() == "desc":
                    query = query.order_by(desc("paper_count"))
                else:
                    query = query.order_by(asc("paper_count"))
            else:
                order_field = getattr(DBRepository, order_by, DBRepository.num_stars)
                if order_dir.lower() == "desc":
                    query = query.order_by(desc(order_field))
                else:
                    query = query.order_by(asc(order_field))

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            # Convert to API models
            api_repositories = []
            for result in results:
                if include_paper_count or order_by == "paper_count":
                    repo, paper_count = result
                    api_repo = self._db_repository_to_api(repo)
                    # Note: paper_count is lost here since Repository model doesn't have this field
                    # This is a limitation of the current API model design
                    api_repositories.append(api_repo)
                else:
                    api_repositories.append(self._db_repository_to_api(result))

            # Calculate pagination info
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Repositories(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=api_repositories,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to fetch repositories: {str(e)}")

    def get_repository_by_id(self, repository_id: str) -> Repository:
        """
        Get a specific repository by ID.

        Args:
            repository_id: Repository ID

        Returns:
            Repository object

        Raises:
            PaperNotFoundError: If repository not found
        """
        try:
            repository = (
                self.db.query(DBRepository)
                .filter(DBRepository.id == int(repository_id))
                .first()
            )

            if not repository:
                raise PaperNotFoundError(
                    f"Repository with ID {repository_id} not found"
                )

            return self._db_repository_to_api(repository)

        except ValueError:
            raise PaperNotFoundError(f"Invalid repository ID: {repository_id}")
        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to fetch repository: {str(e)}")

    def get_repositories_by_owner_and_name(
        self, owner: str, name: str
    ) -> List[Repository]:
        try:
            repositories = (
                self.db.query(DBRepository)
                .filter(DBRepository.owner == owner, DBRepository.name == name)
                .all()
            )
            return [
                self._db_repository_to_api(repository) for repository in repositories
            ]
        except Exception as error:
            raise DatabaseError(f"Failed to fetch repositories: {error}") from error

    def get_repositories_for_paper(self, paper_id: str) -> List[Repository]:
        """
        Get all repositories associated with a specific paper.

        Official repositories come first, then the most-starred ones. Each
        repository's ``is_official`` comes from the paper-repository link.

        Raises:
            PaperNotFoundError: If the paper ID is invalid or not found
        """
        try:
            db_paper_id = int(paper_id)
        except ValueError:
            raise PaperNotFoundError(f"Invalid paper ID: {paper_id}")

        if self.db.query(DBPaper.id).filter(DBPaper.id == db_paper_id).first() is None:
            raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

        rows = (
            self.db.query(DBPaperRepository.is_official, DBRepository)
            .join(DBRepository, DBPaperRepository.repository_id == DBRepository.id)
            .filter(DBPaperRepository.paper_id == db_paper_id)
            .order_by(
                desc(DBPaperRepository.is_official),
                desc(DBRepository.num_stars).nullslast(),
                DBRepository.id,
            )
            .all()
        )
        return [
            self._db_repository_to_api(repository).model_copy(
                update={"is_official": bool(is_official)}
            )
            for is_official, repository in rows
        ]

    def create_or_update_repository(
        self,
        url: str,
        owner: Optional[str] = None,
        name: Optional[str] = None,
        num_stars: int = 0,
        source: str = "unknown",
    ) -> Repository:
        """
        Create a new repository or update existing one.

        GitHub URLs are normalized to lowercase to avoid case-sensitivity duplicates.

        Args:
            url: Repository URL (unique identifier)
            owner: Repository owner
            name: Repository name
            num_stars: Number of stars
            source: Data source

        Returns:
            Repository object (created or updated)
        """
        try:
            repository = self._upsert_repository(url, owner, name, num_stars, source)
            self.db.commit()
        except SQLAlchemyError as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to create/update repository: {str(e)}")
        return self._db_repository_to_api(repository)

    def associate_repository_with_paper(
        self,
        paper_id: str,
        repository_id: str,
        is_official: bool = False,
    ) -> PaperRepository:
        """
        Associate a repository with a paper.

        Args:
            paper_id: Paper ID
            repository_id: Repository ID
            is_official: Whether this repository is official for this paper

        Returns:
            PaperRepository object

        Raises:
            PaperNotFoundError: If paper or repository not found
            DatabaseError: On database errors
        """
        try:
            repository = self._associate_repository(
                paper_id, repository_id, is_official
            )
            self.db.commit()
        except ValueError:
            raise PaperNotFoundError("Invalid paper ID or repository ID")
        except SQLAlchemyError as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to associate repository with paper: {str(e)}")
        return PaperRepository(
            paper_id=paper_id,
            repository_id=repository_id,
            repository=self._db_repository_to_api(repository),
        )

    def create_repository_for_paper(
        self,
        paper_id: str,
        url: str,
        owner: Optional[str] = None,
        name: Optional[str] = None,
        num_stars: int = 0,
        is_official: bool = True,
        source: str = "unknown",
        skip_if_official_exists: bool = True,
    ) -> Optional[Repository]:
        """
        Create a repository and associate it with a paper in one transaction.

        Args:
            paper_id: Paper ID
            url: Repository URL
            owner: Repository owner
            name: Repository name
            num_stars: Number of stars
            is_official: Whether this repository is official for this paper
            source: Data source
            skip_if_official_exists: Skip if paper already has official repository from priority sources

        Returns:
            Repository object if created/updated, None if skipped

        Raises:
            PaperNotFoundError: If paper not found
            DatabaseError: On database errors
        """
        try:
            # Check if we should skip due to existing official repository
            if skip_if_official_exists:
                existing_official = (
                    self.db.query(DBRepository)
                    .join(
                        DBPaperRepository,
                        DBRepository.id == DBPaperRepository.repository_id,
                    )
                    .filter(
                        DBPaperRepository.paper_id == int(paper_id),
                        DBRepository.source.in_(["hf_api"]),  # Priority sources
                        DBPaperRepository.is_official,
                    )
                    .first()
                )

                if existing_official:
                    return None  # Skip - official repository already exists

            repository = self._upsert_repository(url, owner, name, num_stars, source)
            self._associate_repository(paper_id, str(repository.id), is_official)
            self.db.commit()
        except ValueError:
            raise PaperNotFoundError(f"Invalid paper ID: {paper_id}")
        except PaperNotFoundError:
            self.db.rollback()
            raise
        except SQLAlchemyError as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to create repository for paper: {str(e)}")
        return self._db_repository_to_api(repository)

    def _upsert_repository(
        self,
        url: str,
        owner: Optional[str],
        name: Optional[str],
        num_stars: int,
        source: str,
    ) -> DBRepository:
        """Create or update a repository row and flush it without committing."""
        # Normalize GitHub URLs to lowercase to avoid case-sensitivity duplicates
        # GitHub URLs are case-insensitive in practice (they redirect)
        normalized_url = normalize_github_url(url)
        if normalized_url:
            url = normalized_url
            parsed_owner, parsed_name = parse_github_url(url)
            owner = owner or parsed_owner
            name = name or parsed_name
            logger.debug(f"Normalized GitHub URL to: {url}")

        existing_repo = find_repository_by_url(self.db, url)

        if existing_repo:
            if existing_repo.url != url:
                existing_repo.url = url
            existing_repo.owner = owner or existing_repo.owner
            existing_repo.name = name or existing_repo.name
            # Keep highest star count; don't update source - keep original
            existing_repo.num_stars = max(num_stars, existing_repo.num_stars)
            self.db.flush()
            return existing_repo

        new_repo = DBRepository(
            url=url,
            owner=owner,
            name=name,
            num_stars=num_stars,
            source=source,
        )
        self.db.add(new_repo)
        self.db.flush()
        return new_repo

    def _associate_repository(
        self, paper_id: str, repository_id: str, is_official: bool
    ) -> DBRepository:
        """Link a repository to a paper and flush it without committing."""
        paper = self.db.query(DBPaper).filter(DBPaper.id == int(paper_id)).first()
        if not paper:
            raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

        repository = (
            self.db.query(DBRepository)
            .filter(DBRepository.id == int(repository_id))
            .first()
        )
        if not repository:
            raise PaperNotFoundError(f"Repository with ID {repository_id} not found")

        paper_links = self.db.query(DBPaperRepository).filter(
            DBPaperRepository.paper_id == int(paper_id)
        )
        existing_association = paper_links.filter(
            DBPaperRepository.repository_id == int(repository_id)
        ).first()

        if existing_association:
            is_only_repository = paper_links.count() == 1
            existing_association.is_official = (
                is_official or existing_association.is_official or is_only_repository
            )
        else:
            # The first and only repository on a paper page is treated as its
            # official repository by default. Explicit flags still govern
            # additional repositories.
            is_first_repository = paper_links.first() is None
            self.db.add(
                DBPaperRepository(
                    paper_id=int(paper_id),
                    repository_id=int(repository_id),
                    is_official=is_official or is_first_repository,
                )
            )
        self.db.flush()
        return repository

    def _db_repository_to_api(self, db_repository: DBRepository) -> Repository:
        """
        Convert database repository model to API model.

        Args:
            db_repository: Database repository object

        Returns:
            API repository object
        """
        return Repository(
            id=str(db_repository.id),
            url=db_repository.url,
            owner=db_repository.owner,
            name=db_repository.name,
            num_stars=db_repository.num_stars,
            is_official=False,  # Default to False since is_official is now in junction table
            source=db_repository.source,
            trending_score=(
                float(db_repository.trending_score)
                if db_repository.trending_score is not None
                else None
            ),
            trending_score_updated_at=db_repository.trending_score_updated_at,
            created_at=(
                db_repository.created_at.date() if db_repository.created_at else None
            ),
            updated_at=(
                db_repository.updated_at.date() if db_repository.updated_at else None
            ),
        )

    def get_next_repository_group_for_stars_update(
        self, threshold_days: int = 7
    ) -> Optional[Dict[str, Any]]:
        """
        Get the next unique repository (by owner/name) that needs star count updating.
        Returns all repository IDs that share the same owner/name.

        This method groups repositories by owner/name to avoid duplicate API calls
        for the same GitHub repository (e.g., different subdirectories).

        Args:
            threshold_days: Only get repositories older than this many days

        Returns:
            Dictionary with repository group information:
            - owner: Repository owner
            - name: Repository name
            - repository_ids: List of repository IDs sharing this owner/name
            - url_count: Number of URLs for this repository
            - oldest_update: Oldest update timestamp
            - current_stars: Current star count
            - priority: Priority level (1=never updated, 2=needs refresh)
        """
        try:
            threshold_date = datetime.now() - timedelta(days=threshold_days)

            # Create priority for never-updated repositories with 0 stars
            priority_case = case(
                (
                    (func.min(DBRepository.num_stars_updated_at).is_(None))
                    & (func.max(DBRepository.num_stars) == 0),
                    1,
                ),
                else_=2,
            )

            # Query to group by owner/name and get all matching repository IDs
            result = (
                self.db.query(
                    DBRepository.owner,
                    DBRepository.name,
                    func.array_agg(DBRepository.id).label("repository_ids"),
                    func.count(DBRepository.id).label("url_count"),
                    func.min(DBRepository.num_stars_updated_at).label("oldest_update"),
                    func.max(DBRepository.num_stars).label("current_stars"),
                    priority_case.label("priority"),
                )
                .filter(
                    DBRepository.owner.is_not(None),
                    DBRepository.name.is_not(None),
                    DBRepository.owner != "",
                    DBRepository.name != "",
                    (
                        DBRepository.num_stars_updated_at.is_(None)
                        | (DBRepository.num_stars_updated_at < threshold_date)
                        | DBRepository.num_stars.is_(None)
                    ),
                )
                .group_by(DBRepository.owner, DBRepository.name)
                .order_by(
                    priority_case.asc(),
                    func.min(DBRepository.num_stars_updated_at).asc().nullsfirst(),
                    func.count(
                        DBRepository.id
                    ).desc(),  # Process repos with more URLs first
                )
                .first()
            )

            if result:
                return {
                    "owner": result.owner,
                    "name": result.name,
                    "repository_ids": result.repository_ids,
                    "url_count": result.url_count,
                    "oldest_update": result.oldest_update,
                    "current_stars": result.current_stars or 0,
                    "priority": result.priority,
                }

            return None

        except Exception as e:
            raise DatabaseError(
                f"Error fetching next repository group for stars update: {str(e)}"
            )

    def update_repository_stars_batch(
        self, repository_ids: List[int], num_stars: int
    ) -> int:
        """
        Update star counts for multiple repositories in a batch.

        Args:
            repository_ids: List of repository IDs to update
            num_stars: New star count

        Returns:
            Number of repositories updated
        """
        try:
            updated_count = (
                self.db.query(DBRepository)
                .filter(DBRepository.id.in_(repository_ids))
                .update(
                    {
                        DBRepository.num_stars: num_stars,
                        DBRepository.num_stars_updated_at: func.now(),
                        DBRepository.updated_at: func.now(),
                    },
                    synchronize_session=False,
                )
            )

            self.db.commit()
            return updated_count

        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Error updating repository stars: {str(e)}")

    def mark_repositories_as_processed(self, repository_ids: List[int]) -> int:
        """
        Mark repositories as processed even if API call failed.
        This prevents infinite loops for repositories that can't be fetched.

        Args:
            repository_ids: List of repository IDs to mark as processed

        Returns:
            Number of repositories marked
        """
        try:
            updated_count = (
                self.db.query(DBRepository)
                .filter(DBRepository.id.in_(repository_ids))
                .update(
                    {
                        DBRepository.num_stars_updated_at: func.now(),
                        DBRepository.updated_at: func.now(),
                    },
                    synchronize_session=False,
                )
            )

            self.db.commit()
            return updated_count

        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Error marking repositories as processed: {str(e)}")

    def populate_missing_owner_name(self, batch_size: int = 1000) -> Dict[str, int]:
        """
        Populate missing owner and name fields by parsing repository URLs.

        This method finds all repositories with NULL or empty owner/name fields
        and extracts them from the GitHub URLs using parse_github_url utility.

        Args:
            batch_size: Number of repositories to process in each batch

        Returns:
            Dictionary with statistics:
            - total: Total repositories processed
            - updated: Successfully updated repositories
            - skipped: Repositories with invalid/non-GitHub URLs
            - failed: Failed updates
        """
        try:
            from backend.utils.github_utils import parse_github_url

            stats = {"total": 0, "updated": 0, "skipped": 0, "failed": 0}

            # Find repositories with missing owner/name
            repositories = (
                self.db.query(DBRepository)
                .filter(
                    (DBRepository.owner.is_(None))
                    | (DBRepository.name.is_(None))
                    | (DBRepository.owner == "")
                    | (DBRepository.name == "")
                )
                .all()
            )

            stats["total"] = len(repositories)
            logger.info(
                f"Found {stats['total']} repositories with missing owner/name fields"
            )

            # Process in batches
            for i in range(0, len(repositories), batch_size):
                batch = repositories[i : i + batch_size]
                batch_updated = 0

                for repo in batch:
                    try:
                        # Parse GitHub URL to extract owner and name
                        owner, name = parse_github_url(repo.url)

                        if owner and name:
                            # Update repository with parsed values
                            repo.owner = owner
                            repo.name = name
                            batch_updated += 1
                            stats["updated"] += 1
                        else:
                            # Skip non-GitHub URLs or invalid URLs
                            stats["skipped"] += 1
                            logger.debug(
                                f"Skipped repository ID {repo.id}: Unable to parse owner/name from {repo.url}"
                            )

                    except Exception as e:
                        stats["failed"] += 1
                        logger.error(
                            f"Error processing repository ID {repo.id}: {str(e)}"
                        )

                # Commit batch
                try:
                    self.db.commit()
                    logger.info(
                        f"Batch {i // batch_size + 1}: Updated {batch_updated}/{len(batch)} repositories"
                    )
                except Exception as e:
                    self.db.rollback()
                    logger.error(f"Error committing batch: {str(e)}")
                    stats["failed"] += batch_updated
                    stats["updated"] -= batch_updated

            logger.info(
                f"Completed: {stats['updated']} updated, {stats['skipped']} skipped, {stats['failed']} failed"
            )
            return stats

        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Error populating owner/name fields: {str(e)}")

    def get_repository_star_history(
        self,
        repository_id: str,
        limit: Optional[int] = None,
        since: Optional[datetime] = None,
        hours_lookback: Optional[int] = None,
    ) -> RepositoryStarHistoryList:
        """
        Get star count history for a repository.

        Args:
            repository_id: Repository ID
            limit: Maximum number of snapshots to return
            since: Return snapshots after this datetime
            hours_lookback: Number of hours to look back (overrides since if provided)

        Returns:
            RepositoryStarHistoryList with snapshots
        """
        try:
            from backend.models.database import RepositoryStarHistory as DBStarHistory

            # Verify repository exists
            repo = (
                self.db.query(DBRepository)
                .filter(DBRepository.id == int(repository_id))
                .first()
            )
            if not repo:
                raise PaperNotFoundError(
                    f"Repository with ID {repository_id} not found"
                )

            # Build query
            query = self.db.query(DBStarHistory).filter(
                DBStarHistory.repository_id == int(repository_id)
            )

            # Apply time filter
            if hours_lookback:
                cutoff_time = datetime.now() - timedelta(hours=hours_lookback)
                query = query.filter(DBStarHistory.snapshot_at >= cutoff_time)
            elif since:
                query = query.filter(DBStarHistory.snapshot_at >= since)

            # Order by time ascending (oldest first)
            query = query.order_by(DBStarHistory.snapshot_at.asc())

            # Apply limit
            if limit:
                query = query.limit(limit)

            snapshots = query.all()

            # Convert to API models
            api_snapshots = [
                RepositoryStarHistory(
                    id=str(snapshot.id),
                    repository_id=str(snapshot.repository_id),
                    num_stars=snapshot.num_stars,
                    snapshot_at=snapshot.snapshot_at,
                    created_at=snapshot.created_at,
                )
                for snapshot in snapshots
            ]

            return RepositoryStarHistoryList(
                repository_id=repository_id,
                count=len(api_snapshots),
                snapshots=api_snapshots,
            )

        except PaperNotFoundError:
            raise
        except ValueError:
            raise PaperNotFoundError(f"Invalid repository ID: {repository_id}")
        except Exception as e:
            raise DatabaseError(f"Error fetching star history: {str(e)}")
