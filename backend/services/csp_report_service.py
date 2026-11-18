"""Collect Content-Security-Policy violation reports for the Report-Only rollout.

Browsers send either Reporting API batches (``application/reports+json``,
``report-to``) or legacy ``application/csp-report`` bodies (``report-uri``).
Both are reduced to a compact record and appended to a size-capped JSONL log
(rotated to ``.1`` at the cap),
so the policy can be tuned from real traffic before it is enforced.
"""

from __future__ import annotations

import fcntl
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from backend.config import Settings

MAX_BODY_BYTES = 64 * 1024
MAX_LOG_BYTES = 50 * 1024 * 1024
MAX_RECORDS_PER_REQUEST = 20
FIELD_LIMIT = 300


def csp_report_log_path(settings: Settings) -> Path | None:
    """Deployed environments log under their writable log directory."""
    if settings.csp_report_log:
        return Path(settings.csp_report_log)
    if settings.is_deployed:
        return Path(f"/var/log/paperswithcode/{settings.environment}/csp-reports.jsonl")
    return None


def _text(value: object) -> str:
    return value[:FIELD_LIMIT] if isinstance(value, str) else ""


def _url(value: object) -> str:
    """Keep scheme, host and path; queries can carry search text or tokens."""
    text = _text(value)
    parts = urlsplit(text)
    if not parts.scheme or not parts.netloc:
        # Keywords such as "inline", "eval", "data" or "blob".
        return text.split("?", 1)[0].split("#", 1)[0]
    return f"{parts.scheme}://{parts.netloc}{parts.path}"[:FIELD_LIMIT]


def _record(
    *, page, blocked, directive, source, line, sample, disposition
) -> dict[str, object]:
    return {
        "page": _url(page),
        "blocked": _url(blocked),
        "directive": _text(directive),
        "source": _url(source),
        "line": line if isinstance(line, int) else None,
        "sample": _text(sample),
        "disposition": _text(disposition),
    }


def parse_csp_reports(payload: object) -> list[dict[str, object]]:
    """Return compact records for CSP violations in either report format."""
    records: list[dict[str, object]] = []
    if isinstance(payload, dict) and isinstance(payload.get("csp-report"), dict):
        report = payload["csp-report"]
        records.append(
            _record(
                page=report.get("document-uri"),
                blocked=report.get("blocked-uri"),
                directive=report.get("effective-directive")
                or report.get("violated-directive"),
                source=report.get("source-file"),
                line=report.get("line-number"),
                sample=report.get("script-sample"),
                disposition=report.get("disposition"),
            )
        )
    elif isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict) or item.get("type") != "csp-violation":
                continue
            body = item.get("body")
            if not isinstance(body, dict):
                continue
            records.append(
                _record(
                    page=body.get("documentURL") or item.get("url"),
                    blocked=body.get("blockedURL"),
                    directive=body.get("effectiveDirective"),
                    source=body.get("sourceFile"),
                    line=body.get("lineNumber"),
                    sample=body.get("sample"),
                    disposition=body.get("disposition"),
                )
            )
    return records[:MAX_RECORDS_PER_REQUEST]


def append_csp_reports(records: list[dict[str, object]], path: Path) -> None:
    """Append records as JSON lines, rotating to ``.1`` at the size cap."""
    if not records:
        return
    received_at = datetime.now(UTC).isoformat(timespec="seconds")
    lines = "".join(
        json.dumps({"at": received_at, **record}, separators=(",", ":")) + "\n"
        for record in records
    )
    # Backend workers are separate processes; serialize check, rotate, append.
    with path.with_name(path.name + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists() and path.stat().st_size >= MAX_LOG_BYTES:
            # Keep one previous file, so a flood shortens history instead of
            # hiding every later report.
            os.replace(path, path.with_name(path.name + ".1"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(lines)
