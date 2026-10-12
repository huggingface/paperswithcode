import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService


def test_service_direct_and_cascade_deletes_create_badge_tombstones():
    suffix = uuid.uuid4().int % 1_000_000_000
    paper_id = -(suffix * 10 + 1)
    task_id = -(suffix * 10 + 2)
    dataset_id = -(suffix * 10 + 3)
    evaluation_ids = [-(suffix * 10 + offset) for offset in (4, 5, 6)]

    with db_manager.engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                text(
                    """
                    INSERT INTO papers (id, title, source, arxiv_id, is_latest_version)
                    VALUES (:paper_id, 'Badge tombstone test', 'arxiv', :arxiv_id, true)
                    """
                ),
                {"paper_id": paper_id, "arxiv_id": f"badge-test-{suffix}"},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO tasks (id, name, slug)
                    VALUES (:task_id, 'Badge tombstone test', :task_slug)
                    """
                ),
                {"task_id": task_id, "task_slug": f"badge-test-task-{suffix}"},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO datasets (id, name, slug)
                    VALUES (:dataset_id, 'Badge Test Benchmark', :dataset_slug)
                    """
                ),
                {
                    "dataset_id": dataset_id,
                    "dataset_slug": f"badge-test-dataset-{suffix}",
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO evaluations (
                        id, paper_id, task_id, dataset_id, model_name, metrics
                    )
                    SELECT id, :paper_id, :task_id, :dataset_id, 'Badge test', '{}'::jsonb
                    FROM unnest(:evaluation_ids) AS id
                    """
                ),
                {
                    "paper_id": paper_id,
                    "task_id": task_id,
                    "dataset_id": dataset_id,
                    "evaluation_ids": evaluation_ids,
                },
            )

            session = Session(bind=connection)
            EvaluationService(session).delete_evaluation(
                evaluation_ids[0], commit=False
            )
            connection.execute(
                text("DELETE FROM evaluations WHERE id = :evaluation_id"),
                {"evaluation_id": evaluation_ids[1]},
            )
            connection.execute(
                text("DELETE FROM datasets WHERE id = :dataset_id"),
                {"dataset_id": dataset_id},
            )

            rows = connection.execute(
                text(
                    """
                    SELECT evaluation_id, paper_id, task_id, dataset_id,
                           task_slug, dataset_slug, dataset_name
                    FROM evaluation_badge_tombstones
                    WHERE evaluation_id = ANY(:evaluation_ids)
                    ORDER BY evaluation_id
                    """
                ),
                {"evaluation_ids": evaluation_ids},
            ).all()

            assert {row.evaluation_id for row in rows} == set(evaluation_ids)
            assert all(row.paper_id == paper_id for row in rows)
            assert all(row.task_id == task_id for row in rows)
            assert all(row.dataset_id == dataset_id for row in rows)
            assert all(row.task_slug == f"badge-test-task-{suffix}" for row in rows)
            assert all(
                row.dataset_slug == f"badge-test-dataset-{suffix}" for row in rows
            )
            assert all(row.dataset_name == "Badge Test Benchmark" for row in rows)
        finally:
            transaction.rollback()
