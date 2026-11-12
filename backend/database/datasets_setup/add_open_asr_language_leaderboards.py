"""Create the per-language Open ASR Leaderboard benchmarks and metric links.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/add_open_asr_language_leaderboards.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.database import Dataset, Metric, Task
from backend.services.open_asr_language_sync_service import (
    LANGUAGE_BOARDS,
    language_dataset_slug,
    language_name,
)
from backend.services.open_asr_sync_service import (
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


def main() -> None:
    with db_manager.session_local() as session:
        task = session.query(Task).filter(Task.slug == TASK_SLUG).one()
        english = session.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one()
        metrics = (
            session.query(Metric)
            .filter(Metric.name.in_((WER_METRIC, RTFX_METRIC)))
            .all()
        )
        if len(metrics) != 2:
            raise RuntimeError("Open ASR WER and RTFx metrics must exist")

        dataset_ids: list[int] = []
        for label, code in LANGUAGE_BOARDS.items():
            language = language_name(label)
            slug = language_dataset_slug(label)
            dataset = session.query(Dataset).filter(Dataset.slug == slug).one_or_none()
            if dataset is None:
                dataset = Dataset(name=f"Open ASR Leaderboard ({language})", slug=slug)
                session.add(dataset)
                session.flush()
                logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
            # "(<language>)" becomes the chip label under the English board.
            dataset.name = f"Open ASR Leaderboard ({language})"
            dataset.full_name = (
                f"Open Automatic Speech Recognition Leaderboard ({language})"
            )
            dataset.parent_dataset_id = english.id
            dataset.variant_type = "subset"
            dataset.description = (
                "The multilingual view of the Hugging Face Open ASR Leaderboard "
                f"ranks speech recognition models by {language} word error "
                f"rate, averaged across the leaderboard's {language} datasets, "
                "with real-time factor (RTFx) where the Space measures it."
            )
            dataset.short_description = (
                f"ASR models ranked by average {language} WER on the Open ASR "
                "Leaderboard."
            )
            dataset.url = f"{SPACE_SOURCE_URL}?languages={code}"
            dataset.hf_url = SPACE_SOURCE_URL
            dataset.homepage = SPACE_SOURCE_URL
            dataset.paper_url = english.paper_url
            dataset.introducing_paper_id = english.introducing_paper_id
            dataset.introducing_paper_title = english.introducing_paper_title
            dataset.introduced_year = english.introduced_year
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
            for metric in metrics:
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
        session.commit()
        logger.info(
            "Open ASR language benchmarks ready: datasets=%s",
            ",".join(str(dataset_id) for dataset_id in dataset_ids),
        )


if __name__ == "__main__":
    main()
