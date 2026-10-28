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
from backend.models.database.identity import UserProfile
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


INK, SOFT, FAINT, ACCENT, HAIRLINE, PAPER = (
    "#1a1a1a",
    "#555555",
    "#8a8a8a",
    "#2f4f7a",
    "#e6e2da",
    "#faf8f4",
)
SERIF = "Georgia,'Times New Roman',serif"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"


def _score_text(score: dict) -> str:
    metrics = ", ".join(f"{k} {v}" for k, v in score["metrics"].items())
    return f"{score['benchmark']} · {score['model'] or 'result'}: {metrics}"


def _published(value: str) -> str:
    try:
        day = datetime.fromisoformat(value)
    except ValueError:
        return value
    return f"{day:%b} {day.day}, {day:%Y}"


def _period(start: datetime | None, end: datetime | None) -> str:
    if not start or not end:
        return ""
    last = end - timedelta(days=1)
    return f"{start:%b} {start.day} – {last:%b} {last.day}, {last:%Y}"


def digest_sections(entries, rotation: int | None = None) -> tuple[list, list]:
    """New papers on the account's topic first, then entity follows, 20 at most."""
    on_topic = [e for e in entries if any(i.startswith("topic:") for i in e.interests)]
    topic_entries = diverse(on_topic, 10)
    seen = {e.paper_key for e in topic_entries}
    rest = diverse(
        [e for e in entries if e.paper_key not in seen],
        20 - len(topic_entries),
        rotation=rotation,
    )
    return topic_entries, rest


def render_digest(
    entries,
    token: str,
    start: datetime | None = None,
    end: datetime | None = None,
    topic_entries=(),
) -> dict:
    """Email-safe digest: table layout and inline styles only; all catalog text escaped.

    ``topic_entries`` lead under "New on your topic"; ``entries`` follow under
    "From what you follow" when both are present.
    """
    esc = html.escape
    unsubscribe = f"{ORIGIN}/api/v1/research/unsubscribe/{token}"
    count = len(entries) + len(topic_entries)
    noun = "paper" if count == 1 else "papers"
    period = _period(start, end)
    intro = f"{count} new {noun} from what you follow" + (
        f", {period}." if period else "."
    )
    lines = ["Papers with Code · Weekly research digest", intro, ""]
    rows = []
    sections = [
        ("New on your topic", list(topic_entries)),
        ("From what you follow", list(entries)),
    ]
    labelled = all(section for _, section in sections)
    for e in [e for _, section in sections for e in section]:
        heading = next(
            (name for name, section in sections if section and section[0] is e), None
        )
        if labelled and heading:
            lines.extend([heading.upper(), ""])
            rows.append(
                f'<tr><td style="padding:22px 0 0;font-family:{SANS};font-size:12px;'
                f'letter-spacing:.08em;text-transform:uppercase;color:{FAINT};">'
                f"{esc(heading)}</td></tr>"
            )
        url = ORIGIN + e.url
        reasons = ", ".join(e.reasons)
        scores = [_score_text(s) for s in e.scores]
        lines.extend([e.title, url, e.summary, f"Matched: {reasons}", *scores, ""])
        score_html = "".join(
            f'<div style="margin-top:4px;font-family:{MONO};font-size:12px;color:{ACCENT};">'
            f"{esc(text)}</div>"
            for text in scores
        )
        rows.append(
            f'<tr><td style="padding:22px 0;border-top:1px solid {HAIRLINE};">'
            f'<a href="{esc(url, quote=True)}" style="font-family:{SERIF};font-size:19px;'
            f'line-height:1.3;color:{INK};text-decoration:none;">{esc(e.title)}</a>'
            f'<div style="margin-top:6px;font-family:{SANS};font-size:12px;color:{FAINT};">'
            f"{esc(_published(e.published))} · Matched: {esc(reasons)}</div>"
            f'<div style="margin-top:8px;font-family:{SANS};font-size:14px;line-height:1.55;'
            f'color:{SOFT};">{esc(e.summary)}</div>{score_html}</td></tr>'
        )
    lines.extend(
        [
            f"See more matches: {ORIGIN}/following",
            f"Manage follows and email: {ORIGIN}/settings",
            f"Unsubscribe: {unsubscribe}",
        ]
    )
    link = f"color:{ACCENT};text-decoration:none;font-weight:600;"
    body = (
        f'<body style="margin:0;padding:0;background:{PAPER};">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{PAPER};"><tr><td align="center" style="padding:32px 16px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="max-width:600px;background:#ffffff;border:1px solid {HAIRLINE};'
        f'border-radius:10px;"><tr><td style="padding:28px 32px 8px;">'
        f'<div style="font-family:{SERIF};font-size:20px;color:{INK};">Papers '
        f'<span style="font-style:italic;color:{ACCENT};">with Code</span></div>'
        f'<div style="margin-top:18px;font-family:{SANS};font-size:12px;letter-spacing:.08em;'
        f'text-transform:uppercase;color:{FAINT};">Weekly research digest</div>'
        f'<div style="margin-top:6px;font-family:{SANS};font-size:15px;color:{SOFT};">'
        f"{esc(intro)}</div></td></tr>"
        f'<tr><td style="padding:0 32px;"><table role="presentation" width="100%" '
        f'cellpadding="0" cellspacing="0">{"".join(rows)}</table></td></tr>'
        f'<tr><td style="padding:20px 32px 28px;border-top:1px solid {HAIRLINE};'
        f'font-family:{SANS};font-size:14px;">'
        f'<a href="{ORIGIN}/following" style="{link}">See more in your Following feed →</a>'
        f"</td></tr></table>"
        f'<div style="max-width:600px;margin-top:16px;font-family:{SANS};font-size:12px;'
        f'line-height:1.6;color:{FAINT};">You receive this because you turned on the weekly '
        f"email on Papers with Code. "
        f'<a href="{ORIGIN}/settings" style="color:{FAINT};">Manage follows and email</a> · '
        f'<a href="{esc(unsubscribe, quote=True)}" style="color:{FAINT};">Unsubscribe</a>'
        f"</div></td></tr></table></body>"
    )
    return {
        "subject": f"Your weekly research digest: {count} new {noun}",
        "text": "\n".join(lines),
        "html": f'<!doctype html><html><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"></head>{body}</html>',
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
    topic_entries, selected = digest_sections(
        entries, rotation=(end.date().toordinal() // 7) * 20
    )
    payload = render_digest(
        selected, sub.unsubscribe_token, start, end, topic_entries=topic_entries
    )
    payload.update({"to": [sub.email], "from": get_settings().resend_from})
    db.execute(
        insert(ResearchDigest)
        .values(
            hf_subject=subject,
            window_end=end,
            status="pending" if selected or topic_entries else "empty",
            payload=payload,
        )
        .on_conflict_do_nothing()
    )
    db.commit()
    return db.get(ResearchDigest, (subject, end))


def subject_for_username(db: Session, username: str) -> str | None:
    return db.scalar(
        select(UserProfile.hf_subject).where(UserProfile.current_username == username)
    )


def sample_digest(db: Session, subject: str, now: datetime) -> dict | None:
    """Render the past week's feed matches as a digest, without outbox or event gating.

    Lets operators review the email before launch; real digests only contain
    updates discovered after each follow and opt-in.
    """
    sub = db.get(ResearchSubscription, subject)
    if not sub:
        return None
    # The last seven days including today; render_digest treats ``end`` as exclusive.
    start = now - timedelta(days=6)
    entries = matching_entries(db, subject, now, cutoff=start.date())
    topic_entries, selected = digest_sections(entries)
    payload = render_digest(
        selected,
        sub.unsubscribe_token,
        start,
        now + timedelta(days=1),
        topic_entries=topic_entries,
    )
    payload.update(
        {"to": [sub.email] if sub.email else [], "from": get_settings().resend_from}
    )
    return payload


def send_test_digest(db: Session, subject: str, now: datetime) -> str:
    """Send one sample digest to the subscriber's own opted-in, unsuppressed address."""
    if not delivery_ready():
        return "disabled"
    sub = db.get(ResearchSubscription, subject)
    if not sub or not sub.enabled or not sub.email or suppressed(db, sub.email):
        return "not-opted-in"
    payload = sample_digest(db, subject, now)
    payload["subject"] = "[Test] " + payload["subject"]
    response = httpx.post(
        "https://api.resend.com/emails",
        json=payload,
        headers={"Authorization": f"Bearer {get_settings().resend_api_key}"},
        timeout=20,
    )
    response.raise_for_status()
    return f"sent {response.json()['id']} to {sub.email}"


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
