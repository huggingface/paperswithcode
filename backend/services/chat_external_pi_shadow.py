"""Authenticated, non-executing compatibility probe for the external Pi worker."""

from __future__ import annotations

import hashlib
import json
import math
import struct
import uuid
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


def _canonical_json(value: object) -> str:
    if value is None:
        return '["null"]'
    if isinstance(value, bool):
        return f'["boolean",{str(value).lower()}]'
    if isinstance(value, str):
        return f'["string",{json.dumps(value, ensure_ascii=False)}]'
    if isinstance(value, int) and not isinstance(value, bool):
        if not -(2**53 - 1) <= value <= 2**53 - 1:
            raise ValueError("External Pi shadow transcript integer is unsafe")
        return f'["number","{struct.pack(">d", float(value)).hex()}"]'
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("External Pi shadow transcript JSON is invalid")
        return f'["number","{struct.pack(">d", value).hex()}"]'
    if isinstance(value, (list, tuple)):
        return '["array",[' + ",".join(_canonical_json(item) for item in value) + "]]"
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("External Pi shadow transcript key is invalid")
        items = sorted(value.items(), key=lambda item: item[0].encode())
        return (
            '["object",['
            + ",".join(
                f"[{json.dumps(key, ensure_ascii=False)},{_canonical_json(item)}]"
                for key, item in items
            )
            + "]]"
        )
    raise ValueError("External Pi shadow transcript JSON is invalid")


def native_jsonl_transcript_digest(
    entries: tuple[dict[str, object], ...],
) -> str:
    """Digest native entries after recursively key-sorted JSONL serialization."""

    digest = hashlib.sha256()
    for entry in entries:
        line = _canonical_json(entry)
        digest.update(line.encode())
        digest.update(b"\n")
    return digest.hexdigest()


class ExternalPiShadowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_version: int = Field(default=1, ge=1, le=1)
    request_id: str = Field(min_length=1, max_length=200)
    chat_session_id: uuid.UUID
    agent_session_id: uuid.UUID
    current_leaf_id: str | None = Field(default=None, max_length=255)
    prompt: str = Field(max_length=2 * 1024 * 1024)
    tool_names: tuple[str, ...] = Field(max_length=128)
    transcript_entries: tuple[dict[str, object], ...] = Field(
        min_length=1, max_length=2_000
    )

    @model_validator(mode="after")
    def validate_projection_inputs(self):
        if len(self.prompt.encode()) > 2 * 1024 * 1024:
            raise ValueError("External Pi shadow prompt is too large")
        if len(set(self.tool_names)) != len(self.tool_names) or any(
            not name or len(name) > 128 or any(char in name for char in "\r\n\0")
            for name in self.tool_names
        ):
            raise ValueError("External Pi shadow tool names are invalid")
        header = self.transcript_entries[0]
        if header.get("type") != "session" or header.get("id") != str(
            self.agent_session_id
        ):
            raise ValueError("External Pi shadow transcript header is invalid")
        if len(json.dumps(self.transcript_entries, separators=(",", ":")).encode()) > (
            25 * 1024 * 1024
        ):
            raise ValueError("External Pi shadow transcript is too large")
        return self

    @property
    def prompt_sha256(self) -> str:
        return hashlib.sha256(self.prompt.encode()).hexdigest()

    @property
    def tool_names_sha256(self) -> str:
        canonical = ",".join(sorted(self.tool_names))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @property
    def transcript_sha256(self) -> str:
        return native_jsonl_transcript_digest(self.transcript_entries)

    def wire_payload(self) -> dict[str, object]:
        return {
            "type": "shadow_compare",
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "chat_session_id": str(self.chat_session_id),
            "agent_session_id": str(self.agent_session_id),
            "current_leaf_id": self.current_leaf_id,
            "expected_prompt_sha256": self.prompt_sha256,
            "expected_tool_names_sha256": self.tool_names_sha256,
            "expected_transcript_sha256": self.transcript_sha256,
            "transcript_entries": list(self.transcript_entries),
        }


class ExternalPiShadowProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str = Field(pattern=r"^shadow_projection$")
    protocol_version: int = Field(ge=1, le=1)
    request_id: str = Field(min_length=1, max_length=200)
    chat_session_id: uuid.UUID
    agent_session_id: uuid.UUID
    current_leaf_id: str | None = Field(default=None, max_length=255)
    entry_count: int = Field(ge=1, le=2_000)
    transcript_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_names_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def compatible_with(self, request: ExternalPiShadowRequest) -> bool:
        return (
            self.protocol_version == request.protocol_version
            and self.request_id == request.request_id
            and self.chat_session_id == request.chat_session_id
            and self.agent_session_id == request.agent_session_id
            and self.current_leaf_id == request.current_leaf_id
            and self.entry_count == len(request.transcript_entries)
            and self.transcript_sha256 == request.transcript_sha256
            and self.prompt_sha256 == request.prompt_sha256
            and self.tool_names_sha256 == request.tool_names_sha256
        )


class ExternalPiOperationCounters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    shadow_requests: int = Field(ge=0)
    model_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    provider_calls: int = Field(ge=0)
    modal_calls: int = Field(ge=0)
    billing_events: int = Field(ge=0)


class ExternalPiCapabilityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    provider_credentials_present: bool
    modal_credentials_present: bool
    registered_tool_count: int = Field(ge=0, le=128)


class ExternalPiWorkerStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol: str = Field(pattern=r"^external-pi-v1$")
    worker_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    instance_id: uuid.UUID
    release_id: str = Field(min_length=1, max_length=255)
    state: str = Field(pattern=r"^(ready|draining)$")
    active_sessions: int = Field(ge=0, le=32, strict=True)
    maximum_sessions: int = Field(ge=1, le=32, strict=True)
    worker_generation: int | None = Field(default=None, ge=1, strict=True)
    operation_counters: ExternalPiOperationCounters
    capability_evidence: ExternalPiCapabilityEvidence

    @model_validator(mode="after")
    def validate_capacity(self):
        if self.active_sessions > self.maximum_sessions:
            raise ValueError("External Pi worker capacity is invalid")
        return self


class ExternalPiWorkerUnavailable(RuntimeError):
    """The worker could not be reached or returned a transient server failure."""


class ExternalPiShadowCapacity(RuntimeError):
    """The worker rejected shadow work immediately at its fixed capacity."""


class ExternalPiWorkerControlRejected(RuntimeError):
    """The worker rejected the request or violated the control contract."""


@dataclass(slots=True)
class ExternalPiShadowClient:
    base_url: str
    token: str = field(repr=False)
    http: httpx.AsyncClient
    timeout_seconds: float = 5.0

    async def compare(
        self, request: ExternalPiShadowRequest
    ) -> ExternalPiShadowProjection:
        try:
            response = await self.http.post(
                f"{self.base_url.rstrip('/')}/v1/shadow",
                headers={"Authorization": f"Bearer {self.token}"},
                json=request.wire_payload(),
                timeout=self.timeout_seconds,
            )
            if response.status_code == 503:
                try:
                    code = response.json().get("code")
                except (ValueError, AttributeError):
                    code = None
                if code == "shadow_capacity":
                    raise ExternalPiShadowCapacity("External Pi shadow is at capacity")
            response.raise_for_status()
            projection = ExternalPiShadowProjection.model_validate(response.json())
        except ExternalPiShadowCapacity:
            raise
        except (httpx.HTTPError, ValueError, ValidationError) as error:
            raise RuntimeError(
                "External Pi shadow returned an invalid response"
            ) from error
        if not projection.compatible_with(request):
            raise RuntimeError("External Pi shadow compatibility mismatch")
        return projection


@dataclass(slots=True)
class ExternalPiWorkerControlClient:
    base_url: str
    token: str = field(repr=False)
    http: httpx.AsyncClient
    timeout_seconds: float = 5.0

    async def _control(
        self,
        method: str,
        path: str,
        *,
        generation: int | None = None,
        json_body: dict[str, object] | None = None,
    ) -> ExternalPiWorkerStatus:
        headers = {"Authorization": f"Bearer {self.token}"}
        if generation is not None:
            headers["X-PWC-Worker-Generation"] = str(generation)
        try:
            response = await self.http.request(
                method,
                f"{self.base_url.rstrip('/')}{path}",
                headers=headers,
                json=json_body,
                timeout=self.timeout_seconds,
            )
        except httpx.RequestError as error:
            raise ExternalPiWorkerUnavailable(
                "External Pi worker is unavailable"
            ) from error
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            if response.status_code >= 500:
                raise ExternalPiWorkerUnavailable(
                    "External Pi worker is unavailable"
                ) from error
            raise ExternalPiWorkerControlRejected(
                "External Pi worker returned an invalid response"
            ) from error
        try:
            return ExternalPiWorkerStatus.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise ExternalPiWorkerControlRejected(
                "External Pi worker returned an invalid response"
            ) from error

    async def status(self) -> ExternalPiWorkerStatus:
        return await self._control("GET", "/v1/status")

    async def bind_claim(self, generation: int) -> ExternalPiWorkerStatus:
        return await self._control(
            "POST",
            "/v1/claim",
            json_body={"worker_generation": generation},
        )

    async def begin_drain(self, generation: int) -> ExternalPiWorkerStatus:
        return await self._control("POST", "/v1/drain", generation=generation)
