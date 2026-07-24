"""Self-contained tool accounting and bounded inert output."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

ALLOWED_TOOLS = frozenset({"Bash", "Read", "Grep"})
_HINT = "\n[output truncated; narrow, filter, or paginate the request and try again]\n"
_ANSI = re.compile(rb"(?:\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~])")
_SEARCH = re.compile(r"(?:^|[;&|()\n]\s*)pwc\s+search(?:\s|$)", re.IGNORECASE)


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
    calls: int = 0
    searches: int = 0
    output_bytes: int = 0
    started: dict[str, float] = field(default_factory=dict)

    def authorize(
        self,
        tool_id: str,
        name: str,
        args: dict[str, Any],
        workspace: Path = Path("/workspace"),
        guide: Path = Path("/opt/pwc/CLI_GUIDE.md"),
    ) -> Decision:
        if name not in ALLOWED_TOOLS:
            return Decision(False, "Only Bash, Read, and Grep are available.")
        if self.calls >= self.maximum_calls:
            return Decision(False, "Tool limit reached. Answer from existing evidence.")
        if name in {"Read", "Grep"}:
            path = args.get("file_path") or args.get("path")
            if isinstance(path, str):
                candidate = Path(path)
                if not (
                    _inside(candidate, workspace)
                    or candidate.resolve(strict=False) == guide
                ):
                    return Decision(
                        False,
                        "Read and Grep are limited to the workspace and CLI guide.",
                    )
        search = (
            name == "Bash"
            and isinstance(args.get("command"), str)
            and bool(_SEARCH.search(args["command"]))
        )
        if search and self.searches >= self.maximum_direct_searches:
            return Decision(
                False, "Direct pwc search limit reached. Use papers already found."
            )
        self.calls += 1
        self.searches += int(search)
        self.started[tool_id] = time.monotonic()
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
        started = self.started.pop(tool_id, None)
        took_ms = round((time.monotonic() - started) * 1000) if started else 0
        return {
            "type": "tool_result",
            "id": tool_id,
            "status": status,
            "took_ms": took_ms,
            "content": [{"type": "text", "text": text, "truncated": truncated}],
            "metadata": {"exit_code": exit_code, "output_truncated": truncated},
        }
