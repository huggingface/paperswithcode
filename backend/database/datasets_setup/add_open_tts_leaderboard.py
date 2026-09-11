"""Create the Open TTS Leaderboard benchmarks and metric links.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_open_tts_leaderboard.py
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.database import Dataset, Metric, Paper, Task
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.open_tts_sync_service import (
    ALL_LANGUAGE_DATASET_SLUG,
    DATASET_SLUG,
    RTFX_METRIC,
    SPACE_SOURCE_URL,
    TASK_SLUG,
    WER_METRIC,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

NAME = "Open TTS Leaderboard"
DESCRIPTION = (
    "The Hugging Face Open TTS Leaderboard compares open text-to-speech models "
    "on intelligibility and generation speed. This benchmark mirrors its "
    "default comparable view: English macro-averages across Seed-TTS and "
    "CV3-Eval without voice cloning."
)
SHORT_DESCRIPTION = (
    "Open TTS models ranked by English WER and RTFx on Seed-TTS and CV3-Eval."
)
ALL_LANGUAGE_NAME = "Open TTS Leaderboard — All Languages Average"
ALL_LANGUAGE_DESCRIPTION = (
    "The multilingual view of the Hugging Face Open TTS Leaderboard compares "
    "open text-to-speech models using macro-average intelligibility and "
    "generation speed across every language currently exposed by the Space, "
    "on Seed-TTS and CV3-Eval without voice cloning."
)
ALL_LANGUAGE_SHORT_DESCRIPTION = (
    "Open TTS models ranked by average WER and RTFx across all available languages."
)
BENCHMARKS = (
    (DATASET_SLUG, NAME, DESCRIPTION, SHORT_DESCRIPTION),
    (
        ALL_LANGUAGE_DATASET_SLUG,
        ALL_LANGUAGE_NAME,
        ALL_LANGUAGE_DESCRIPTION,
        ALL_LANGUAGE_SHORT_DESCRIPTION,
    ),
)
SOURCE_TITLE = "Open TTS Leaderboard"
# The formal citation declares only 2026; use the Space's public createdAt date
# rather than inventing a January publication date.
SOURCE_DATE = date(2026, 9, 7)
SOURCE_ABSTRACT = (
    "A Hugging Face Audio Team leaderboard for open-source text-to-speech "
    "models evaluated on intelligibility, speed, and speaker similarity across "
    "multilingual evaluation sets."
)


def _paper_url(paper: Paper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def main() -> None:
    with db_manager.session_local() as session:
        source_result = ExternalResourceService(session).add_external_resource(
            ExternalResourceInput(
                source_url=SPACE_SOURCE_URL,
                title=SOURCE_TITLE,
                abstract=SOURCE_ABSTRACT,
                date_published=SOURCE_DATE,
            ),
            commit=False,
        )
        source_paper = session.get(Paper, int(source_result.paper.id))
        if source_paper is None:
            raise RuntimeError("Open TTS Leaderboard source was not indexed")

        task = session.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        if task is None:
            raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")

        metrics: dict[str, Metric] = {}
        for name, direction in (
            (WER_METRIC, "lower_is_better"),
            (RTFX_METRIC, "higher_is_better"),
        ):
            metric = session.query(Metric).filter(Metric.name == name).one_or_none()
            if metric is None:
                metric = Metric(name=name, direction=direction)
                session.add(metric)
                session.flush()
                logger.info("Created metric %r (id=%s)", metric.name, metric.id)
            metrics[name] = metric

        dataset_ids: list[int] = []
        for slug, name, description, short_description in BENCHMARKS:
            dataset = session.query(Dataset).filter(Dataset.slug == slug).one_or_none()
            if dataset is None:
                dataset = Dataset(name=name, slug=slug)
                session.add(dataset)
                session.flush()
                logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
            dataset.name = name
            dataset.full_name = name
            dataset.description = description
            dataset.short_description = short_description
            dataset.url = SPACE_SOURCE_URL
            dataset.hf_url = SPACE_SOURCE_URL
            dataset.homepage = SPACE_SOURCE_URL
            dataset.paper_url = _paper_url(source_paper)
            dataset.introducing_paper_id = source_paper.id
            dataset.introducing_paper_title = source_paper.title
            dataset.introduced_year = 2026
            session.flush()
            dataset_ids.append(dataset.id)

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
            for metric in metrics.values():
                session.execute(
                    text(
                        """
                        INSERT INTO task_dataset_metrics
                            (task_id, dataset_id, metric_id)
                        VALUES (:task_id, :dataset_id, :metric_id)
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {
                        "task_id": task.id,
                        "dataset_id": dataset.id,
                        "metric_id": metric.id,
                    },
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
            "Open TTS benchmarks ready: datasets=%s metrics=%s source=%s",
            ",".join(str(dataset_id) for dataset_id in dataset_ids),
            ",".join(metrics),
            _paper_url(source_paper),
        )


if __name__ == "__main__":
    main()
