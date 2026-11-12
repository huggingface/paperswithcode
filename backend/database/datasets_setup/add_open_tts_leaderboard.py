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
    CORE_LANGUAGES,
    DATASET_SLUG,
    LANGUAGE_BOARDS,
    RTFX_METRIC,
    SPACE_SOURCE_URL,
    TASK_SLUG,
    WER_METRIC,
    language_dataset_slug,
    language_name,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

NAME = "Open TTS Leaderboard"
DATASETS = "Seed-TTS, CV3-Eval, and MiniMax Multilingual"
DESCRIPTION = (
    "The Hugging Face Open TTS Leaderboard compares open text-to-speech models "
    "on intelligibility and generation speed. This benchmark mirrors its "
    f"default comparable view: English macro-averages across {DATASETS} "
    "without voice cloning."
)
SHORT_DESCRIPTION = f"Open TTS models ranked by English WER and RTFx on {DATASETS}."
CORE_LANGUAGE_NAMES = ", ".join(language_name(label) for label in CORE_LANGUAGES)
# Variant names end in "(<qualifier>)": the task page lists them as chips
# labelled by that qualifier under the English board.
ALL_LANGUAGE_NAME = f"Open TTS Leaderboard ({len(CORE_LANGUAGES)}-language average)"
ALL_LANGUAGE_DESCRIPTION = (
    "The multilingual view of the Hugging Face Open TTS Leaderboard compares "
    "open text-to-speech models using macro-average intelligibility and "
    f"generation speed across the {len(CORE_LANGUAGES)} languages that Seed-TTS "
    f"and CV3-Eval cover ({CORE_LANGUAGE_NAMES}), on {DATASETS} without voice "
    "cloning. Languages covered only by MiniMax have their own boards."
)
ALL_LANGUAGE_SHORT_DESCRIPTION = (
    f"Open TTS models ranked by average WER and RTFx across "
    f"{len(CORE_LANGUAGES)} languages."
)


def _language_benchmark(label: str) -> tuple[str, str, str, str]:
    language = language_name(label)
    return (
        language_dataset_slug(label),
        f"Open TTS Leaderboard ({language})",
        (
            "The per-language view of the Hugging Face Open TTS Leaderboard "
            f"ranks open text-to-speech models on {language} intelligibility "
            f"and generation speed, macro-averaged across the {DATASETS} sets "
            f"that cover {language}, without voice cloning."
        ),
        f"Open TTS models ranked by {language} WER and RTFx.",
    )


BENCHMARKS = (
    (DATASET_SLUG, NAME, DESCRIPTION, SHORT_DESCRIPTION),
    (
        ALL_LANGUAGE_DATASET_SLUG,
        ALL_LANGUAGE_NAME,
        ALL_LANGUAGE_DESCRIPTION,
        ALL_LANGUAGE_SHORT_DESCRIPTION,
    ),
    *(_language_benchmark(label) for label in LANGUAGE_BOARDS),
)
DEEPLINK_CODES = {
    language_dataset_slug(label): code for label, code in LANGUAGE_BOARDS.items()
}
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
        parent: Dataset | None = None
        for slug, name, description, short_description in BENCHMARKS:
            dataset = session.query(Dataset).filter(Dataset.slug == slug).one_or_none()
            if dataset is None:
                dataset = Dataset(name=name, slug=slug)
                session.add(dataset)
                session.flush()
                logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
            dataset.name = name
            dataset.full_name = name
            if parent is None:
                parent = dataset  # BENCHMARKS lists the English board first.
            else:
                dataset.parent_dataset_id = parent.id
                dataset.variant_type = "subset"
            dataset.description = description
            dataset.short_description = short_description
            dataset.url = SPACE_SOURCE_URL
            if (code := DEEPLINK_CODES.get(slug)) is not None:
                dataset.url = f"{SPACE_SOURCE_URL}?languages={code}"
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
