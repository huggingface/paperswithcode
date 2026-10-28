"""Authenticated private follows and public signed delivery callbacks."""

from datetime import date, datetime, timezone
import binascii
import json
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.models.database.research import ResearchSubscription
from backend.models.research import (
    FollowKind,
    FollowView,
    ResearchFeedEntry,
    SubscriptionUpdate,
    SubscriptionView,
    TopicUpdate,
    TopicView,
)
from backend.routers.auth import decode_request_session
from backend.services import research_follow_service as service
from backend.services import research_topic_service
from backend.services.research_delivery_service import (
    delivery_ready,
    verify_webhook,
    record_suppression,
)
from backend.utils.auth import require_user

router = APIRouter(tags=["research"])


@router.get("/me/follows", response_model=list[FollowView])
def list_follows(
    user: dict = Depends(require_user), db: Session = Depends(get_database_session)
):
    return service.follows(db, user["hf_subject"])


@router.put("/me/follows/{kind}/{entity_id}", status_code=204)
def follow(
    kind: FollowKind,
    entity_id: int,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    service.set_follow(db, user["hf_subject"], kind, entity_id, True)


@router.delete("/me/follows/{kind}/{entity_id}", status_code=204)
def unfollow(
    kind: FollowKind,
    entity_id: int,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    service.set_follow(db, user["hf_subject"], kind, entity_id, False)


@router.get("/me/topic", response_model=TopicView | None)
def topic(
    user: dict = Depends(require_user), db: Session = Depends(get_database_session)
):
    return research_topic_service.topic_view(db, user["hf_subject"])


@router.put("/me/topic", response_model=TopicView)
def set_topic(
    body: TopicUpdate,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    text = research_topic_service.display_text(body.text)
    if len(research_topic_service.normalize(text)) < 3:
        raise HTTPException(422, "Describe the topic in a few words")
    research_topic_service.set_topic(
        db, user["hf_subject"], text, datetime.now(timezone.utc)
    )
    return research_topic_service.topic_view(db, user["hf_subject"])


@router.delete("/me/topic", status_code=204)
def clear_topic(
    user: dict = Depends(require_user), db: Session = Depends(get_database_session)
):
    research_topic_service.set_topic(
        db, user["hf_subject"], None, datetime.now(timezone.utc)
    )


@router.get("/me/following", response_model=list[ResearchFeedEntry])
def following(
    offset: int = Query(0, ge=0),
    limit: int = Query(40, ge=1, le=100),
    start_date: date | None = Query(
        None, description="Earliest publication date; defaults to 30 days ago"
    ),
    end_date: date | None = Query(
        None, description="Latest publication date; defaults to today"
    ),
    all_time: bool = Query(False, description="Ignore the default 30-day window"),
    has_code: bool = Query(False, description="Only papers with linked code"),
    has_hf_artifacts: bool = Query(
        False, description="Only papers with Hugging Face artifacts"
    ),
    topic_only: bool = Query(False, description="Only papers matching the topic"),
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    return service.feed_entries(
        db,
        user["hf_subject"],
        datetime.now(timezone.utc),
        offset,
        limit,
        start_date=start_date,
        end_date=end_date,
        all_time=all_time,
        has_code=has_code,
        has_hf_artifacts=has_hf_artifacts,
        topic_only=topic_only,
    )


def subscription_view(db, sub, request):
    identity = decode_request_session(request) or {}
    verified = identity.get("email") if identity.get("email_verified") is True else None
    email = sub.email or verified
    return SubscriptionView(
        enabled=sub.enabled,
        email=email,
        suppressed=service.suppressed(db, email),
        delivery_ready=delivery_ready(),
    )


@router.get("/me/research-email", response_model=SubscriptionView)
def email_settings(
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    sub = service.subscription(db, user["hf_subject"])
    db.commit()
    return subscription_view(db, sub, request)


@router.put("/me/research-email", response_model=SubscriptionView)
def update_email(
    body: SubscriptionUpdate,
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    service.subscription(db, user["hf_subject"])
    sub = db.scalar(
        select(ResearchSubscription)
        .where(ResearchSubscription.hf_subject == user["hf_subject"])
        .with_for_update()
    )
    if body.enabled:
        identity = decode_request_session(request) or {}
        email = identity.get("email")
        if (
            identity.get("email_verified") is not True
            or not isinstance(email, str)
            or not email.strip()
            or len(email) > 320
        ):
            raise HTTPException(
                409, "Request verified email access from Hugging Face before opting in"
            )
        email = email.strip().lower()
        if service.suppressed(db, email):
            raise HTTPException(409, "Delivery to this email address is suppressed")
        if not sub.enabled or sub.email != email:
            sub.opted_in_at = datetime.now(timezone.utc)
        sub.email = email
    sub.enabled = body.enabled
    db.commit()
    return subscription_view(db, sub, request)


@router.get("/research/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe_page(token: str):
    # GET is a confirmation page: email-link scanners must not opt users out.
    return '<h1>Unsubscribe from weekly research emails</h1><form method="post"><button>Unsubscribe</button></form>'


@router.post("/research/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe(token: str, db: Session = Depends(get_database_session)):
    sub = db.scalar(
        select(ResearchSubscription)
        .where(ResearchSubscription.unsubscribe_token == token)
        .with_for_update()
    )
    if sub:
        sub.enabled = False
        db.commit()
    return "<h1>You are unsubscribed</h1><p>Your research follows are unchanged.</p>"


MAX_WEBHOOK_BYTES = 100_000


async def _bounded_body(request: Request, limit: int) -> bytes:
    """Read at most ``limit`` bytes, refusing before buffering anything larger."""

    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, "Webhook too large")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise HTTPException(413, "Webhook too large")
    return bytes(body)


@router.post("/research/resend-webhook", status_code=204)
async def resend_webhook(request: Request, db: Session = Depends(get_database_session)):
    body = await _bounded_body(request, MAX_WEBHOOK_BYTES)
    try:
        event = verify_webhook(
            body, request.headers, get_settings().resend_webhook_secret
        )
        record_suppression(db, event)
    except (ValueError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise HTTPException(400, "Invalid webhook") from exc
