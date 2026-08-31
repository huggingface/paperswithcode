"""Shared stale-while-revalidate snapshots for the CRON admin dashboard."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.config import get_settings
from backend.services.cron_health import build_cron_dashboard, to_iso8601
from backend.services.cron_registry import CronJobDefinition

logger = logging.getLogger(__name__)

SNAPSHOT_SCHEMA_VERSION = 1
SNAPSHOT_TTL_SECONDS = 60


class CronDashboardSnapshotError(RuntimeError):
    """Raised when no valid CRON dashboard snapshot can be produced."""


class CronDashboardSnapshotService:
    def __init__(
        self,
        *,
        runtime_data_dir: Path | None = None,
        builder: Callable[[dict[str, Any] | None], dict[str, Any]] | None = None,
        now: Callable[[], datetime] | None = None,
        ttl_seconds: int = SNAPSHOT_TTL_SECONDS,
    ) -> None:
        root = runtime_data_dir or Path(get_settings().runtime_data_dir)
        self.snapshot_dir = root / "cron-dashboard"
        self.snapshot_path = self.snapshot_dir / "status-v1.json"
        self.lock_path = self.snapshot_dir / "status-v1.lock"
        self.autonomous_snapshot_path = self.snapshot_dir / "autonomous-health-v1.json"
        self.builder = builder or (
            lambda previous: build_cron_dashboard(previous_dashboard=previous)
        )
        self.now = now or (lambda: datetime.now(UTC))
        self.ttl_seconds = ttl_seconds

    def get_status(self, *, force_refresh: bool = False) -> tuple[dict[str, Any], bool]:
        """Return a decorated snapshot and whether to schedule a refresh."""

        envelope = self._read_snapshot()
        if force_refresh:
            try:
                refreshed = self.refresh(force=True, blocking=False)
            except Exception as exc:
                logger.exception(
                    "cron_dashboard_snapshot force_refresh_failed error=%s",
                    type(exc).__name__,
                )
                if envelope is not None:
                    return self._decorate(envelope, refreshing=False), False
                raise CronDashboardSnapshotError(
                    "CRON dashboard snapshot refresh failed"
                ) from exc
            if refreshed is not None:
                return refreshed, False
            if envelope is not None:
                return self._decorate(envelope, refreshing=True), False
            try:
                refreshed = self.refresh(force=False, blocking=True)
            except Exception as exc:
                raise CronDashboardSnapshotError(
                    "CRON dashboard snapshot refresh failed"
                ) from exc
            if refreshed is not None:
                return refreshed, False

        if envelope is not None:
            decorated = self._decorate(envelope, refreshing=False)
            if not decorated["snapshot_stale"]:
                return decorated, False
            decorated["refreshing"] = True
            return decorated, True

        try:
            refreshed = self.refresh(force=False, blocking=True)
        except CronDashboardSnapshotError:
            raise
        except Exception as exc:
            raise CronDashboardSnapshotError(
                "CRON dashboard snapshot refresh failed"
            ) from exc
        if refreshed is None:
            raise CronDashboardSnapshotError("CRON dashboard snapshot is unavailable")
        return refreshed, False

    def refresh(
        self, *, force: bool = False, blocking: bool = False
    ) -> dict[str, Any] | None:
        """Refresh the shared snapshot while holding the cross-worker lock."""

        lock_handle = self._acquire_lock(blocking=blocking)
        if lock_handle is None:
            return None
        try:
            previous = self._read_snapshot()
            if previous is not None and not force:
                decorated = self._decorate(previous, refreshing=False)
                if not decorated["snapshot_stale"]:
                    return decorated

            previous_payload = previous.get("payload") if previous else None
            started = self.now()
            payload = self.builder(previous_payload)
            if not isinstance(payload, dict) or not isinstance(
                payload.get("jobs"), list
            ):
                raise CronDashboardSnapshotError(
                    "CRON dashboard collector returned an invalid payload"
                )
            completed = self.now()
            envelope = {
                "schema_version": SNAPSHOT_SCHEMA_VERSION,
                "generated_at": to_iso8601(completed),
                "refresh_duration_ms": max(
                    0.0, (completed - started).total_seconds() * 1000
                ),
                "payload": payload,
            }
            self._write_snapshot(envelope)
            logger.info(
                "cron_dashboard_snapshot refreshed duration_ms=%.1f jobs=%d",
                envelope["refresh_duration_ms"],
                len(payload["jobs"]),
            )
            return self._decorate(envelope, refreshing=False)
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            lock_handle.close()

    def refresh_in_background(self) -> None:
        try:
            self.refresh(force=False, blocking=False)
        except Exception as exc:
            logger.exception(
                "cron_dashboard_snapshot refresh_failed error=%s",
                type(exc).__name__,
            )

    def build_autonomous_snapshot(
        self,
        *,
        daily: bool,
        definitions: tuple[CronJobDefinition, ...] | None = None,
    ) -> dict[str, Any]:
        """Persist one strict, content-free deterministic operator snapshot."""

        from backend.services.autonomous_cron_probe import AutonomousCronProbe

        dashboard = self.refresh(force=True, blocking=True)
        if dashboard is None:
            raise CronDashboardSnapshotError("strict CRON snapshot is unavailable")
        observed_at = self.now()
        audit = AutonomousCronProbe(
            dashboard_provider=lambda: dashboard,
            definitions=definitions,
        ).audit_all_jobs(observed_at)
        payload = audit.as_dict()
        payload["mode"] = "daily" if daily else "strict_15m"
        self._write_json(self.autonomous_snapshot_path, payload)
        return payload

    def _read_snapshot(self) -> dict[str, Any] | None:
        try:
            value = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "cron_dashboard_snapshot invalid error=%s", type(exc).__name__
            )
            return None
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != SNAPSHOT_SCHEMA_VERSION
            or not isinstance(value.get("generated_at"), str)
            or not isinstance(value.get("payload"), dict)
            or not isinstance(value["payload"].get("jobs"), list)
        ):
            logger.warning("cron_dashboard_snapshot invalid_schema")
            return None
        try:
            datetime.fromisoformat(value["generated_at"].replace("Z", "+00:00"))
        except ValueError:
            logger.warning("cron_dashboard_snapshot invalid_timestamp")
            return None
        return value

    def _decorate(
        self, envelope: dict[str, Any], *, refreshing: bool
    ) -> dict[str, Any]:
        generated = datetime.fromisoformat(
            envelope["generated_at"].replace("Z", "+00:00")
        )
        age_seconds = max(0.0, (self.now() - generated).total_seconds())
        return {
            **envelope["payload"],
            "snapshot_generated_at": envelope["generated_at"],
            "snapshot_age_seconds": round(age_seconds, 3),
            "snapshot_stale": age_seconds > self.ttl_seconds,
            "refreshing": refreshing,
        }

    def _acquire_lock(self, *, blocking: bool):
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+", encoding="utf-8")
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(handle.fileno(), flags)
        except BlockingIOError:
            handle.close()
            return None
        return handle

    def _write_snapshot(self, envelope: dict[str, Any]) -> None:
        self._write_json(self.snapshot_path, envelope)

    def _write_json(self, destination: Path, payload: dict[str, Any]) -> None:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f"{destination.stem}-", suffix=".tmp", dir=self.snapshot_dir
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
