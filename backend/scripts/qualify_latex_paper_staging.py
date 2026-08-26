#!/usr/bin/env python3
"""Fail-closed, content-free staging qualification for private LaTeX papers.

The runner uses the active staging Unix socket plus an authenticated headless
browser. It creates only an operator-owned disposable chat and deletes it in
``finally``, except for the explicit kill-switch preservation phase. Its JSON
report deliberately contains no prompt, response, source, diagnostic, URL,
identifier, credential, or trace payload.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
import uuid
from dataclasses import asdict, dataclass
from io import BytesIO
from typing import Any, Awaitable, Callable, Iterable
from urllib.parse import quote
from zipfile import BadZipFile, ZipFile

from backend.config import Settings, get_settings
from backend.routers.auth import _encode_legacy_session
from backend.scripts.qualify_chat_browser import ChromePage
from backend.scripts.staging_qualification_http import STAGING_ORIGIN
from backend.scripts.staging_qualification_http import client as staging_client


CONFIRMATION = "QUALIFY_STAGING_LATEX_PAPER"
LUNA_MODEL = "gpt-5.6-luna@openai"
QUALIFICATION_OWNER_PREFIX = "operator:pi-qualification:"
TURN_TIMEOUT_SECONDS = 240
COMPILE_TIMEOUT_SECONDS = 180
COMPILE_POLL_SECONDS = 1
MAX_CANARY_ARCHIVE_BYTES = 5_000_000
MAX_CANARY_SOURCE_BYTES = 20_000_000
_TELEMETRY_CANARY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{15,255}\Z")
_MUTATION_HEADERS = {
    "Host": "staging.paperswithcode.co",
    "Origin": STAGING_ORIGIN,
    "Sec-Fetch-Site": "same-origin",
}


@dataclass(frozen=True)
class Check:
    """One bounded qualification observation safe to print or retain."""

    name: str
    passed: bool
    elapsed_ms: int
    executed: bool = True


def overall_passed(checks: Iterable[Check]) -> bool:
    """A skipped required gate is never a successful qualification."""

    values = list(checks)
    return bool(values) and all(check.executed and check.passed for check in values)


def unexercised_gates(
    *, expect_enabled: bool, kill_switch_passed: bool | None = None
) -> list[Check]:
    """Make non-deterministic/operator-gated acceptance work visible as unmet.

    The runner must not forge repair history, alter feature flags, or query an
    external trace store with protected credentials. A disabled-mode observation
    is counted only when its actual result is supplied; every unavailable gate
    deliberately remains false rather than being inferred.
    """

    checks = [
        Check(
            name="telemetry_content_free",
            passed=False,
            executed=False,
            elapsed_ms=0,
        ),
        Check(
            name="kill_switch_rollback",
            passed=kill_switch_passed is True,
            executed=kill_switch_passed is not None,
            elapsed_ms=0,
        ),
    ]
    if expect_enabled and kill_switch_passed is not None:
        raise ValueError("enabled runs cannot claim a kill-switch observation")
    return checks


def report(checks: Iterable[Check]) -> dict[str, object]:
    """Return only check names, booleans, and timings."""

    values = list(checks)
    return {
        "checks": [asdict(check) for check in values],
        "passed": overall_passed(values),
    }


def _paper_flags_enabled(settings: Settings) -> bool:
    return bool(
        settings.chat_artifacts_enabled
        and settings.chat_latex_paper_enabled
        and settings.chat_latex_compiler_jobs_enabled
    )


def validate_settings(settings: Settings, *, expect_enabled: bool) -> None:
    """Refuse any non-staging or unexpectedly configured qualification run."""

    if settings.environment != "staging":
        raise ValueError("Qualification requires PWC_ENVIRONMENT=staging")
    if settings.chat_posterly_enabled or settings.chat_artifact_shared_preview_enabled:
        raise ValueError(
            "private paper qualification requires Posterly and shared previews off"
        )
    enabled = _paper_flags_enabled(settings)
    if expect_enabled and not enabled:
        raise ValueError("paper feature flags must be enabled for this run")
    if not expect_enabled and enabled:
        raise ValueError("paper feature flags must be off for this run")


def validate_qualification_owner(qualification_owner: str) -> None:
    """Restrict the runner to the staged Pi owner namespace only."""

    if (
        not qualification_owner.startswith(QUALIFICATION_OWNER_PREFIX)
        or len(qualification_owner) > 128
    ):
        raise ValueError("qualification owner must use a protected Pi operator prefix")


def validate_phase(
    *,
    expect_enabled: bool,
    preserve_for_kill_switch: bool,
    verify_historical: bool,
) -> None:
    """Keep the two kill-switch phases ordered and incapable of flag mutation."""

    if preserve_for_kill_switch and verify_historical:
        raise ValueError("kill-switch phase flags are mutually exclusive")
    if preserve_for_kill_switch and not expect_enabled:
        raise ValueError("preserve-for-kill-switch requires enabled paper flags")
    if verify_historical and expect_enabled:
        raise ValueError("verify-historical requires disabled paper flags")


def validate_telemetry_canary(canary: str | None) -> None:
    """Accept only a bounded opaque marker that is safe inside a TeX comment."""

    if canary is None:
        return
    if not _TELEMETRY_CANARY.fullmatch(canary):
        raise ValueError("telemetry canary must be a 16-256 character opaque marker")


def private_authoring_prompt(prompt: str, telemetry_canary: str | None) -> str:
    """Add a private marker to the authoring input without ever reporting it."""

    validate_telemetry_canary(telemetry_canary)
    if telemetry_canary is None:
        return prompt
    return (
        f"{prompt} Include the exact opaque private manuscript marker "
        f"{telemetry_canary} in a LaTeX comment in the private draft."
    )


def validate_selected_model(models: dict[str, Any], model: str) -> None:
    """Require Luna as both the staging default and the explicit test selection."""

    if "luna" not in model.casefold():
        raise ValueError("qualification requires an explicit Luna model")
    choices = {
        str(item.get("id"))
        for item in models.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if model not in choices:
        raise ValueError("explicit Luna model is not in discovered staging models")
    if models.get("default_model") != model:
        raise ValueError(
            "qualification requires the selected Luna model to be default Luna"
        )


def summarize_event(event: dict[str, Any]) -> dict[str, object]:
    """Extract only safe structural fields from an SSE event.

    Never return an answer delta, title, source, diagnostic, tool argument, or
    tool result.  Artifact IDs stay in memory solely to drive private API calls
    and are not included in the final report.
    """

    kind = str(event.get("type") or "")
    result: dict[str, object] = {"kind": kind}
    if kind == "paper_artifact":
        descriptor = event.get("descriptor")
        artifact_id = (
            descriptor.get("artifact_id") if isinstance(descriptor, dict) else None
        )
        result.update(
            paper_artifact=True,
            paper_operation=str(event.get("operation") or ""),
            paper_activated=event.get("activated") is True,
        )
        if isinstance(artifact_id, str):
            result["artifact_id"] = artifact_id
    return result


@dataclass(frozen=True)
class TurnObservation:
    """Content-free facts retained from one streamed turn."""

    terminal: bool
    successful: bool
    had_error: bool
    paper_artifact_id: str | None
    paper_activated: bool
    paper_operation: str | None
    paper_operations: tuple[str, ...]
    citations_structural: bool


@dataclass(frozen=True)
class PaperState:
    """Private identifiers held only long enough to exercise owner APIs."""

    source_version_id: str | None
    source_status: str | None
    source_actor_type: str | None
    preview_version_id: str | None
    repair_attempts_remaining: int | None = None
    repair_exhausted: bool = False


async def _check(
    checks: list[Check],
    name: str,
    operation: Callable[[], Awaitable[bool]],
) -> bool:
    """Record a boolean result without leaking an exception or response body."""

    started = time.perf_counter()
    try:
        passed = bool(await operation())
    except Exception:
        passed = False
    checks.append(
        Check(
            name=name,
            passed=passed,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )
    )
    return passed


def _json_object(response) -> dict[str, Any] | None:
    """Parse an object internally; callers must never print its contents."""

    try:
        value = response.json()
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _citation_structure(value: object) -> bool:
    return bool(
        isinstance(value, list)
        and value
        and all(
            isinstance(item, dict) and isinstance(item.get("kind"), str)
            for item in value
        )
    )


async def stream_turn(client, *, session_id: str, prompt: str) -> TurnObservation:
    """Drive a turn while discarding every text-bearing SSE field immediately."""

    terminal = False
    successful = False
    had_error = False
    paper_artifact_id: str | None = None
    paper_activated = False
    paper_operation: str | None = None
    paper_operations: list[str] = []
    citations_structural = False
    payload = {
        "session_id": session_id,
        "message": prompt,
        "client_message_id": str(uuid.uuid4()),
        "reasoning_effort": "high",
    }
    async with client.stream("POST", "/api/v1/chat/stream", json=payload) as response:
        if response.status_code != 200:
            return TurnObservation(
                terminal=False,
                successful=False,
                had_error=True,
                paper_artifact_id=None,
                paper_activated=False,
                paper_operation=None,
                paper_operations=(),
                citations_structural=False,
            )
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            summary = summarize_event(event)
            if summary.get("kind") == "paper_artifact":
                value = summary.get("artifact_id")
                paper_artifact_id = value if isinstance(value, str) else None
                paper_activated = (
                    paper_activated or summary.get("paper_activated") is True
                )
                operation = summary.get("paper_operation")
                paper_operation = operation if isinstance(operation, str) else None
                if paper_operation:
                    paper_operations.append(paper_operation)
            elif summary.get("kind") == "done":
                terminal = True
                successful = event.get("finish_reason") == "success"
                citations_structural = _citation_structure(event.get("citations"))
            elif summary.get("kind") == "error":
                terminal = True
                had_error = True
    return TurnObservation(
        terminal=terminal,
        successful=successful,
        had_error=had_error,
        paper_artifact_id=paper_artifact_id,
        paper_activated=paper_activated,
        paper_operation=paper_operation,
        paper_operations=tuple(paper_operations),
        citations_structural=citations_structural,
    )


async def create_qualification_session(
    client, *, model: str
) -> tuple[str | None, bool]:
    """Create an explicit operator-owned Pi session and verify its model pin."""

    response = await client.post(
        "/api/v1/chat/admin/sessions",
        json={
            "agent_harness": "pi",
            "selected_model": model,
            "reasoning_effort": "high",
        },
    )
    payload = _json_object(response)
    session_id = payload.get("id") if payload else None
    selected = payload.get("selected_model") if payload else None
    return (
        session_id
        if response.status_code == 201 and isinstance(session_id, str)
        else None,
        response.status_code == 201 and selected == model,
    )


def paper_state(descriptor: dict[str, Any]) -> PaperState:
    """Read only compile state and opaque IDs from a private descriptor."""

    source = descriptor.get("source_head")
    preview = descriptor.get("preview_head")
    return PaperState(
        source_version_id=(
            source.get("version_id")
            if isinstance(source, dict) and isinstance(source.get("version_id"), str)
            else None
        ),
        source_status=(
            source.get("compile_status")
            if isinstance(source, dict)
            and isinstance(source.get("compile_status"), str)
            else None
        ),
        source_actor_type=(
            source.get("actor_type")
            if isinstance(source, dict) and isinstance(source.get("actor_type"), str)
            else None
        ),
        preview_version_id=(
            preview.get("version_id")
            if isinstance(preview, dict) and isinstance(preview.get("version_id"), str)
            else None
        ),
        repair_attempts_remaining=(
            source.get("repair_attempts_remaining")
            if isinstance(source, dict)
            and isinstance(source.get("repair_attempts_remaining"), int)
            else None
        ),
        repair_exhausted=(
            source.get("repair_exhausted") is True
            if isinstance(source, dict)
            else False
        ),
    )


def bounded_repair_passes(
    turn: TurnObservation,
    state: PaperState,
    *,
    failed_source_id: str,
    preserved_preview_id: str,
) -> bool:
    """Require exactly three repair receipts without accepting a new source head."""

    return bool(
        turn.terminal
        and turn.successful
        and not turn.had_error
        and turn.paper_operations.count("repair") == 3
        and state.source_version_id == failed_source_id
        and state.source_status == "failed"
        and state.preview_version_id == preserved_preview_id
        and state.repair_attempts_remaining == 0
        and state.repair_exhausted
    )


async def get_descriptor(client, artifact_id: str) -> dict[str, Any] | None:
    response = await client.get(f"/api/v1/chat/artifacts/{artifact_id}")
    return _json_object(response) if response.status_code == 200 else None


async def wait_for_compile(
    client, artifact_id: str
) -> tuple[dict[str, Any] | None, PaperState]:
    """Poll owner reconciliation until a source head reaches a terminal state."""

    deadline = time.monotonic() + COMPILE_TIMEOUT_SECONDS
    latest: dict[str, Any] | None = None
    state = PaperState(None, None, None, None)
    while time.monotonic() < deadline:
        response = await client.post(
            f"/api/v1/chat/artifacts/{artifact_id}/refresh-compile",
            headers=_MUTATION_HEADERS,
        )
        if response.status_code != 200:
            return None, state
        latest = _json_object(response)
        if latest is None:
            return None, state
        state = paper_state(latest)
        if state.source_status in {"succeeded", "failed"}:
            return latest, state
        await asyncio.sleep(COMPILE_POLL_SECONDS)
    return latest, state


async def manifest_files(
    client, artifact_id: str, version_id: str
) -> tuple[str | None, list[dict[str, str]]] | None:
    """Fetch text files only to submit a complete, disposable owner edit."""

    manifest_response = await client.get(
        f"/api/v1/chat/artifacts/{artifact_id}/versions/{version_id}/manifest"
    )
    manifest = _json_object(manifest_response)
    if manifest_response.status_code != 200 or manifest is None:
        return None
    root = manifest.get("root_document")
    entries = manifest.get("files")
    if not isinstance(root, str) or not isinstance(entries, list):
        return None
    values: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            return None
        path = entry.get("path")
        if entry.get("media_type") not in {"text/x-tex", "application/x-bibtex"}:
            continue
        if not isinstance(path, str):
            return None
        response = await client.get(
            f"/api/v1/chat/artifacts/{artifact_id}/versions/{version_id}/source/{quote(path, safe='/')}"
        )
        if response.status_code != 200:
            return None
        values.append({"path": path, "content": response.text})
    return root, values


def malformed_project(root_document: str) -> list[dict[str, str]]:
    """Return a disposable invalid source while retaining the real root path."""

    return [
        {
            "path": root_document,
            "content": "\\documentclass{article}\\begin{document}\\undefinedcontrolsequence\\end{document}",
        }
    ]


def edited_project_files(
    files: list[dict[str, str]],
    *,
    root_document: str,
    telemetry_canary: str | None,
) -> list[dict[str, str]] | None:
    """Add a disposable edit and optional opaque marker to the real root file."""

    validate_telemetry_canary(telemetry_canary)
    changed = [dict(item) for item in files]
    for item in changed:
        if item.get("path") != root_document:
            continue
        content = item.get("content")
        if not isinstance(content, str):
            return None
        content += "\n% staging qualification edit\n"
        if telemetry_canary is not None:
            content += f"% {telemetry_canary}\n"
        item["content"] = content
        return changed
    return None


async def save_compile(
    client, artifact_id: str, parent_version_id: str, files: list[dict[str, str]]
) -> dict[str, Any] | None:
    response = await client.post(
        f"/api/v1/chat/artifacts/{artifact_id}/save-compile",
        headers=_MUTATION_HEADERS,
        json={"expected_parent_version_id": parent_version_id, "files": files},
    )
    return _json_object(response) if response.status_code == 200 else None


async def upload_figure(
    client, artifact_id: str, parent_version_id: str
) -> dict[str, Any] | None:
    """Upload a fixed 1×1 PNG with no manuscript-derived bytes."""

    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0dIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    response = await client.post(
        f"/api/v1/chat/artifacts/{artifact_id}/figures",
        headers=_MUTATION_HEADERS,
        data={
            "expected_parent_version_id": parent_version_id,
            "path": "figures/qualification.png",
        },
        files={"figure": ("qualification.png", png, "image/png")},
    )
    return _json_object(response) if response.status_code == 200 else None


async def history(client, artifact_id: str) -> list[dict[str, Any]] | None:
    response = await client.get(
        f"/api/v1/chat/artifacts/{artifact_id}/versions?limit=20"
    )
    payload = _json_object(response)
    items = payload.get("items") if payload else None
    return items if response.status_code == 200 and isinstance(items, list) else None


async def restore(
    client, artifact_id: str, source_version_id: str, parent_version_id: str
) -> dict[str, Any] | None:
    response = await client.post(
        f"/api/v1/chat/artifacts/{artifact_id}/versions/restore",
        headers=_MUTATION_HEADERS,
        json={
            "source_version_id": source_version_id,
            "expected_parent_version_id": parent_version_id,
        },
    )
    return _json_object(response) if response.status_code == 200 else None


async def public_share_omits_paper(
    client, *, session_id: str, artifact_id: str
) -> bool:
    response = await client.post(
        f"/api/v1/chat/sessions/{session_id}/share", headers=_MUTATION_HEADERS
    )
    share = _json_object(response)
    share_id = share.get("share_id") if share else None
    if response.status_code != 200 or not isinstance(share_id, str):
        return False
    public = await client.get(f"/api/v1/chat/shares/{share_id}")
    payload = _json_object(public)
    if public.status_code != 200 or payload is None:
        return False

    def contains_private(value: object) -> bool:
        if isinstance(value, dict):
            return any(contains_private(item) for item in value.values())
        if isinstance(value, list):
            return any(contains_private(item) for item in value)
        return value in {artifact_id, "latex_paper", "latex-paper"}

    return not contains_private(payload)


async def archive_preserves_private_paper(
    client, *, session_id: str, artifact_id: str
) -> bool:
    """Archive only this exact operator owner's sessions, then re-read its paper."""

    archived = await client.post(
        "/api/v1/chat/sessions/archive-oldest", headers=_MUTATION_HEADERS
    )
    archive_result = _json_object(archived)
    if (
        archived.status_code != 200
        or archive_result is None
        or not isinstance(archive_result.get("archived_count"), int)
        or archive_result["archived_count"] < 1
    ):
        return False
    session = await client.get(f"/api/v1/chat/sessions/{session_id}")
    detail = _json_object(session)
    paper = detail.get("latex_paper") if detail else None
    if (
        session.status_code != 200
        or not isinstance(paper, dict)
        or paper.get("artifact_id") != artifact_id
    ):
        return False
    artifact = await client.get(f"/api/v1/chat/artifacts/{artifact_id}")
    descriptor = _json_object(artifact)
    return bool(
        artifact.status_code == 200
        and isinstance(descriptor, dict)
        and descriptor.get("artifact_id") == artifact_id
    )


async def _only_owner_session_id(client) -> str | None:
    """Return one active session only when this authenticated owner has exactly one."""

    response = await client.get("/api/v1/chat/sessions?limit=50")
    payload = _json_object(response)
    items = payload.get("items") if payload else None
    if (
        response.status_code != 200
        or not isinstance(items, list)
        or len(items) != 1
        or payload.get("next_cursor") is not None
        or not isinstance(items[0], dict)
    ):
        return None
    session_id = items[0].get("id")
    return session_id if isinstance(session_id, str) else None


async def _private_paper_readable(
    client,
    *,
    session_id: str,
    artifact_id: str,
    model: str,
    require_source_export: bool,
) -> bool:
    """Check owner-only paper metadata without retaining or printing its content."""

    session = await client.get(f"/api/v1/chat/sessions/{session_id}")
    detail = _json_object(session)
    paper = detail.get("latex_paper") if detail else None
    if (
        session.status_code != 200
        or not isinstance(detail, dict)
        or detail.get("selected_model") != model
        or not isinstance(paper, dict)
        or paper.get("artifact_id") != artifact_id
    ):
        return False
    artifact = await client.get(f"/api/v1/chat/artifacts/{artifact_id}")
    descriptor = _json_object(artifact)
    if (
        artifact.status_code != 200
        or not isinstance(descriptor, dict)
        or descriptor.get("artifact_id") != artifact_id
    ):
        return False
    if not require_source_export:
        return True
    state = paper_state(descriptor)
    if not state.source_version_id:
        return False
    source = await client.get(
        f"/api/v1/chat/artifacts/{artifact_id}/versions/"
        f"{state.source_version_id}/export/source.zip"
    )
    return bool(
        source.status_code == 200
        and source.headers.get("content-type", "").startswith("application/zip")
    )


async def preserved_owner_artifact(
    client, *, session_id: str, artifact_id: str, model: str
) -> bool:
    """Prove preparation left exactly one active, private owner paper session."""

    only_session_id = await _only_owner_session_id(client)
    return bool(
        only_session_id == session_id
        and await _private_paper_readable(
            client,
            session_id=session_id,
            artifact_id=artifact_id,
            model=model,
            require_source_export=False,
        )
    )


async def historical_private_artifact_readable(
    client, *, model: str
) -> tuple[str | None, bool]:
    """Read the single preserved paper after flags are disabled, without output."""

    session_id = await _only_owner_session_id(client)
    if session_id is None:
        return None, False
    session = await client.get(f"/api/v1/chat/sessions/{session_id}")
    detail = _json_object(session)
    paper = detail.get("latex_paper") if detail else None
    artifact_id = paper.get("artifact_id") if isinstance(paper, dict) else None
    if not isinstance(artifact_id, str):
        return session_id, False
    readable = await _private_paper_readable(
        client,
        session_id=session_id,
        artifact_id=artifact_id,
        model=model,
        require_source_export=True,
    )
    return session_id, readable


async def delete_sessions(client, session_ids: Iterable[str]) -> bool:
    """Delete every disposable session and verify each is no longer readable."""

    passed = True
    for session_id in sorted(set(session_ids)):
        deleted = await client.delete(f"/api/v1/chat/sessions/{session_id}")
        missing = await client.get(f"/api/v1/chat/sessions/{session_id}")
        passed = passed and deleted.status_code == 204 and missing.status_code == 404
    return passed


def browser_responsive_check(
    *, cookie_name: str, cookie: str, session_id: str, model: str, one_model: bool
) -> bool:
    """Use the real staging UI and only return structural responsive facts."""

    with ChromePage(
        cookies={cookie_name: cookie}, timeout=TURN_TIMEOUT_SECONDS
    ) as page:
        page.navigate(f"/chat/{session_id}?model={quote(model, safe='')}")
        page.select_model(model, only_available=one_model)
        page.wait_for(
            "Boolean(document.querySelector('[data-testid=\"latex-paper-panel\"]'))"
        )
        desktop = page.evaluate(
            "(() => { const panel=document.querySelector('[data-testid=\"latex-paper-panel\"]');"
            "return Boolean(panel && panel.querySelector('#paper-preview-tab') && "
            "panel.querySelector('#paper-files-tab') && "
            "['complementary','dialog'].includes(panel.getAttribute('role'))); })()"
        )
        page.command(
            "Emulation.setDeviceMetricsOverride",
            {"width": 600, "height": 900, "deviceScaleFactor": 1, "mobile": False},
        )
        mobile = page.wait_for(
            "(() => { const panel=document.querySelector('[data-testid=\"latex-paper-panel\"]');"
            "return Boolean(panel && panel.getAttribute('role') === 'dialog' && "
            "panel.querySelector('#paper-preview-tab') && panel.querySelector('#paper-files-tab')); })()"
        )
        return bool(desktop and mobile)


async def _manifest(client, artifact_id: str, version_id: str) -> dict[str, Any] | None:
    response = await client.get(
        f"/api/v1/chat/artifacts/{artifact_id}/versions/{version_id}/manifest"
    )
    return _json_object(response) if response.status_code == 200 else None


async def _stale_save_conflict(
    client, *, artifact_id: str, stale_version_id: str, files: list[dict[str, str]]
) -> bool:
    response = await client.post(
        f"/api/v1/chat/artifacts/{artifact_id}/save-compile",
        headers=_MUTATION_HEADERS,
        json={"expected_parent_version_id": stale_version_id, "files": files},
    )
    return response.status_code == 409


async def _downloads_exist(client, *, artifact_id: str, version_id: str) -> bool:
    pdf = await client.get(f"/api/v1/chat/artifacts/{artifact_id}/export/pdf")
    source = await client.get(
        f"/api/v1/chat/artifacts/{artifact_id}/versions/{version_id}/export/source.zip"
    )
    return bool(
        pdf.status_code == 200
        and pdf.headers.get("content-type", "").startswith("application/pdf")
        and source.status_code == 200
        and source.headers.get("content-type", "").startswith("application/zip")
    )


async def owner_source_zip_contains(
    client, *, artifact_id: str, version_id: str, canary: str
) -> bool:
    """Boundedly scan one private source ZIP for a supplied opaque marker."""

    validate_telemetry_canary(canary)
    response = await client.get(
        f"/api/v1/chat/artifacts/{artifact_id}/versions/{version_id}/export/source.zip"
    )
    if (
        response.status_code != 200
        or not response.headers.get("content-type", "").startswith("application/zip")
        or len(response.content) > MAX_CANARY_ARCHIVE_BYTES
    ):
        return False
    marker = canary.encode("ascii")
    total_uncompressed = 0
    try:
        with ZipFile(BytesIO(response.content)) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                total_uncompressed += member.file_size
                if (
                    member.file_size > MAX_CANARY_SOURCE_BYTES
                    or total_uncompressed > MAX_CANARY_SOURCE_BYTES
                ):
                    return False
                tail = b""
                with archive.open(member) as source:
                    while chunk := source.read(64 * 1024):
                        scanned = tail + chunk
                        if marker in scanned:
                            return True
                        tail = scanned[-(len(marker) - 1) :]
    except (BadZipFile, NotImplementedError, OSError, RuntimeError, ValueError):
        return False
    return False


async def _preview_and_files_exist(
    client, *, artifact_id: str, source_version_id: str, preview_version_id: str
) -> bool:
    manifest = await _manifest(client, artifact_id, source_version_id)
    preview = await client.get(
        f"/api/v1/chat/artifacts/{artifact_id}/versions/{preview_version_id}/preview"
    )
    return bool(
        manifest is not None
        and isinstance(manifest.get("root_document"), str)
        and isinstance(manifest.get("files"), list)
        and preview.status_code == 200
        and preview.headers.get("content-type", "").startswith("application/pdf")
    )


async def _create_session_check(
    client, session_ids: set[str], model: str
) -> tuple[str | None, bool]:
    session_id, selected = await create_qualification_session(client, model=model)
    if session_id is not None:
        session_ids.add(session_id)
    return session_id, bool(session_id and selected)


async def run_qualification(
    settings: Settings,
    *,
    admin_subject: str,
    admin_username: str,
    qualification_owner: str,
    model: str,
    expect_enabled: bool,
    preserve_for_kill_switch: bool = False,
    verify_historical: bool = False,
    telemetry_canary: str | None = None,
) -> list[Check]:
    """Run deterministic private-paper checks through the active staging slot.

    Normal enabled runs prove every deterministic paper path, including archive
    readability. A preserve run is a deliberately separate setup phase: it
    retains exactly one owner session so a later disabled-mode run can prove
    historical readability and non-activation. The runner never flips a flag,
    fabricates a repair receipt, or treats uninspected telemetry as passed.
    """

    validate_settings(settings, expect_enabled=expect_enabled)
    validate_qualification_owner(qualification_owner)
    validate_phase(
        expect_enabled=expect_enabled,
        preserve_for_kill_switch=preserve_for_kill_switch,
        verify_historical=verify_historical,
    )
    validate_telemetry_canary(telemetry_canary)
    checks: list[Check] = []
    session_ids: set[str] = set()
    preserved_primary_id: str | None = None
    preserved_artifact_id: str | None = None
    cookie = _encode_legacy_session(
        {
            "sub": admin_subject,
            "username": admin_username,
            "chat_qualification_owner": qualification_owner,
        }
    )
    cookies = {settings.session_cookie_name: cookie}
    async with staging_client(timeout=TURN_TIMEOUT_SECONDS, cookies=cookies) as client:
        try:
            healthy = await _check(
                checks,
                "active_staging_health",
                lambda: _health_is_ok(client),
            )
            if not healthy:
                checks.extend(unexercised_gates(expect_enabled=expect_enabled))
                return checks
            discovered: dict[str, Any] | None = None

            async def discover_luna() -> bool:
                nonlocal discovered
                response = await client.get("/api/v1/chat/models")
                discovered = _json_object(response)
                if response.status_code != 200 or discovered is None:
                    return False
                validate_selected_model(discovered, model)
                return True

            model_available = await _check(checks, "selected_luna_model", discover_luna)
            if not model_available:
                checks.extend(unexercised_gates(expect_enabled=expect_enabled))
                return checks

            if verify_historical:
                historical_session_id: str | None = None

                async def historical_readable() -> bool:
                    nonlocal historical_session_id
                    (
                        historical_session_id,
                        readable,
                    ) = await historical_private_artifact_readable(client, model=model)
                    if historical_session_id is not None:
                        session_ids.add(historical_session_id)
                    return readable

                historical_ok = await _check(
                    checks,
                    "historical_private_descriptor_source_export",
                    historical_readable,
                )
                historical_nonactivation = False
                if historical_ok and historical_session_id is not None:
                    historical_nonactivation = await _check(
                        checks,
                        "disabled_historical_write_paper_nonactivation",
                        lambda: _disabled_nonactivation(client, historical_session_id),
                    )
                else:
                    checks.append(
                        Check(
                            name="disabled_historical_write_paper_nonactivation",
                            passed=False,
                            executed=False,
                            elapsed_ms=0,
                        )
                    )
                checks.extend(
                    unexercised_gates(
                        expect_enabled=False,
                        kill_switch_passed=(historical_ok and historical_nonactivation),
                    )
                )
                return checks

            primary_id: str | None = None

            async def create_primary() -> bool:
                nonlocal primary_id
                primary_id, selected = await _create_session_check(
                    client, session_ids, model
                )
                return selected

            created = await _check(checks, "explicit_luna_session", create_primary)
            if not created or primary_id is None:
                checks.extend(unexercised_gates(expect_enabled=expect_enabled))
                return checks

            if not expect_enabled:
                disabled_nonactivation = await _check(
                    checks,
                    "disabled_nonactivation",
                    lambda: _disabled_nonactivation(client, primary_id),
                )
                checks.extend(
                    unexercised_gates(
                        expect_enabled=False,
                        kill_switch_passed=disabled_nonactivation,
                    )
                )
                return checks

            ordinary: TurnObservation | None = None

            async def plain_nonactivation() -> bool:
                nonlocal ordinary
                ordinary = await stream_turn(
                    client,
                    session_id=primary_id,
                    prompt="Give one concise, cited research observation without creating a paper artifact.",
                )
                return bool(
                    ordinary.terminal
                    and ordinary.successful
                    and not ordinary.had_error
                    and ordinary.paper_artifact_id is None
                )

            await _check(
                checks, "enabled_plain_turn_nonactivation", plain_nonactivation
            )
            checks.append(
                Check(
                    name="citations_structural",
                    passed=bool(ordinary and ordinary.citations_structural),
                    elapsed_ms=0,
                )
            )

            artifact_id: str | None = None

            async def slash_activation() -> bool:
                nonlocal artifact_id
                turn = await stream_turn(
                    client,
                    session_id=primary_id,
                    prompt=private_authoring_prompt(
                        "/write-paper Prepare a brief cited technical paper as a private artifact.",
                        telemetry_canary,
                    ),
                )
                artifact_id = turn.paper_artifact_id
                return bool(
                    turn.terminal
                    and turn.successful
                    and turn.paper_activated
                    and turn.paper_operation == "draft"
                    and artifact_id
                )

            activated = await _check(
                checks, "slash_write_paper_activation", slash_activation
            )
            if not activated or artifact_id is None:
                checks.extend(unexercised_gates(expect_enabled=True))
                return checks

            async def natural_activation() -> bool:
                secondary_id, selected = await _create_session_check(
                    client, session_ids, model
                )
                if not selected or secondary_id is None:
                    return False
                turn = await stream_turn(
                    client,
                    session_id=secondary_id,
                    prompt="Please create a private, cited technical paper from this research chat.",
                )
                return bool(
                    turn.terminal
                    and turn.successful
                    and turn.paper_activated
                    and turn.paper_operation == "draft"
                    and turn.paper_artifact_id
                )

            await _check(checks, "natural_prompt_activation", natural_activation)

            first_descriptor: dict[str, Any] | None = None
            first_state = PaperState(None, None, None, None)

            async def first_compile() -> bool:
                nonlocal first_descriptor, first_state
                first_descriptor, first_state = await wait_for_compile(
                    client, artifact_id
                )
                return bool(
                    first_descriptor
                    and first_state.source_status == "succeeded"
                    and first_state.source_version_id
                    and first_state.preview_version_id
                )

            compiled = await _check(checks, "first_compile", first_compile)
            if (
                not compiled
                or not first_state.source_version_id
                or not first_state.preview_version_id
            ):
                checks.extend(unexercised_gates(expect_enabled=True))
                return checks

            await _check(
                checks,
                "preview_and_files",
                lambda: _preview_and_files_exist(
                    client,
                    artifact_id=artifact_id,
                    source_version_id=first_state.source_version_id or "",
                    preview_version_id=first_state.preview_version_id or "",
                ),
            )
            original_success_version = first_state.source_version_id
            edited_state = PaperState(None, None, None, None)
            editable_files: list[dict[str, str]] = []
            root_document: str | None = None

            async def edit_and_compile() -> bool:
                nonlocal edited_state, editable_files, root_document
                project = await manifest_files(
                    client, artifact_id, original_success_version
                )
                if project is None:
                    return False
                root_document, editable_files = project
                if not root_document or not editable_files:
                    return False
                changed = edited_project_files(
                    editable_files,
                    root_document=root_document,
                    telemetry_canary=telemetry_canary,
                )
                if changed is None:
                    return False
                saved = await save_compile(
                    client, artifact_id, original_success_version, changed
                )
                if saved is None:
                    return False
                _descriptor, edited_state = await wait_for_compile(client, artifact_id)
                return bool(
                    edited_state.source_status == "succeeded"
                    and edited_state.source_version_id
                    and edited_state.source_version_id != original_success_version
                )

            edited = await _check(checks, "editing_save_compile", edit_and_compile)
            if not edited or not edited_state.source_version_id:
                checks.extend(unexercised_gates(expect_enabled=True))
                return checks

            figure_state = PaperState(None, None, None, None)

            async def figure_upload() -> bool:
                nonlocal figure_state
                uploaded = await upload_figure(
                    client, artifact_id, edited_state.source_version_id or ""
                )
                if uploaded is None:
                    return False
                descriptor, figure_state = await wait_for_compile(client, artifact_id)
                if descriptor is None or not figure_state.source_version_id:
                    return False
                manifest = await _manifest(
                    client, artifact_id, figure_state.source_version_id
                )
                files = manifest.get("files") if manifest else None
                return bool(
                    figure_state.source_status == "succeeded"
                    and isinstance(files, list)
                    and any(
                        isinstance(item, dict)
                        and item.get("path") == "figures/qualification.png"
                        for item in files
                    )
                )

            figures = await _check(checks, "figure_upload", figure_upload)
            if not figures or not figure_state.source_version_id:
                checks.extend(unexercised_gates(expect_enabled=True))
                return checks

            await _check(
                checks,
                "optimistic_edit_conflict",
                lambda: _stale_save_conflict(
                    client,
                    artifact_id=artifact_id,
                    stale_version_id=original_success_version,
                    files=editable_files,
                ),
            )

            failed_state = PaperState(None, None, None, None)

            async def failed_source_preserves_pdf() -> bool:
                nonlocal failed_state
                if root_document is None:
                    return False
                malformed = malformed_project(root_document)
                saved = await save_compile(
                    client, artifact_id, figure_state.source_version_id or "", malformed
                )
                if saved is None:
                    return False
                _descriptor, failed_state = await wait_for_compile(client, artifact_id)
                if (
                    failed_state.source_status != "failed"
                    or failed_state.preview_version_id
                    != figure_state.preview_version_id
                    or not figure_state.preview_version_id
                ):
                    return False
                preview = await client.get(
                    f"/api/v1/chat/artifacts/{artifact_id}/versions/{figure_state.preview_version_id}/preview"
                )
                return bool(
                    preview.status_code == 200
                    and preview.headers.get("content-type", "").startswith(
                        "application/pdf"
                    )
                )

            failed = await _check(
                checks, "failed_source_stale_pdf", failed_source_preserves_pdf
            )
            if not failed or not failed_state.source_version_id:
                checks.extend(unexercised_gates(expect_enabled=True))
                return checks

            repair_state = PaperState(None, None, None, None)

            async def bounded_repair() -> bool:
                nonlocal repair_state
                turn = await stream_turn(
                    client,
                    session_id=primary_id,
                    prompt=(
                        "Run the bounded repair qualification on the current failed "
                        "private paper. First use pwc-paper repair-context with "
                        "/workspace/paper. Leave its controlled invalid TeX unchanged. "
                        "Then make exactly three separate pwc-paper repair calls using "
                        "the current private descriptor's artifact and failed-source IDs, "
                        "waiting for each receipt. Stop immediately after the third receipt."
                    ),
                )
                descriptor = await get_descriptor(client, artifact_id)
                if descriptor is None:
                    return False
                repair_state = paper_state(descriptor)
                return bounded_repair_passes(
                    turn,
                    repair_state,
                    failed_source_id=failed_state.source_version_id or "",
                    preserved_preview_id=figure_state.preview_version_id or "",
                )

            await _check(checks, "repair_three_attempt_bound", bounded_repair)

            restored_state = PaperState(None, None, None, None)

            async def history_and_restore() -> bool:
                nonlocal restored_state
                rows = await history(client, artifact_id)
                if not isinstance(rows, list) or len(rows) < 3:
                    return False
                restore_source_version = (
                    figure_state.source_version_id
                    if telemetry_canary is not None
                    else original_success_version
                )
                restored = await restore(
                    client,
                    artifact_id,
                    restore_source_version,
                    failed_state.source_version_id or "",
                )
                if restored is None:
                    return False
                _descriptor, restored_state = await wait_for_compile(
                    client, artifact_id
                )
                return bool(
                    restored_state.source_status == "succeeded"
                    and restored_state.source_actor_type == "restore"
                    and restored_state.source_version_id
                )

            restored = await _check(checks, "history_restore", history_and_restore)
            if not restored or not restored_state.source_version_id:
                checks.extend(unexercised_gates(expect_enabled=True))
                return checks

            if telemetry_canary is not None:
                await _check(
                    checks,
                    "telemetry_canary_owner_source_present",
                    lambda: owner_source_zip_contains(
                        client,
                        artifact_id=artifact_id,
                        version_id=restored_state.source_version_id or "",
                        canary=telemetry_canary,
                    ),
                )
            await _check(
                checks,
                "private_exports",
                lambda: _downloads_exist(
                    client,
                    artifact_id=artifact_id,
                    version_id=restored_state.source_version_id or "",
                ),
            )
            await _check(
                checks,
                "share_omits_private_paper",
                lambda: public_share_omits_paper(
                    client, session_id=primary_id, artifact_id=artifact_id
                ),
            )
            if not preserve_for_kill_switch:
                await _check(
                    checks,
                    "archive_preserves_private_paper",
                    lambda: archive_preserves_private_paper(
                        client, session_id=primary_id, artifact_id=artifact_id
                    ),
                )

            one_model = bool(
                discovered
                and isinstance(discovered.get("items"), list)
                and len(discovered["items"]) == 1
            )
            await _check(
                checks,
                "responsive_preview_files_ui",
                lambda: asyncio.to_thread(
                    browser_responsive_check,
                    cookie_name=settings.session_cookie_name,
                    cookie=cookie,
                    session_id=primary_id,
                    model=model,
                    one_model=one_model,
                ),
            )
            if preserve_for_kill_switch:
                ready_to_preserve = all(
                    check.executed and check.passed for check in checks
                )
                checks.append(
                    Check(
                        name="preserve_kill_switch_artifact",
                        passed=ready_to_preserve,
                        elapsed_ms=0,
                    )
                )
                if ready_to_preserve:
                    preserved_primary_id = primary_id
                    preserved_artifact_id = artifact_id
            checks.extend(unexercised_gates(expect_enabled=True))
            return checks
        finally:
            delete_ids = session_ids
            if preserved_primary_id is not None:
                delete_ids = session_ids - {preserved_primary_id}
            await _check(
                checks,
                "delete_disposable_sessions",
                lambda: delete_sessions(client, delete_ids),
            )
            if preserved_primary_id is not None and preserved_artifact_id is not None:
                await _check(
                    checks,
                    "preserved_single_owner_private_artifact",
                    lambda: preserved_owner_artifact(
                        client,
                        session_id=preserved_primary_id,
                        artifact_id=preserved_artifact_id,
                        model=model,
                    ),
                )


async def _health_is_ok(client) -> bool:
    response = await client.get("/health")
    return response.status_code == 200


async def _disabled_nonactivation(client, session_id: str) -> bool:
    turn = await stream_turn(
        client,
        session_id=session_id,
        prompt="/write-paper Do not create a paper when the feature is disabled.",
    )
    return bool(
        turn.terminal
        and turn.successful
        and not turn.had_error
        and turn.paper_artifact_id is None
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--admin-subject", required=True)
    result.add_argument("--admin-username", required=True)
    result.add_argument("--qualification-owner", required=True)
    result.add_argument("--model", default=LUNA_MODEL)
    result.add_argument("--expect", choices=("enabled", "disabled"), default="enabled")
    result.add_argument("--preserve-for-kill-switch", action="store_true")
    result.add_argument("--verify-historical", action="store_true")
    result.add_argument("--telemetry-canary")
    result.add_argument("--confirm", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"--confirm must be {CONFIRMATION}")
    try:
        validate_qualification_owner(args.qualification_owner)
    except ValueError:
        raise SystemExit(
            "--qualification-owner must use a protected Pi operator prefix"
        ) from None
    try:
        settings = get_settings()
        validate_settings(settings, expect_enabled=args.expect == "enabled")
        validate_phase(
            expect_enabled=args.expect == "enabled",
            preserve_for_kill_switch=args.preserve_for_kill_switch,
            verify_historical=args.verify_historical,
        )
        validate_telemetry_canary(args.telemetry_canary)
        checks = asyncio.run(
            run_qualification(
                settings,
                admin_subject=args.admin_subject,
                admin_username=args.admin_username,
                qualification_owner=args.qualification_owner,
                model=args.model,
                expect_enabled=args.expect == "enabled",
                preserve_for_kill_switch=args.preserve_for_kill_switch,
                verify_historical=args.verify_historical,
                telemetry_canary=args.telemetry_canary,
            )
        )
    except Exception:
        checks = [Check(name="preflight", passed=False, elapsed_ms=0)]
        checks.extend(unexercised_gates(expect_enabled=args.expect == "enabled"))
    payload = report(checks)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
