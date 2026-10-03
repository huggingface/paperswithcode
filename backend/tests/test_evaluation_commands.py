"""SQLite contract tests for the direct and paper-edit evaluation adapters."""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models import database as dbm
from backend.models.evaluations import EvaluationUpdateRequest
from backend.models.paper_edits import PaperEditDocument
from backend.services.catalog_errors import CatalogNotFoundError, CatalogValidationError
from backend.services.evaluation_commands import (
    apply_evaluation_command,
    evaluation_command,
    update_payload,
)
from backend.services.evaluation_curation_service import EvaluationCurationService
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_edit_service import PaperEditService
from backend.services.pending_edit_mutations import PendingEditMutationService
from backend.services.pending_edit_errors import PendingEditError
from backend.services.pending_edit_payloads import validate_payload


@compiles(BigInteger, "sqlite")
def _bigint(_type, _compiler, **_kwargs):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
def _array(_type, _compiler, **_kwargs):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _json(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    tables = [
        dbm.Paper,
        dbm.Task,
        dbm.Dataset,
        dbm.Metric,
        dbm.TaskDataset,
        dbm.TaskDatasetMetric,
        dbm.Evaluation,
        dbm.Repository,
        dbm.PaperRepository,
        dbm.ProjectPage,
        dbm.PaperProjectPage,
        dbm.HfArtifact,
        dbm.PaperHfArtifact,
        dbm.CatalogMutationEvent,
        dbm.CatalogMutationIdempotency,
    ]
    dbm.Base.metadata.create_all(engine, tables=[model.__table__ for model in tables])
    with Session(engine) as session:
        session.add_all(
            [
                dbm.Paper(id=1, title="Paper", arxiv_id="2601.00001"),
                dbm.Paper(id=2, title="Other", arxiv_id="2601.00002"),
                dbm.Task(id=1, name="Task", slug="task"),
                dbm.Dataset(id=1, name="Dataset", slug="dataset"),
                dbm.Metric(id=1, name="Accuracy", direction="higher_is_better"),
            ]
        )
        session.flush()
        session.add_all(
            [
                dbm.TaskDataset(task_id=1, dataset_id=1, supports_harness=True),
                dbm.TaskDatasetMetric(task_id=1, dataset_id=1, metric_id=1),
            ]
        )
        session.commit()
        yield session
    engine.dispose()


ACTOR = {"role": "admin", "hf_subject": "command-test"}


def mutation():
    return dict(
        actor=ACTOR,
        request_id="test",
        idempotency_key=str(uuid.uuid4()),
        expected_version=None,
    )


def create_payload():
    return dict(
        paper_id=1,
        task_id=1,
        dataset_id=1,
        metrics={"Accuracy": 0},
        best_metric="Accuracy",
        harness="Runner",
        source_url="https://example.com/result",
        num_parameters=0,
        hf_model_url="https://huggingface.co/org/model",
        model_name="Original",
    )


def paper_apply(db, payload, evaluation_id=None, paper_id=1):
    document = PaperEditDocument(
        paper_id=paper_id,
        version="0" * 64,
        idempotency_key=uuid.uuid4(),
        operations=[
            dict(section="evaluations", evaluation_id=evaluation_id, payload=payload)
        ],
    )
    service = PaperEditService(db)
    service.apply(paper_id, service.prepare(document), ACTOR)
    return db.query(dbm.Evaluation).order_by(dbm.Evaluation.id.desc()).first()


def pending_apply(db, payload, evaluation_id=None, paper_id=1):
    operation = {"op": "create" if evaluation_id is None else "update", "data": payload}
    if evaluation_id is not None:
        operation["evaluation_id"] = evaluation_id
    PendingEditMutationService(db)._paper_evaluations(
        paper_id, {"operations": [operation]}
    )
    return db.query(dbm.Evaluation).order_by(dbm.Evaluation.id.desc()).first()


@pytest.mark.parametrize("adapter", ["direct", "paper", "pending"])
def test_create_and_patch_presence_parity(db, adapter):
    curation = EvaluationCurationService(db)
    if adapter == "direct":
        result = curation.create(payload=create_payload(), mutation=mutation())
        row = db.get(dbm.Evaluation, int(result.id))
    else:
        apply = pending_apply if adapter == "pending" else paper_apply
        row = apply(db, create_payload())
    assert row.metrics == {"Accuracy": 0}
    assert row.num_parameters == 0
    original = (row.harness, row.source_url, row.num_parameters, row.hf_model_url)

    def update(payload):
        if adapter == "direct":
            curation.update(
                evaluation_id=row.id,
                payload=update_payload(EvaluationUpdateRequest.model_validate(payload)),
                mutation=mutation(),
            )
        else:
            apply(db, payload, row.id)

    update({"model_name": "Updated"})
    assert (
        row.harness,
        row.source_url,
        row.num_parameters,
        row.hf_model_url,
    ) == original
    update(
        dict(
            harness=None,
            source_url=None,
            num_parameters=None,
            hf_model_url=None,
            model_name=None,
            metrics=None,
        )
    )
    assert (row.harness, row.source_url, row.num_parameters, row.hf_model_url) == (
        None,
    ) * 4
    assert (
        row.model_name == "Updated"
    )  # Legacy non-clearable fields retain null semantics.
    assert row.metrics == {"Accuracy": 0}
    assert row.external_source_url is None


@pytest.mark.parametrize("adapter", ["direct", "paper", "pending"])
def test_negative_parameter_count_rejected(db, adapter):
    payload = {**create_payload(), "num_parameters": -1}
    with pytest.raises((ValidationError, CatalogValidationError, PendingEditError)):
        if adapter == "direct":
            EvaluationCurationService(db).create(payload=payload, mutation=mutation())
        else:
            apply = pending_apply if adapter == "pending" else paper_apply
            apply(db, payload)
    assert db.query(dbm.Evaluation).count() == 0


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_batch_foreign_paper_failure_rolls_back_rows_ranks_and_audit(db, operation):
    service = EvaluationCurationService(db)
    existing = service.create(payload=create_payload(), mutation=mutation())
    before_events = db.query(dbm.CatalogMutationEvent).count()
    with pytest.raises(CatalogNotFoundError):
        service.batch(
            paper_id=2,
            operations=[
                dict(
                    operation="create",
                    payload={
                        **create_payload(),
                        "paper_id": 2,
                        "metrics": {"Accuracy": 99},
                    },
                ),
                dict(operation=operation, evaluation_id=int(existing.id), payload={}),
            ],
            mutation=mutation(),
        )
    assert db.query(dbm.Evaluation).count() == 1
    assert db.get(dbm.Evaluation, int(existing.id)).best_rank == 1
    assert db.query(dbm.CatalogMutationEvent).count() == before_events


def test_paper_edit_rejects_cross_paper_evaluation(db):
    row = paper_apply(db, create_payload())
    with pytest.raises(CatalogValidationError, match="does not belong"):
        paper_apply(db, {"model_name": "Changed"}, row.id, paper_id=2)
    assert row.model_name == "Original"


def test_applicator_never_commits_or_rolls_back_and_delete_is_reversible(db):
    service = EvaluationService(db)
    row = apply_evaluation_command(
        service, evaluation_command("create", create_payload()), paper_id=1
    )
    db.commit()
    events = []
    event.listen(db, "after_commit", lambda _session: events.append("commit"))
    event.listen(db, "after_rollback", lambda _session: events.append("rollback"))
    apply_evaluation_command(
        service, evaluation_command("delete", {}, int(row.id)), paper_id=1
    )
    assert db.query(dbm.Evaluation).count() == 0
    with pytest.raises(CatalogValidationError):
        apply_evaluation_command(
            service,
            evaluation_command(
                "create", {**create_payload(), "metrics": {"Unknown": 0}}
            ),
        )
    assert events == []
    db.rollback()
    assert db.query(dbm.Evaluation).count() == 1


def test_legacy_flags_preserve_absent_metadata():
    command = evaluation_command(
        "update", {"source_url": None, "source_url_set": False}, 1
    )
    assert "source_url" not in command.payload.model_fields_set


def test_direct_batch_update_delete_and_audit(db):
    service = EvaluationCurationService(db)
    created = service.create(payload=create_payload(), mutation=mutation())
    result = service.batch(
        paper_id=1,
        operations=[
            dict(
                operation="update",
                evaluation_id=int(created.id),
                payload={"metrics": {"Accuracy": 42}},
            ),
            dict(operation="create", payload=create_payload()),
        ],
        mutation=mutation(),
    )
    assert result["result_ids"][0] == int(created.id)
    assert len(result["evaluations"]) == 2
    assert db.get(dbm.Evaluation, int(created.id)).metrics == {"Accuracy": 42}
    service.delete(evaluation_id=int(created.id), mutation=mutation())
    assert db.get(dbm.Evaluation, int(created.id)) is None
    assert [
        row.operation
        for row in db.query(dbm.CatalogMutationEvent).order_by(
            dbm.CatalogMutationEvent.created_at
        )
    ] == ["create", "batch", "delete"]


def test_url_normalization_is_shared_by_both_adapters(db):
    payload = {**create_payload(), "source_url": "  https://example.com/result  "}
    result = EvaluationCurationService(db).create(payload=payload, mutation=mutation())
    row = paper_apply(db, payload)
    assert row.source_url == result.source_url == "https://example.com/result"


@pytest.mark.parametrize("kind", ["create", "update"])
@pytest.mark.parametrize(
    "invalid",
    [
        {"num_parameters": -1},
        {"task_id": -1},
        {"dataset_id": 0},
        {"metrics": {}},
        {"metrics": {"Accuracy": " "}},
        {"metrics": {"": 5}},
        {"best_metric": " "},
        {"source_url": "javascript:alert(1)"},
        {"evaluated_on": "invalid"},
    ],
)
def test_pending_mixed_batch_reports_index_before_writing(db, kind, invalid):
    row = paper_apply(db, create_payload())
    operations = [
        {"op": "update", "evaluation_id": row.id, "data": {"model_name": "Changed"}},
        {"op": kind, "evaluation_id": row.id, "data": {**create_payload(), **invalid}},
    ]
    with pytest.raises(PendingEditError, match=r"operations\[1\]"):
        PendingEditMutationService(db)._paper_evaluations(1, {"operations": operations})
    assert row.model_name == "Original"
    assert db.query(dbm.Evaluation).count() == 1


def test_pending_reports_every_invalid_member():
    with pytest.raises(PendingEditError) as error:
        validate_payload(
            "evaluations", {"operations": [None, {"op": "create", "data": {}}]}
        )
    assert "operations[0]" in str(error.value)
    assert "operations[1]" in str(error.value)


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_pending_foreign_paper_rejected_before_any_mutation(db, operation):
    row = paper_apply(db, create_payload())
    with pytest.raises(PendingEditError, match=r"operations\[1\].*not on paper"):
        PendingEditMutationService(db)._paper_evaluations(
            2,
            {
                "operations": [
                    {"op": "create", "data": create_payload()},
                    {
                        "op": operation,
                        "evaluation_id": row.id,
                        "data": {"model_name": "Wrong"},
                    },
                ]
            },
        )
    assert row.model_name == "Original"
    assert db.query(dbm.Evaluation).count() == 1


def test_pending_create_scoped_to_context_and_flags_cannot_override_presence(db):
    row = pending_apply(db, {**create_payload(), "paper_id": 2})
    assert row.paper_id == 1
    pending_apply(db, {"source_url": None, "source_url_set": False}, row.id)
    assert row.source_url is None
    payload = validate_payload(
        "evaluations",
        {
            "operations": [
                {
                    "op": "update",
                    "evaluation_id": row.id,
                    "data": {"model_name": "Name", "num_parameters_set": True},
                }
            ]
        },
    )
    assert payload["operations"][0]["data"] == {"model_name": "Name"}


def test_pending_valid_stored_payload_preserves_json_date_and_null_presence(db):
    data = {**create_payload(), "evaluated_on": "2026-01-01", "hf_model_url": None}
    normalized = validate_payload(
        "evaluations", {"operations": [{"op": "create", "data": data}]}
    )
    assert normalized["operations"][0]["data"]["evaluated_on"] == "2026-01-01"
    assert normalized["operations"][0]["data"]["hf_model_url"] is None
    row = pending_apply(db, normalized["operations"][0]["data"])
    assert row.evaluated_on.isoformat() == "2026-01-01"
    PendingEditMutationService(db)._paper_evaluations(
        1, {"operations": [{"op": "delete", "evaluation_id": row.id}]}
    )
    assert db.query(dbm.Evaluation).count() == 0
