"""Weekly digest outbox and Resend delivery. Disabled unless every launch gate is set."""

import base64
import hashlib
import hmac
import html
import json
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import case, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.database.research import (
    ResearchDigest,
    ResearchSubscription,
    ResearchSuppression,
)
from backend.services.research_follow_service import (
    diverse,
    matching_entries,
    suppressed,
)

ORIGIN = "https://paperswithcode.co"


def delivery_ready() -> bool:
    s = get_settings()
    return bool(
        s.research_email_enabled
        and s.resend_api_key
        and s.resend_from
        and s.resend_domain_verified
        and s.resend_webhook_secret
        and s.resend_webhooks_ready
        and s.environment == "production"
    )


def weekly_window(now: datetime) -> tuple[datetime, datetime]:
    now = now.astimezone(timezone.utc)
    end = now.replace(hour=8, minute=0, second=0, microsecond=0) - timedelta(
        days=now.weekday()
    )
    if end > now:
        end -= timedelta(days=7)
    return end - timedelta(days=7), end


def render_digest(entries, token: str) -> dict:
    unsubscribe = f"{ORIGIN}/api/v1/research/unsubscribe/{token}"
    lines = ["Your weekly research updates", ""]
    blocks = ["<h1>Your weekly research updates</h1>"]
    for e in entries:
        reasons = ", ".join(e.reasons)
        scores = "; ".join(
            f"{s['benchmark']} ({s['model'] or 'result'}): "
            + ", ".join(f"{k}: {v}" for k, v in s["metrics"].items())
            for s in e.scores
        )
        url = ORIGIN + e.url
        lines.extend([e.title, e.summary, reasons, scores, url, ""])
        blocks.append(
            f'<h2><a href="{html.escape(url, quote=True)}">{html.escape(e.title)}</a></h2>'
            f"<p>{html.escape(e.summary)}</p><p>{html.escape(reasons)}</p>"
            f"<p>{html.escape(scores)}</p>"
        )
    lines.extend([f"More matches: {ORIGIN}/following", f"Unsubscribe: {unsubscribe}"])
    blocks.append(
        f'<p><a href="{ORIGIN}/following">More matches in your Following feed</a></p>'
        f'<p><a href="{unsubscribe}">Unsubscribe</a></p>'
    )
    return {
        "subject": "Your weekly research updates",
        "text": "\n".join(lines),
        "html": "".join(blocks),
        "headers": {
            "List-Unsubscribe": f"<{unsubscribe}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    }


def prepare_digest(db: Session, subject: str, now: datetime) -> ResearchDigest | None:
    start, end = weekly_window(now)
    # Do not resurrect missed weeks or create a backlog when delivery is enabled.
    if now - end >= timedelta(hours=23):
        return None
    existing = db.get(ResearchDigest, (subject, end))
    if existing:
        return existing
    sub = db.get(ResearchSubscription, subject)
    if not sub or not sub.enabled or not sub.email or suppressed(db, sub.email):
        return None
    entries = matching_entries(
        db,
        subject,
        now,
        window_start=start,
        window_end=end,
        opted_in_at=sub.opted_in_at,
    )
    selected = diverse(entries, 20, rotation=(end.date().toordinal() // 7) * 20)
    payload = render_digest(selected, sub.unsubscribe_token)
    payload.update({"to": [sub.email], "from": get_settings().resend_from})
    db.execute(
        insert(ResearchDigest)
        .values(
            hf_subject=subject,
            window_end=end,
            status="pending" if selected else "empty",
            payload=payload,
        )
        .on_conflict_do_nothing()
    )
    db.commit()
    return db.get(ResearchDigest, (subject, end))


def expire_pending_digests(db: Session, now: datetime) -> int:
    """Close old outboxes even when the hourly run is outside its send window."""
    result = db.execute(
        update(ResearchDigest)
        .where(
            ResearchDigest.status == "pending",
            ResearchDigest.window_end <= now - timedelta(hours=23),
        )
        .values(
            status=case(
                (ResearchDigest.first_attempt_at.is_not(None), "uncertain"),
                else_="expired",
            )
        )
    )
    db.commit()
    return result.rowcount


def deliver_digest(db: Session, subject: str, end: datetime, now: datetime) -> str:
    if not delivery_ready():
        return "disabled"
    # Lock the subscription too: unsubscribe/opt-out serialize with the send.
    sub = db.scalar(
        select(ResearchSubscription)
        .where(ResearchSubscription.hf_subject == subject)
        .with_for_update()
    )
    digest = db.scalar(
        select(ResearchDigest)
        .where(ResearchDigest.hf_subject == subject, ResearchDigest.window_end == end)
        .with_for_update()
    )
    if digest is None or digest.status != "pending":
        return digest.status if digest else "missing"
    if (
        not sub
        or not sub.enabled
        or not sub.email
        or suppressed(db, sub.email)
        or digest.payload["to"] != [sub.email]
        or (sub.opted_in_at and sub.opted_in_at >= end)
    ):
        digest.status = "cancelled"
        db.commit()
        return "cancelled"
    # Resend retains keys for 24h. Never retry an ambiguous request beyond 23h.
    if digest.first_attempt_at and now - digest.first_attempt_at >= timedelta(hours=23):
        digest.status = "uncertain"
        db.commit()
        return "uncertain"
    if digest.first_attempt_at is None:
        digest.first_attempt_at = now
        db.commit()  # Durable pre-POST checkpoint, before any network side effect.
        return deliver_digest(db, subject, end, now)
    key = (
        "research-"
        + hashlib.sha256(f"{subject}:{end.isoformat()}".encode()).hexdigest()
    )
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            json=digest.payload,
            headers={
                "Authorization": f"Bearer {get_settings().resend_api_key}",
                "Idempotency-Key": key,
            },
            timeout=20,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        db.rollback()  # Keep the immutable payload/key pending for bounded retries.
        return "retry"
    digest.provider_id = response.json()["id"]
    digest.status = "sent"
    db.commit()
    return "sent"


def verify_webhook(body: bytes, headers, secret: str, now: float | None = None) -> dict:
    """Resend's Standard Webhooks/Svix HMAC with timestamp replay protection."""
    stamp = headers.get("svix-timestamp", "")
    event_id = headers.get("svix-id", "")
    if not secret or not event_id or abs((now or time.time()) - int(stamp)) > 300:
        raise ValueError("Invalid webhook timestamp")
    key = base64.b64decode(secret.removeprefix("whsec_"), validate=True)
    signed = event_id.encode() + b"." + stamp.encode() + b"." + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    if not any(
        hmac.compare_digest(part, "v1," + expected)
        for part in headers.get("svix-signature", "").split()
    ):
        raise ValueError("Invalid webhook signature")
    event = json.loads(body)
    if not isinstance(event, dict):
        raise ValueError("Invalid webhook payload")
    return event


def record_suppression(db: Session, event: dict) -> None:
    if event.get("type") not in (
        "email.bounced",
        "email.complained",
        "email.suppressed",
    ):
        return
    recipients = event.get("data", {}).get("to", [])
    if not isinstance(recipients, list):
        raise ValueError("Invalid recipients")
    for email in recipients:
        if not isinstance(email, str) or len(email) > 320:
            raise ValueError("Invalid recipient")
        email = email.lower()
        db.execute(
            insert(ResearchSuppression)
            .values(email=email, reason=event["type"])
            .on_conflict_do_nothing()
        )
        # Suppression is address-wide, including any other account using it.
        db.query(ResearchSubscription).filter(
            ResearchSubscription.email == email
        ).update({"enabled": False})
    db.commit()
