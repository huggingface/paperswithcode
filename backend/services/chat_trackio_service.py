"""Export existing chat observations to the Trackio 0.37 HTTP trace API.

Network writes run on a bounded background queue, never on the chat stream.
Provider requests are correlated by trace_id but kept in separate runs from
turn aggregates, so the dashboard does not double-count their token usage.

Entries are batched into one ``bulk_log`` request each, because a research
turn emits a chat trace, one provider-request trace per model call, and
several lifecycle observations; sending each as its own POST could not keep
up with production traffic and most traces were dropped on the queue.
Lifecycle observations are exported as plain numeric metrics rather than
single-span traces, which keeps them content-free and small.
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
MAX_BATCH_ENTRIES = 20
MAX_QUEUE_ENTRIES = 512
MAX_QUEUE_BYTES = 64 * 1024 * 1024
BATCH_LINGER_SECONDS = 0.25
DROP_LOG_INTERVAL_SECONDS = 60.0
LIFECYCLE_SPAN_NAME = "durable-chat-lifecycle"


class TrackioClient:
    def __init__(
        self, url: str, token: str, project: str, environment: str, release: str
    ):
        self.url = url.rstrip("/") + "/api/bulk_log"
        self.token = token
        self.project = project
        self.environment = environment
        self.release = release
        self.pending: queue.Queue[bytes] = queue.Queue(maxsize=MAX_QUEUE_ENTRIES)
        self._lock = threading.Lock()
        self._pending_bytes = 0
        self._last_drop_log = 0.0
        self._unlogged_drops = 0
        self.counters = {
            "submitted": 0,
            "dropped": 0,
            "sent": 0,
            "failed": 0,
            "rejected": 0,
        }
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

    def summary(self) -> dict[str, int]:
        with self._lock:
            return {
                **self.counters,
                "queued": self.pending.qsize(),
                "queued_bytes": self._pending_bytes,
            }

    def submit(self, root: TrackioObservation) -> None:
        kind = {
            "provider-request": "provider-requests",
            LIFECYCLE_SPAN_NAME: "lifecycle",
        }.get(root.span["name"], "chat")
        run = f"{self.environment}-{kind}-{root.span['start_time'][:10]}"
        entry = {
            "project": self.project,
            "run": run,
            "run_id": hashlib.sha256(f"{self.project}:{run}".encode()).hexdigest()[:32],
            "log_id": root.span["id"],
            "metrics": (
                _lifecycle_metrics(root)
                if root.span["name"] == LIFECYCLE_SPAN_NAME
                else {"trace": self._trace_metric(root)}
            ),
        }
        self._enqueue(entry, root.trace_id)

    def log_metrics(self, kind: str, metrics: dict[str, float], *, log_id: str) -> None:
        """Queue plain numeric metrics into today's ``<environment>-<kind>`` run."""
        if not kind or not metrics or not log_id:
            raise ValueError("Trackio metrics need a run kind, values, and a log id")
        run = f"{self.environment}-{kind}-{datetime.now(UTC).date().isoformat()}"
        entry = {
            "project": self.project,
            "run": run,
            "run_id": hashlib.sha256(f"{self.project}:{run}".encode()).hexdigest()[:32],
            "log_id": log_id,
            "metrics": dict(metrics),
        }
        self._enqueue(entry, log_id)

    def _enqueue(self, entry: dict[str, Any], trace_id: str) -> None:
        encoded = json.dumps(entry, default=str).encode()
        with self._lock:
            self.counters["submitted"] += 1
            if len(encoded) > MAX_PAYLOAD_BYTES:
                # One oversized turn, not a burst: always worth its own line.
                self.counters["dropped"] += 1
                logger.warning(
                    "chat Trackio trace dropped: payload exceeds 2 MiB trace_id=%s",
                    trace_id,
                )
                return
            if self._pending_bytes + len(encoded) > MAX_QUEUE_BYTES:
                self._drop_queue_full(trace_id)
                return
            try:
                self.pending.put_nowait(encoded)
            except queue.Full:
                self._drop_queue_full(trace_id)
                return
            self._pending_bytes += len(encoded)

    def _trace_metric(self, root: TrackioObservation) -> dict[str, Any]:
        messages = []
        for field in ("input", "output"):
            value = root.span.get(field)
            if isinstance(value, list):
                messages.extend(value)
        return {
            "_type": "trackio.trace",
            "messages": messages,
            "metadata": {
                **root.span["metadata"],
                "trace_id": root.trace_id,
                "environment": self.environment,
                "release": self.release,
            },
            "spans": root.spans,
        }

    def _drop_queue_full(self, trace_id: str) -> None:
        # Called with ``self._lock`` held.  Queue-full drops arrive in bursts,
        # so log the first one per interval with the count suppressed since,
        # keeping the prefix the alert monitor matches.  The trace ID is a
        # hash, not chat content.
        self.counters["dropped"] += 1
        self._unlogged_drops += 1
        now = time.monotonic()
        if now - self._last_drop_log < DROP_LOG_INTERVAL_SECONDS:
            return
        count = self._unlogged_drops
        self._unlogged_drops = 0
        self._last_drop_log = now
        logger.warning(
            "chat Trackio trace dropped: export queue full trace_id=%s "
            "dropped_since_last_log=%d",
            trace_id,
            count,
        )

    def _batch_payload(self, entries: list[bytes]) -> bytes:
        return (
            b'{"args":[],"kwargs":{"logs":['
            + b",".join(entries)
            + b'],"hf_token":'
            + json.dumps(self.token).encode()
            + b"}}"
        )

    def _send(self, payload: bytes) -> bool:
        # No redirect following: credentials must stay on the configured Space.
        last_error = "unknown"
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
                            return True
                        logger.warning("chat Trackio export rejected by API")
                        with self._lock:
                            self.counters["rejected"] += 1
                        return False
                    if response.status_code not in {408, 429, 500, 502, 503, 504}:
                        logger.warning(
                            "chat Trackio export failed HTTP %s", response.status_code
                        )
                        return False
                    last_error = f"HTTP {response.status_code}"
                except (httpx.HTTPError, ValueError) as exc:
                    # Never log payloads, response bodies or tokens.
                    last_error = type(exc).__name__
                if attempt < 2:
                    time.sleep(2**attempt)
        logger.warning(
            "chat Trackio export failed after 3 attempts last_error=%s", last_error
        )
        return False

    def _next_batch(self) -> list[bytes]:
        first = self.pending.get()
        batch = [first]
        total = len(first)
        deadline = time.monotonic() + BATCH_LINGER_SECONDS
        while len(batch) < MAX_BATCH_ENTRIES:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                entry = self.pending.get(timeout=remaining)
            except queue.Empty:
                break
            if total + len(entry) > MAX_PAYLOAD_BYTES:
                self._requeue_front(entry)
                break
            batch.append(entry)
            total += len(entry)
        return batch

    def _requeue_front(self, entry: bytes) -> None:
        # ``queue.Queue`` has no push-front.  Reinsert under its mutex so an
        # entry that would overflow the current POST keeps its place.  ``get``
        # never touched ``unfinished_tasks``, so nothing is adjusted here; the
        # batch that eventually carries the entry calls ``task_done`` for it.
        with self.pending.mutex:
            self.pending.queue.appendleft(entry)
            self.pending.not_empty.notify()

    def _work(self) -> None:
        while True:
            batch = self._next_batch()
            try:
                delivered = self._send(self._batch_payload(batch))
            except Exception:
                # Keep the exporter alive; telemetry failures must not break chat.
                logger.warning("chat Trackio exporter failed unexpectedly")
                delivered = False
            finally:
                with self._lock:
                    self._pending_bytes -= sum(len(entry) for entry in batch)
                for _ in batch:
                    self.pending.task_done()
            with self._lock:
                self.counters["sent" if delivered else "failed"] += len(batch)

    def flush(self, timeout: float = 5) -> bool:
        deadline = time.monotonic() + timeout
        while self.pending.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.05)
        return not self.pending.unfinished_tasks


def _lifecycle_metrics(root: TrackioObservation) -> dict[str, int]:
    metadata = root.span["metadata"]
    name = f"lifecycle/{metadata['event']}"
    code = metadata.get("code")
    if code and code != "none":
        name = f"{name}/{code}"
    return {name: metadata["value"]}


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
