"""Export existing chat observations to the Trackio 0.37 HTTP trace API.

Network writes run on a bounded background queue, never on the chat stream.
Provider requests are correlated by trace_id but kept in separate runs from
turn aggregates, so the dashboard does not double-count their token usage.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import queue
import threading
import time
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import httpx

from backend.config import Settings

logger = logging.getLogger(__name__)
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024


class TrackioClient:
    def __init__(
        self, url: str, token: str, project: str, environment: str, release: str
    ):
        self.url = url.rstrip("/") + "/api/bulk_log"
        self.token = token
        self.project = project
        self.environment = environment
        self.release = release
        self.pending: queue.Queue[bytes] = queue.Queue(maxsize=32)
        self.worker = threading.Thread(
            target=self._work, name="chat-trackio", daemon=True
        )
        self.worker.start()
        atexit.register(self.flush)

    @staticmethod
    def create_trace_id(*, seed: str) -> str:
        # Same deterministic ID as Langfuse, including the persisted DB column.
        return hashlib.sha256(seed.encode()).hexdigest()[:32]

    def start_observation(
        self, *, trace_context: dict | None = None, **fields: Any
    ) -> TrackioObservation:
        return TrackioObservation(
            self, (trace_context or {}).get("trace_id") or uuid.uuid4().hex, **fields
        )

    def submit(self, root: TrackioObservation) -> None:
        kind = {
            "provider-request": "provider-requests",
            "durable-chat-lifecycle": "lifecycle",
        }.get(root.span["name"], "chat")
        run = f"{self.environment}-{kind}-{root.span['start_time'][:10]}"
        metadata = {
            **root.span["metadata"],
            "trace_id": root.trace_id,
            "environment": self.environment,
            "release": self.release,
        }
        messages = []
        for field in ("input", "output"):
            value = root.span.get(field)
            if isinstance(value, list):
                messages.extend(value)
        entry = {
            "project": self.project,
            "run": run,
            "run_id": hashlib.sha256(f"{self.project}:{run}".encode()).hexdigest()[:32],
            "log_id": root.span["id"],
            "metrics": {
                "trace": {
                    "_type": "trackio.trace",
                    "messages": messages,
                    "metadata": metadata,
                    "spans": root.spans,
                }
            },
        }
        payload = json.dumps(
            {
                "args": [],
                "kwargs": {
                    "logs": [entry],
                    "hf_token": self.token,
                },
            },
            default=str,
        ).encode()
        if len(payload) > MAX_PAYLOAD_BYTES:
            logger.warning(
                "chat Trackio trace dropped: payload exceeds 2 MiB trace_id=%s",
                root.trace_id,
            )
            return
        try:
            self.pending.put_nowait(payload)
        except queue.Full:
            logger.warning(
                "chat Trackio trace dropped: export queue full trace_id=%s",
                root.trace_id,
            )

    def _send(self, payload: bytes) -> None:
        # No redirect following: credentials must stay on the configured Space.
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            for attempt in range(3):
                try:
                    response = client.post(
                        self.url,
                        content=payload,
                        headers={
                            "Authorization": f"Bearer {self.token}",
                            "Content-Type": "application/json",
                        },
                    )
                    if response.is_success:
                        body = response.json()
                        if (
                            isinstance(body, dict)
                            and body.get("error") is None
                            and "data" in body
                        ):
                            return
                        logger.warning("chat Trackio export rejected by API")
                        return
                    if response.status_code not in {408, 429, 500, 502, 503, 504}:
                        logger.warning(
                            "chat Trackio export failed HTTP %s", response.status_code
                        )
                        return
                except (httpx.HTTPError, ValueError):
                    # Never log payloads, response bodies or tokens.
                    pass
                if attempt < 2:
                    time.sleep(2**attempt)
        logger.warning("chat Trackio export failed after 3 attempts")

    def _work(self) -> None:
        while True:
            payload = self.pending.get()
            try:
                self._send(payload)
            except Exception:
                # Keep the exporter alive; telemetry failures must not break chat.
                logger.warning("chat Trackio exporter failed unexpectedly")
            finally:
                self.pending.task_done()

    def flush(self, timeout: float = 5) -> bool:
        deadline = time.monotonic() + timeout
        while self.pending.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.05)
        return not self.pending.unfinished_tasks


class TrackioObservation:
    """The observation lifecycle used by ChatTurnTrace and ProviderRequestTrace."""

    def __init__(
        self,
        client: TrackioClient,
        trace_id: str,
        *,
        name: str,
        as_type: str = "span",
        parent: TrackioObservation | None = None,
        **fields: Any,
    ):
        self.client = client
        self.trace_id = trace_id
        self.parent = parent
        self.spans = parent.spans if parent else []
        self.span: dict[str, Any] = {
            "id": uuid.uuid4().hex,
            "name": name,
            "kind": {"agent": "span", "retriever": "tool"}.get(as_type, as_type),
            "start_time": datetime.now(UTC).isoformat(),
            "metadata": {},
        }
        if parent:
            self.span["parent_id"] = parent.span["id"]
        self.spans.append(self.span)
        self.update(**fields)

    def start_observation(self, **fields: Any) -> TrackioObservation:
        return TrackioObservation(self.client, self.trace_id, parent=self, **fields)

    def update(self, **fields: Any) -> TrackioObservation:
        metadata = fields.get("metadata") or {}
        self.span["metadata"].update(metadata)
        for key in ("input", "output", "model"):
            if key in fields:
                self.span[key] = fields[key]
        if "level" in fields:
            self.span["status"] = {"ERROR": "error", "WARNING": "interrupted"}.get(
                fields["level"], "success"
            )
        if fields.get("status_message"):
            self.span["metadata"]["status_message"] = fields["status_message"]
        if fields.get("completion_start_time"):
            self.span["metadata"]["completion_start_time"] = fields[
                "completion_start_time"
            ].isoformat()
        usage = fields.get("usage_details")
        if usage:
            self.span["usage"] = {
                {"input": "input_tokens", "output": "output_tokens"}.get(
                    key, key
                ): value
                for key, value in usage.items()
            }
        cost = fields.get("cost_details")
        if cost and "total" in cost:
            self.span["cost_usd"] = cost["total"]
        return self

    def end(self) -> TrackioObservation:
        if "end_time" in self.span:
            return self
        self.span["end_time"] = datetime.now(UTC).isoformat()
        if self.parent is None:
            self.client.submit(self)
        return self


@lru_cache(maxsize=4)
def _client(
    url: str, token: str, project: str, environment: str, release: str
) -> TrackioClient:
    return TrackioClient(url, token, project, environment, release)


def configured_trackio_client(settings: Settings) -> TrackioClient | None:
    if not settings.chat_trackio_enabled:
        return None
    if not settings.chat_trackio_url or not settings.chat_trackio_hf_token:
        logger.warning(
            "chat Trackio client initialization failed: URL or HF token missing"
        )
        return None
    return _client(
        settings.chat_trackio_url,
        settings.chat_trackio_hf_token,
        settings.chat_trackio_project,
        settings.environment,
        settings.release_id,
    )
