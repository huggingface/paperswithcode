"""Papers trending on X: the daily "AI Papers on X" sheet and its homepage feed.

A headless routine exports each dated sheet tab and replaces that day's rows
through the admin API. ArXiv papers missing from the catalog are imported;
non-arXiv rows match an existing external paper by its source URL, otherwise
they are reported back as unresolved.
"""

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.models.database import Paper as DBPaper, PaperXTrending
from backend.models.papers import Papers
from backend.models.x_trending import (
    XTrendingDayResult,
    XTrendingPaperInput,
    XTrendingUnresolved,
)
from backend.services.paper_feed_executor import GENERAL_ORDERING, PaperFeedExecutor
from backend.services.paper_ingestion_service import (
    PaperIngestionError,
    PaperIngestionService,
)
from backend.services.paper_service import PaperService


class XTrendingService:
    def __init__(self, db: Session, ingestion: PaperIngestionService | None = None):
        self.db = db
        self.ingestion = ingestion or PaperIngestionService(db)

    async def replace_day(
        self, shared_on: date, rows: list[XTrendingPaperInput]
    ) -> XTrendingDayResult:
        """Replace one day's papers with the resolvable rows of its sheet tab."""
        entries: dict[int, PaperXTrending] = {}
        imported: list[str] = []
        unresolved: list[XTrendingUnresolved] = []
        for row in sorted(rows, key=lambda row: row.rank):
            paper, reason = await self._resolve(row, imported)
            if paper is None:
                unresolved.append(
                    XTrendingUnresolved(
                        rank=row.rank,
                        arxiv_id=row.arxiv_id,
                        source_url=row.source_url,
                        title=row.title,
                        reason=reason,
                    )
                )
                continue
            # A paper listed twice in one day keeps its best rank.
            entries.setdefault(
                paper.id,
                PaperXTrending(
                    shared_on=shared_on,
                    paper_id=paper.id,
                    rank=row.rank,
                    post_url=row.post_url,
                    post_author=row.post_author,
                    like_count=row.like_count,
                    repost_count=row.repost_count,
                    view_count=row.view_count,
                ),
            )
        self.db.query(PaperXTrending).filter(
            PaperXTrending.shared_on == shared_on
        ).delete(synchronize_session=False)
        self.db.add_all(entries.values())
        self.db.commit()
        return XTrendingDayResult(
            shared_on=shared_on.isoformat(),
            linked=len(entries),
            imported=imported,
            unresolved=unresolved,
        )

    async def _resolve(
        self, row: XTrendingPaperInput, imported: list[str]
    ) -> tuple[DBPaper | None, str]:
        if row.arxiv_id:
            try:
                paper, created = await self.ingestion.get_or_import_arxiv_paper(
                    row.arxiv_id
                )
            except PaperIngestionError as error:
                return None, f"arxiv import failed: {error.error_type or 'unknown'}"
            if created:
                imported.append(paper.arxiv_id)
            return paper, ""
        paper = (
            self.db.query(DBPaper)
            .filter(
                DBPaper.source == "external",
                DBPaper.source_url == row.source_url,
                DBPaper.is_latest_version,
            )
            .first()
        )
        return paper, "" if paper else "no external paper with this source URL"

    def feed(
        self,
        *,
        page: int,
        page_size: int,
        start_date: date | None,
        end_date: date | None,
        include_resources: bool,
        has_code: bool,
        has_hf_artifacts: bool,
    ) -> Papers:
        """Papers ever shared on X, published within the window, by trending score.

        Like the other homepage tabs, the window filters on publication date.
        """
        shared = select(PaperXTrending.paper_id)
        # Match the stored paper's arXiv id too, so a newer version that has
        # since become the latest row stays in the feed.
        shared_arxiv_ids = select(DBPaper.arxiv_id).where(
            DBPaper.id.in_(shared), DBPaper.arxiv_id.is_not(None)
        )
        papers = PaperService(self.db)
        return PaperFeedExecutor(papers).execute(
            self.db.query(DBPaper).filter(
                or_(DBPaper.id.in_(shared), DBPaper.arxiv_id.in_(shared_arxiv_ids))
            ),
            page=page,
            page_size=page_size,
            order_by="trending",
            order_dir="desc",
            ordering=GENERAL_ORDERING,
            has_code=has_code,
            has_hf_artifacts=has_hf_artifacts,
            start_date=start_date,
            end_date=end_date,
            include_resources=include_resources,
        )
