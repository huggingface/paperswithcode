"""Recompute evaluations.external from paper-native sources.

Run after linking conference pages, project pages, repos, or HF artifacts:

    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/recompute_evaluations_external.py
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from backend.database.connection import db_manager
from backend.models.database import Evaluation, Paper
from backend.services.evaluation_service import evaluation_is_external

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main() -> None:
    updated = 0
    checked = 0

    with db_manager.session_local() as session:
        rows = session.execute(
            select(Evaluation, Paper)
            .join(Paper, Paper.id == Evaluation.paper_id)
            .where(Evaluation.source_url.is_not(None))
        ).all()

        for evaluation, paper in rows:
            checked += 1
            source_url = evaluation.source_url
            derived = evaluation_is_external(
                source_url,
                paper.arxiv_id,
                paper.id,
                session,
            )
            if evaluation.external != derived:
                evaluation.external = derived
                updated += 1

        session.commit()

    logger.info(
        "Recomputed external flags for %s evaluations; updated %s rows.",
        checked,
        updated,
    )


if __name__ == "__main__":
    main()
