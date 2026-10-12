"""
Test script for evaluation rank recalculation.

This script tests the automatic rank recalculation functionality by:
1. Creating test evaluations with different metric values
2. Verifying ranks are calculated correctly
3. Testing rank updates when evaluations are added/updated/deleted

Usage:
    uv run --env-file backend/keys.env python -m pytest backend/tests/test_rank_recalculation.py -v
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import get_settings
from backend.models.database import (
    CatalogMutationEvent,
    CatalogMutationIdempotency,
    Dataset,
    Evaluation,
    Metric,
    Paper,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.catalog_errors import CatalogPersistenceError
from backend.services.evaluation_curation_service import EvaluationCurationService
from backend.services.evaluation_service import EvaluationService
from backend.utils.exceptions import DatabaseError


@pytest.fixture(scope="function")
def db_session():
    """
    Create a test database session.
    """
    settings = get_settings()
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def rank_target(db_session):
    paper = db_session.query(Paper).first()
    assert paper is not None
    suffix = uuid.uuid4().hex
    task = Task(name=f"Rank test {suffix}", slug=f"rank-test-{suffix}")
    dataset = Dataset(name=f"Rank dataset {suffix}", slug=f"rank-dataset-{suffix}")
    metrics = []
    created_metric_ids = []
    for name in ("mAP", "FPS"):
        metric = db_session.query(Metric).filter(Metric.name == name).first()
        if metric is None:
            metric = Metric(name=name, direction="higher_is_better")
            db_session.add(metric)
            db_session.flush()
            created_metric_ids.append(metric.id)
        metrics.append(metric)
    db_session.add_all([task, dataset])
    db_session.flush()
    db_session.add(TaskDataset(task_id=task.id, dataset_id=dataset.id))
    db_session.add_all(
        TaskDatasetMetric(task_id=task.id, dataset_id=dataset.id, metric_id=metric.id)
        for metric in metrics
    )
    db_session.commit()
    try:
        yield task.id, dataset.id, paper.id
    finally:
        # Tests commit individual mutations.  Reset any failed in-flight
        # transaction, then remove every dependent row before the isolated
        # leaderboard itself so assertion failures cannot leak fixtures.
        db_session.rollback()
        db_session.query(Evaluation).filter(
            Evaluation.task_id == task.id,
            Evaluation.dataset_id == dataset.id,
        ).delete(synchronize_session=False)
        db_session.query(TaskDatasetMetric).filter(
            TaskDatasetMetric.task_id == task.id,
            TaskDatasetMetric.dataset_id == dataset.id,
        ).delete(synchronize_session=False)
        db_session.query(TaskDataset).filter(
            TaskDataset.task_id == task.id,
            TaskDataset.dataset_id == dataset.id,
        ).delete(synchronize_session=False)
        db_session.query(Task).filter(Task.id == task.id).delete(
            synchronize_session=False
        )
        db_session.query(Dataset).filter(Dataset.id == dataset.id).delete(
            synchronize_session=False
        )
        if created_metric_ids:
            db_session.query(Metric).filter(Metric.id.in_(created_metric_ids)).delete(
                synchronize_session=False
            )
        db_session.commit()


def test_rank_calculation_basic(db_session, rank_target):
    """
    Test basic rank calculation for a simple leaderboard.
    """
    service = EvaluationService(db_session)

    # Create test evaluations (using existing paper, task, dataset IDs)
    # You'll need to adjust these IDs based on your database
    test_task_id, test_dataset_id, test_paper_id = rank_target

    # Create evaluations with different mAP scores
    eval1 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model A",
        metrics={"mAP": "60.5"},
        best_metric="mAP",
    )

    eval2 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model B",
        metrics={"mAP": "65.9"},
        best_metric="mAP",
    )

    eval3 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model C",
        metrics={"mAP": "63.2"},
        best_metric="mAP",
    )

    # Verify ranks
    # Model B (65.9) should be rank 1
    # Model C (63.2) should be rank 2
    # Model A (60.5) should be rank 3

    eval1_updated = service.get_evaluation(int(eval1.id))
    eval2_updated = service.get_evaluation(int(eval2.id))
    eval3_updated = service.get_evaluation(int(eval3.id))

    assert eval1_updated.best_rank == 3, (
        f"Model A should be rank 3, got {eval1_updated.best_rank}"
    )
    assert eval2_updated.best_rank == 1, (
        f"Model B should be rank 1, got {eval2_updated.best_rank}"
    )
    assert eval3_updated.best_rank == 2, (
        f"Model C should be rank 2, got {eval3_updated.best_rank}"
    )

    print("✓ Basic rank calculation test passed")

    # Cleanup
    service.delete_evaluation(int(eval1.id))
    service.delete_evaluation(int(eval2.id))
    service.delete_evaluation(int(eval3.id))


def test_rank_recalculation_on_update(db_session, rank_target):
    """
    Test that ranks are recalculated when an evaluation is updated.
    """
    service = EvaluationService(db_session)

    test_task_id, test_dataset_id, test_paper_id = rank_target

    # Create evaluations
    eval1 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model X",
        metrics={"mAP": "60.0"},
        best_metric="mAP",
    )

    eval2 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model Y",
        metrics={"mAP": "62.0"},
        best_metric="mAP",
    )

    # Verify initial ranks
    eval1_v1 = service.get_evaluation(int(eval1.id))
    eval2_v1 = service.get_evaluation(int(eval2.id))
    assert eval1_v1.best_rank == 2
    assert eval2_v1.best_rank == 1

    service.update_evaluation(int(eval1.id), metrics={"mAP": "65.0"}, best_metric="mAP")

    # Verify ranks were recalculated
    eval1_v2 = service.get_evaluation(int(eval1.id))
    eval2_v2 = service.get_evaluation(int(eval2.id))

    assert eval1_v2.best_rank == 1, "Updated Model X should now be rank 1"
    assert eval2_v2.best_rank == 2, "Model Y should now be rank 2"

    print("✓ Rank recalculation on update test passed")

    # Cleanup
    service.delete_evaluation(int(eval1.id))
    service.delete_evaluation(int(eval2.id))


def test_curation_update_rank_failure_rolls_back_evaluation_ranks_audit_and_idempotency(
    db_session, rank_target, monkeypatch
):
    """The curation transaction, not nested rank refresh, owns rollback."""
    task_id, dataset_id, paper_id = rank_target
    service = EvaluationService(db_session)
    lower = service.create_evaluation(
        paper_id=paper_id,
        task_id=task_id,
        dataset_id=dataset_id,
        model_name="Rollback lower",
        metrics={"mAP": "60.0"},
        best_metric="mAP",
    )
    higher = service.create_evaluation(
        paper_id=paper_id,
        task_id=task_id,
        dataset_id=dataset_id,
        model_name="Rollback higher",
        metrics={"mAP": "62.0"},
        best_metric="mAP",
    )
    before_lower = service.get_evaluation(int(lower.id))
    before_higher = service.get_evaluation(int(higher.id))
    event_count = db_session.query(CatalogMutationEvent).count()
    idempotency_key = f"rank-failure-{uuid.uuid4().hex}"
    actor = {
        "hf_subject": f"rank-test-{uuid.uuid4().hex}",
        "username": "rank-test",
        "role": "admin",
    }

    original_recalculate = EvaluationService.recalculate_ranks

    def fail_after_rank_writes(self, *args, **kwargs):
        original_recalculate(self, *args, **kwargs)
        raise DatabaseError("rank refresh failed")

    monkeypatch.setattr(EvaluationService, "recalculate_ranks", fail_after_rank_writes)

    with pytest.raises(CatalogPersistenceError, match="^rank refresh failed$"):
        EvaluationCurationService(db_session).update(
            evaluation_id=int(lower.id),
            payload={"metrics": {"mAP": "70.0"}, "best_metric": "mAP"},
            mutation={
                "actor": actor,
                "idempotency_key": idempotency_key,
                "expected_version": None,
                "request_id": f"rank-failure-{uuid.uuid4().hex}",
            },
        )

    db_session.expire_all()
    after_lower = service.get_evaluation(int(lower.id))
    after_higher = service.get_evaluation(int(higher.id))
    assert after_lower.metrics == before_lower.metrics
    assert after_lower.best_rank == before_lower.best_rank == 2
    assert after_higher.best_rank == before_higher.best_rank == 1
    assert db_session.query(CatalogMutationEvent).count() == event_count
    assert (
        db_session.get(
            CatalogMutationIdempotency, (actor["hf_subject"], idempotency_key)
        )
        is None
    )


def test_evaluation_put_rolls_back_rank_audit_and_idempotency_after_writes_begin(
    db_session, rank_target, monkeypatch
):
    """A failing outer commit rolls back real route, rank, audit, and key writes."""
    from backend.database.connection import get_database_session
    from backend.main import create_app
    from backend.utils.auth import evaluation_mutation_context

    task_id, dataset_id, paper_id = rank_target
    service = EvaluationService(db_session)
    lower = service.create_evaluation(
        paper_id=paper_id,
        task_id=task_id,
        dataset_id=dataset_id,
        model_name="Route rollback lower",
        metrics={"mAP": "60.0"},
        best_metric="mAP",
    )
    higher = service.create_evaluation(
        paper_id=paper_id,
        task_id=task_id,
        dataset_id=dataset_id,
        model_name="Route rollback higher",
        metrics={"mAP": "62.0"},
        best_metric="mAP",
    )
    before_lower = service.get_evaluation(int(lower.id))
    before_higher = service.get_evaluation(int(higher.id))
    event_count = db_session.query(CatalogMutationEvent).count()
    idempotency_key = f"route-rank-failure-{uuid.uuid4().hex}"
    actor = {
        "hf_subject": f"route-rank-test-{uuid.uuid4().hex}",
        "username": "route-rank-test",
        "role": "admin",
    }
    observed = {}

    def fail_outer_commit():
        db_session.flush()
        observed["rank"] = db_session.get(Evaluation, int(lower.id)).best_rank
        observed["event_count"] = db_session.query(CatalogMutationEvent).count()
        observed["idempotency"] = db_session.get(
            CatalogMutationIdempotency, (actor["hf_subject"], idempotency_key)
        )
        raise DatabaseError("outer mutation commit failed")

    monkeypatch.setattr(db_session, "commit", fail_outer_commit)
    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: db_session
    app.dependency_overrides[evaluation_mutation_context] = lambda: {
        "actor": actor,
        "idempotency_key": idempotency_key,
        "expected_version": None,
        "request_id": f"route-rank-failure-{uuid.uuid4().hex}",
    }

    with TestClient(app) as client:
        response = client.put(
            f"/api/v1/evaluations/{lower.id}",
            json={"metrics": {"mAP": "70.0"}, "best_metric": "mAP"},
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert observed["rank"] == 1
    assert observed["event_count"] == event_count + 1
    assert observed["idempotency"] is not None
    db_session.expire_all()
    assert service.get_evaluation(int(lower.id)).metrics == before_lower.metrics
    assert (
        service.get_evaluation(int(lower.id)).best_rank == before_lower.best_rank == 2
    )
    assert (
        service.get_evaluation(int(higher.id)).best_rank == before_higher.best_rank == 1
    )
    assert db_session.query(CatalogMutationEvent).count() == event_count
    assert (
        db_session.get(
            CatalogMutationIdempotency, (actor["hf_subject"], idempotency_key)
        )
        is None
    )


def test_rank_recalculation_on_delete(db_session, rank_target):
    """
    Test that ranks are recalculated when an evaluation is deleted.
    """
    service = EvaluationService(db_session)

    test_task_id, test_dataset_id, test_paper_id = rank_target

    # Create evaluations
    eval1 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model P",
        metrics={"mAP": "55.0"},
        best_metric="mAP",
    )

    eval2 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model Q",
        metrics={"mAP": "60.0"},
        best_metric="mAP",
    )

    eval3 = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model R",
        metrics={"mAP": "58.0"},
        best_metric="mAP",
    )

    # Verify initial ranks
    eval1_v1 = service.get_evaluation(int(eval1.id))
    eval2_v1 = service.get_evaluation(int(eval2.id))
    eval3_v1 = service.get_evaluation(int(eval3.id))

    assert eval1_v1.best_rank == 3
    assert eval2_v1.best_rank == 1
    assert eval3_v1.best_rank == 2

    # Delete the top-ranked evaluation
    service.delete_evaluation(int(eval2.id))

    # Verify remaining evaluations have updated ranks
    eval1_v2 = service.get_evaluation(int(eval1.id))
    eval3_v2 = service.get_evaluation(int(eval3.id))

    assert eval1_v2.best_rank == 2, "Model P should now be rank 2"
    assert eval3_v2.best_rank == 1, "Model R should now be rank 1"

    print("✓ Rank recalculation on delete test passed")

    # Cleanup
    service.delete_evaluation(int(eval1.id))
    service.delete_evaluation(int(eval3.id))


def test_separate_ranking_by_additional_data(db_session, rank_target):
    """
    Test that evaluations with/without additional data are ranked separately.
    """
    service = EvaluationService(db_session)

    test_task_id, test_dataset_id, test_paper_id = rank_target

    # Create evaluations without additional data
    eval1_no_extra = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model No Extra 1",
        metrics={"mAP": "60.0"},
        best_metric="mAP",
        uses_additional_data=False,
    )

    eval2_no_extra = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model No Extra 2",
        metrics={"mAP": "62.0"},
        best_metric="mAP",
        uses_additional_data=False,
    )

    # Create evaluations with additional data
    eval1_extra = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model Extra 1",
        metrics={"mAP": "65.0"},
        best_metric="mAP",
        uses_additional_data=True,
    )

    eval2_extra = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="Model Extra 2",
        metrics={"mAP": "68.0"},
        best_metric="mAP",
        uses_additional_data=True,
    )

    service.recalculate_ranks(test_task_id, test_dataset_id, uses_additional_data=False)
    service.recalculate_ranks(test_task_id, test_dataset_id, uses_additional_data=True)

    # Verify ranks within each group
    eval1_no_extra_check = service.get_evaluation(int(eval1_no_extra.id))
    eval2_no_extra_check = service.get_evaluation(int(eval2_no_extra.id))
    eval1_extra_check = service.get_evaluation(int(eval1_extra.id))
    eval2_extra_check = service.get_evaluation(int(eval2_extra.id))

    # Within the no-extra-data group
    assert eval1_no_extra_check.best_rank == 2
    assert eval2_no_extra_check.best_rank == 1

    # Within the extra-data group
    assert eval1_extra_check.best_rank == 2
    assert eval2_extra_check.best_rank == 1

    print("✓ Separate ranking by additional data test passed")

    # Cleanup
    service.delete_evaluation(int(eval1_no_extra.id))
    service.delete_evaluation(int(eval2_no_extra.id))
    service.delete_evaluation(int(eval1_extra.id))
    service.delete_evaluation(int(eval2_extra.id))


def test_fps_rank_includes_secondary_metric_rows(db_session, rank_target):
    """
    FPS rank should include mAP-primary rows that also report FPS, not only
    rows whose best_metric is FPS.
    """
    service = EvaluationService(db_session)

    test_task_id, test_dataset_id, test_paper_id = rank_target

    slow_fps = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="__rank_test_slow_fps__",
        metrics={"FPS": "1.0"},
        best_metric="FPS",
    )
    slow_rank_before = service.get_evaluation(int(slow_fps.id)).best_rank

    faster_map = service.create_evaluation(
        paper_id=test_paper_id,
        task_id=test_task_id,
        dataset_id=test_dataset_id,
        model_name="__rank_test_fast_map_fps__",
        metrics={"mAP": "1.0", "FPS": "99999"},
        best_metric="mAP",
    )

    slow_rank_after = service.get_evaluation(int(slow_fps.id)).best_rank
    assert slow_rank_after == slow_rank_before + 1, (
        f"Adding a faster mAP-primary row should push the FPS-primary row down by 1 "
        f"(before={slow_rank_before}, after={slow_rank_after})"
    )

    service.delete_evaluation(int(faster_map.id))
    service.delete_evaluation(int(slow_fps.id))
