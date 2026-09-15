"""Public paper-edit document. Operations are explicit; omitted sections stay intact."""

import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.utils.public_urls import normalize_public_url


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EditLink(StrictModel):
    url: str = Field(max_length=2000)
    is_official: bool = False
    _url = field_validator("url", mode="before")(normalize_public_url)


class TaskEdit(StrictModel):
    task_ids: list[int] = Field(max_length=100)


class MethodEdit(StrictModel):
    method_ids: list[int] = Field(max_length=100)


class RepositoryEdit(StrictModel):
    repositories: list[EditLink] = Field(max_length=100)


class ProjectPageEdit(StrictModel):
    project_pages: list[EditLink] = Field(max_length=100)


class ArtifactEdit(StrictModel):
    hf_models: list[str] = Field(default_factory=list, max_length=100)
    hf_datasets: list[str] = Field(default_factory=list, max_length=100)
    hf_spaces: list[str] = Field(default_factory=list, max_length=100)


class SourceEdit(StrictModel):
    source_url: str = Field(max_length=2000)
    _url = field_validator("source_url", mode="before")(normalize_public_url)


class PaperEditOperation(StrictModel):
    section: Literal[
        "tasks",
        "methods",
        "repositories",
        "project_pages",
        "hf_artifacts",
        "source_url",
        "evaluations",
    ]
    evaluation_id: int | None = Field(default=None, gt=0)
    payload: dict[str, Any]


class PaperEditDocument(StrictModel):
    schema_version: Literal["v1"] = "v1"
    paper_id: int = Field(gt=0)
    version: str = Field(min_length=64, max_length=64)
    idempotency_key: UUID
    operations: list[PaperEditOperation] = Field(max_length=50)
    # Exported reference material is never interpreted as an edit.
    current: dict[str, Any] | None = None

    @model_validator(mode="after")
    def bounded_document(self):
        if (
            len(json.dumps(self.model_dump(mode="json"), allow_nan=False).encode())
            > 1_048_576
        ):
            raise ValueError("Edit document must be at most 1 MiB")
        return self


class DeviceStart(BaseModel):
    paper_id: int = Field(gt=0)


class DeviceExchange(BaseModel):
    device_code: str = Field(min_length=32, max_length=128)


class EditingSuspension(BaseModel):
    hf_subject: str = Field(min_length=1, max_length=255)
    suspended: bool
