"""
Tests for API alignment with November 2025 schema updates.

This test suite validates:
1. Triple-based leaderboard metric validation
2. Project page CRUD operations
3. Paper-project page associations
4. Repository star history endpoint
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    Evaluation as DBEvaluation,
    Paper as DBPaper,
    Task as DBTask,
    Dataset as DBDataset,
    Metric as DBMetric,
    TaskDatasetMetric as DBTaskDatasetMetric,
    ProjectPage as DBProjectPage,
    Repository as DBRepository,
    RepositoryStarHistory as DBRepositoryStarHistory,
)
from backend.services.evaluation_service import EvaluationService
from backend.services.project_page_service import ProjectPageService
from backend.services.repository_service import RepositoryService
from backend.models.evaluations import EvaluationCreateRequest
from backend.models.papers import ProjectPageCreateRequest, ProjectPageUpdateRequest


@pytest.fixture
def db_session():
    """Create a test database session."""
    with db_manager.session_local() as session:
        yield session
        session.rollback()


@pytest.fixture
def test_paper(db_session: Session):
    """Create a test paper."""
    paper = DBPaper(
        title="Test Paper for API Alignment",
        abstract="Test abstract",
        arxiv_id="2025.12345",
        version="v1",
        is_latest_version=True,
        date_published=datetime.now().date(),
    )
    db_session.add(paper)
    db_session.commit()
    db_session.refresh(paper)
    return paper


@pytest.fixture
def test_task(db_session: Session):
    """Create a test task."""
    task = DBTask(
        name="Test Task",
        description="Test task description",
        slug="test-task",
        level=0,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.fixture
def test_dataset(db_session: Session):
    """Create a test dataset."""
    dataset = DBDataset(
        name="Test Dataset",
        slug="test-dataset",
        description="Test dataset description",
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)
    return dataset


@pytest.fixture
def test_metric(db_session: Session):
    """Create a test metric."""
    metric = DBMetric(
        name="TestAP",
        full_name="Test Average Precision",
        direction="higher_is_better",
    )
    db_session.add(metric)
    db_session.commit()
    db_session.refresh(metric)
    return metric


@pytest.fixture
def test_repository(db_session: Session):
    """Create a test repository."""
    repo = DBRepository(
        url="https://github.com/test/repo",
        owner="test",
        name="repo",
        num_stars=100,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


class TestTripleValidation:
    """Test leaderboard triple (task, dataset, metric) validation."""

    def test_evaluation_with_allowed_metric(
        self, db_session, test_paper, test_task, test_dataset, test_metric
    ):
        """Test that evaluation succeeds when metric is in allowed list."""
        # Create triple: task + dataset + metric
        triple = DBTaskDatasetMetric(
            task_id=test_task.id,
            dataset_id=test_dataset.id,
            metric_id=test_metric.id,
        )
        db_session.add(triple)
        db_session.commit()

        # Create evaluation with allowed metric
        service = EvaluationService(db_session)
        request = EvaluationCreateRequest(
            paper_id=test_paper.id,
            task_id=test_task.id,
            dataset_id=test_dataset.id,
            model_name="Test Model",
            metrics={"TestAP": "85.5"},
            best_metric="TestAP",
        )

        evaluation = service.create_evaluation(
            paper_id=request.paper_id,
            task_id=request.task_id,
            dataset_id=request.dataset_id,
            model_name=request.model_name,
            metrics=request.metrics,
            best_metric=request.best_metric,
        )

        assert evaluation is not None
        assert evaluation.best_metric == "TestAP"

    def test_evaluation_with_disallowed_metric(
        self, db_session, test_paper, test_task, test_dataset, test_metric
    ):
        """Test that evaluation fails when metric is not in allowed list."""
        # Create triple with TestAP
        triple = DBTaskDatasetMetric(
            task_id=test_task.id,
            dataset_id=test_dataset.id,
            metric_id=test_metric.id,
        )
        db_session.add(triple)
        db_session.commit()

        # Try to create evaluation with different metric
        service = EvaluationService(db_session)
        request = EvaluationCreateRequest(
            paper_id=test_paper.id,
            task_id=test_task.id,
            dataset_id=test_dataset.id,
            model_name="Test Model",
            metrics={"WER": "5.2"},  # Not in allowed list
            best_metric="WER",
        )

        with pytest.raises(ValueError, match="not allowed"):
            service.create_evaluation(
                paper_id=request.paper_id,
                task_id=request.task_id,
                dataset_id=request.dataset_id,
                model_name=request.model_name,
                metrics=request.metrics,
                best_metric=request.best_metric,
            )

    def test_evaluation_without_triple_is_rejected(
        self, db_session, test_paper, test_task, test_dataset
    ):
        """An evaluation requires a configured task-dataset metric triple."""
        service = EvaluationService(db_session)
        request = EvaluationCreateRequest(
            paper_id=test_paper.id,
            task_id=test_task.id,
            dataset_id=test_dataset.id,
            model_name="Test Model",
            metrics={"AnyMetric": "99.9"},
            best_metric="AnyMetric",
        )

        with pytest.raises(ValueError, match="No leaderboard defined"):
            service.create_evaluation(
                paper_id=request.paper_id,
                task_id=request.task_id,
                dataset_id=request.dataset_id,
                model_name=request.model_name,
                metrics=request.metrics,
                best_metric=request.best_metric,
            )

        assert (
            db_session.query(DBEvaluation)
            .filter(
                DBEvaluation.paper_id == request.paper_id,
                DBEvaluation.task_id == request.task_id,
                DBEvaluation.dataset_id == request.dataset_id,
            )
            .count()
            == 0
        )


class TestProjectPageCRUD:
    """Test project page CRUD operations."""

    def test_create_project_page(self, db_session):
        """Test creating a new project page."""
        service = ProjectPageService(db_session)
        request = ProjectPageCreateRequest(
            url="https://example.com/project",
            is_official=True,
            source="manual",
        )

        page = service.create_project_page(request)

        assert page is not None
        assert page.url == "https://example.com/project"
        assert page.is_official is True
        assert page.source == "manual"

    def test_create_duplicate_project_page(self, db_session):
        """Test that creating duplicate project page fails."""
        service = ProjectPageService(db_session)
        request = ProjectPageCreateRequest(
            url="https://example.com/duplicate",
            is_official=True,
            source="manual",
        )

        # Create first page
        service.create_project_page(request)

        # Try to create duplicate
        with pytest.raises(ValueError, match="already exists"):
            service.create_project_page(request)

    def test_update_project_page(self, db_session):
        """Test updating a project page."""
        service = ProjectPageService(db_session)

        # Create page
        create_request = ProjectPageCreateRequest(
            url="https://example.com/update-test",
            is_official=False,
            source="manual",
        )
        page = service.create_project_page(create_request)

        # Update page
        update_request = ProjectPageUpdateRequest(
            is_official=True,
            source="ai_extraction",
        )
        updated_page = service.update_project_page(page.id, update_request)

        assert updated_page.is_official is True
        assert updated_page.source == "ai_extraction"
        assert updated_page.url == "https://example.com/update-test"  # Unchanged

    def test_delete_project_page(self, db_session):
        """Test deleting a project page."""
        service = ProjectPageService(db_session)

        # Create page
        request = ProjectPageCreateRequest(
            url="https://example.com/delete-test",
            is_official=True,
            source="manual",
        )
        page = service.create_project_page(request)

        # Delete page
        service.delete_project_page(page.id)

        # Verify deletion
        deleted_page = (
            db_session.query(DBProjectPage)
            .filter(DBProjectPage.id == int(page.id))
            .first()
        )
        assert deleted_page is None


class TestPaperProjectPageAssociations:
    """Test paper-project page association management."""

    def test_associate_project_page_with_paper(self, db_session, test_paper):
        """Test associating a project page with a paper."""
        service = ProjectPageService(db_session)

        # Create project page
        create_request = ProjectPageCreateRequest(
            url="https://example.com/paper-project",
            is_official=True,
            source="manual",
        )
        page = service.create_project_page(create_request)

        # Associate with paper
        association = service.associate_project_page_with_paper(
            paper_id=str(test_paper.id),
            project_page_id=page.id,
        )

        assert association is not None
        assert association.paper_id == str(test_paper.id)
        assert association.project_page_id == page.id


class TestRepositoryStarHistory:
    """Test repository star history endpoint."""

    def test_get_star_history(self, db_session, test_repository):
        """Test retrieving star history for a repository."""
        # Create some star history snapshots
        now = datetime.now()
        for i in range(5):
            snapshot = DBRepositoryStarHistory(
                repository_id=test_repository.id,
                num_stars=100 + i * 10,
                snapshot_at=now - timedelta(hours=i),
            )
            db_session.add(snapshot)
        db_session.commit()

        # Retrieve history
        service = RepositoryService(db_session)
        history = service.get_repository_star_history(
            repository_id=str(test_repository.id),
            hours_lookback=24,
        )

        assert history is not None
        assert history.repository_id == str(test_repository.id)
        assert history.count == 5
        assert len(history.snapshots) == 5
        # Verify ordering (oldest first)
        assert history.snapshots[0].num_stars == 140
        assert history.snapshots[-1].num_stars == 100

    def test_get_star_history_with_limit(self, db_session, test_repository):
        """Test retrieving star history with limit."""
        # Create snapshots
        now = datetime.now()
        for i in range(10):
            snapshot = DBRepositoryStarHistory(
                repository_id=test_repository.id,
                num_stars=100 + i,
                snapshot_at=now - timedelta(hours=i),
            )
            db_session.add(snapshot)
        db_session.commit()

        # Retrieve with limit
        service = RepositoryService(db_session)
        history = service.get_repository_star_history(
            repository_id=str(test_repository.id),
            limit=3,
        )

        assert history.count == 3
        assert len(history.snapshots) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
