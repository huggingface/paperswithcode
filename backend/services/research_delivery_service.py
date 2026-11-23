"""Weekly digest outbox and Resend delivery. Disabled unless every launch gate is set."""

import base64
import hashlib
import hmac
import html
import json
import time
from collections import Counter
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


INK, SOFT, FAINT, ACCENT, HAIRLINE, PAPER, ELEVATED, SUBTLE = (
    "#1a1814",
    "#5a554c",
    "#8e8678",
    "#305880",
    "#e4dfd4",
    "#faf8f4",
    "#ffffff",
    "#f2efe8",
)
SERIF = "Newsreader,Georgia,'Times New Roman',serif"
SANS = "Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
FONTS = (
    "https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@"
    "0,6..72,500;0,6..72,600;1,6..72,400&family=Inter:wght@400;600"
    "&family=JetBrains+Mono:wght@400;500&display=swap"
)
HEAD = (
    '<meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    '<meta name="color-scheme" content="light only">'
    f'<link href="{FONTS}" rel="stylesheet">'
    "<style>@media (max-width:520px){"
    ".pwc-pad{padding-left:20px!important;padding-right:20px!important}"
    ".pwc-thumb{width:72px!important;height:102px!important}"
    ".pwc-thumb-cell{width:72px!important;padding-right:14px!important}"
    ".pwc-title{font-size:26px!important}}</style>"
)
EYEBROW = (
    f"font-family:{MONO};font-size:11px;font-weight:500;letter-spacing:.12em;"
    f"text-transform:uppercase;color:{FAINT};"
)
TABLE = 'role="presentation" cellpadding="0" cellspacing="0" border="0"'
MARK = (
    f'<table {TABLE} width="24" style="width:24px;border-collapse:collapse;">'
    f'<tr><td style="padding:4px;background:{INK};line-height:0;">'
    f'<table {TABLE} width="16" style="width:16px;border-collapse:collapse;">'
    f'<tr><td style="padding:5px;background:{PAPER};line-height:0;">'
    f'<table {TABLE} width="6" style="width:6px;border-collapse:collapse;">'
    f'<tr><td height="6" style="height:6px;background:{INK};line-height:0;'
    f'font-size:0;">&nbsp;</td></tr></table></td></tr></table></td></tr></table>'
)


def _wordmark(size: int) -> str:
    return (
        f'<table {TABLE}><tr><td valign="middle" style="padding-right:10px;">{MARK}</td>'
        f'<td valign="middle" style="font-family:{SERIF};font-size:{size}px;'
        f'line-height:1;color:{INK};font-weight:600;white-space:nowrap;">Papers '
        f'<span style="font-style:italic;font-weight:400;color:{SOFT};">with Code</span>'
        f"</td></tr></table>"
    )


def _absolute(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("/"):
        return ORIGIN + url
    if url.startswith("https://"):
        return url
    return None


def _card(e, url: str, also: str, scores: list[str]) -> str:
    esc = html.escape
    href = esc(url, quote=True)
    thumbnail = _absolute(e.thumbnail_url)
    thumb_html = (
        f'<td class="pwc-thumb-cell" width="96" valign="top" '
        f'style="width:96px;padding-right:20px;"><a href="{href}">'
        f'<img class="pwc-thumb" src="{esc(thumbnail, quote=True)}" width="96" '
        f'height="136" alt="" style="display:block;width:96px;height:136px;'
        f"object-fit:cover;object-position:top;border:1px solid {HAIRLINE};"
        f'border-radius:4px;background:{SUBTLE};"></a></td>'
        if thumbnail
        else ""
    )
    also_html = (
        f'<div style="font-family:{SANS};font-size:12px;line-height:1.5;color:{FAINT};">'
        f"Also matches {esc(also)}</div>"
        if also
        else ""
    )
    score_html = "".join(
        f'<div style="margin-top:8px;"><span style="display:inline-block;padding:3px 8px;'
        f"background:{SUBTLE};border-radius:4px;font-family:{MONO};font-size:12px;"
        f'line-height:1.5;color:{INK};">{esc(text)}</span></div>'
        for text in scores
    )
    return (
        f'<tr><td style="padding:24px 0;border-top:1px solid {HAIRLINE};">'
        f'<table {TABLE} width="100%"><tr>{thumb_html}<td valign="top">{also_html}'
        f'<a href="{href}" style="display:block;margin-top:4px;font-family:{SERIF};'
        f"font-size:20px;font-weight:500;line-height:1.25;letter-spacing:-.01em;"
        f'color:{INK};text-decoration:none;">{esc(e.title)}</a>'
        f'<div style="margin-top:6px;font-family:{MONO};font-size:12px;color:{FAINT};">'
        f"{esc(_published(e.published))}</div>"
        f'<div style="margin-top:10px;font-family:{SANS};font-size:14px;line-height:1.6;'
        f'color:{SOFT};">{esc(e.summary)}</div>{score_html}</td></tr></table></td></tr>'
    )


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
    """New papers on the account's topics first, then entity follows, 20 at most."""
    on_topic = [e for e in entries if any(i.startswith("topic:") for i in e.interests)]
    topic_entries = diverse(on_topic, 10)
    seen = {e.paper_key for e in topic_entries}
    rest = diverse(
        [e for e in entries if e.paper_key not in seen],
        20 - len(topic_entries),
        rotation=rotation,
    )
    return topic_entries, rest


def digest_groups(entries, topic_entries=()) -> list[tuple[str, list]]:
    """One heading per follow, topics first and larger groups earlier.

    A paper sits under its most shared topic, or its most shared follow when it
    matched no topic, so it appears once.
    """
    groups = {}
    for batch, topical in ((list(topic_entries), True), (list(entries), False)):
        options = {
            id(e): [
                reason
                for interest, reason in zip(e.interests, e.reasons)
                if not topical or interest.startswith("topic:")
            ]
            or e.reasons
            for e in batch
        }
        counts = Counter(reason for e in batch for reason in options[id(e)])
        for e in batch:
            label = max(options[id(e)], key=counts.__getitem__, default="")
            groups.setdefault((topical, label), []).append(e)
    ordered = sorted(groups.items(), key=lambda item: (not item[0][0], -len(item[1])))
    return [(label, group) for (_, label), group in ordered]


def render_digest(
    entries,
    token: str,
    start: datetime | None = None,
    end: datetime | None = None,
    topic_entries=(),
) -> dict:
    """Email-safe digest: table layout and inline styles only; all catalog text escaped.

    Papers are grouped under the follow they matched (``digest_groups``), with
    ``topic_entries`` grouped by topic ahead of ``entries``.
    """
    esc = html.escape
    unsubscribe = f"{ORIGIN}/api/v1/research/unsubscribe/{token}"
    count = len(entries) + len(topic_entries)
    noun = "paper" if count == 1 else "papers"
    period = _period(start, end)
    headline = f"{count} new {noun} from what you follow"
    intro = headline + (f", {period}." if period else ".")
    lines = ["Papers with Code · Weekly research digest", intro, ""]
    rows = []
    for index, (label, group) in enumerate(digest_groups(entries, topic_entries)):
        heading = label.strip("\u201c\u201d") or "From what you follow"
        size = f"{len(group)} {'paper' if len(group) == 1 else 'papers'}"
        lines.extend([f"{heading.upper()} ({size})", ""])
        rows.append(
            f'<tr><td style="padding:{16 if index == 0 else 40}px 0 12px;">'
            f'<table {TABLE} width="100%"><tr><td valign="bottom" style="font-family:'
            f"{SERIF};font-size:22px;font-weight:500;line-height:1.2;"
            f'letter-spacing:-.01em;color:{INK};">{esc(heading)}</td>'
            f'<td valign="bottom" align="right" style="padding-left:12px;white-space:nowrap;'
            f'font-family:{MONO};font-size:12px;color:{FAINT};">{size}</td></tr></table>'
            f"</td></tr>"
        )
        for e in group:
            url = ORIGIN + e.url
            also = ", ".join(r for r in e.reasons if r != label)
            scores = [_score_text(s) for s in e.scores]
            lines.extend([e.title, url, e.summary])
            if also:
                lines.append(f"Also matches {also}")
            lines.extend([*scores, ""])
            rows.append(_card(e, url, also, scores))
    lines.extend(
        [
            f"See more matches: {ORIGIN}/following",
            f"Manage follows and email: {ORIGIN}/settings",
            f"Unsubscribe: {unsubscribe}",
        ]
    )
    period_html = (
        f'<div style="margin-top:8px;font-family:{SANS};font-size:15px;line-height:1.5;'
        f'color:{SOFT};">{esc(period)}</div>'
        if period
        else ""
    )
    footer_link = f"color:{SOFT};text-decoration:underline;"
    body = (
        f'<body style="margin:0;padding:0;background:{PAPER};">'
        f'<div style="display:none;max-height:0;overflow:hidden;">{esc(intro)}</div>'
        f'<table {TABLE} width="100%" style="background:{PAPER};">'
        f'<tr><td align="center" style="padding:32px 16px;">'
        f'<table {TABLE} width="100%" style="max-width:640px;background:{ELEVATED};'
        f'border:1px solid {HAIRLINE};border-radius:8px;">'
        f'<tr><td class="pwc-pad" style="padding:22px 36px;border-bottom:1px solid '
        f'{HAIRLINE};"><a href="{ORIGIN}" style="text-decoration:none;">{_wordmark(20)}'
        f"</a></td></tr>"
        f'<tr><td class="pwc-pad" style="padding:32px 36px 4px;">'
        f'<div style="{EYEBROW}">Weekly research digest</div>'
        f'<div class="pwc-title" style="margin-top:10px;font-family:{SERIF};font-size:30px;'
        f'font-weight:500;line-height:1.15;letter-spacing:-.02em;color:{INK};">'
        f"{esc(headline)}</div>{period_html}</td></tr>"
        f'<tr><td class="pwc-pad" style="padding:16px 36px 8px;">'
        f'<table {TABLE} width="100%">{"".join(rows)}</table></td></tr>'
        f'<tr><td class="pwc-pad" style="padding:28px 36px 32px;border-top:1px solid '
        f'{HAIRLINE};"><table {TABLE}><tr><td style="background:{ACCENT};'
        f'border-radius:6px;"><a href="{ORIGIN}/following" style="display:inline-block;'
        f"padding:12px 20px;font-family:{SANS};font-size:14px;font-weight:600;"
        f'color:#ffffff;text-decoration:none;">See more in your Following feed →</a>'
        f"</td></tr></table></td></tr></table>"
        f'<table {TABLE} width="100%" style="max-width:640px;">'
        f'<tr><td class="pwc-pad" style="padding:24px 36px 0;font-family:{SANS};'
        f'font-size:12px;line-height:1.6;color:{FAINT};">'
        f"You receive this because you turned on the weekly email on Papers with Code. "
        f'<a href="{ORIGIN}/settings" style="{footer_link}">Manage follows and email</a>'
        f' · <a href="{esc(unsubscribe, quote=True)}" style="{footer_link}">Unsubscribe</a>'
        f'<div style="margin-top:12px;font-family:{MONO};font-size:11px;color:{FAINT};">'
        f'<a href="{ORIGIN}" style="color:{FAINT};text-decoration:none;">'
        f"paperswithcode.co</a></div></td></tr></table></td></tr></table></body>"
    )
    return {
        "subject": f"Your weekly research digest: {count} new {noun}",
        "text": "\n".join(lines),
        "html": f"<!doctype html><html><head>{HEAD}</head>{body}</html>",
        "headers": {
            "List-Unsubscribe": f"<{unsubscribe}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    }


def prepare_digest(db: Session, subject: str, now: datetime) -> ResearchDigest | None:
    start, end = weekly_window(now)
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
    if digest.first_attempt_at and now - digest.first_attempt_at >= timedelta(hours=23):
        digest.status = "uncertain"
        db.commit()
        return "uncertain"
    if digest.first_attempt_at is None:
        digest.first_attempt_at = now
        db.commit()
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
        db.rollback()
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
        db.query(ResearchSubscription).filter(
            ResearchSubscription.email == email
        ).update({"enabled": False})
    db.commit()
