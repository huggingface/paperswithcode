"""Strict API and durable projection models for authenticated research chat."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

StrictText = Annotated[str, StringConstraints(max_length=8000)]
AuthorName = Annotated[str, StringConstraints(max_length=300)]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: StrictText
    session_id: uuid.UUID | None = None
    client_message_id: Annotated[
        str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)
    ]
    initial_model: str | None = None
    replace_message_id: uuid.UUID | None = None
    prior_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_message(self) -> "ChatRequest":
        if not self.message.strip():
            raise ValueError("Message must not be empty")
        if (self.replace_message_id is None) != (self.prior_revision is None):
            raise ValueError(
                "Replacement message and revision must be supplied together"
            )
        return self


class ChatPaperMetadata(BaseModel):
    arxiv_id: str | None
    source: Literal["arxiv", "external"]
    source_url: str | None
    thumbnail_url: str | None = Field(default=None, max_length=1000)
    authors: list[dict[str, str]]
    published: str | None
    conference: str | None
    citation_count: int | None
    tasks: list[dict[str, str]]
    methods: list[dict[str, str]]
    repositories: list[dict[str, str | int | None]]
    project_pages: list[dict[str, str]]


class ChatPaperHit(BaseModel):
    route_id: str = Field(max_length=200)
    title: str = Field(max_length=500)
    content: str = Field(max_length=4000)
    content_truncated: bool
    metadata: ChatPaperMetadata


class CitationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: int = Field(ge=0, le=100)
    route_id: str = Field(max_length=200)
    title: str = Field(max_length=500)
    source_url: str | None = Field(default=None, max_length=2000)
    authors: list[AuthorName] = Field(default_factory=list, max_length=50)
    published: str | None = Field(default=None, max_length=32)
    conference: str | None = Field(default=None, max_length=200)


class ReasoningDisplayBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["reasoning"]
    text: str = Field(max_length=20_000)


class ToolDisplayBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["tool"]
    id: str = Field(max_length=200)
    name: Literal["search_papers"]
    args: dict[str, object]
    status: Literal["done"]
    hits: int = Field(ge=0, le=10_000)
    took_ms: int = Field(ge=0, le=600_000)
    results: list[ChatPaperHit] = Field(max_length=10)

    @field_validator("args")
    @classmethod
    def validate_args(cls, value: dict[str, object]) -> dict[str, object]:
        if set(value) - {"query", "top_k", "mode"}:
            raise ValueError("Unsupported search tool arguments")
        if len(json.dumps(value, ensure_ascii=False).encode()) > 2_000:
            raise ValueError("Search tool arguments are too large")
        return value


class AnswerDisplayBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["answer"]
    text: str = Field(max_length=80_000)
    done: Literal[True] = True


DisplayBlock = Annotated[
    Union[ReasoningDisplayBlock, ToolDisplayBlock, AnswerDisplayBlock],
    Field(discriminator="kind"),
]
DISPLAY_BLOCKS_ADAPTER = TypeAdapter(list[DisplayBlock])


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    turn_id: uuid.UUID
    sequence: int
    role: Literal["user", "assistant"]
    content: str
    revision: int
    status: str
    citations: list[CitationSnapshot] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)
    display_blocks: list[DisplayBlock] = Field(default_factory=list)
    model: str | None = None
    error_code: str | None = None
    created_at: datetime


class ChatSessionSummary(BaseModel):
    id: uuid.UUID
    title: str
    selected_model: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    is_busy: bool = False


class ChatSessionDetail(ChatSessionSummary):
    messages: list[ChatMessageResponse]
    transcript_status: str


class ChatSessionList(BaseModel):
    items: list[ChatSessionSummary]
    next_cursor: str | None = None


class CreateSessionRequest(BaseModel):
    selected_model: str | None = None


class UpdateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=80)
    selected_model: str | None = None

    @model_validator(mode="after")
    def one_change(self) -> "UpdateSessionRequest":
        if self.title is None and self.selected_model is None:
            raise ValueError("Supply a title or selected_model")
        if self.title is not None and not " ".join(self.title.split()):
            raise ValueError("Title must not be empty")
        return self


class _StrictEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StreamStartEvent(_StrictEvent):
    type: Literal["stream_start"]
    request_id: str
    session_id: uuid.UUID


class ReasoningStartEvent(_StrictEvent):
    type: Literal["reasoning_start"]


class ReasoningDeltaEvent(_StrictEvent):
    type: Literal["reasoning_delta"]
    text: str


class ReasoningEndEvent(_StrictEvent):
    type: Literal["reasoning_end"]


class ToolCallEvent(_StrictEvent):
    type: Literal["tool_call"]
    id: str
    name: str
    args: dict[str, object]


class ToolResultEvent(_StrictEvent):
    type: Literal["tool_result"]
    id: str
    hits: int
    took_ms: int
    results: list[ChatPaperHit]


class AnswerDeltaEvent(_StrictEvent):
    type: Literal["answer_delta"]
    text: str


class DoneEvent(_StrictEvent):
    type: Literal["done"]
    followups: list[str] = Field(default_factory=list)
    finish_reason: str = "success"


class ErrorEvent(_StrictEvent):
    type: Literal["error"]
    message: str
    code: str | None = None


class SessionTitleStartEvent(_StrictEvent):
    type: Literal["session_title_start"]


class SessionTitleDeltaEvent(_StrictEvent):
    type: Literal["session_title_delta"]
    text: str


class SessionTitleDoneEvent(_StrictEvent):
    type: Literal["session_title_done"]
    title: str


ChatEvent = Annotated[
    Union[
        StreamStartEvent,
        ReasoningStartEvent,
        ReasoningDeltaEvent,
        ReasoningEndEvent,
        ToolCallEvent,
        ToolResultEvent,
        AnswerDeltaEvent,
        DoneEvent,
        ErrorEvent,
        SessionTitleStartEvent,
        SessionTitleDeltaEvent,
        SessionTitleDoneEvent,
    ],
    Field(discriminator="type"),
]
_CHAT_EVENT_ADAPTER = TypeAdapter(ChatEvent)


def sse_event(event_type: str, **payload: object) -> bytes:
    event = _CHAT_EVENT_ADAPTER.validate_python({"type": event_type, **payload})
    return (
        "data: "
        + json.dumps(
            event.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
        )
        + "\n\n"
    ).encode()
