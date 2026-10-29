"""Strict API and durable projection models for authenticated research chat."""

from __future__ import annotations

import json
import re
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
FinishReason = Literal["success", "max_turns", "tool_limit", "scope_blocked"]
ReasoningEffort = Literal["low", "medium", "high", "max"]


class PaperMentionRequest(BaseModel):
    """One browser-selected occurrence in UTF-16 textarea coordinates."""

    model_config = ConfigDict(extra="forbid")

    route_id: Annotated[
        str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)
    ]
    title: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    start: int = Field(ge=0, le=16_000)
    end: int = Field(gt=0, le=16_000)


class PaperMentionSnapshot(BaseModel):
    """Safe durable/UI projection of one server-resolved paper mention."""

    model_config = ConfigDict(extra="forbid")

    occurrence_id: str = Field(min_length=1, max_length=32)
    route_id: str = Field(min_length=1, max_length=200)
    paper_id: str = Field(min_length=1, max_length=64)
    arxiv_id: str | None = Field(default=None, max_length=50)
    title: str = Field(min_length=1, max_length=500)
    source: Literal["arxiv", "external"]
    source_url: str | None = Field(default=None, max_length=2000)
    start: int = Field(ge=0, le=16_000)
    end: int = Field(gt=0, le=16_000)
    paper_version: str | None = Field(default=None, max_length=32)
    metadata_updated_at: str | None = Field(default=None, max_length=64)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_truncated: bool
    content_available: bool
    included_bytes: int = Field(ge=0, le=81_920)
    context_reference: dict[str, str] | None = None


class ViewerContextRequest(BaseModel):
    """Low-trust orientation captured when a reader turn is submitted."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1, le=10_000)


PAPER_SELECTION_MAX_CHARS = 8_000
PAPER_SELECTION_MAX_BYTES = 16_384


def normalize_paper_selection_text(value: str) -> str:
    text = value.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[^\S\n]+", " ", text)
    return text.strip()


class PaperSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_id: Annotated[
        str,
        StringConstraints(min_length=1, max_length=200, strip_whitespace=True),
    ]
    paper_version: Annotated[
        str,
        StringConstraints(min_length=1, max_length=32, strip_whitespace=True),
    ]
    page: int = Field(ge=1, le=10_000)
    text: Annotated[
        str, StringConstraints(min_length=1, max_length=PAPER_SELECTION_MAX_CHARS)
    ]

    @field_validator("text")
    @classmethod
    def normalize_and_bound_text(cls, value: str) -> str:
        normalized = normalize_paper_selection_text(value)
        if not normalized:
            raise ValueError("Paper selection must not be empty")
        if len(normalized.encode("utf-8")) > PAPER_SELECTION_MAX_BYTES:
            raise ValueError("Paper selection exceeds the maximum size")
        return normalized


class PaperSelectionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_id: str
    paper_version: str
    page: int
    text: str
    text_sha256: str
    included_bytes: int
    page_verified: Literal[False] = False


class PrimaryPaperProjection(BaseModel):
    """Authoritative safe session projection for a reader-bound paper."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    route_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    arxiv_id: str | None = Field(default=None, min_length=1, max_length=50)


def _utf16_slice(value: str, start: int, end: int) -> str:
    raw = value.encode("utf-16-le")
    if end * 2 > len(raw):
        raise ValueError("Paper mention range is outside the message")
    try:
        return raw[start * 2 : end * 2].decode("utf-16-le")
    except UnicodeDecodeError as exc:
        raise ValueError("Paper mention range must align to UTF-16 characters") from exc


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: StrictText
    session_id: uuid.UUID | None = None
    client_message_id: Annotated[
        str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)
    ]
    initial_model: str | None = None
    replace_message_id: uuid.UUID | None = None
    retry_message_id: uuid.UUID | None = None
    prior_revision: int | None = Field(default=None, ge=1)
    web_search_enabled: bool = False
    reasoning_effort: ReasoningEffort | None = None
    paper_mentions: list[PaperMentionRequest] = Field(
        default_factory=list, max_length=10
    )
    primary_paper_route_id: (
        Annotated[
            str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)
        ]
        | None
    ) = None
    viewer_context: ViewerContextRequest | None = None
    paper_selection: PaperSelectionRequest | None = None

    @model_validator(mode="after")
    def validate_message(self) -> "ChatRequest":
        if not self.message.strip():
            raise ValueError("Message must not be empty")
        if (self.replace_message_id is None) != (self.prior_revision is None):
            raise ValueError(
                "Replacement message and revision must be supplied together"
            )
        if self.retry_message_id is not None and (
            self.session_id is None or self.replace_message_id is not None
        ):
            raise ValueError(
                "Retry requires an existing session and cannot replace a message"
            )
        previous_end = -1
        distinct: set[str] = set()
        for mention in self.paper_mentions:
            if mention.start < previous_end or mention.end <= mention.start:
                raise ValueError(
                    "Paper mention ranges must be ordered and non-overlapping"
                )
            marker = _utf16_slice(self.message, mention.start, mention.end)
            if marker not in {mention.title, f"@{mention.title}"}:
                raise ValueError(
                    "Paper mention range does not match its visible marker"
                )
            previous_end = mention.end
            distinct.add(mention.route_id)
        if len(distinct) > 3:
            raise ValueError("A message may mention at most three distinct papers")
        if self.viewer_context is not None and (
            self.session_id is None and self.primary_paper_route_id is None
        ):
            raise ValueError("Viewer context requires a paper-bound chat")
        if self.paper_selection is not None and (
            self.session_id is None and self.primary_paper_route_id is None
        ):
            raise ValueError("Paper selection requires a paper-bound chat")
        return self


class ChatBrowserLatencyRequest(BaseModel):
    """Content-free browser timing update for one admitted request."""

    model_config = ConfigDict(extra="forbid")

    submission_to_stream_start_ms: float | None = Field(
        default=None, ge=0, le=3_600_000, allow_inf_nan=False
    )
    submission_to_first_visible_delta_ms: float | None = Field(
        default=None, ge=0, le=3_600_000, allow_inf_nan=False
    )
    submission_to_first_reasoning_delta_ms: float | None = Field(
        default=None, ge=0, le=3_600_000, allow_inf_nan=False
    )
    submission_to_first_tool_call_ms: float | None = Field(
        default=None, ge=0, le=3_600_000, allow_inf_nan=False
    )
    submission_to_first_answer_delta_ms: float | None = Field(
        default=None, ge=0, le=3_600_000, allow_inf_nan=False
    )
    terminal_classification: (
        Literal["complete", "stopped", "error", "network_error", "aborted"] | None
    ) = None

    @model_validator(mode="after")
    def require_measurement(self) -> "ChatBrowserLatencyRequest":
        if (
            self.submission_to_stream_start_ms is None
            and self.submission_to_first_visible_delta_ms is None
            and self.submission_to_first_reasoning_delta_ms is None
            and self.submission_to_first_tool_call_ms is None
            and self.submission_to_first_answer_delta_ms is None
            and self.terminal_classification is None
        ):
            raise ValueError("At least one browser timing field is required")
        return self


class ChatFeedbackRequest(BaseModel):
    """One explicit end-user rating for a completed assistant response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    value: bool
    comment: str | None = Field(default=None, max_length=500)


class ChatFeedbackEntry(BaseModel):
    """One stored rating, as listed for operators."""

    assistant_message_id: uuid.UUID
    session_id: uuid.UUID
    turn_id: uuid.UUID
    value: bool
    comment: str | None = None
    trace_id: str | None = None
    exported_to: str | None = None
    created_at: datetime
    updated_at: datetime


class ChatFeedbackListResponse(BaseModel):
    environment: str
    total: int
    positive: int
    negative: int
    items: list[ChatFeedbackEntry]


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
    kind: Literal["catalog_paper", "external_source"] = "catalog_paper"
    position: int = Field(ge=0, le=100)
    route_id: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=2000)
    source_type: Literal["paper", "article"] | None = None
    provider: Literal["paperswithcode", "semantic_scholar", "web"] = "paperswithcode"
    title: str = Field(max_length=500)
    excerpt: str | None = Field(default=None, max_length=4000)
    source_url: str | None = Field(default=None, max_length=2000)
    thumbnail_url: str | None = Field(default=None, max_length=1000)
    favicon_url: str | None = Field(default=None, max_length=1000)
    arxiv_id: str | None = Field(default=None, max_length=50)
    semantic_scholar_id: str | None = Field(default=None, max_length=100)
    authors: list[AuthorName] = Field(default_factory=list, max_length=50)
    published: str | None = Field(default=None, max_length=32)
    conference: str | None = Field(default=None, max_length=200)
    citation_count: int | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_kind(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        kind = normalized.get("kind")
        if kind in {None, "paper"} and normalized.get("route_id"):
            normalized["kind"] = "catalog_paper"
            normalized.setdefault("provider", "paperswithcode")
        elif kind == "web":
            normalized["kind"] = "external_source"
            normalized.setdefault("source_type", "article")
            normalized.setdefault("provider", "web")
        return normalized

    @model_validator(mode="after")
    def validate_kind(self) -> "CitationSnapshot":
        if self.kind == "catalog_paper" and not self.route_id:
            raise ValueError("Catalog paper citations require route_id")
        if self.kind == "external_source" and (
            not self.url or not self.url.startswith("https://") or self.route_id
        ):
            raise ValueError(
                "External source citations require an HTTPS url and no route_id"
            )
        if self.kind == "external_source" and self.source_type is None:
            raise ValueError("External source citations require source_type")
        return self


class ReasoningDisplayBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["reasoning"]
    text: str = Field(max_length=20_000)
    citations: list[CitationSnapshot] = Field(default_factory=list, max_length=20)


class ToolTextContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["text"] = "text"
    text: str = Field(max_length=24_900)
    truncated: bool = False


class ToolResultMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exit_code: int | None = None
    output_truncated: bool = False


class ToolDisplayBlock(BaseModel):
    """Browser projection for both historical search and generic v2 tools."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["tool"]
    schema_version: Literal[1, 2] = 1
    id: str = Field(max_length=200)
    name: str = Field(min_length=1, max_length=64)
    args: dict[str, object]
    arguments_redacted: bool = False
    status: Literal["running", "done", "success", "error", "denied"]
    took_ms: int = Field(default=0, ge=0, le=600_000)
    content: list[ToolTextContent] = Field(default_factory=list, max_length=1)
    metadata: ToolResultMetadata = Field(default_factory=ToolResultMetadata)
    # Legacy v1 search projection. Retained until local_mcp history is retired.
    hits: int | None = Field(default=None, ge=0, le=10_000)
    results: list[ChatPaperHit] | None = Field(default=None, max_length=10)

    @field_validator("args")
    @classmethod
    def validate_args(cls, value: dict[str, object]) -> dict[str, object]:
        if len(json.dumps(value, ensure_ascii=False).encode()) > 16_000:
            raise ValueError("Tool arguments are too large")
        return value

    @model_validator(mode="after")
    def validate_schema(self) -> "ToolDisplayBlock":
        if self.schema_version == 1:
            if self.name != "search_papers":
                raise ValueError("Legacy tool blocks must be search_papers")
            if set(self.args) - {"query", "top_k", "mode"}:
                raise ValueError("Unsupported search tool arguments")
            if self.hits is None or self.results is None:
                raise ValueError("Legacy search blocks require hits and results")
        return self


class AnswerDisplayBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["answer"]
    text: str = Field(max_length=80_000)
    done: Literal[True] = True
    citations: list[CitationSnapshot] = Field(default_factory=list, max_length=20)


class McpAppInput(BaseModel):
    """The only reconstructable App input retained in chat history."""

    model_config = ConfigDict(extra="forbid")
    elements: str = Field(min_length=2, max_length=128 * 1024)

    @field_validator("elements")
    @classmethod
    def validate_json(cls, value: str) -> str:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("App elements must be JSON") from exc
        if not isinstance(parsed, list):
            raise ValueError("App elements must be a JSON array")
        return value


class McpAppResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: list[ToolTextContent] = Field(default_factory=list, max_length=1)
    # Checkpoint IDs are retained only for the owner projection.  Public-share
    # projection removes them before it leaves the authenticated session.
    structuredContent: dict[str, str] = Field(default_factory=dict, max_length=4)
    isError: bool = False

    @field_validator("structuredContent")
    @classmethod
    def validate_result(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) - {"checkpointId"}:
            raise ValueError("Unsupported App result field")
        if any(len(item) > 512 for item in value.values()):
            raise ValueError("App result field is too large")
        return value


class AppDisplayBlock(BaseModel):
    """Closed, bounded projection for a remote MCP App instance."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["app"]
    schema_version: Literal[1] = 1
    # Worker tool call IDs are reused as instance IDs.  OpenAI Responses IDs
    # take the form ``call_<id>|fc_<id>`` (up to ~90 characters in practice),
    # so this bound matches ``ToolDisplayBlock.id`` rather than a bare UUID.
    instance_id: str = Field(min_length=1, max_length=200)
    provider: Literal["excalidraw"]
    server: Literal["excalidraw"]
    tool: Literal["create_view"]
    resource_uri: Literal["ui://excalidraw/mcp-app.html"]
    resource_version: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    status: Literal["loading", "ready", "error", "unavailable", "incompatible"]
    input: McpAppInput
    result: McpAppResult = Field(default_factory=McpAppResult)
    csp: dict[str, list[str]] = Field(default_factory=dict, max_length=12)
    permissions: dict[str, bool] = Field(default_factory=dict, max_length=2)
    height: int = Field(default=525, ge=240, le=720)
    public_fork: bool = False

    @field_validator("csp")
    @classmethod
    def validate_csp(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        if any(len(key) > 64 or len(items) > 16 for key, items in value.items()):
            raise ValueError("Invalid App CSP")
        if len(json.dumps(value, ensure_ascii=False).encode()) > 8_192:
            raise ValueError("App CSP is too large")
        return value


class LatexPaperFile(BaseModel):
    """One bounded file entry in an immutable LaTeX paper source manifest."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=300)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=0, le=8 * 1024 * 1024)
    media_type: Literal[
        "text/x-tex",
        "application/x-bibtex",
        "image/png",
        "image/jpeg",
        "application/pdf",
    ]
    blob_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if (
            normalized != value
            or normalized.startswith("/")
            or "//" in normalized
            or any(part in {"", ".", ".."} for part in normalized.split("/"))
        ):
            raise ValueError("Paper file path must be a normalized relative path")
        return value

    @model_validator(mode="after")
    def validate_blob_reference(self) -> "LatexPaperFile":
        is_figure = self.media_type in {"image/png", "image/jpeg", "application/pdf"}
        if is_figure != (self.blob_digest is not None):
            raise ValueError("Only figures may have a content-addressed blob reference")
        return self


class LatexPaperDisplayMetadata(BaseModel):
    """Small, safe summary that can be projected without source bytes."""

    model_config = ConfigDict(extra="forbid")

    summary: str | None = Field(default=None, max_length=500)
    unresolved_todo_count: int = Field(default=0, ge=0, le=10_000)
    warning_count: int = Field(default=0, ge=0, le=10_000)


class LatexPaperVersionProvenance(BaseModel):
    """Bounded authorship and change context for an immutable paper version."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["human_save", "ai_draft", "ai_repair", "restore"]
    model_identity: str | None = Field(default=None, max_length=300)
    change_summary: str | None = Field(default=None, max_length=500)
    changed_files: list[
        Annotated[str, StringConstraints(min_length=1, max_length=300)]
    ] = Field(default_factory=list, max_length=100)
    reference_changes: list[
        Annotated[str, StringConstraints(min_length=1, max_length=500)]
    ] = Field(default_factory=list, max_length=50)
    restored_from_version_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_actor_details(self) -> "LatexPaperVersionProvenance":
        if self.action in {"ai_draft", "ai_repair"} and not self.model_identity:
            raise ValueError("AI paper versions require a model identity")
        if self.action in {"human_save", "restore"} and self.model_identity:
            raise ValueError("Human and restore versions cannot claim an AI model")
        if self.action != "restore" and self.restored_from_version_id is not None:
            raise ValueError("Only restore versions can name a restored source")
        for path in self.changed_files:
            if (
                path.startswith("/")
                or "\\" in path
                or any(part in {"", ".", ".."} for part in path.split("/"))
            ):
                raise ValueError(
                    "Changed paper file paths must be normalized and relative"
                )
        return self


class LatexPaperManifest(BaseModel):
    """Kind-specific immutable source manifest for a private LaTeX paper."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    kind: Literal["latex_paper"] = "latex_paper"
    title: str = Field(min_length=1, max_length=300)
    root_document: str = Field(min_length=1, max_length=300)
    files: list[LatexPaperFile] = Field(min_length=1, max_length=100)
    display_metadata: LatexPaperDisplayMetadata = Field(
        default_factory=LatexPaperDisplayMetadata
    )

    @model_validator(mode="after")
    def validate_files(self) -> "LatexPaperManifest":
        paths = [file.path for file in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("Paper manifest contains duplicate file paths")
        root = next(
            (file for file in self.files if file.path == self.root_document), None
        )
        if (
            root is None
            or root.media_type != "text/x-tex"
            or not root.path.endswith(".tex")
        ):
            raise ValueError("Paper root document must be a declared TeX file")
        return self


class LatexPaperVersionDescriptor(BaseModel):
    """Bounded API descriptor for one immutable paper source version."""

    model_config = ConfigDict(extra="forbid")

    version_id: uuid.UUID
    version: int = Field(ge=1, le=10_000)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    compile_status: Literal["queued", "compiling", "succeeded", "failed"]
    created_at: datetime | None = None
    actor_type: Literal["ai", "human", "restore"] = "human"
    parent_version_id: uuid.UUID | None = None
    preview_head_version_id: uuid.UUID | None = None
    compile_diagnostics: list["LatexPaperDiagnostic"] = Field(
        default_factory=list, max_length=20
    )
    repair_attempts_remaining: int = Field(default=3, ge=0, le=3)
    repair_exhausted: bool = False
    generation_provenance: dict | None = None
    display_metadata: LatexPaperDisplayMetadata = Field(
        default_factory=LatexPaperDisplayMetadata
    )
    provenance: LatexPaperVersionProvenance = Field(
        default_factory=lambda: LatexPaperVersionProvenance(action="human_save")
    )

    @model_validator(mode="after")
    def validate_preview_head(self) -> "LatexPaperVersionDescriptor":
        if (
            self.preview_head_version_id == self.version_id
            and self.compile_status != "succeeded"
        ):
            raise ValueError(
                "An uncompiled source version cannot point at itself as preview"
            )
        return self


class LatexPaperDiagnostic(BaseModel):
    """Normalized, bounded compiler feedback safe to show in the paper canvas."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["error", "warning"]
    phase: str | None = Field(default=None, max_length=64)
    file: str | None = Field(default=None, max_length=300)
    line: int | None = Field(default=None, ge=1, le=1_000_000)
    message: str = Field(min_length=1, max_length=1000)


class LatexPaperArtifactDescriptor(BaseModel):
    """Private paper descriptor with intentionally independent source and preview heads."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    source_head: LatexPaperVersionDescriptor | None = None
    preview_head: LatexPaperVersionDescriptor | None = None
    editing_enabled: bool = False


class LatexPaperSourceEdit(BaseModel):
    """One editable UTF-8 source file from an explicit human save."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=300)
    content: str = Field(max_length=2 * 1024 * 1024)


class LatexPaperSaveCompileRequest(BaseModel):
    """The complete browser working copy guarded by its checked-out parent."""

    model_config = ConfigDict(extra="forbid")

    expected_parent_version_id: uuid.UUID
    files: list[LatexPaperSourceEdit] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_paths(self) -> "LatexPaperSaveCompileRequest":
        if len({file.path for file in self.files}) != len(self.files):
            raise ValueError("Paper save contains duplicate file paths")
        return self


class LatexPaperRestoreRequest(BaseModel):
    """Restore a historical source snapshot as an immutable child of the head."""

    model_config = ConfigDict(extra="forbid")

    source_version_id: uuid.UUID
    expected_parent_version_id: uuid.UUID


class LatexPaperHistoryPage(BaseModel):
    """A bounded, newest-first page of paper version audit metadata."""

    model_config = ConfigDict(extra="forbid")

    items: list[LatexPaperVersionDescriptor] = Field(
        default_factory=list, max_length=50
    )
    next_cursor: str | None = Field(default=None, max_length=16)


class ArtifactDisplayBlock(BaseModel):
    """Bounded Posterly descriptor; artifact bytes always live out of band."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["artifact"]
    schema_version: Literal[1] = 1
    scope: Literal["owner", "public"] = "owner"
    publication_id: str | None = Field(default=None, min_length=1, max_length=64)
    artifact_id: uuid.UUID | None = None
    version_id: uuid.UUID | None = None
    public_capability: uuid.UUID | None = None
    identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    version: int | None = Field(default=None, ge=1, le=10_000)
    artifact_kind: Literal["posterly"] = "posterly"
    title: str = Field(min_length=1, max_length=300)
    status: Literal["generating", "ready", "error"]
    phase: (
        Literal[
            "preparing_paper",
            "designing_poster",
            "checking_poster",
            "rendering_poster",
            "publishing_poster",
        ]
        | None
    ) = None
    preview_mime: Literal["image/png"] | None = None
    source_language: Literal["html"] | None = None
    gate_status: Literal["passed", "warnings", "failed"] | None = None
    total_bytes: int | None = Field(default=None, ge=0, le=32 * 1024 * 1024)
    error_code: str | None = Field(default=None, min_length=1, max_length=64)
    error_message: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_scope_and_status(self) -> "ArtifactDisplayBlock":
        if self.status == "generating":
            if self.scope != "owner" or not self.publication_id or self.phase is None:
                raise ValueError(
                    "Generating artifacts require owner correlation and phase"
                )
            if any(
                value is not None
                for value in (
                    self.artifact_id,
                    self.version_id,
                    self.public_capability,
                    self.version,
                    self.preview_mime,
                    self.source_language,
                    self.gate_status,
                    self.total_bytes,
                )
            ):
                raise ValueError("Generating artifacts cannot expose ready metadata")
            return self
        if self.status == "error":
            if (
                self.scope != "owner"
                or not self.publication_id
                or not self.error_code
                or not self.error_message
                or self.phase is not None
            ):
                raise ValueError(
                    "Failed artifacts require bounded owner error metadata"
                )
            if any(
                value is not None
                for value in (
                    self.artifact_id,
                    self.version_id,
                    self.public_capability,
                    self.version,
                    self.preview_mime,
                    self.source_language,
                    self.gate_status,
                    self.total_bytes,
                )
            ):
                raise ValueError("Failed artifacts cannot expose ready metadata")
            return self
        if self.error_code is not None or self.error_message is not None:
            raise ValueError("Ready artifacts cannot contain failure metadata")
        if self.phase is not None or self.version is None or self.gate_status is None:
            raise ValueError("Ready artifacts require version and gate metadata")
        if self.preview_mime != "image/png" or self.total_bytes is None:
            raise ValueError("Ready artifacts require a validated PNG and byte count")
        if self.scope == "owner":
            if self.artifact_id is None or self.version_id is None:
                raise ValueError("Owner artifacts require private IDs")
            if self.public_capability is not None or self.source_language != "html":
                raise ValueError("Owner artifact metadata is inconsistent")
        elif (
            self.public_capability is None
            or self.artifact_id is not None
            or self.version_id is not None
            or self.publication_id is not None
            or self.source_language is not None
        ):
            raise ValueError("Public artifacts require only a public capability")
        return self


DisplayBlock = Annotated[
    Union[
        ReasoningDisplayBlock,
        ToolDisplayBlock,
        AppDisplayBlock,
        ArtifactDisplayBlock,
        AnswerDisplayBlock,
    ],
    Field(discriminator="kind"),
]
DISPLAY_BLOCKS_ADAPTER = TypeAdapter(list[DisplayBlock])


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    turn_id: uuid.UUID
    sequence: int
    role: Literal["user", "assistant"]
    content: str
    paper_mentions: list[PaperMentionSnapshot] = Field(default_factory=list)
    paper_selection: PaperSelectionSnapshot | None = None
    viewer_context: ViewerContextRequest | None = None
    revision: int
    status: str
    citations: list[CitationSnapshot] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)
    display_blocks: list[DisplayBlock] = Field(default_factory=list)
    model: str | None = None
    reasoning_effort: ReasoningEffort = "high"
    finish_reason: FinishReason | None = None
    error_code: str | None = None
    created_at: datetime


class ChatShareSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    share_id: uuid.UUID
    public_path: str = Field(max_length=64)
    created_at: datetime
    updated_at: datetime


class PublicChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str = Field(max_length=256_000)
    paper_mentions: list[PaperMentionSnapshot] = Field(default_factory=list)
    paper_selection: PaperSelectionSnapshot | None = None
    display_blocks: list[DisplayBlock] = Field(default_factory=list)
    citations: list[CitationSnapshot] = Field(default_factory=list, max_length=20)
    model: str | None = Field(default=None, max_length=255)
    display_state: Literal["complete", "interrupted", "failed"] = "complete"
    finish_reason: FinishReason | Literal["stopped"] | None = None
    error: str | None = Field(default=None, max_length=500)


class ChatShareDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    share_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model: str | None = Field(default=None, max_length=255)
    model_label: str | None = Field(default=None, max_length=255)
    model_provider: Literal["huggingface", "openrouter", "openai"] | None = None
    messages: list[PublicChatMessage]


class ChatSessionSummary(BaseModel):
    id: uuid.UUID
    title: str
    selected_model: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    is_busy: bool = False
    web_search_enabled: bool = False
    reasoning_effort: ReasoningEffort = "high"
    primary_paper: PrimaryPaperProjection | None = None


class ChatSessionDetail(ChatSessionSummary):
    messages: list[ChatMessageResponse]
    transcript_status: str
    latex_paper: LatexPaperArtifactDescriptor | None = None


class ChatSessionList(BaseModel):
    items: list[ChatSessionSummary]
    next_cursor: str | None = None


class ArchiveOldChatsResponse(BaseModel):
    archived_count: int = Field(ge=0)


class CreateSessionRequest(BaseModel):
    selected_model: str | None = None
    reasoning_effort: ReasoningEffort = "medium"


class UpdateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=80)
    selected_model: str | None = None
    reasoning_effort: ReasoningEffort | None = None

    @model_validator(mode="after")
    def one_change(self) -> "UpdateSessionRequest":
        if (
            self.title is None
            and self.selected_model is None
            and self.reasoning_effort is None
        ):
            raise ValueError("Supply a title, selected_model, or reasoning_effort")
        if self.title is not None and not " ".join(self.title.split()):
            raise ValueError("Title must not be empty")
        return self


class ChatAvailabilityResponse(BaseModel):
    status: Literal["available", "paused"]
    reason: Literal["chat_temporarily_disabled"] | None = None
    expected_recovery_at: datetime | None = None
    paper_mentions_enabled: bool = False
    web_search_available: bool = False
    native_pdf_reader_enabled: bool = False
    paper_reader_chat_enabled: bool = False
    paper_reader_selection_enabled: bool = False
    paper_reader_citations_enabled: bool = False
    paper_artifacts_enabled: bool = False


class ChatAutocompleteVocabularyResponse(BaseModel):
    names: list[str]


class ChatWebSearchEventResponse(BaseModel):
    id: str
    type: str
    error_class: str | None = None
    created_at: datetime
    details: dict[str, object]


class ChatWebSearchBudgetResponse(BaseModel):
    environment: str
    billing_cycle: str
    cycle_end_at: datetime
    available: bool
    warning_calls: int
    hard_limit_calls: int
    call_count: int
    remaining_calls: int
    success_count: int
    failure_count: int
    provider_cost_microusd: int
    last_latency_ms: int | None = None
    last_result_count: int | None = None
    circuit_state: Literal["armed", "warning", "cooldown", "tripped"]
    trip_reason: str | None = None
    cooldown_until: datetime | None = None
    last_provider_error_class: str | None = None
    events: list[ChatWebSearchEventResponse]


class ChatSandboxSpendEventResponse(BaseModel):
    id: str
    type: str
    severity: str
    reason: str | None = None
    created_at: datetime
    details: dict[str, object]


class ChatSandboxDailySpendResponse(BaseModel):
    date: str
    blank_pool_microusd: int
    assigned_microusd: int


class ChatSandboxPriorCycleResponse(BaseModel):
    billing_cycle: str
    estimated_microusd: int
    provider_floor_microusd: int
    effective_microusd: int


class ChatSandboxSpendResponse(BaseModel):
    environment: str
    provider_mode: Literal["starter_workspace", "team_environments"]
    billing_cycle: str
    cycle_end_at: datetime
    circuit_state: Literal["armed", "warning", "tripped"]
    trip_reason: str | None = None
    tripped_at: datetime | None = None
    estimated_microusd: int
    provider_floor_microusd: int
    effective_microusd: int
    warning_microusd: int
    application_cap_microusd: int
    environment_cap_microusd: int | None = None
    workspace_cap_microusd: int
    remaining_microusd: int
    outstanding_reservation_microusd: int
    last_metered_at: datetime | None = None
    last_reconciled_at: datetime | None = None
    last_reconciliation_attempt_at: datetime | None = None
    next_reconciliation_at: datetime | None = None
    reconciliation_state: Literal["fresh", "stale", "unavailable"]
    live_count: int
    termination_uncertain_count: int
    live_states: dict[str, int]
    oldest_live_at: datetime | None = None
    burn_rate_microusd_per_hour: int | None = None
    projected_cap_hit_at: datetime | None = None
    prior_cycle: ChatSandboxPriorCycleResponse | None = None
    daily_spend: list[ChatSandboxDailySpendResponse]
    events: list[ChatSandboxSpendEventResponse]


class ChatQualificationScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    run_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    profile: Literal["32-functional-turns", "100-immediate-admission"]


class ChatQualificationScopeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    scope_id: uuid.UUID
    run_id: str
    profile: Literal["32-functional-turns", "100-immediate-admission"]
    app_release_id: str
    window_started_at: datetime
    expires_at: datetime


class ChatQualificationEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    scope_id: uuid.UUID = Field(strict=False)


class ChatQualificationTeardownResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_tool_turns: Literal[0, 16]
    targeted_sessions: int = Field(ge=0, le=16)
    closed_intervals: int = Field(ge=0, le=16)
    eviction_events: int = Field(ge=0, le=16)
    source: Literal["exact_scope_canonical_eviction"]


class ChatQualificationServerLatencyP95(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    provider_gateway_received_ms: int = Field(ge=0, le=600_000)
    provider_ttft_ms: int = Field(ge=0, le=600_000)
    first_semantic_event_ms: int = Field(ge=0, le=600_000)


class ChatQualificationEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_users: Literal[32, 100]
    admitted_turns: int = Field(ge=0, le=100)
    admission_denominator_events: int = Field(ge=0, le=100)
    terminal_turns: int = Field(ge=0, le=100)
    queued_states: int = Field(ge=0, le=1_000_000)
    stale_fences: int = Field(ge=0, le=1_000_000)
    executor_starts: int = Field(ge=0, le=1_000_000)
    duplicate_executor_starts: int = Field(ge=0, le=1_000_000)
    workspace_creates: int = Field(ge=0, le=1_000_000)
    workspace_reuses: int = Field(ge=0, le=1_000_000)
    workspace_evictions: int = Field(ge=0, le=1_000_000)
    billed_duration_ms: int = Field(ge=0, le=2**63 - 1)
    window_started_at_ms: int = Field(ge=1, le=2**63 - 1)
    window_ended_at_ms: int = Field(ge=1, le=2**63 - 1)
    p95_server_latency_ms_by_workload: dict[
        Literal["no_tool", "read", "bash"], ChatQualificationServerLatencyP95
    ] = Field(max_length=3)
    source: Literal["durable_qualification_records"]


class _StrictEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StreamStartEvent(_StrictEvent):
    type: Literal["stream_start"]
    request_id: str
    session_id: uuid.UUID
    provider_execution: bool = True


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
    redacted: bool = False


class ToolCallStartEvent(_StrictEvent):
    type: Literal["tool_call_start"]
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=64)
    content_index: int = Field(ge=-1, le=10_000)
    redacted: bool = False


class ToolCallArgumentsDeltaEvent(_StrictEvent):
    type: Literal["tool_call_arguments_delta"]
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=64)
    delta: str = Field(min_length=1, max_length=65_536)
    partial_args: dict[str, object]
    snapshot: bool = False
    redacted: bool = False


class ToolCallArgumentsDoneEvent(_StrictEvent):
    type: Literal["tool_call_arguments_done"]
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=64)
    args: dict[str, object]
    redacted: bool = False


class ToolResultEvent(_StrictEvent):
    type: Literal["tool_result"]
    id: str
    status: Literal["success", "error", "denied"] | None = None
    took_ms: int
    content: list[ToolTextContent] | None = None
    metadata: ToolResultMetadata | None = None
    # Legacy local_mcp shape.
    hits: int | None = None
    results: list[ChatPaperHit] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ToolResultEvent":
        legacy = self.hits is not None or self.results is not None
        generic = self.status is not None or self.content is not None
        if legacy == generic:
            raise ValueError("Tool result must be exactly one of legacy or generic")
        if legacy and (self.hits is None or self.results is None):
            raise ValueError("Legacy tool result requires hits and results")
        if generic and (self.status is None or self.content is None):
            raise ValueError("Generic tool result requires status and content")
        return self


class SandboxStartEvent(_StrictEvent):
    type: Literal["sandbox_start"]
    session_id: uuid.UUID


class SandboxReadyEvent(_StrictEvent):
    type: Literal["sandbox_ready"]
    session_id: uuid.UUID
    cold_start_ms: int = Field(ge=0, le=600_000)


class WorkspaceReadyEvent(_StrictEvent):
    """Backend-neutral marker emitted immediately before model query dispatch."""

    type: Literal["workspace_ready"]


class LifecycleEvent(_StrictEvent):
    """Truthful, non-semantic progress before model-originated output."""

    type: Literal["lifecycle"]
    phase: Literal["preparing_workspace", "starting_agent", "connecting_model"]


class AnswerDeltaEvent(_StrictEvent):
    type: Literal["answer_delta"]
    text: str


class DoneEvent(_StrictEvent):
    type: Literal["done"]
    followups: list[str] = Field(default_factory=list)
    finish_reason: FinishReason | Literal["stopped"] = "success"
    citations: list[CitationSnapshot] = Field(default_factory=list, max_length=20)


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


class AppStartEvent(_StrictEvent):
    type: Literal["app_start"]
    id: str
    instance_id: str = Field(min_length=1, max_length=200)
    provider: Literal["excalidraw"]
    server: Literal["excalidraw"]
    tool: Literal["create_view"]
    resource_uri: Literal["ui://excalidraw/mcp-app.html"]
    input: McpAppInput


class AppResultEvent(_StrictEvent):
    type: Literal["app_result"]
    id: str
    status: Literal["ready", "error"]
    took_ms: int = Field(ge=0)
    result: McpAppResult


class ArtifactStartEvent(_StrictEvent):
    type: Literal["artifact_start"]
    publication_id: str = Field(
        min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )
    identifier: str = Field(
        min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    kind: Literal["posterly"]
    title: str = Field(min_length=1, max_length=300)


class ArtifactReadyEvent(ArtifactStartEvent):
    type: Literal["artifact_ready"]
    artifact_id: uuid.UUID
    version_id: uuid.UUID
    version: int = Field(ge=1)
    preview_mime: Literal["image/png"]
    source_language: Literal["html"]
    gate_status: Literal["passed", "warnings", "failed"]
    total_bytes: int = Field(ge=0, le=32 * 1024 * 1024)


class ArtifactErrorEvent(_StrictEvent):
    type: Literal["artifact_error"]
    publication_id: str = Field(
        min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )
    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=500)


class PaperArtifactEvent(_StrictEvent):
    """Private-paper lifecycle marker emitted after a trusted worker receipt."""

    type: Literal["paper_artifact"]
    operation: Literal["create", "begin-edit", "draft", "repair"]
    activated: bool
    descriptor: LatexPaperArtifactDescriptor


ChatEvent = Annotated[
    Union[
        StreamStartEvent,
        ReasoningStartEvent,
        ReasoningDeltaEvent,
        ReasoningEndEvent,
        ToolCallEvent,
        ToolCallStartEvent,
        ToolCallArgumentsDeltaEvent,
        ToolCallArgumentsDoneEvent,
        ToolResultEvent,
        AppStartEvent,
        AppResultEvent,
        ArtifactStartEvent,
        ArtifactReadyEvent,
        ArtifactErrorEvent,
        PaperArtifactEvent,
        SandboxStartEvent,
        SandboxReadyEvent,
        WorkspaceReadyEvent,
        LifecycleEvent,
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
