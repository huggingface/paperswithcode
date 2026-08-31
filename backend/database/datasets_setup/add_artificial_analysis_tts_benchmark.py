"""Create the Artificial Analysis TTS Arena benchmark.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_artificial_analysis_tts_benchmark.py
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.database import Dataset, Metric, Paper, Task
from backend.services.artificial_analysis_tts_sync_service import (
    DATASET_SLUG,
    METRIC_NAME,
    TASK_SLUG,
    TTS_MODELS_URL,
)
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

NAME = "Artificial Analysis TTS Arena"
METHODOLOGY_URL = "https://artificialanalysis.ai/text-to-speech/methodology"
DESCRIPTION = (
    "Artificial Analysis Provider Voice Arena leaderboard for text-to-speech "
    "models. Quality Elo is derived from pairwise listener preferences while "
    "each model uses a representative selection of its provider's voices."
)
SHORT_DESCRIPTION = (
    "Provider-voice text-to-speech quality ranked by listener-preference Elo."
)
SOURCE_TITLE = "Artificial Analysis Text to Speech Benchmarking Methodology"
SOURCE_DATE = date(2024, 7, 15)
SOURCE_ABSTRACT = (
    "Artificial Analysis benchmarks serverless text-to-speech APIs across "
    "quality, price, and generation speed. Its Provider Voice Arena compares "
    "models using representative provider voices and derives Quality Elo from "
    "pairwise listener preferences."
)


def _paper_url(paper: Paper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def main() -> None:
    with db_manager.session_local() as session:
        source_result = ExternalResourceService(session).add_external_resource(
            ExternalResourceInput(
                source_url=METHODOLOGY_URL,
                title=SOURCE_TITLE,
                abstract=SOURCE_ABSTRACT,
                date_published=SOURCE_DATE,
            ),
            commit=False,
        )
        source_paper = session.get(Paper, int(source_result.paper.id))
        if source_paper is None:
            raise RuntimeError("Artificial Analysis TTS methodology was not indexed")

        task = session.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        if task is None:
            raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
        metric = session.query(Metric).filter(Metric.name == METRIC_NAME).one_or_none()
        if metric is None:
            metric = Metric(name=METRIC_NAME, direction="higher_is_better")
            session.add(metric)
            session.flush()
            logger.info("Created metric %r (id=%s)", metric.name, metric.id)

        dataset = (
            session.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        if dataset is None:
            dataset = Dataset(name=NAME, slug=DATASET_SLUG)
            session.add(dataset)
            session.flush()
            logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
        dataset.name = NAME
        dataset.full_name = NAME
        dataset.description = DESCRIPTION
        dataset.short_description = SHORT_DESCRIPTION
        dataset.url = TTS_MODELS_URL
        dataset.homepage = METHODOLOGY_URL
        dataset.paper_url = _paper_url(source_paper)
        dataset.introducing_paper_id = source_paper.id
        dataset.introducing_paper_title = source_paper.title
        dataset.introduced_year = 2024
        session.flush()

        session.execute(
            text(
                """
                INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
                VALUES (:task_id, :dataset_id, FALSE)
                ON CONFLICT (task_id, dataset_id) DO NOTHING
                """
            ),
            {"task_id": task.id, "dataset_id": dataset.id},
        )
        session.execute(
            text(
                """
                INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                VALUES (:task_id, :dataset_id, :metric_id)
                ON CONFLICT DO NOTHING
                """
            ),
            {"task_id": task.id, "dataset_id": dataset.id, "metric_id": metric.id},
        )
        session.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'manual')
                ON CONFLICT (paper_id, task_id)
                DO UPDATE SET source = 'manual'
                """
            ),
            {"paper_id": source_paper.id, "task_id": task.id},
        )
        session.commit()
        logger.info(
            "Artificial Analysis TTS benchmark ready: dataset=%s metric=%s source=%s",
            dataset.id,
            metric.id,
            _paper_url(source_paper),
        )


if __name__ == "__main__":
    main()
