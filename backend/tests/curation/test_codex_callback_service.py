from __future__ import annotations

import re
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.curation import ApplyMutationRequest, EnrichPaperMutation
from backend.models.evaluations import EvaluationCreateRequest
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
    CodexCurationEvaluationPaperMismatchError,
    CodexCurationEvaluationsNotAllowedError,
    CodexCurationMutationClosedError,
    CodexCurationPaperNotFoundError,
    _requires_scheduled_dispatch_pause,
)


def _scheduled_policy(service, row, body):
    """Run the scheduled policy the way the worker reaches it: after pre-apply.

    jobs/curation_api.py stores the exact proposal in the pre-apply trace and
    then applies it, so the job row holds the same proposal as the request.
    """

    row.proposal = body.model_dump(mode="json")
    return service._validate_scheduled_policy(row, body)


def _evaluation(
    *,
    paper_id: int = 42,
    model_name: str,
    source_url: str = "https://arxiv.org/abs/2601.00001",
) -> EvaluationCreateRequest:
    return EvaluationCreateRequest(
        paper_id=paper_id,
        task_id=19,
        dataset_id=340,
        model_name=model_name,
        metrics={"GenEval Score": 0.9},
        best_metric="GenEval Score",
        source_url=source_url,
    )


def _score_evidence(**overrides):
    return {
        "task_id": 19,
        "dataset_id": 340,
        "metric": "GenEval Score",
        "source_value": 90,
        "source_scale": "0-100",
        "source_url": "https://arxiv.org/html/2601.00001",
        "table_reference": "Table 1, Useful Model, overall",
        **overrides,
    }


class _ResultQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *_args):
        return self

    def one_or_none(self):
        return self.result


class _ListQuery:
    def __init__(self, rows):
        self.rows = rows

    def join(self, *_args):
        return self

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def limit(self, _limit):
        return self

    def all(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)


class _MutationDatabase:
    def __init__(self, existing=()):
        self.existing = iter(existing)
        self.commits = 0
        self.rollbacks = 0
        self.refreshes = []
        self.queries = 0
        self.pending = []

    def refresh(self, row, *, with_for_update):
        self.refreshes.append((row, with_for_update))

    def query(self, _model):
        self.queries += 1
        return _ResultQuery(next(self.existing))

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1
        self.pending.clear()


def _service(db, evaluation_service) -> CodexCurationCallbackService:
    return CodexCurationCallbackService(
        db,
        evaluation_service=evaluation_service,
        association_service=SimpleNamespace(),
    )


def _stored_evaluation(**overrides):
    values = {
        "id": 77,
        "paper_id": 42,
        "task_id": 19,
        "dataset_id": 340,
        "model_name": "Existing Model",
        "harness": None,
        "methodology": "Older evidence.",
        "metrics": {"GenEval Score": 0.8},
        "uses_additional_data": False,
        "is_open": True,
        "best_rank": None,
        "best_metric": "GenEval Score",
        "evaluated_on": None,
        "source_url": "https://arxiv.org/abs/2601.00001",
        "external_source_url": None,
        "num_parameters": None,
        "hf_model_url": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_context_projection_preserves_the_worker_payload():
    task = SimpleNamespace(id=19, name="Image generation", slug="image-generation")
    method = SimpleNamespace(id=59, name="Diffusion", slug="diffusion")
    page = SimpleNamespace(url="https://example.com/project", is_official=True)
    repository = SimpleNamespace(url="https://github.com/example/model")
    paper = SimpleNamespace(
        id=42,
        title="A useful model",
        abstract="Abstract",
        arxiv_id="2601.00001",
        source="arxiv",
        source_url=None,
        date_published=datetime(2026, 1, 1, tzinfo=UTC),
        urls_extracted=True,
        thumbnail_url="/thumbnails/42.jpg",
        tasks=[task],
        methods=[method],
        project_pages=[page],
        evaluations=[_stored_evaluation()],
    )

    class Database:
        def get(self, *_args):
            return paper

        def query(self, *_args):
            return _ListQuery([(repository, True)])

    class SerializedJob:
        def model_dump(self, *, mode):
            assert mode == "json"
            return {"id": "job-42", "kind": "enrich-paper"}

    class JobService:
        def serialize(self, row, settings):
            assert row.paper_id == 42
            assert settings.codex_jobs_enabled
            return SerializedJob()

    service = CodexCurationCallbackService(
        Database(),
        job_service=JobService(),
        evaluation_service=SimpleNamespace(),
        association_service=SimpleNamespace(),
    )

    result = service.context(
        SimpleNamespace(paper_id=42),
        get_settings().model_copy(update={"codex_jobs_enabled": True}),
    )

    assert result["job"] == {"id": "job-42", "kind": "enrich-paper"}
    assert result["paper"] == {
        "id": 42,
        "title": "A useful model",
        "abstract": "Abstract",
        "arxiv_id": "2601.00001",
        "source": "arxiv",
        "source_url": None,
        "markdown_expected": False,
        "date_published": datetime(2026, 1, 1, tzinfo=UTC),
        "urls_extracted": True,
        "thumbnail_url": "/thumbnails/42.jpg",
        "tasks": [
            {
                "id": 19,
                "name": "Image generation",
                "slug": "image-generation",
                "source": "unknown",
            }
        ],
        "methods": [
            {"id": 59, "name": "Diffusion", "slug": "diffusion", "evidence": []}
        ],
        "repositories": [
            {
                "url": "https://github.com/example/model",
                "is_official": True,
                "source": None,
            }
        ],
        "project_pages": [
            {"url": "https://example.com/project", "is_official": True, "source": None}
        ],
        "hf_models": [],
        "hf_datasets": [],
        "hf_spaces": [],
        "organizations": [],
        "method_exclusions": [],
        "evaluations": [vars(_stored_evaluation())],
    }


def test_context_reports_a_missing_scoped_paper():
    class Database:
        def get(self, *_args):
            return None

    service = CodexCurationCallbackService(
        Database(),
        evaluation_service=SimpleNamespace(),
        association_service=SimpleNamespace(),
    )

    with pytest.raises(CodexCurationPaperNotFoundError, match="Paper not found"):
        service.context(SimpleNamespace(paper_id=42), get_settings())


def test_leaderboard_inventory_preserves_match_and_recent_score_evidence():
    dataset = SimpleNamespace(
        id=340,
        name="GenEval",
        slug="geneval",
        full_name="GenEval benchmark",
        split_name=None,
        variant_type=None,
        short_description="Image-generation alignment.",
        description="Long description",
        warning=None,
    )
    task = SimpleNamespace(id=19, name="Image generation", slug="image-generation")
    task_dataset = SimpleNamespace(supports_harness=False)
    metric = SimpleNamespace(
        id=101,
        name="GenEval Score",
        direction="higher_is_better",
        scale="0-1",
    )
    examples = [
        SimpleNamespace(model_name="Useful Model", metrics={"GenEval Score": 0.9}),
        SimpleNamespace(model_name="Missing Metric", metrics={"Other": 1.0}),
    ]

    class Database:
        def query(self, *models):
            if len(models) == 4:
                return _ListQuery([(dataset, task, task_dataset, metric)])
            return _ListQuery(examples)

    service = CodexCurationCallbackService(
        Database(),
        evaluation_service=SimpleNamespace(),
        association_service=SimpleNamespace(),
    )

    assert service.leaderboard_inventory("Gen-Eval") == [
        {
            "dataset": {
                "id": 340,
                "name": "GenEval",
                "slug": "geneval",
                "full_name": "GenEval benchmark",
                "split_name": None,
                "variant_type": None,
                "description": "Image-generation alignment.",
                "warning": None,
            },
            "task": {
                "id": 19,
                "name": "Image generation",
                "slug": "image-generation",
            },
            "match_quality": "exact",
            "supports_harness": False,
            "metrics": [
                {
                    "id": 101,
                    "name": "GenEval Score",
                    "direction": "higher_is_better",
                    "scale": "0-1",
                    "recent_values": [{"model_name": "Useful Model", "value": 0.9}],
                }
            ],
        }
    ]


def test_leaderboard_inventory_orders_exact_matches_before_close_matches():
    exact = SimpleNamespace(
        id=1,
        name="GenEval",
        slug="geneval",
        full_name=None,
        split_name=None,
        variant_type=None,
        short_description=None,
        description=None,
        warning=None,
    )
    close = SimpleNamespace(
        id=2,
        name="GenEval Extended",
        slug="geneval-extended",
        full_name=None,
        split_name=None,
        variant_type=None,
        short_description=None,
        description=None,
        warning=None,
    )
    task = SimpleNamespace(id=19, name="Image generation", slug="image-generation")
    link = SimpleNamespace(supports_harness=False)
    metric = SimpleNamespace(
        id=101, name="Score", direction="higher_is_better", scale=None
    )

    class Database:
        def query(self, *models):
            if len(models) == 4:
                return _ListQuery(
                    [(close, task, link, metric), (exact, task, link, metric)]
                )
            return _ListQuery([])

    service = CodexCurationCallbackService(
        Database(),
        evaluation_service=SimpleNamespace(),
        association_service=SimpleNamespace(),
    )

    inventory = service.leaderboard_inventory("GenEval")

    assert [item["dataset"]["id"] for item in inventory] == [1, 2]
    assert [item["match_quality"] for item in inventory] == ["exact", "close"]


def test_mixed_evaluation_apply_uses_one_final_transaction():
    database = _MutationDatabase(existing=[None, _stored_evaluation()])
    calls = []

    class Evaluations:
        def find_leaderboard_duplicate(self, **_identity):
            return None

        def create_evaluation(self, **values):
            calls.append(("create", values))

        def update_evaluation(self, evaluation_id, **values):
            calls.append(("update", evaluation_id, values))

    row = SimpleNamespace(
        kind="add-evals",
        status="running",
        submitted_at=None,
        applied_at=None,
        paper_id=42,
    )

    result = _service(database, Evaluations()).apply(
        row,
        ApplyMutationRequest(
            evaluations=[
                _evaluation(model_name="New Model"),
                _evaluation(model_name="Existing Model"),
            ]
        ),
    )

    assert result == {
        "status": "applied",
        "evaluations_created": 1,
        "evaluations_updated": 1,
    }
    assert database.refreshes == [(row, True)]
    assert database.commits == 1
    assert database.rollbacks == 0
    assert calls[0][0] == "create"
    assert calls[0][1]["commit"] is False
    assert calls[1][0:2] == ("update", 77)
    assert calls[1][2]["commit"] is False
    assert calls[1][2]["harness_set"] is True
    assert calls[1][2]["source_url_set"] is True
    assert calls[1][2]["num_parameters_set"] is True
    assert calls[1][2]["hf_model_url_set"] is True
    assert row.submitted_at == row.applied_at


def test_exact_existing_evaluation_is_a_true_no_op():
    existing = _stored_evaluation(
        methodology=None,
        metrics={"GenEval Score": 0.9},
    )
    database = _MutationDatabase(existing=[existing])

    class Evaluations:
        def find_leaderboard_duplicate(self, **_identity):
            return None

        def create_evaluation(self, **_values):
            raise AssertionError("exact duplicate must not be created")

        def update_evaluation(self, *_args, **_values):
            raise AssertionError("exact duplicate must not be rewritten")

    row = SimpleNamespace(
        kind="add-evals",
        status="running",
        submitted_at=None,
        applied_at=None,
        paper_id=42,
    )

    result = _service(database, Evaluations()).apply(
        row,
        ApplyMutationRequest(evaluations=[_evaluation(model_name="Existing Model")]),
    )

    assert result == {
        "status": "no_changes",
        "evaluations_created": 0,
        "evaluations_updated": 0,
    }
    assert row.applied_at is None


def test_evaluation_diff_ignores_omitted_server_managed_rank_and_date():
    existing = _stored_evaluation(
        methodology="Retained methodology",
        best_rank=3,
        evaluated_on=datetime(2026, 8, 1, tzinfo=UTC).date(),
        metrics={"GenEval Score": 0.9},
    )
    proposal = _evaluation(model_name="Existing Model")

    assert CodexCurationCallbackService._evaluation_changes(existing, proposal) == {}


def test_evaluation_diff_ignores_omitted_external_source_copied_from_source_url():
    existing = _stored_evaluation(
        methodology=None,
        metrics={"GenEval Score": 0.9},
        source_url="https://arxiv.org/abs/2601.00001",
        external_source_url="https://arxiv.org/abs/2601.00001",
    )
    proposal = _evaluation(model_name="Existing Model")

    assert CodexCurationCallbackService._evaluation_changes(existing, proposal) == {}


def test_late_evaluation_failure_rolls_back_the_whole_apply():
    database = _MutationDatabase(existing=[None, None])

    class Evaluations:
        def find_leaderboard_duplicate(self, **_identity):
            return None

        def create_evaluation(self, **values):
            assert values["commit"] is False
            database.pending.append(values["model_name"])
            if len(database.pending) == 2:
                raise ValueError("second result is invalid")

    row = SimpleNamespace(
        kind="add-evals", status="running", applied_at=None, paper_id=42
    )

    with pytest.raises(ValueError, match="second result is invalid"):
        _service(database, Evaluations()).apply(
            row,
            ApplyMutationRequest(
                evaluations=[
                    _evaluation(model_name="First Model"),
                    _evaluation(model_name="Invalid Model"),
                ]
            ),
        )

    assert database.pending == []
    assert database.commits == 0
    assert database.rollbacks == 1
    assert not hasattr(row, "submitted_at")
    assert row.applied_at is None


@pytest.mark.parametrize("trigger", ["hf-trending-cron", "admin"])
@pytest.mark.parametrize(
    "error_type", [ValueError, CodexCurationEvaluationsNotAllowedError]
)
def test_validation_failure_keeps_job_open_for_one_corrected_apply(error_type, trigger):
    row = SimpleNamespace(
        id=42,
        kind="add-evals",
        status="running",
        trigger=trigger,
        submitted_at=None,
        applied_at=None,
        paper_id=42,
    )

    class Database(_MutationDatabase):
        def get(self, model, _key):
            return row if model is type(row) else None

    database = Database()
    service = _service(database, SimpleNamespace())
    service._validate_scheduled_policy = lambda *_args: (_ for _ in ()).throw(
        error_type("Evaluation metric value 91.9 is outside configured scale 0-1")
    )

    with pytest.raises(ValueError, match="outside configured scale"):
        service._apply_authorized(row, ApplyMutationRequest(evaluations=[]))

    assert row.submitted_at is None
    assert row.applied_at is None
    assert row.validation_summary["status"] == "rejected"
    assert "outside configured scale" in row.validation_summary["error"]
    assert database.rollbacks == 1
    assert database.commits == 1

    with pytest.raises(ValueError, match="outside configured scale"):
        service._apply_authorized(row, ApplyMutationRequest(evaluations=[]))

    assert row.submitted_at is not None
    assert row.validation_summary["retryable"] is False
    assert database.rollbacks == 2
    assert database.commits == 2

    with pytest.raises(
        CodexCurationMutationClosedError, match="may no longer apply mutations"
    ):
        service._apply_authorized(row, ApplyMutationRequest(evaluations=[]))

    assert database.rollbacks == 3
    assert database.commits == 2


def test_rejected_scheduled_benchmark_gap_keeps_job_open_for_correction(
    monkeypatch,
):
    row = SimpleNamespace(
        id=42,
        kind="add-evals",
        status="running",
        trigger="hf-trending-cron",
        submitted_at=None,
        applied_at=None,
        paper_id=42,
        url_candidates={"source_documents": []},
    )

    class Database(_MutationDatabase):
        def get(self, model, _key):
            return row if model is type(row) else SimpleNamespace(id=42)

    class Gaps:
        def __init__(self, _db):
            pass

        def validate(self, _gaps, **_kwargs):
            return [], [{"index": 0, "error": "evidence source URL is not scoped"}]

    monkeypatch.setattr(
        "backend.services.codex_curation_callback_service.BenchmarkGapService", Gaps
    )
    database = Database()
    service = _service(database, SimpleNamespace())

    with pytest.raises(ValueError, match="benchmark gap"):
        service._apply_authorized(
            row,
            ApplyMutationRequest(
                evaluations=[],
                benchmark_gaps=[{"reasoning": "A proposed gap"}],
            ),
        )

    assert row.submitted_at is None
    assert row.validation_summary["retryable"] is True
    assert row.validation_summary["benchmark_gaps_rejected"] == [
        {"index": 0, "error": "evidence source URL is not scoped"}
    ]


def test_all_evaluation_paper_ids_are_checked_before_the_first_write():
    database = _MutationDatabase()

    class Evaluations:
        def find_leaderboard_duplicate(self, **_identity):
            return None

        def create_evaluation(self, **_values):
            raise AssertionError("prevalidation must happen before mutation")

    row = SimpleNamespace(
        kind="add-evals", status="running", applied_at=None, paper_id=42
    )

    with pytest.raises(
        CodexCurationEvaluationPaperMismatchError,
        match="Evaluation paper does not match job",
    ):
        _service(database, Evaluations()).apply(
            row,
            ApplyMutationRequest(
                evaluations=[
                    _evaluation(model_name="Scoped Model"),
                    _evaluation(paper_id=99, model_name="Wrong Paper"),
                ]
            ),
        )

    assert database.queries == 0
    assert database.commits == 0
    assert database.rollbacks == 1
    assert not hasattr(row, "submitted_at")


def test_late_scheduled_callback_does_not_pause_dispatch_or_overwrite_audit():
    from backend.models.database import PaperCurationSchedulerState

    state = SimpleNamespace(paused_at=None, pause_condition=None, pause_reason=None)
    row = SimpleNamespace(
        id=42,
        kind="add-evals",
        status="completed",
        submitted_at=datetime.now(UTC),
        applied_at=None,
        paper_id=42,
        trigger="hf-daily-cron",
        validation_summary={"post_write_verification": "passed"},
    )

    class Database(_MutationDatabase):
        def get(self, model, _key):
            return state if model is PaperCurationSchedulerState else row

    database = Database()
    with pytest.raises(
        CodexCurationMutationClosedError,
        match="This job may no longer apply mutations",
    ):
        _service(database, SimpleNamespace())._apply_authorized(
            row, ApplyMutationRequest(evaluations=[])
        )

    assert state.paused_at is None
    assert state.pause_condition is None
    assert row.validation_summary == {"post_write_verification": "passed"}
    assert database.commits == 0


@pytest.mark.parametrize(
    "error",
    [
        ValueError("rejected proposal"),
        CodexCurationMutationClosedError("late callback"),
        CodexCurationPaperNotFoundError("deleted paper"),
        RuntimeError("unexpected callback failure"),
    ],
)
def test_callback_apply_failures_do_not_pause_scheduled_dispatch(error):
    assert _requires_scheduled_dispatch_pause(error) is False


def test_scheduled_enrichment_can_leave_project_pages_unchanged():
    class Database:
        def get(self, _model, _key):
            return SimpleNamespace(id=42)

        def query(self, _model):
            return _ListQuery([])

    result = _scheduled_policy(
        _service(Database(), SimpleNamespace()),
        SimpleNamespace(
            kind="enrich-paper",
            paper_id=42,
            trigger="hf-daily-cron",
            trace_status="disabled",
            url_candidates={"complete": True},
        ),
        ApplyMutationRequest(
            enrich=EnrichPaperMutation(task_ids=[], method_ids=[], urls_extracted=True)
        ),
    )

    assert result["removed_hf_api_project_pages"] == []


@pytest.mark.parametrize(
    "preapply_proposal",
    [
        # The worker previewed adding a task but applies something else.
        {"enrich": {"task_ids": [7], "method_ids": [], "urls_extracted": True}},
        # No usable pre-apply proposal was recorded.
        {},
        None,
    ],
)
def test_scheduled_apply_must_match_its_preapply_proposal(preapply_proposal):
    class Database:
        def get(self, _model, _key):
            return SimpleNamespace(id=42)

        def query(self, _model):
            return _ListQuery([])

    row = SimpleNamespace(
        kind="enrich-paper",
        paper_id=42,
        trigger="hf-daily-cron",
        trace_status="preapply_stored",
        url_candidates={"complete": True},
        proposal=preapply_proposal,
    )
    body = ApplyMutationRequest(
        enrich=EnrichPaperMutation(task_ids=[], method_ids=[], urls_extracted=True)
    )

    with pytest.raises(
        CodexCurationMutationClosedError, match="does not match its pre-apply"
    ):
        _service(Database(), SimpleNamespace())._validate_scheduled_policy(row, body)


def test_scheduled_enrichment_allows_evidenced_hf_project_page_removal():
    from backend.models.database import Paper

    page = SimpleNamespace(url="https://example.github.io/team/", source="hf_api")
    paper = SimpleNamespace(project_pages=[page])

    class Query:
        def filter(self, *_args):
            return self

        def count(self):
            return 0

        def all(self):
            return []

        def __iter__(self):
            return iter(())

    class Database:
        def get(self, model, _key):
            return paper if model is Paper else None

        def query(self, _model):
            return Query()

    result = _scheduled_policy(
        _service(Database(), SimpleNamespace()),
        SimpleNamespace(
            kind="enrich-paper",
            paper_id=42,
            trigger="hf-daily-cron",
            trace_status="disabled",
            url_candidates={"complete": True},
        ),
        ApplyMutationRequest(
            enrich=EnrichPaperMutation(
                task_ids=[],
                method_ids=[],
                project_pages=[],
                urls_extracted=True,
                project_page_removal_reasons={
                    "https://example.github.io/team/": (
                        "Checked page is a generic lab team page, not a paper project."
                    )
                },
            )
        ),
    )

    assert result["removed_hf_api_project_pages"] == ["https://example.github.io/team/"]


def test_scheduled_enrichment_rejects_project_page_removal_without_reason():
    from backend.models.database import Paper

    paper = SimpleNamespace(
        project_pages=[
            SimpleNamespace(url="https://example.github.io/team/", source="hf_api")
        ]
    )

    class Query:
        def filter(self, *_args):
            return self

        def count(self):
            return 0

        def all(self):
            return []

        def __iter__(self):
            return iter(())

    class Database:
        def get(self, model, _key):
            return paper if model is Paper else None

        def query(self, _model):
            return Query()

    with pytest.raises(ValueError, match="project-page removal requires a reason"):
        _scheduled_policy(
            _service(Database(), SimpleNamespace()),
            SimpleNamespace(
                kind="enrich-paper",
                paper_id=42,
                trigger="hf-daily-cron",
                trace_status="disabled",
                url_candidates={"complete": True},
            ),
            ApplyMutationRequest(
                enrich=EnrichPaperMutation(
                    task_ids=[],
                    method_ids=[],
                    project_pages=[],
                    urls_extracted=True,
                )
            ),
        )


@pytest.mark.parametrize(
    "scale,source_value,source_scale,stored,include_evidence,error",
    [
        ("0-1", 90, "0-100", 0.9, True, None),
        ("0-100", 86.89, "0-100", 0.8689, True, "Score scale mismatch"),
        ("0-100", 98.40, "0-100", 0.984, True, "Score scale mismatch"),
        ("0-100", 86.89, "0-100", 86.89, True, None),
        ("0-100", 0.8689, "0-1", 86.89, True, None),
        ("0-100", 0.4, "0-100", 0.4, True, None),
        ("0-100", 86.89, "0-100", 0.8689, False, "score_evidence"),
        ("0-1", 90, "0-100", 90, True, "outside configured scale"),
    ],
)
def test_scheduled_evaluation_accepts_configured_metric_names(
    scale, source_value, source_scale, stored, include_evidence, error
):
    from backend.models.database import Evaluation, Metric, Paper, TaskDataset

    paper = SimpleNamespace(
        id=42,
        source="arxiv",
        source_url=None,
        arxiv_id="2601.00001",
    )
    leaderboard = SimpleNamespace(supports_harness=False)
    metric = SimpleNamespace(name="GenEval Score", scale=scale)

    class Query:
        def __init__(self, model):
            self.model = model

        def join(self, *_args):
            return self

        def filter(self, *_args):
            return self

        def one_or_none(self):
            return leaderboard if self.model is TaskDataset else None

        def all(self):
            if self.model is Metric:
                return [metric]
            if self.model is Evaluation:
                return []
            return []

    class Database:
        def get(self, model, _key):
            return paper if model is Paper else None

        def query(self, model):
            return Query(model)

    row = SimpleNamespace(
        kind="add-evals",
        paper_id=42,
        trigger="hf-daily-cron",
        trace_status="preapply_stored",
    )
    evaluation = _evaluation(model_name="Useful Model")
    evaluation.metrics = {"GenEval Score": stored}
    body = ApplyMutationRequest(
        evaluations=[evaluation],
        evaluation_removals=[],
        benchmark_gaps=[],
        validation_evidence=[],
        score_evidence=[
            _score_evidence(source_value=source_value, source_scale=source_scale)
        ]
        if include_evidence
        else [],
    )
    service = _service(Database(), SimpleNamespace())
    if error:
        with pytest.raises(ValueError, match=error):
            _scheduled_policy(service, row, body)
        return
    result = _scheduled_policy(service, row, body)
    assert result == {"policy": "scheduled-add-evals-v1", "evaluations": 1}


@pytest.mark.parametrize(
    "board,source_value,source_scale,stored,error",
    [
        (
            [{"GenEval Score": "92.1"}, {"GenEval Score": 88.4}, {"GenEval Score": 95}],
            0.923,
            "0-100",
            0.923,
            "looks like a 0-1 fraction",
        ),
        (
            [{"GenEval Score": "92.1"}, {"GenEval Score": 88.4}, {"GenEval Score": 95}],
            0.923,
            "0-1",
            92.3,
            None,
        ),
        (
            [{"GenEval Score": "92.1"}, {"GenEval Score": 0.9}, {"GenEval Score": 95}],
            0.8,
            "0-100",
            0.8,
            None,
        ),
        (
            [
                {"GenEval Score": "92.1 ± 0.3"},
                {"GenEval Score": "88.4+/-1.1"},
                {"GenEval Score": "95%"},
            ],
            0.923,
            "0-100",
            0.923,
            "looks like a 0-1 fraction",
        ),
        (
            [
                {"GenEval Score": "92.1"},
                {"GenEval Score": "n/a"},
                {"GenEval Score": 95},
            ],
            0.923,
            "0-100",
            0.923,
            None,
        ),
    ],
)
def test_scheduled_evaluation_checks_sub_one_percent_against_leaderboard(
    board, source_value, source_scale, stored, error
):
    from backend.models.database import Evaluation, Metric, Paper

    paper = SimpleNamespace(
        id=42, source="arxiv", source_url=None, arxiv_id="2601.00001"
    )

    class Query:
        def __init__(self, model):
            self.model = model

        def join(self, *_args):
            return self

        def filter(self, *_args):
            return self

        def one_or_none(self):
            return SimpleNamespace(supports_harness=False)

        def all(self):
            if self.model is Metric:
                return [SimpleNamespace(name="GenEval Score", scale="0-100")]
            if self.model is Evaluation.metrics:
                return [(metrics,) for metrics in board]
            return []

    class Database:
        def get(self, model, _key):
            return paper if model is Paper else None

        def query(self, model):
            return Query(model)

    row = SimpleNamespace(
        kind="add-evals",
        paper_id=42,
        trigger="hf-daily-cron",
        trace_status="preapply_stored",
    )
    evaluation = _evaluation(model_name="Useful Model")
    evaluation.metrics = {"GenEval Score": stored}
    body = ApplyMutationRequest(
        evaluations=[evaluation],
        evaluation_removals=[],
        benchmark_gaps=[],
        validation_evidence=[],
        score_evidence=[
            _score_evidence(source_value=source_value, source_scale=source_scale)
        ],
    )
    service = _service(Database(), SimpleNamespace())
    if error:
        with pytest.raises(ValueError, match=error):
            _scheduled_policy(service, row, body)
        return
    result = _scheduled_policy(service, row, body)
    assert result == {"policy": "scheduled-add-evals-v1", "evaluations": 1}


@pytest.mark.parametrize(
    "proposal",
    [
        {
            "evaluations": [_evaluation(model_name="Useful Model")],
            "score_evidence": [_score_evidence()],
        },
        # Curators often nest each row's source cell inside that row.
        {
            "evaluations": [
                {
                    **_evaluation(model_name="Useful Model").model_dump(),
                    "score_evidence": [_score_evidence()],
                }
            ],
        },
        # Identical repeats and cells for rows the curator dropped are harmless.
        {
            "evaluations": [_evaluation(model_name="Useful Model")],
            "score_evidence": [
                _score_evidence(),
                _score_evidence(),
                _score_evidence(dataset_id=999),
            ],
        },
    ],
)
def test_scheduled_evaluation_canonicalizes_noncanonical_arxiv_source_url(proposal):
    from backend.models.database import Evaluation, Paper

    paper = SimpleNamespace(
        id=42,
        source="arxiv",
        source_url=None,
        arxiv_id="2601.00001",
    )

    class Query:
        def __init__(self, model):
            self.model = model

        def join(self, *_args):
            return self

        def filter(self, *_args):
            return self

        def one_or_none(self):
            return SimpleNamespace(supports_harness=False)

        def all(self):
            if self.model is Evaluation:
                return []
            return [SimpleNamespace(name="GenEval Score", scale="0-1")]

    class Database:
        def get(self, model, _key):
            return paper if model is Paper else None

        def query(self, model):
            return Query(model)

    row = SimpleNamespace(
        kind="add-evals",
        paper_id=42,
        trigger="hf-daily-cron",
        trace_status="preapply_stored",
    )

    body = ApplyMutationRequest(**proposal)

    result = _scheduled_policy(_service(Database(), SimpleNamespace()), row, body)

    assert result == {"policy": "scheduled-add-evals-v1", "evaluations": 1}
    assert body.evaluations[0].source_url == (
        "https://paperswithcode.co/paper/2601.00001"
    )
    assert body.evaluations[0].external_source_url == (
        "https://paperswithcode.co/paper/2601.00001"
    )


@pytest.mark.parametrize(
    ("bad_evidence", "detail"),
    [
        (
            [_score_evidence(), _score_evidence(source_value=91)],
            r"conflicting entries for \[19, 340, 'GenEval Score'\]",
        ),
        (
            [_score_evidence(dataset_id=999)],
            r"Missing \[task_id, dataset_id, metric\]: \[\[19, 340, 'GenEval Score'\]\]",
        ),
    ],
)
def test_scheduled_score_evidence_cannot_conflict_or_be_reused_for_another_leaderboard(
    bad_evidence, detail
):
    paper = SimpleNamespace(source="arxiv", arxiv_id="2601.00001")
    service = _service(SimpleNamespace(get=lambda *_: paper), SimpleNamespace())
    service._validate_scheduled_capability_boundary = lambda *_: None
    with pytest.raises(ValueError, match="exactly one score_evidence") as error:
        _scheduled_policy(
            service,
            SimpleNamespace(
                trigger="hf-daily-cron",
                kind="add-evals",
                paper_id=42,
                trace_status="preapply_stored",
            ),
            ApplyMutationRequest(
                evaluations=[_evaluation(model_name="Useful Model")],
                score_evidence=bad_evidence,
            ),
        )
    assert re.search(detail, str(error.value))


def test_scheduled_source_canonicalization_is_recorded_in_existing_row_diff():
    from backend.models.database import Evaluation, Metric, Paper, TaskDataset

    paper = SimpleNamespace(
        id=42,
        source="arxiv",
        source_url=None,
        arxiv_id="2601.00001",
    )
    existing = _stored_evaluation(methodology=None, metrics={"GenEval Score": 0.9})

    class Query:
        def __init__(self, model):
            self.model = model

        def join(self, *_args):
            return self

        def filter(self, *_args):
            return self

        def one_or_none(self):
            if self.model is TaskDataset:
                return SimpleNamespace(supports_harness=False)
            return None

        def all(self):
            if self.model is Metric:
                return [SimpleNamespace(name="GenEval Score", scale="0-1")]
            if self.model is Evaluation:
                return [existing]
            return []

    class Database:
        def get(self, model, _key):
            return paper if model is Paper else None

        def query(self, model):
            return Query(model)

    before = CodexCurationCallbackService._evaluation_state(existing)
    audit = {
        "evaluation_id": existing.id,
        "before_state": before,
        "field_diff": {},
        "evidence": [{"source_url": "https://arxiv.org/abs/2601.00001"}],
    }
    body = ApplyMutationRequest(
        evaluations=[_evaluation(model_name="Existing Model")],
        validation_evidence=[audit],
        score_evidence=[_score_evidence()],
    )

    result = _scheduled_policy(
        _service(Database(), SimpleNamespace()),
        SimpleNamespace(
            kind="add-evals",
            paper_id=42,
            trigger="hf-daily-cron",
            trace_status="preapply_stored",
        ),
        body,
    )

    assert result == {"policy": "scheduled-add-evals-v1", "evaluations": 1}
    assert body.validation_evidence[0]["field_diff"]["source_url"] == {
        "before": "https://arxiv.org/abs/2601.00001",
        "after": "https://paperswithcode.co/paper/2601.00001",
    }


def test_scheduled_evaluation_rejects_multiple_models_per_leaderboard():
    from backend.models.database import Paper

    paper = SimpleNamespace(
        id=42,
        source="arxiv",
        source_url=None,
        arxiv_id="2601.00001",
    )

    class Database:
        def get(self, model, _key):
            return paper if model is Paper else None

    row = SimpleNamespace(
        kind="add-evals",
        paper_id=42,
        trigger="hf-daily-cron",
        trace_status="preapply_stored",
    )
    source = "https://paperswithcode.co/paper/2601.00001"

    with pytest.raises(ValueError, match="best eligible target result"):
        _scheduled_policy(
            _service(Database(), SimpleNamespace()),
            row,
            ApplyMutationRequest(
                evaluations=[
                    _evaluation(model_name="Best Model", source_url=source),
                    _evaluation(model_name="Lower Ablation", source_url=source),
                ],
                evaluation_removals=[],
                benchmark_gaps=[],
                validation_evidence=[],
            ),
        )


@pytest.mark.parametrize(
    ("row", "payload", "status_code", "detail"),
    [
        (
            SimpleNamespace(
                kind="add-evals",
                status="completed",
                submitted_at=None,
                applied_at=None,
                paper_id=42,
            ),
            {"evaluations": []},
            409,
            "This job may no longer apply mutations",
        ),
        (
            SimpleNamespace(
                kind="enrich-paper",
                status="running",
                submitted_at=None,
                applied_at=None,
                paper_id=42,
            ),
            {},
            422,
            "Enrichment payload is required",
        ),
    ],
)
def test_apply_rejections_keep_http_contract(
    monkeypatch, row, payload, status_code, detail
):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    database = _MutationDatabase()
    monkeypatch.setattr(codex_curation_callbacks, "_callback_job", lambda *_args: row)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: database

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/codex-curation/jobs/"
            "00000000-0000-0000-0000-000000000042/apply",
            headers={"Authorization": "Bearer scoped-token"},
            json=payload,
        )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert database.commits == 0
    assert database.rollbacks == 1


def test_admin_validation_rejection_returns_detail_to_worker(monkeypatch):
    from backend.routers import codex_curation_callbacks

    row = SimpleNamespace(
        kind="add-evals",
        trigger="admin",
        status="running",
        submitted_at=None,
        applied_at=None,
        paper_id=42,
    )

    class Service:
        def apply(self, *_args, **_kwargs):
            raise ValueError("Benchmark 'CIFAR-100' is not already_present")

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    monkeypatch.setattr(codex_curation_callbacks, "_callback_job", lambda *_args: row)
    monkeypatch.setattr(codex_curation_callbacks, "_service", lambda _db: Service())
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: _MutationDatabase()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/codex-curation/jobs/"
            "00000000-0000-0000-0000-000000000042/apply",
            headers={"Authorization": "Bearer scoped-token"},
            json={"evaluations": []},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Benchmark 'CIFAR-100' is not already_present"}


def test_callback_auth_errors_and_disabled_precedence_are_stable():
    enabled = get_settings().model_copy(update={"codex_jobs_enabled": True})
    disabled = enabled.model_copy(update={"codex_jobs_enabled": False})

    class Database:
        def get(self, *_args):
            return None

    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: Database()
    app.dependency_overrides[get_settings] = lambda: enabled
    path = (
        "/api/v1/admin/codex-curation/jobs/00000000-0000-0000-0000-000000000042/context"
    )
    with TestClient(app) as client:
        missing = client.get(path)
        invalid = client.get(path, headers={"Authorization": "Bearer invalid"})
        app.dependency_overrides[get_settings] = lambda: disabled
        hidden = client.get(path)

    assert missing.status_code == 401
    assert missing.json() == {"detail": "Missing job bearer token"}
    assert invalid.status_code == 401
    assert invalid.json() == {"detail": "Invalid job bearer token"}
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "Not found"}


@pytest.mark.parametrize(
    "url, accepted",
    [
        ("http://example.com/project", True),
        ("http://new.example/project", False),
        ("https://new.example/project", True),
    ],
)
def test_scheduled_enrichment_only_allows_existing_http_project_pages(url, accepted):
    class Database:
        def get(self, _model, _key):
            return SimpleNamespace(
                project_pages=[
                    SimpleNamespace(url="http://example.com/project", source="hf_api")
                ]
            )

        def query(self, _model):
            return _ListQuery([])

    service = _service(Database(), SimpleNamespace())
    row = SimpleNamespace(
        kind="enrich-paper",
        paper_id=42,
        trigger="hf-daily-cron",
        trace_status="disabled",
        url_candidates={"complete": True},
    )
    body = ApplyMutationRequest(
        enrich=EnrichPaperMutation(
            task_ids=[],
            method_ids=[],
            urls_extracted=True,
            project_pages=[{"url": "http://example.com/project"}, {"url": url}],
        )
    )
    if accepted:
        assert (
            _scheduled_policy(service, row, body)["removed_hf_api_project_pages"] == []
        )
    else:
        with pytest.raises(ValueError, match="Project page links must use HTTPS"):
            _scheduled_policy(service, row, body)


def test_retry_feedback_is_scoped_and_exposes_only_rejection_details():
    previous = SimpleNamespace(
        id="old",
        kind="add-evals",
        paper_id=42,
        candidate_id=None,
        error="Rejected",
        validation_summary={
            "error": "exact field diff required",
            "before_state": {"private": "omit"},
        },
        proposal={"untrusted": "omit"},
    )
    db = SimpleNamespace(get=lambda *_: previous)
    service = CodexCurationCallbackService(
        db,
        job_service=SimpleNamespace(),
        evaluation_service=SimpleNamespace(),
        association_service=SimpleNamespace(),
    )
    row = SimpleNamespace(retry_of_id="old", kind="add-evals", paper_id=42)
    result = service._retry_feedback(row)
    assert result["validation_error"] == "exact field diff required"
    assert "proposal" not in result
    assert "before_state" not in result
    row.paper_id = 43
    assert service._retry_feedback(row) is None
    assert service._retry_feedback(SimpleNamespace()) is None


@pytest.mark.parametrize(
    ("kind", "source", "pending", "expected"),
    [
        ("add-evals", "external", True, True),
        ("add-evals", "external", False, False),
        ("enrich-paper", "external", True, False),
        ("add-evals", "arxiv", True, False),
    ],
)
def test_context_expects_page_markdown_only_for_external_add_evals(
    kind, source, pending, expected
):
    paper = SimpleNamespace(
        id=131370,
        title="Introducing GPT-6.1 Terra",
        abstract=None,
        arxiv_id="2601.00001" if source == "arxiv" else None,
        source=source,
        source_url="https://openai.com/index/introducing-gpt-6-1-terra",
        date_published=None,
        urls_extracted=False,
        thumbnail_url=None,
        tasks=[],
        methods=[],
        project_pages=[],
        evaluations=[],
    )

    class Database:
        def get(self, *_args):
            return paper

        def query(self, *_args):
            return _ListQuery([])

    class JobService:
        def serialize(self, row, settings):
            return SimpleNamespace(model_dump=lambda *, mode: {"kind": row.kind})

    checked = []

    def markdown_pending(checked_paper, *, bucket_id, token):
        checked.append(checked_paper.id)
        return pending

    service = CodexCurationCallbackService(
        Database(),
        job_service=JobService(),
        evaluation_service=SimpleNamespace(),
        association_service=SimpleNamespace(),
        markdown_pending=markdown_pending,
    )

    result = service.context(
        SimpleNamespace(paper_id=131370, kind=kind), get_settings()
    )

    assert result["paper"]["markdown_expected"] is expected
    assert checked == ([131370] if kind == "add-evals" and source == "external" else [])
