"""Send a content-free alert when scheduled submission review fails."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from backend.config import Settings, get_settings
from backend.database.connection import db_manager
from backend.services.autonomous_alert_service import (
    AutonomousAlert,
    AutonomousAlertService,
)
from backend.services.autonomous_operations_repository import Operator


def build_alert_payload(settings: Settings) -> dict[str, str]:
    return {
        "text": (
            "PwC autonomous submission review failed; severity=critical; "
            f"environment={settings.environment}; release={settings.release_id}; "
            f"runbook={settings.autonomous_alert_runbook_url or 'not-configured'}"
        )
    }


def send_failure_alert(settings: Settings) -> str:
    payload = build_alert_payload(settings)
    routes = (
        ("primary", settings.autonomous_alert_slack_webhook_url),
        ("fallback", settings.autonomous_alert_fallback_webhook_url),
    )
    with httpx.Client(timeout=5) as client:
        for name, url in routes:
            if not url:
                continue
            try:
                response = client.post(url, json=payload)
                response.raise_for_status()
            except httpx.HTTPError:
                continue
            return name
    raise RuntimeError("autonomous submission failure alert delivery failed")


def main() -> int:
    settings = get_settings()
    with db_manager.session_local() as db:
        receipt = AutonomousAlertService(
            primary_url=settings.autonomous_alert_slack_webhook_url,
            fallback_url=settings.autonomous_alert_fallback_webhook_url,
        ).send_autonomous_alert(
            db,
            AutonomousAlert(
                event_kind="operator_failure",
                operator=Operator.SUBMISSIONS,
                resource_key="submission_review",
                environment=settings.environment,
                release_id=settings.release_id or "unknown",
                occurred_at=datetime.now(UTC),
                runbook_url=(
                    settings.autonomous_alert_runbook_url
                    or "https://paperswithcode.co/docs/autonomous-operations"
                ),
            ),
        )
    print(
        "autonomous submission failure alert delivered via "
        f"{receipt.delivered_route} receipt={receipt.id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
