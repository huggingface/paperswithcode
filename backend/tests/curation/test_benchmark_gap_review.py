"""Daily benchmark-gap review: eligibility, overseer decisions, creation, rollback."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.curation import (
    AddBenchmarkMutation,
    ApplyMutationRequest,
    ReviewBenchmarkGapsMutation,
)
from backend.models.database import (
    Base,
    BenchmarkCurationCandidate,
    BenchmarkCurationEvidence,
    Dataset,
    Evaluation,
    Metric,
    Paper,
    PaperCurationBootstrapBundle,
    PaperCurationJob,
    PaperCurationWorkflow,
    PaperXTrending,
    PaperCurationSchedulerState,
    PaperDataset,
    PaperTask,
    Task,
    TaskDataset,
    TaskDatasetMetric,
    TrendingModelCandidate,
)
from backend.services import benchmark_gap_review_service as review_module
from backend.services.benchmark_gap_review_service import BenchmarkGapReviewService
from backend.services.benchmark_gap_service import (
    BenchmarkGapService,
    benchmark_candidate_identity_key,
)
from backend.services.codex_add_evals_service import CodexPaperJobService
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
    _retryable_validation,
)
from jobs import curation_api


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Task.__table__,
            Dataset.__table__,
            Metric.__table__,
            TaskDataset.__table__,
            TaskDatasetMetric.__table__,
            PaperTask.__table__,
            PaperDataset.__table__,
            Evaluation.__table__,
            TrendingModelCandidate.__table__,
            PaperCurationWorkflow.__table__,
            PaperXTrending.__table__,
            PaperCurationBootstrapBundle.__table__,
            PaperCurationJob.__table__,
            BenchmarkCurationCandidate.__table__,
            BenchmarkCurationEvidence.__table__,
            PaperCurationSchedulerState.__table__,
        ],
    )
    with Session(engine) as session:
        yield session


def service(db) -> BenchmarkGapReviewService:
    return BenchmarkGapReviewService(db, get_settings(), CodexPaperJobService())


def add_paper(db, paper_id: int, arxiv_id: str, title: str | None = None) -> Paper:
    paper = Paper(
        id=paper_id,
        arxiv_id=arxiv_id,
        title=title or f"Paper {paper_id}",
        source="arxiv",
        is_latest_version=True,
    )
    db.add(paper)
    db.flush()
    return paper


def add_candidate(
    db,
    name: str,
    *,
    papers: int = 3,
    confidence: str = "high",
    status: str = "candidate",
    gap_type: str = "dataset_missing",
    task_ids: list[int] | None = None,
    **fields,
) -> BenchmarkCurationCandidate:
    fields.setdefault("identity_key", uuid.uuid4().hex)
    fields.setdefault("first_seen_at", datetime.now(UTC))
    candidate = BenchmarkCurationCandidate(
        id=uuid.uuid4(),
        canonical_name=name,
        gap_type=gap_type,
        task_ids=task_ids or [],
        aliases=fields.pop("aliases", []),
        status=status,
        distinct_paper_count=papers,
        confidence=confidence,
        last_seen_at=datetime.now(UTC),
        **fields,
    )
    db.add(candidate)
    db.flush()
    return candidate


def add_evidence(db, candidate, paper_ids, *, metric="Accuracy", task_id=None):
    job = PaperCurationJob(
        id=uuid.uuid4(),
        kind="add-evals",
        paper_id=paper_ids[0],
        requested_by="test",
        status="completed",
        trigger="hf-daily-cron",
    )
    db.add(job)
    db.flush()
    for paper_id in paper_ids:
        db.add(
            BenchmarkCurationEvidence(
                id=uuid.uuid4(),
                candidate_id=candidate.id,
                paper_id=paper_id,
                job_id=job.id,
                payload={
                    "protocol": {
                        "metrics": [{"name": metric, "direction": "higher_is_better"}],
                        "splits": ["test"],
                    },
                    "proposed_benchmark": {
                        "canonical_sources": [
                            {"kind": "paper", "url": "https://arxiv.org/abs/1406.5670"}
                        ],
                        "task_candidates": (
                            [{"task_id": task_id}] if task_id is not None else []
                        ),
                    },
                    "assessment": {"recommendation": "add_candidate"},
                },
            )
        )
    db.flush()
    return job


def test_eligibility_needs_three_papers_and_respects_review_state(db):
    now = datetime.now(UTC)
    strong = add_candidate(db, "Tiny-ImageNet", papers=16)
    add_candidate(db, "TwoPapers", papers=2)
    add_candidate(db, "LowConfidence", papers=5, confidence="low")
    add_candidate(
        db, "RejectedQuiet", papers=5, status="rejected", reviewed_paper_count=3
    )
    reopened = add_candidate(
        db, "RejectedReopened", papers=6, status="rejected", reviewed_paper_count=3
    )
    add_candidate(
        db, "DeferredFuture", papers=4, deferred_until=now + timedelta(days=1)
    )
    deferred_past = add_candidate(
        db, "DeferredPast", papers=4, deferred_until=now - timedelta(days=1)
    )
    add_candidate(db, "Approved", papers=9, status="approved")

    eligible = service(db).eligible_query(now).all()

    assert [item.id for item in eligible] == [strong.id, reopened.id, deferred_past.id]


def test_reconcile_starts_one_review_per_day(db):
    add_candidate(db, "ModelNet40", papers=9)
    review = service(db)

    assert review.reconcile(dispatch=False, dry_run=True)["review_due"] is True
    assert db.query(PaperCurationJob).count() == 0

    first = review.reconcile(dispatch=False)
    second = review.reconcile(dispatch=False)

    job = db.get(PaperCurationJob, uuid.UUID(first["review_job_id"]))
    assert job.kind == "review-benchmark-gaps"
    assert job.trigger == "benchmark-gap-cron"
    assert job.paper_id is None and job.benchmark_candidate_id is None
    assert second["review_due"] is False
    assert "review_job_id" not in second


def test_review_applies_each_decision_and_queues_creation(db):
    for paper_id in range(1, 8):
        add_paper(db, paper_id, f"2601.0000{paper_id}")
    keep = add_candidate(db, "Tiny-ImageNet", papers=4, task_ids=[1])
    add_evidence(db, keep, [1, 2, 3, 4])
    alias = add_candidate(db, "TinyImageNet", papers=3, task_ids=[2])
    add_evidence(db, alias, [3, 5, 6])
    private = add_candidate(db, "OurInternalSet", papers=3)
    thin = add_candidate(db, "MaybeBench", papers=3)

    result = service(db).apply_review(
        ReviewBenchmarkGapsMutation(
            summary="One approval, one alias, one private set, one unclear.",
            decisions=[
                {"candidate_id": keep.id, "decision": "approve", "reason": "Standard."},
                {
                    "candidate_id": alias.id,
                    "decision": "merge",
                    "merge_into_candidate_id": keep.id,
                    "reason": "Same dataset, other spelling.",
                },
                {
                    "candidate_id": private.id,
                    "decision": "reject",
                    "reason": "Private.",
                },
                {"candidate_id": thin.id, "decision": "defer", "reason": "Unclear."},
            ],
        )
    )

    assert result["decisions"] == {"approve": 1, "merge": 1, "reject": 1, "defer": 1}
    assert keep.status == "approved"
    assert keep.distinct_paper_count == 6
    assert keep.aliases == ["TinyImageNet"]
    assert keep.task_ids == [1, 2]
    assert alias.status == "merged" and alias.merged_into_id == keep.id
    assert private.status == "rejected" and private.reviewed_paper_count == 3
    assert thin.status == "candidate" and thin.deferred_until is not None
    [job_id] = result["creation_jobs_queued"]
    job = db.get(PaperCurationJob, uuid.UUID(job_id))
    assert (job.kind, job.benchmark_candidate_id) == ("add-benchmark", keep.id)


def test_review_rejects_ineligible_candidates_and_merge_chains(db):
    approved = add_candidate(db, "Approved", status="approved")
    with pytest.raises(ValueError, match="outside this review's batch"):
        service(db).apply_review(
            ReviewBenchmarkGapsMutation(
                summary="x",
                decisions=[
                    {"candidate_id": approved.id, "decision": "approve", "reason": "x"}
                ],
            )
        )
    a, b, c = (add_candidate(db, name) for name in ("A", "B", "C"))
    with pytest.raises(ValueError, match="itself merged"):
        service(db).apply_review(
            ReviewBenchmarkGapsMutation(
                summary="x",
                decisions=[
                    {
                        "candidate_id": a.id,
                        "decision": "merge",
                        "merge_into_candidate_id": b.id,
                        "reason": "x",
                    },
                    {
                        "candidate_id": b.id,
                        "decision": "merge",
                        "merge_into_candidate_id": c.id,
                        "reason": "x",
                    },
                    {"candidate_id": c.id, "decision": "approve", "reason": "x"},
                ],
            )
        )


def test_creation_jobs_respect_the_daily_cap(db, monkeypatch):
    monkeypatch.setattr(review_module, "DAILY_CREATION_CAP", 3)
    for index in range(5):
        add_candidate(db, f"Bench{index}", papers=10 - index, status="approved")
    review = service(db)

    assert len(review.queue_approved_creations()) == 3
    assert review.queue_approved_creations() == []


def creation_setup(db):
    for paper_id in range(1, 5):
        add_paper(db, paper_id, f"2601.0000{paper_id}")
    source = add_paper(db, 10, "1406.5670", "3D ShapeNets")
    parent = Task(id=263, name="3D understanding", slug="3d-understanding", level=0)
    db.add(parent)
    db.add(Metric(id=3, name="Overall Accuracy", direction="higher_is_better"))
    db.flush()
    candidate = add_candidate(db, "ModelNet40", papers=4, status="approved")
    add_evidence(db, candidate, [1, 2, 3, 4], metric="Overall Accuracy")
    job = service(db).job_service.enqueue_benchmark_job(
        db,
        kind="add-benchmark",
        benchmark_candidate_id=candidate.id,
        requested_by="test",
        settings=get_settings(),
        priority=20,
    )
    return candidate, job, source, parent


def create_mutation(**overrides) -> AddBenchmarkMutation:
    value = {
        "decision": "create",
        "reason": "ModelNet40 is the standard CAD classification benchmark.",
        "evidence_urls": ["https://arxiv.org/abs/1406.5670"],
        "new_dataset": {
            "name": "ModelNet40",
            "description": "12,311 CAD models in 40 categories.",
            "homepage": "https://modelnet.cs.princeton.edu/",
        },
        "source_paper": {"existing_paper_id": 10},
        "new_task": {
            "name": "3D Shape Classification",
            "description": "Classify 3D shapes.",
            "keywords": "shape classification, point cloud classification",
            "parent_task_id": 263,
        },
        "metrics": [{"existing_metric_id": 3}],
    }
    value.update(overrides)
    return AddBenchmarkMutation.model_validate(value)


def test_create_configures_leaderboard_and_requeues_evidence_papers(db):
    candidate, job, source, parent = creation_setup(db)

    result = service(db).apply_add_benchmark(job, create_mutation())

    dataset = db.query(Dataset).filter(Dataset.slug == "modelnet40").one()
    task = db.query(Task).filter(Task.slug == "3d-shape-classification").one()
    assert (task.parent_id, task.level) == (parent.id, 1)
    assert dataset.introducing_paper_id == source.id
    assert dataset.paper_url == "https://paperswithcode.co/paper/1406.5670"
    assert db.get(TaskDataset, (task.id, dataset.id)) is not None
    assert db.get(TaskDatasetMetric, (task.id, dataset.id, 3)) is not None
    assert db.get(PaperTask, (source.id, task.id)).source == "auto"
    assert candidate.status == "promoted"
    assert candidate.resolution["created"]["dataset"] is True
    assert candidate.resolution["primary_metric"] == "Overall Accuracy"
    rechecks = db.query(PaperCurationJob).filter(PaperCurationJob.kind == "add-evals")
    assert sorted(
        row.paper_id for row in rechecks if row.trigger == "benchmark-gap-cron"
    ) == [1, 2, 3, 4]
    assert len(result["recheck_job_ids"]) == 4


def test_create_refuses_duplicates_of_existing_catalog_rows(db):
    _candidate, job, _source, _parent = creation_setup(db)
    db.add(Dataset(id=77, name="ModelNet-40", slug="modelnet-40"))
    db.flush()

    with pytest.raises(ValueError, match="dataset 77.*map_existing"):
        service(db).apply_add_benchmark(job, create_mutation())


def _respelled_overall_accuracy(direction: str) -> list[dict]:
    return [
        {
            "new_metric": {
                "name": "overall accuracy",
                "full_name": "Overall accuracy",
                "direction": direction,
                "description": "Share of correct shapes.",
            }
        }
    ]


def test_create_reuses_an_existing_metric_proposed_under_a_new_spelling(db):
    candidate, job, _source, _parent = creation_setup(db)

    service(db).apply_add_benchmark(
        job,
        create_mutation(metrics=_respelled_overall_accuracy("higher_is_better")),
    )

    dataset = db.query(Dataset).filter(Dataset.slug == "modelnet40").one()
    task = db.query(Task).filter(Task.slug == "3d-shape-classification").one()
    assert db.query(Metric).count() == 1
    assert db.get(TaskDatasetMetric, (task.id, dataset.id, 3)) is not None
    assert candidate.resolution["metric_ids"] == [3]
    assert candidate.resolution["created"]["metric_ids"] == []


def test_create_refuses_a_respelled_metric_with_the_opposite_direction(db):
    _candidate, job, _source, _parent = creation_setup(db)

    with pytest.raises(ValueError, match="duplicates metric 3.*higher_is_better"):
        service(db).apply_add_benchmark(
            job,
            create_mutation(metrics=_respelled_overall_accuracy("lower_is_better")),
        )


def test_create_requires_source_paper_evidence(db):
    _candidate, job, _source, _parent = creation_setup(db)

    with pytest.raises(ValueError, match="canonical URL in evidence_urls"):
        service(db).apply_add_benchmark(
            job, create_mutation(evidence_urls=["https://modelnet.cs.princeton.edu/"])
        )


def test_arxiv_source_evidence_rejection_names_the_url_to_add(db):
    _candidate, job, _source, _parent = creation_setup(db)

    with pytest.raises(ValueError, match=r"add https://arxiv\.org/abs/2407\.04973$"):
        service(db).apply_add_benchmark(
            job,
            create_mutation(
                source_paper={"arxiv_id": "2407.04973"},
                evidence_urls=["https://arxiv.org/html/2605.25571"],
            ),
        )


def test_external_source_evidence_rejection_names_the_source_url(db):
    _candidate, job, _source, _parent = creation_setup(db)

    with pytest.raises(ValueError, match="add https://example.com/faust exactly"):
        service(db).apply_add_benchmark(
            job,
            create_mutation(
                source_paper={
                    "external_paper": {
                        "title": "FAUST",
                        "abstract": "Mesh registration benchmark.",
                        "source_url": "https://example.com/faust",
                        "date_published": "2014-06-24",
                    }
                },
                evidence_urls=["https://example.com/other"],
            ),
        )


def test_runner_preflight_requires_the_source_paper_in_evidence():
    def proposal(source, evidence):
        return {"add_benchmark": {"source_paper": source, "evidence_urls": evidence}}

    with pytest.raises(ValueError, match=r"add https://arxiv\.org/abs/1903\.12261$"):
        curation_api.check_benchmark_source_evidence(
            proposal({"arxiv_id": "1903.12261"}, ["https://arxiv.org/html/2609.00374"])
        )
    curation_api.check_benchmark_source_evidence(
        proposal({"arxiv_id": "1903.12261"}, ["https://arxiv.org/html/1903.12261v2"])
    )
    faust = "https://openaccess.thecvf.com/content_cvpr_2014/html/Bogo_FAUST.html"
    with pytest.raises(ValueError, match=f"add {re.escape(faust)}$"):
        curation_api.check_benchmark_source_evidence(
            proposal({"external_paper": {"source_url": faust}}, [])
        )
    curation_api.check_benchmark_source_evidence(
        proposal({"external_paper": {"source_url": faust}}, [faust + "/"])
    )
    curation_api.check_benchmark_source_evidence(
        proposal({"existing_paper_id": 10}, [])
    )
    curation_api.check_benchmark_source_evidence({"evaluations": []})


def test_map_existing_adds_links_without_rewriting_the_dataset(db):
    candidate, job, _source, parent = creation_setup(db)
    db.add(Dataset(id=77, name="ModelNet40", slug="modelnet40", description="Kept."))
    db.flush()

    service(db).apply_add_benchmark(
        job,
        AddBenchmarkMutation.model_validate(
            {
                "decision": "map_existing",
                "reason": "Dataset exists without a classification leaderboard.",
                "evidence_urls": ["https://arxiv.org/abs/1406.5670"],
                "existing_dataset_id": 77,
                "source_paper": {"existing_paper_id": 10},
                "existing_task_id": parent.id,
                "metrics": [{"existing_metric_id": 3}],
            }
        ),
    )

    dataset = db.get(Dataset, 77)
    assert dataset.description == "Kept."
    assert dataset.introducing_paper_id == 10
    assert db.get(TaskDatasetMetric, (parent.id, 77, 3)) is not None
    assert candidate.resolution["created"]["dataset"] is False
    assert candidate.resolution["created"]["introducing_paper_set"] is True


def test_reject_and_defer_need_no_catalog_rows(db):
    candidate, job, _source, _parent = creation_setup(db)
    defer = AddBenchmarkMutation(
        decision="defer", reason="Sources down.", evidence_urls=["https://x.org"]
    )

    assert service(db).apply_add_benchmark(job, defer)["status"] == "deferred"
    assert candidate.status == "approved" and candidate.deferred_until is not None
    with pytest.raises(ValidationError):
        AddBenchmarkMutation(
            decision="reject",
            reason="x",
            evidence_urls=["https://x.org"],
            existing_task_id=1,
        )


def test_failed_creation_backs_off_then_returns_to_review(db):
    candidate, job, _source, _parent = creation_setup(db)
    review = service(db)

    job.status = "failed"
    review.handle_terminal_job(job)
    assert candidate.status == "approved"
    first_retry = candidate.deferred_until

    second = review.job_service.enqueue_benchmark_job(
        db,
        kind="add-benchmark",
        benchmark_candidate_id=candidate.id,
        requested_by="test",
        settings=get_settings(),
        priority=20,
    )
    second.status = "failed"
    review.handle_terminal_job(second)

    assert first_retry is not None
    assert candidate.status == "candidate"
    assert candidate.deferred_until > first_retry


def test_rollback_removes_created_rows_unless_others_use_them(db):
    candidate, job, _source, _parent = creation_setup(db)
    review = service(db)
    review.apply_add_benchmark(
        job,
        create_mutation(
            metrics=[
                {
                    "new_metric": {
                        "name": "Mean Class Accuracy",
                        "full_name": "Mean class accuracy",
                        "direction": "higher_is_better",
                        "scale": "0-100",
                        "description": "Accuracy averaged over classes.",
                    }
                }
            ],
            metric_choice_reason="Test: rollback must remove the new metric.",
        ),
    )
    dataset = db.query(Dataset).filter(Dataset.slug == "modelnet40").one()
    task_id = candidate.resolution["task_id"]
    db.add(
        Evaluation(
            paper_id=4,
            task_id=task_id,
            dataset_id=dataset.id,
            metrics={"Mean Class Accuracy": 90.1},
        )
    )
    foreign = Evaluation(
        paper_id=10, task_id=task_id, dataset_id=dataset.id, metrics={"x": 1}
    )
    db.add(foreign)
    for row in db.query(PaperCurationJob).filter(PaperCurationJob.kind == "add-evals"):
        row.status = "completed"
    db.flush()

    with pytest.raises(ValueError, match=r"papers \[10\]"):
        review.rollback(candidate.id)
    db.delete(foreign)
    db.flush()

    result = review.rollback(candidate.id)

    assert result["evaluations"] == 1
    assert db.query(Dataset).filter(Dataset.slug == "modelnet40").first() is None
    assert db.query(Metric).filter(Metric.name == "Mean Class Accuracy").first() is None
    assert db.get(Task, task_id) is None
    assert candidate.status == "rejected"
    assert candidate.resolution["rolled_back_at"]


def test_callback_accepts_only_the_job_kind_payload():
    callback = CodexCurationCallbackService(SimpleNamespace())
    row = SimpleNamespace(
        kind="review-benchmark-gaps",
        status="running",
        submitted_at=None,
        applied_at=None,
    )
    review = {
        "summary": "x",
        "decisions": [
            {"candidate_id": str(uuid.uuid4()), "decision": "reject", "reason": "x"}
        ],
    }

    callback._validate_mutation(row, ApplyMutationRequest(review_benchmark_gaps=review))
    with pytest.raises(ValueError, match="accept only review_benchmark_gaps"):
        callback._validate_mutation(
            row,
            ApplyMutationRequest(
                review_benchmark_gaps=review, validation_evidence=[{"x": 1}]
            ),
        )
    with pytest.raises(ValueError, match="only for their jobs"):
        callback._validate_mutation(
            SimpleNamespace(**{**vars(row), "kind": "enrich-paper"}),
            ApplyMutationRequest(review_benchmark_gaps=review, enrich={}),
        )


def test_remote_schema_accepts_benchmark_gap_proposals():
    schema = json.loads(Path("jobs/schemas/curation_proposal.schema.json").read_text())
    empty = {
        "evaluations": [],
        "evaluation_removals": [],
        "benchmark_gaps": [],
        "validation_evidence": [],
    }
    review = {
        **empty,
        "review_benchmark_gaps": {
            "summary": "x",
            "decisions": [
                {
                    "candidate_id": str(uuid.uuid4()),
                    "decision": "merge",
                    "merge_into_candidate_id": str(uuid.uuid4()),
                    "reason": "Alias.",
                }
            ],
        },
    }
    create = {
        **empty,
        "add_benchmark": create_mutation().model_dump(mode="json", exclude_none=True),
    }

    validator = Draft202012Validator(schema)
    assert list(validator.iter_errors(review)) == []
    assert list(validator.iter_errors(create)) == []
    ApplyMutationRequest.model_validate(review)
    ApplyMutationRequest.model_validate(create)


def test_url_preflight_skips_paper_sources_for_benchmark_gap_jobs(tmp_path):
    context = tmp_path / "context.json"
    output = tmp_path / "out.json"
    context.write_text(json.dumps({"job": {"kind": "add-benchmark"}, "paper": {}}))

    subprocess.run(
        [sys.executable, "jobs/url_preflight.py", str(context), str(output)],
        check=True,
    )

    assert json.loads(output.read_text())["complete"] is True


def test_new_reports_join_the_candidate_a_duplicate_was_merged_into(db):
    add_paper(db, 1, "2601.00001")
    target = add_candidate(db, "Tiny-ImageNet", papers=0)
    gap = {
        "gap_type": "dataset_missing",
        "reasoning": "Blocked result.",
        "_normalized": {
            "name": "TinyImageNet",
            "canonical_url": None,
            "task_ids": [],
            "aliases": [],
        },
    }
    add_candidate(
        db,
        "TinyImageNet",
        papers=0,
        status="merged",
        merged_into_id=target.id,
        identity_key=benchmark_candidate_identity_key(gap),
    )
    job = PaperCurationJob(
        id=uuid.uuid4(),
        kind="add-evals",
        paper_id=1,
        requested_by="test",
        status="running",
        trigger="hf-daily-cron",
    )
    db.add(job)
    db.flush()

    [result] = BenchmarkGapService(db).persist(paper_id=1, job_id=job.id, gaps=[gap])

    assert result["candidate_id"] == str(target.id)
    assert target.distinct_paper_count == 1


def test_dispatch_keeps_a_two_job_lane_for_benchmark_gap_work(db, monkeypatch):
    settings = get_settings().model_copy(
        update={
            "codex_jobs_enabled": True,
            "codex_curation_scheduler_enabled": True,
            "codex_jobs_max_active": 10,
            "codex_jobs_max_scheduled_active": 10,
        }
    )
    db.add(PaperCurationSchedulerState(id=1, dispatch_enabled=True))
    jobs = CodexPaperJobService()
    gap_jobs = [
        jobs.enqueue_benchmark_job(
            db,
            kind="add-benchmark",
            benchmark_candidate_id=add_candidate(db, f"Bench{index}").id,
            requested_by="test",
            settings=settings,
            priority=20,
        )
        for index in range(3)
    ]
    paper = add_paper(db, 1, "2601.00001")
    paper.hf_daily_featured_on = datetime.now(UTC).date()
    workflow = PaperCurationWorkflow(
        id=uuid.uuid4(),
        paper_id=1,
        cohort_date=datetime.now(UTC).date(),
        policy_version="hf-daily-v1",
        status="queued",
    )
    daily = PaperCurationJob(
        id=uuid.uuid4(),
        kind="enrich-paper",
        paper_id=1,
        requested_by="hf-daily-cron",
        status="queued",
        trigger="hf-daily-cron",
        parent_workflow_id=workflow.id,
        priority=100,
    )
    db.add_all([workflow, daily])
    db.commit()
    monkeypatch.setattr(
        CodexPaperJobService,
        "_dispatch_row",
        lambda _self, _db, _settings, row: setattr(row, "status", "running"),
    )

    jobs.dispatch_next(db, settings)

    assert sorted(row.status for row in gap_jobs) == ["queued", "running", "running"]
    assert daily.status == "running"


@pytest.mark.parametrize(
    ("pause_condition", "dispatched"),
    [
        (None, True),
        ("terminal_failure_rate", True),
        ("apply_or_verification_failures", True),
        ("operator", False),
        ("daily_token_guardrail", False),
    ],
)
def test_dispatch_starts_the_overseer_past_the_lane_and_health_pauses(
    db, monkeypatch, pause_condition, dispatched
):
    settings = get_settings().model_copy(
        update={
            "codex_jobs_enabled": True,
            "codex_curation_scheduler_enabled": True,
            "codex_jobs_max_active": 4,
            "codex_jobs_max_scheduled_active": 3,
        }
    )
    db.add(
        PaperCurationSchedulerState(
            id=1,
            dispatch_enabled=pause_condition != "operator",
            paused_at=datetime.now(UTC) if pause_condition else None,
            pause_condition=pause_condition,
        )
    )
    jobs = CodexPaperJobService()
    for index in range(3):
        row = jobs.enqueue_benchmark_job(
            db,
            kind="add-benchmark",
            benchmark_candidate_id=add_candidate(db, f"Bench{index}").id,
            requested_by="test",
            settings=settings,
            priority=20,
        )
        # Two creation jobs fill the benchmark-gap lane.
        row.status = "running" if index < 2 else "queued"
    review = jobs.enqueue_benchmark_job(
        db,
        kind="review-benchmark-gaps",
        benchmark_candidate_id=None,
        requested_by="test",
        settings=settings,
        priority=10,
    )
    db.commit()
    monkeypatch.setattr(
        CodexPaperJobService,
        "_dispatch_row",
        lambda _self, _db, _settings, row: setattr(row, "status", "running"),
    )

    jobs.dispatch_next(db, settings)

    assert review.status == ("running" if dispatched else "queued")
    assert (
        db.query(PaperCurationJob)
        .filter_by(kind="add-benchmark", status="queued")
        .count()
        == 1
    )


def test_failure_backoff_counts_only_the_current_approval(db):
    candidate, job, _source, _parent = creation_setup(db)
    review = service(db)
    job.status = "failed"
    job.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    candidate.reviewed_at = datetime(2026, 2, 1, tzinfo=UTC)
    retry = review.job_service.enqueue_benchmark_job(
        db,
        kind="add-benchmark",
        benchmark_candidate_id=candidate.id,
        requested_by="test",
        settings=get_settings(),
        priority=20,
    )
    retry.created_at = datetime(2026, 2, 2, tzinfo=UTC)
    retry.status = "failed"
    db.flush()

    review.handle_terminal_job(retry)

    assert candidate.status == "approved"


def test_merging_into_a_promoted_candidate_rechecks_the_new_papers(db):
    for paper_id in range(1, 6):
        add_paper(db, paper_id, f"2601.0000{paper_id}")
    promoted = add_candidate(db, "ModelNet40", papers=3, status="promoted")
    add_evidence(db, promoted, [1, 2, 3])
    alias = add_candidate(db, "ModelNet-40", papers=3)
    add_evidence(db, alias, [3, 4, 5])

    service(db).apply_review(
        ReviewBenchmarkGapsMutation(
            summary="Alias of a configured benchmark.",
            decisions=[
                {
                    "candidate_id": alias.id,
                    "decision": "merge",
                    "merge_into_candidate_id": promoted.id,
                    "reason": "Same benchmark.",
                }
            ],
        )
    )

    rechecked = sorted(
        row.paper_id
        for row in db.query(PaperCurationJob).filter(
            PaperCurationJob.kind == "add-evals",
            PaperCurationJob.trigger == "benchmark-gap-cron",
        )
    )
    assert rechecked == [1, 2, 3, 4, 5]


def test_first_creation_job_of_an_approval_counts_toward_backoff(db):
    candidate = add_candidate(db, "ModelNet40", papers=4)
    review = service(db)
    [first_id] = review.apply_review(
        ReviewBenchmarkGapsMutation(
            summary="x",
            decisions=[
                {"candidate_id": candidate.id, "decision": "approve", "reason": "x"}
            ],
        )
    )["creation_jobs_queued"]
    db.flush()
    first = db.get(PaperCurationJob, uuid.UUID(first_id))
    first.status = "failed"
    review.handle_terminal_job(first)
    second = review.job_service.enqueue_benchmark_job(
        db,
        kind="add-benchmark",
        benchmark_candidate_id=candidate.id,
        requested_by="test",
        settings=get_settings(),
        priority=20,
    )
    second.status = "failed"

    review.handle_terminal_job(second)

    assert candidate.status == "candidate"


def test_review_decides_exactly_the_batch_it_was_served(db):
    first = add_candidate(db, "Tiny-ImageNet", papers=16)
    skipped = add_candidate(db, "ModelNet40", papers=9)
    gone = add_candidate(db, "LaterRejected", papers=4)
    review = service(db)
    job = review.job_service.enqueue_benchmark_job(
        db,
        kind="review-benchmark-gaps",
        benchmark_candidate_id=None,
        requested_by="test",
        settings=get_settings(),
        priority=10,
    )
    served = review.review_context(job)["candidates"]
    assert [item["id"] for item in served] == [
        str(first.id),
        str(skipped.id),
        str(gone.id),
    ]
    # After the snapshot: a new candidate outranks the batch, one leaves it.
    late = add_candidate(db, "BrandNewBench", papers=30)
    gone.status = "rejected"
    gone.reviewed_paper_count = 4
    assert review.review_context(job)["candidates"][0]["id"] == str(first.id)

    with pytest.raises(ValueError, match=f"1 have no decision: {skipped.id}"):
        review.apply_review(
            ReviewBenchmarkGapsMutation(
                summary="x",
                decisions=[
                    {"candidate_id": first.id, "decision": "approve", "reason": "x"}
                ],
            ),
            scope=job.review_scope,
        )
    with pytest.raises(ValueError, match="outside this review's batch"):
        review.apply_review(
            ReviewBenchmarkGapsMutation(
                summary="x",
                decisions=[
                    {"candidate_id": late.id, "decision": "approve", "reason": "x"}
                ],
            ),
            scope=job.review_scope,
        )

    result = review.apply_review(
        ReviewBenchmarkGapsMutation(
            summary="x",
            decisions=[
                {"candidate_id": first.id, "decision": "approve", "reason": "x"},
                {"candidate_id": skipped.id, "decision": "defer", "reason": "y"},
                {"candidate_id": gone.id, "decision": "approve", "reason": "x"},
            ],
        ),
        scope=job.review_scope,
    )

    assert result["decisions"] == {"approve": 1, "defer": 1}
    assert result["skipped_no_longer_eligible"] == [str(gone.id)]
    assert gone.status == "rejected"
    assert late.status == "candidate" and late.reviewed_at is None


def test_mistyped_review_candidate_is_a_retryable_proposal_error(db):
    candidate = add_candidate(db, "H2O", papers=5)
    review = service(db)
    job = review.job_service.enqueue_benchmark_job(
        db,
        kind="review-benchmark-gaps",
        benchmark_candidate_id=None,
        requested_by="test",
        settings=get_settings(),
        priority=10,
    )
    review.review_context(job)
    callback = CodexCurationCallbackService(db)
    typo = uuid.UUID(
        str(candidate.id)[:-1] + ("0" if str(candidate.id)[-1] != "0" else "1")
    )

    def body(candidate_id):
        return ApplyMutationRequest(
            review_benchmark_gaps={
                "summary": "x",
                "decisions": [
                    {
                        "candidate_id": str(candidate_id),
                        "decision": "reject",
                        "reason": "x",
                    }
                ],
            }
        )

    with pytest.raises(
        ValueError, match=f"outside this review's batch: {typo}"
    ) as error:
        callback._validate_scheduled_capability_boundary(job, body(typo))
    assert _retryable_validation(job, error.value)
    [(_, resource)] = callback._validate_scheduled_capability_boundary(
        job, body(candidate.id)
    )
    assert resource.exists


def test_skipped_merges_do_not_block_eligible_merges_into_them(db):
    keep = add_candidate(db, "Tiny-ImageNet", papers=5)
    middle = add_candidate(db, "TinyImageNet", papers=4)
    alias = add_candidate(db, "Tiny ImageNet 200", papers=3)
    scope = [str(keep.id), str(middle.id), str(alias.id)]
    # Deferred after the snapshot: no longer eligible, still a merge target.
    middle.deferred_until = datetime.now(UTC) + timedelta(days=1)

    result = service(db).apply_review(
        ReviewBenchmarkGapsMutation(
            summary="x",
            decisions=[
                {"candidate_id": keep.id, "decision": "approve", "reason": "x"},
                {
                    "candidate_id": middle.id,
                    "decision": "merge",
                    "merge_into_candidate_id": keep.id,
                    "reason": "x",
                },
                {
                    "candidate_id": alias.id,
                    "decision": "merge",
                    "merge_into_candidate_id": middle.id,
                    "reason": "x",
                },
            ],
        ),
        scope=scope,
    )

    assert result["decisions"] == {"approve": 1, "merge": 1}
    assert result["skipped_no_longer_eligible"] == [str(middle.id)]
    assert alias.merged_into_id == middle.id


def test_review_refuses_one_templated_reason_across_candidates(db):
    tiny = add_candidate(db, "Tiny-ImageNet", papers=16)
    pets = add_candidate(db, "OxfordPets", papers=8, aliases=["Oxford-IIIT Pet"])
    alias = add_candidate(db, "TinyImageNet", papers=3)
    other_alias = add_candidate(db, "Tiny ImageNet", papers=3)

    def decisions(tiny_reason, pets_reason):
        merge = "Same dataset as Tiny-ImageNet under another spelling."
        return ReviewBenchmarkGapsMutation(
            summary="x",
            decisions=[
                {"candidate_id": tiny.id, "decision": "approve", "reason": tiny_reason},
                {"candidate_id": pets.id, "decision": "approve", "reason": pets_reason},
                # Merges may share a reason.
                *(
                    {
                        "candidate_id": item.id,
                        "decision": "merge",
                        "merge_into_candidate_id": tiny.id,
                        "reason": merge,
                    }
                    for item in (alias, other_alias)
                ),
            ],
        )

    templated = decisions(
        "Tiny-ImageNet is a standard public benchmark reported by 16 papers.",
        "Oxford-IIIT Pet is a standard public benchmark reported by 8 papers.",
    )
    with pytest.raises(ValueError, match="2 decisions reuse 1 templates") as error:
        service(db).apply_review(templated)
    # The error names every clashing candidate so one retry can fix them all.
    assert f"{tiny.id}, {pets.id}" in str(error.value)

    # The runner's apply helper refuses the same proposal before the server.
    context = {"review": {"candidates": service(db)._summaries([tiny, pets])}}
    with pytest.raises(ValueError, match="no apply attempted") as error:
        curation_api.check_review_reasons(
            {"review_benchmark_gaps": templated.model_dump(mode="json")}, context
        )
    assert f"{tiny.id}, {pets.id}" in str(error.value)

    result = service(db).apply_review(
        decisions(
            "Tiny-ImageNet: 200-class ImageNet subset; 15 of 16 papers report "
            "top-1 Accuracy under Image Classification.",
            "OxfordPets already exists as a dataset without a classification "
            "leaderboard; 7 papers report Accuracy.",
        )
    )

    assert result["decisions"] == {"approve": 2, "merge": 2}


def votes_setup(db):
    for paper_id in range(1, 6):
        add_paper(db, paper_id, f"2601.0000{paper_id}")
    add_paper(db, 10, "1406.5670", "DomainNet")
    db.add_all(
        [
            Task(id=1, name="Image Classification", slug="image-classification"),
            Task(id=7, name="Embedding models", slug="embedding-models"),
            Task(id=23, name="Retrieval", slug="retrieval", parent_id=7),
            Task(
                id=50, name="Domain Adaptation", slug="domain-adaptation", parent_id=1
            ),
            Metric(id=3, name="Accuracy", direction="higher_is_better"),
            Metric(id=4, name="mAP@200", direction="higher_is_better"),
        ]
    )
    db.flush()
    # The first report proposed Retrieval, so the candidate's task_ids do too.
    candidate = add_candidate(
        db, "DomainNet", papers=5, status="approved", task_ids=[23]
    )
    add_evidence(db, candidate, [1], metric="mAP@200", task_id=23)
    add_evidence(db, candidate, [2, 3, 4, 5], metric="Accuracy", task_id=1)
    # A paper reported twice still counts once.
    add_evidence(db, candidate, [3, 2], metric="Accuracy", task_id=1)
    job = service(db).job_service.enqueue_benchmark_job(
        db,
        kind="add-benchmark",
        benchmark_candidate_id=candidate.id,
        requested_by="test",
        settings=get_settings(),
        priority=20,
    )
    return candidate, job


def domainnet_mutation(**overrides) -> AddBenchmarkMutation:
    return create_mutation(
        **{
            "reason": "DomainNet is the standard domain adaptation benchmark.",
            "new_dataset": {"name": "DomainNet", "description": "345 classes."},
            "new_task": None,
            "existing_task_id": 1,
            "metrics": [{"existing_metric_id": 3}],
            **overrides,
        }
    )


def test_contexts_count_reporting_papers_per_task_and_metric(db):
    candidate, job = votes_setup(db)

    context = service(db).creation_context(job)

    summary = context["candidate"]
    assert [(item["id"], item["papers"]) for item in summary["reported_tasks"]] == [
        (1, 4),
        (23, 1),
    ]
    assert [(item["name"], item["papers"]) for item in summary["reported_metrics"]] == [
        ("Accuracy", 4),
        ("mAP@200", 1),
    ]
    assert context["evidence_consensus"] == {
        "task_ids": [1],
        "primary_metrics": ["Accuracy"],
    }
    assert {item["id"] for item in context["related_tasks"]} == {1, 23, 50}


def test_creation_holds_task_and_metric_to_the_reporting_papers(db):
    candidate, job = votes_setup(db)
    review = service(db)

    with pytest.raises(ValueError, match=r"Image Classification \(1\): 4 papers"):
        review.apply_add_benchmark(job, domainnet_mutation(existing_task_id=23))
    with pytest.raises(ValueError, match="Accuracy: 4 papers"):
        review.apply_add_benchmark(
            job, domainnet_mutation(metrics=[{"existing_metric_id": 4}])
        )
    with pytest.raises(ValueError, match="Accuracy: 4 papers"):
        review.apply_add_benchmark(
            job,
            domainnet_mutation(
                metrics=[
                    {
                        "new_metric": {
                            "name": "Prec@200",
                            "full_name": "Precision at 200",
                            "direction": "higher_is_better",
                            "description": "Retrieval precision.",
                        }
                    }
                ]
            ),
        )

    # A descendant of a leading task fits, as does an explained choice.
    result = review.apply_add_benchmark(
        job,
        domainnet_mutation(
            existing_task_id=50,
            metrics=[{"existing_metric_id": 3}, {"existing_metric_id": 4}],
        ),
    )

    assert result["task_id"] == 50 and result["primary_metric"] == "Accuracy"
    assert candidate.resolution["task_choice_reason"] is None


def test_creation_accepts_an_explained_task_or_metric_choice(db):
    candidate, job = votes_setup(db)

    service(db).apply_add_benchmark(
        job,
        domainnet_mutation(
            existing_task_id=23,
            metrics=[{"existing_metric_id": 4}],
            task_choice_reason="Explained task.",
            metric_choice_reason="Explained metric.",
        ),
    )

    assert candidate.status == "promoted"
    assert candidate.resolution["task_choice_reason"] == "Explained task."
    assert candidate.resolution["metric_choice_reason"] == "Explained metric."


def test_creation_without_task_votes_falls_back_to_candidate_tasks(db):
    candidate, job, _source, parent = creation_setup(db)
    candidate.task_ids = [999]
    db.add(Task(id=999, name="Point Clouds", slug="point-clouds"))
    db.flush()

    with pytest.raises(ValueError, match=r"Point Clouds \(999\)"):
        service(db).apply_add_benchmark(job, create_mutation())
