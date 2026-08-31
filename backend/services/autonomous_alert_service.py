"""Content-free autonomous alert routing with durable deduplication receipts."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from urllib.parse import urlsplit

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.database import AutonomousAlertDelivery
from backend.services.autonomous_digest_service import render_daily_digest
from backend.services.autonomous_operations_repository import Operator


_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_RELEASE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SECRET_PREFIXES = ("sk-", "hf_", "bearer", "eyj")
_RULES: dict[str, tuple[str, int]] = {
    "operator_failure": ("high", 15 * 60),
    "site_impact": ("critical", 5 * 60),
    "lease_timeout": ("high", 30 * 60),
    "repair_started": ("info", 15 * 60),
    "review_rejected": ("high", 30 * 60),
    "deploy_succeeded": ("info", 15 * 60),
    "rollback": ("critical", 15 * 60),
    "provider_switch": ("high", 15 * 60),
    "budget_threshold": ("high", 60 * 60),
    "both_provider_outage": ("critical", 5 * 60),
    "daily_digest": ("info", 24 * 60 * 60),
}


class AlertDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AutonomousAlert:
    event_kind: str
    operator: Operator | None
    resource_key: str
    environment: str
    release_id: str
    occurred_at: datetime
    runbook_url: str

    def __post_init__(self) -> None:
        parsed = urlsplit(self.runbook_url)
        if (
            self.event_kind not in _RULES
            or (self.operator is not None and not isinstance(self.operator, Operator))
            or self.environment not in {"staging", "production"}
            or self.occurred_at.tzinfo is None
            or _CODE.fullmatch(self.resource_key) is None
            or self.resource_key.lower().startswith(_SECRET_PREFIXES)
            or _RELEASE.fullmatch(self.release_id) is None
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
        ):
            raise ValueError("Autonomous alert fields must be bounded and content-free")


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    id: uuid.UUID
    event_kind: str
    severity: str
    delivered_route: str
    dedup_key: str
    created_at: datetime


Sender = Callable[[str, dict[str, str]], int]


class AutonomousAlertService:
    def __init__(
        self,
        *,
        primary_url: str,
        fallback_url: str,
        digest_url: str = "",
        sender: Sender | None = None,
    ) -> None:
        for route in (primary_url, fallback_url, digest_url):
            parsed = urlsplit(route)
            if route and (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise ValueError("Autonomous delivery routes must use HTTPS")
        if primary_url and primary_url == fallback_url:
            raise ValueError("Autonomous alert fallback must be a distinct route")
        if digest_url and digest_url in {primary_url, fallback_url}:
            raise ValueError("Autonomous digest must use a distinct mobile route")
        self.primary_url = primary_url
        self.fallback_url = fallback_url
        self.digest_url = digest_url
        self.sender = sender or self._send

    @staticmethod
    def _send(url: str, payload: dict[str, str]) -> int:
        with httpx.Client(timeout=5) as client:
            response = client.post(url, json=payload)
        return response.status_code

    @staticmethod
    def _receipt(row: AutonomousAlertDelivery) -> DeliveryReceipt:
        return DeliveryReceipt(
            row.id,
            row.event_kind,
            row.severity,
            row.delivered_route,
            row.dedup_key,
            row.created_at,
        )

    @staticmethod
    def _attempt(
        sender: Sender, url: str, payload: dict[str, str]
    ) -> tuple[str, int | None]:
        if not url:
            return "not_configured", None
        try:
            status = sender(url, payload)
        except (httpx.HTTPError, OSError, RuntimeError):
            return "failed", None
        if not isinstance(status, int) or not 100 <= status <= 599:
            return "failed", None
        return ("acknowledged" if 200 <= status < 300 else "failed"), status

    def _deliver(
        self,
        db: Session,
        alert: AutonomousAlert,
        *,
        digest: Mapping[str, object] | None = None,
    ) -> DeliveryReceipt:
        severity, window_seconds = _RULES[alert.event_kind]
        if digest is None:
            payload = {
                "text": (
                    "PwC autonomous operations alert; "
                    f"event={alert.event_kind}; severity={severity}; "
                    f"operator={alert.operator.value if alert.operator else 'global'}; "
                    f"environment={alert.environment}; release={alert.release_id}; "
                    f"runbook={alert.runbook_url}"
                )
            }
        else:
            if alert.event_kind != "daily_digest":
                raise ValueError("Digest payload requires a daily-digest alert")
            payload = {"text": render_daily_digest(digest)}
        bucket = int(alert.occurred_at.timestamp()) // window_seconds
        resource_digest = sha256(alert.resource_key.encode()).hexdigest()
        release_digest = sha256(alert.release_id.encode()).hexdigest()
        dedup_key = sha256(
            "|".join(
                (
                    alert.event_kind,
                    alert.operator.value if alert.operator else "global",
                    resource_digest,
                    alert.environment,
                    str(bucket),
                )
            ).encode()
        ).hexdigest()
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            db.execute(
                select(
                    func.pg_advisory_xact_lock(
                        func.hashtextextended(f"autonomous:alert:{dedup_key}", 0)
                    )
                )
            )
        existing = db.scalar(
            select(AutonomousAlertDelivery).where(
                AutonomousAlertDelivery.dedup_key == dedup_key
            )
        )
        if existing is not None:
            receipt = self._receipt(existing)
            if severity != "info" and receipt.delivered_route == "none":
                raise AlertDeliveryError("autonomous urgent alert was not acknowledged")
            return receipt

        if digest is not None:
            primary_state, primary_status = self._attempt(
                self.sender, self.digest_url, payload
            )
            fallback_state, fallback_status = "suppressed", None
            delivered_route = (
                "primary"
                if primary_state == "acknowledged"
                else "suppressed"
                if primary_state == "not_configured"
                else "none"
            )
        elif severity == "info":
            primary_state, primary_status = "suppressed", None
            fallback_state, fallback_status = "suppressed", None
            delivered_route = "suppressed"
        else:
            primary_state, primary_status = self._attempt(
                self.sender, self.primary_url, payload
            )
            if primary_state == "acknowledged":
                fallback_state, fallback_status = "not_needed", None
                delivered_route = "primary"
            else:
                fallback_state, fallback_status = self._attempt(
                    self.sender, self.fallback_url, payload
                )
                delivered_route = (
                    "fallback" if fallback_state == "acknowledged" else "none"
                )
        row = AutonomousAlertDelivery(
            id=uuid.uuid4(),
            dedup_key=dedup_key,
            event_kind=alert.event_kind,
            severity=severity,
            operator=alert.operator.value if alert.operator else None,
            resource_digest=resource_digest,
            environment=alert.environment,
            release_digest=release_digest,
            primary_state=primary_state,
            primary_status_code=primary_status,
            fallback_state=fallback_state,
            fallback_status_code=fallback_status,
            delivered_route=delivered_route,
            created_at=alert.occurred_at,
        )
        db.add(row)
        db.commit()
        receipt = self._receipt(row)
        if severity != "info" and delivered_route == "none":
            raise AlertDeliveryError("autonomous urgent alert was not acknowledged")
        return receipt

    def send_autonomous_alert(
        self, db: Session, alert: AutonomousAlert
    ) -> DeliveryReceipt:
        if alert.event_kind == "daily_digest":
            raise ValueError("Daily digest delivery requires aggregate digest data")
        return self._deliver(db, alert)

    def send_daily_digest(
        self,
        db: Session,
        alert: AutonomousAlert,
        digest: Mapping[str, object],
    ) -> DeliveryReceipt:
        receipt = self._deliver(db, alert, digest=digest)
        if receipt.delivered_route != "primary":
            self.send_autonomous_alert(
                db,
                AutonomousAlert(
                    event_kind="operator_failure",
                    operator=alert.operator,
                    resource_key="daily_digest_delivery",
                    environment=alert.environment,
                    release_id=alert.release_id,
                    occurred_at=alert.occurred_at,
                    runbook_url=alert.runbook_url,
                ),
            )
        return receipt


def send_autonomous_alert(
    db: Session,
    alert: AutonomousAlert,
    *,
    primary_url: str,
    fallback_url: str,
) -> DeliveryReceipt:
    return AutonomousAlertService(
        primary_url=primary_url,
        fallback_url=fallback_url,
    ).send_autonomous_alert(db, alert)


def send_budget_threshold_alert(
    db: Session,
    operator: Operator,
    reason_code: str,
    occurred_at: datetime,
) -> None:
    """Route a cumulative-budget transition without exposing run content."""
    from backend.config import get_settings

    settings = get_settings()
    AutonomousAlertService(
        primary_url=settings.autonomous_alert_slack_webhook_url,
        fallback_url=settings.autonomous_alert_fallback_webhook_url,
        digest_url=settings.autonomous_digest_webhook_url,
    ).send_autonomous_alert(
        db,
        AutonomousAlert(
            event_kind="budget_threshold",
            operator=operator,
            resource_key=reason_code,
            environment=settings.environment,
            release_id=settings.release_id or "unknown",
            occurred_at=occurred_at,
            runbook_url=(
                settings.autonomous_alert_runbook_url
                or "https://paperswithcode.co/docs/autonomous-operations#attempt-or-budget-exhausted"
            ),
        ),
    )
