"""Read services for the first-class framework catalogue."""

from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.taxonomy import (
    FrameworkCatalog,
    FrameworkCatalogCategory,
    FrameworkCatalogDomain,
    FrameworkCatalogItem,
)
from backend.models.database import (
    Framework as DBFramework,
    FrameworkCategory as DBFrameworkCategory,
    FrameworkDomain as DBFrameworkDomain,
    FrameworkPlatform as DBFrameworkPlatform,
    Paper as DBPaper,
    PaperRepository as DBPaperRepository,
    Repository as DBRepository,
)
from backend.utils.github_utils import normalize_github_url, parse_github_url


class FrameworkService:
    def __init__(self, db: Session):
        self.db = db

    def get_catalog(self) -> FrameworkCatalog:
        domains = (
            self.db.query(DBFrameworkDomain)
            .order_by(DBFrameworkDomain.display_order, DBFrameworkDomain.name)
            .all()
        )
        categories = (
            self.db.query(DBFrameworkCategory)
            .order_by(
                DBFrameworkCategory.domain_id,
                DBFrameworkCategory.display_order,
                DBFrameworkCategory.name,
            )
            .all()
        )
        framework_rows = (
            self.db.query(DBFramework, DBRepository, DBPaper)
            .outerjoin(DBRepository, DBFramework.repository_id == DBRepository.id)
            .outerjoin(DBPaper, DBFramework.introducing_paper_id == DBPaper.id)
            .order_by(
                DBFramework.category_id,
                DBFramework.display_order,
                DBFramework.name,
            )
            .all()
        )
        platform_rows = (
            self.db.query(DBFrameworkPlatform)
            .order_by(DBFrameworkPlatform.framework_id, DBFrameworkPlatform.platform)
            .all()
        )
        paper_count_rows = (
            self.db.query(
                DBFramework.id,
                func.count(func.distinct(DBPaper.id)),
            )
            .outerjoin(
                DBPaperRepository,
                DBPaperRepository.repository_id == DBFramework.repository_id,
            )
            .outerjoin(
                DBPaper,
                (DBPaper.id == DBPaperRepository.paper_id) & DBPaper.is_latest_version,
            )
            .group_by(DBFramework.id)
            .all()
        )
        paper_counts = dict(paper_count_rows)

        platforms_by_framework: dict[int, list[str]] = defaultdict(list)
        for row in platform_rows:
            platforms_by_framework[row.framework_id].append(row.platform)

        frameworks_by_category: dict[int, list[FrameworkCatalogItem]] = defaultdict(
            list
        )
        for framework, repository, paper in framework_rows:
            frameworks_by_category[framework.category_id].append(
                FrameworkCatalogItem(
                    id=str(framework.id),
                    slug=framework.slug,
                    name=framework.name,
                    organization_name=framework.organization_name,
                    description=framework.description,
                    when_to_use=framework.when_to_use,
                    platforms=platforms_by_framework[framework.id],
                    github_url=repository.url if repository else None,
                    repository=self._repository_identity(repository),
                    paper_count=paper_counts.get(framework.id, 0),
                    docs_url=framework.docs_url,
                    introducing_paper_arxiv_id=paper.arxiv_id if paper else None,
                )
            )

        categories_by_domain: dict[int, list[FrameworkCatalogCategory]] = defaultdict(
            list
        )
        for category in categories:
            categories_by_domain[category.domain_id].append(
                FrameworkCatalogCategory(
                    slug=category.slug,
                    name=category.name,
                    description=category.description,
                    guide_url=category.guide_url,
                    guide_label=category.guide_label,
                    frameworks=frameworks_by_category[category.id],
                )
            )

        return FrameworkCatalog(
            domains=[
                FrameworkCatalogDomain(
                    slug=domain.slug,
                    name=domain.name,
                    description=domain.description,
                    categories=categories_by_domain[domain.id],
                )
                for domain in domains
            ]
        )

    @staticmethod
    def _repository_identity(repository: DBRepository | None) -> str | None:
        if not repository:
            return None
        if repository.owner and repository.name:
            return f"{repository.owner}/{repository.name}"
        normalized_url = normalize_github_url(repository.url)
        if not normalized_url:
            return None
        owner, name = parse_github_url(normalized_url)
        return f"{owner}/{name}" if owner and name else None
