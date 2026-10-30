"""Paper implementation coverage predicates: code repositories and Hub artifacts."""

from __future__ import annotations

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import aliased

from backend.models.database import Paper as DBPaper
from backend.models.database import PaperRepository as DBPaperRepository


def family_repository_exists_clause(
    paper=DBPaper,
    *,
    official_only: bool = False,
):
    """Return whether any version in ``paper``'s family links a repository."""
    family = aliased(DBPaper)
    conditions = [
        or_(
            and_(
                paper.arxiv_id.is_not(None),
                family.arxiv_id == paper.arxiv_id,
            ),
            and_(paper.arxiv_id.is_(None), family.id == paper.id),
        )
    ]
    if official_only:
        conditions.append(DBPaperRepository.is_official)
    return exists(
        select(1)
        .select_from(family)
        .join(DBPaperRepository, DBPaperRepository.paper_id == family.id)
        .where(*conditions)
    )


# Hub artifacts come from the HF CRON's junction table (arXiv papers) or from
# explicit URL arrays on the paper (external papers). Feed-card badges count
# both, so every ``has_hf_artifacts`` filter must accept either.
HF_ARTIFACTS_EXIST_SQL = """(
    EXISTS (SELECT 1 FROM paper_hf_artifacts pha WHERE pha.paper_id = p.id)
    OR cardinality(p.hf_models) > 0
    OR cardinality(p.hf_datasets) > 0
    OR cardinality(p.hf_spaces) > 0
)"""


def hf_artifacts_exist_clause():
    """Return whether a paper links any Hugging Face model, dataset, or Space."""
    return or_(
        DBPaper.hf_artifacts.any(),
        func.cardinality(DBPaper.hf_models) > 0,
        func.cardinality(DBPaper.hf_datasets) > 0,
        func.cardinality(DBPaper.hf_spaces) > 0,
    )
