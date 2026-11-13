"""Self-contained tool accounting and bounded inert output."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from backend.chat_execution_policy import (
    ANSWER_NOW_REASON,
    normalize_public_https_url,
)

WEB_SEARCH_TOOL = "mcp__web__search_web"
ALLOWED_TOOLS = frozenset({"Bash", "Read", WEB_SEARCH_TOOL})
_HINT = "\n[output truncated; narrow, filter, or paginate the request and try again]\n"
_ANSI = re.compile(rb"(?:\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~])")
_SEARCH = re.compile(r"(?:^|[;&|()\n]\s*)(?:pwc|s2)\s+search(?:\s|$)", re.IGNORECASE)
_URL = re.compile(r'https?://[^\s<>"\\]+', re.IGNORECASE)
_HARD_FAILURE = re.compile(
    r"(?:\b429\b|execution limit|tool limit reached|search limit reached)",
    re.IGNORECASE,
)
_ALWAYS_FETCHABLE_HOSTS = frozenset({"arxiv.org"})
_UNAVAILABLE_TOOL_REASON = "That tool is not available."
_INVALID_WEB_SEARCH_REASON = "Web search is not available for this request."
_INVALID_WEB_FETCH_REASON = (
    "WebFetch requires an approved public HTTPS URL from the user or a prior "
    "catalog tool result."
)
_READ_SCOPE_REASON = (
    "Read and Grep may only access /workspace or the approved CLI guides. "
    "Rerun the source command with output redirected to /workspace, then try again."
)
_INLINED_SKILL_REASON = (
    "The pwc, s2, and restricted hf CLI skills are already included verbatim in "
    "your system prompt. Read that text instead and run the CLI directly."
)


def _prefix(payload: bytes, maximum: int) -> bytes:
    value = payload[:maximum]
    while value:
        try:
            value.decode()
            return value
        except UnicodeDecodeError as error:
            value = value[: error.start]
    return b""


def bound_tool_output(payload: bytes | str, maximum: int) -> tuple[str, bool]:
    if maximum <= 0:
        return "", True
    raw = payload.encode() if isinstance(payload, str) else payload
    raw = _ANSI.sub(b"", raw)
    text = raw.decode(errors="replace")
    clean = "".join(c for c in text if c in "\n\t" or ord(c) >= 0x20).encode()
    if len(clean) <= maximum:
        return clean.decode(), False
    hint = _HINT.encode()
    if maximum < len(hint):
        return _prefix(hint, maximum).decode(), True
    return (_prefix(clean, maximum - len(hint)) + hint).decode(), True


def _inside(value: Path, root: Path) -> bool:
    try:
        value.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _public_url(value: str) -> str | None:
    return normalize_public_https_url(value)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str | None = None


@dataclass
class ToolBudget:
    maximum_calls: int
    maximum_direct_searches: int
    maximum_result_bytes: int
    maximum_turn_output_bytes: int
    maximum_rounds: int = 6
    maximum_web_searches: int = 3
    web_search_enabled: bool = False
    calls: int = 0
    searches: int = 0
    web_searches: int = 0
    web_search_failed: bool = False
    output_bytes: int = 0
    started: dict[str, float] = field(default_factory=dict)
    started_names: dict[str, str] = field(default_factory=dict)
    fetchable_urls: set[str] = field(default_factory=set)
    tool_rounds_started: int = 0
    tool_rounds_denied: int = 0
    tool_rounds_executed: int = 0
    executed_round_numbers: set[int] = field(default_factory=set)
    round_by_tool_id: dict[str, int] = field(default_factory=dict)
    active_round_tool_ids: set[str] = field(default_factory=set)
    tooling_closed: bool = False
    close_reason: str | None = None
    denied_calls: int = 0
    completed_calls: int = 0

    def seed_urls(self, urls: list[str]) -> None:
        self.fetchable_urls = set(urls)

    def register_round(
        self, tool_ids: list[str], maximum_rounds: int | None = None
    ) -> None:
        pending = [
            tool_id for tool_id in tool_ids if tool_id not in self.round_by_tool_id
        ]
        if not pending:
            return
        self.tool_rounds_started += 1
        round_number = self.tool_rounds_started
        for tool_id in pending:
            self.round_by_tool_id[tool_id] = round_number
        if round_number > max(self.maximum_rounds, maximum_rounds or 0):
            self.tool_rounds_denied += 1
            self.close(ANSWER_NOW_REASON)

    def register_call(self, tool_id: str, maximum_rounds: int | None = None) -> None:
        # Pre-tool hooks run before the streamed assistant-message boundary that
        # registers the complete batch. Starts without an intervening result are
        # therefore parallel calls from the same assistant turn.
        if tool_id in self.round_by_tool_id:
            self.active_round_tool_ids.add(tool_id)
            return
        if self.active_round_tool_ids:
            round_number = self.round_by_tool_id[next(iter(self.active_round_tool_ids))]
            self.round_by_tool_id[tool_id] = round_number
        else:
            self.register_round([tool_id], maximum_rounds)
        self.active_round_tool_ids.add(tool_id)

    def complete_call(self, tool_id: str) -> None:
        self.active_round_tool_ids.discard(tool_id)
        self.round_by_tool_id.pop(tool_id, None)

    def close(self, reason: str = ANSWER_NOW_REASON) -> None:
        self.tooling_closed = True
        self.close_reason = reason

    def observe_urls(self, payload: str) -> None:
        for match in _URL.finditer(payload):
            if normalized := _public_url(match.group()):
                self.fetchable_urls.add(normalized)

    def authorize(
        self,
        tool_id: str,
        name: str,
        args: dict[str, Any],
        workspace: Path = Path("/workspace"),
        guide: Path = Path("/opt/pwc/PWC_CLI_SKILL.md"),
        hf_guide: Path = Path("/opt/pwc/HF_CLI_SKILL.md"),
        s2_guide: Path = Path("/opt/pwc/S2_CLI_SKILL.md"),
        posterly_publish_guide: Path = Path("/opt/pwc/POSTERLY_PUBLISH.md"),
        posterly_root: Path = Path("/opt/posterly"),
        maximum_calls: int | None = None,
    ) -> Decision:
        if tool_id not in self.round_by_tool_id:
            # Compatibility fallback for callers that do not expose an SDK
            # assistant-message boundary. Normal execution registers first.
            self.register_round([tool_id])
        if self.tooling_closed:
            self.denied_calls += 1
            return Decision(False, self.close_reason or ANSWER_NOW_REASON)
        if name not in ALLOWED_TOOLS:
            self.denied_calls += 1
            return Decision(False, _UNAVAILABLE_TOOL_REASON)
        if self.calls >= max(self.maximum_calls, maximum_calls or 0):
            self.close()
            self.denied_calls += 1
            return Decision(False, ANSWER_NOW_REASON)
        if name == WEB_SEARCH_TOOL:
            query = args.get("query")
            if (
                not self.web_search_enabled
                or not isinstance(query, str)
                or not query.strip()
                or len(query) > 500
                or set(args) != {"query"}
            ):
                self.denied_calls += 1
                return Decision(False, _INVALID_WEB_SEARCH_REASON)
            if self.web_search_failed:
                self.close()
                self.denied_calls += 1
                return Decision(False, ANSWER_NOW_REASON)
            if self.web_searches >= self.maximum_web_searches:
                self.close()
                self.denied_calls += 1
                return Decision(False, ANSWER_NOW_REASON)
        if name == "WebFetch":
            url = args.get("url")
            normalized = _public_url(url) if isinstance(url, str) else None
            if normalized is None:
                self.denied_calls += 1
                return Decision(False, _INVALID_WEB_FETCH_REASON)
            hostname = urlsplit(normalized).hostname
            if (
                normalized not in self.fetchable_urls
                and hostname not in _ALWAYS_FETCHABLE_HOSTS
            ):
                self.denied_calls += 1
                return Decision(False, _INVALID_WEB_FETCH_REASON)
        if name in {"Read", "Grep"}:
            path = args.get("file_path") or args.get("path")
            if isinstance(path, str):
                candidate = Path(path).resolve(strict=False)
                # These three skills are rendered into the system prompt, so a
                # read is a wasted tool round rather than a scope violation.
                if candidate in {
                    guide.resolve(strict=False),
                    hf_guide.resolve(strict=False),
                    s2_guide.resolve(strict=False),
                }:
                    self.denied_calls += 1
                    return Decision(False, _INLINED_SKILL_REASON)
                if not (
                    _inside(Path(path), workspace)
                    or candidate == posterly_publish_guide.resolve(strict=False)
                    or _inside(Path(path), posterly_root)
                ):
                    self.denied_calls += 1
                    return Decision(False, _READ_SCOPE_REASON)
        search = (
            name == "Bash"
            and isinstance(args.get("command"), str)
            and bool(_SEARCH.search(args["command"]))
        )
        if search and self.searches >= self.maximum_direct_searches:
            self.close()
            self.denied_calls += 1
            return Decision(False, ANSWER_NOW_REASON)
        self.calls += 1
        self.searches += int(search)
        self.web_searches += int(name == WEB_SEARCH_TOOL)
        self.started[tool_id] = time.monotonic()
        self.started_names[tool_id] = name
        round_number = self.round_by_tool_id[tool_id]
        if round_number not in self.executed_round_numbers:
            self.executed_round_numbers.add(round_number)
            self.tool_rounds_executed += 1
        return Decision(True)

    def result(
        self,
        tool_id: str,
        payload: bytes | str,
        *,
        status: Literal["success", "error", "denied"],
        exit_code: int | None = None,
    ) -> dict[str, Any]:
        remaining = max(0, self.maximum_turn_output_bytes - self.output_bytes)
        text, truncated = bound_tool_output(
            payload, min(self.maximum_result_bytes, remaining)
        )
        self.output_bytes += len(text.encode())
        name = self.started_names.pop(tool_id, None)
        hard_failure = bool(_HARD_FAILURE.search(text))
        if name == WEB_SEARCH_TOOL and status != "success":
            self.web_search_failed = True
            self.close()
        elif hard_failure and (status == "error" or name == "Bash"):
            self.close()
            if status == "success":
                status = "error"
                exit_code = exit_code or 1
        if name not in {"WebFetch", WEB_SEARCH_TOOL}:
            self.observe_urls(text)
        started = self.started.pop(tool_id, None)
        if status != "denied":
            self.complete_call(tool_id)
        if started is not None:
            self.completed_calls += 1
        took_ms = round((time.monotonic() - started) * 1000) if started else 0
        return {
            "type": "tool_result",
            "id": tool_id,
            "status": status,
            "took_ms": took_ms,
            "content": [{"type": "text", "text": text, "truncated": truncated}],
            "metadata": {"exit_code": exit_code, "output_truncated": truncated},
        }
