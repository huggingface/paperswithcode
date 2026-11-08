"""Authenticated follows, public topic pages, and signed delivery callbacks."""

from datetime import date, datetime, timezone
import binascii
import json
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.models.database.research import ResearchSubscription
from backend.models.papers import Paper
from backend.models.research import (
    FollowerVisibilityUpdate,
    FollowKind,
    FollowSuggestions,
    FollowView,
    PublicTopicView,
    ResearchFeedEntry,
    SubscriptionUpdate,
    SubscriptionView,
    TopicBubble,
    TopicOrderUpdate,
    TopicUpdate,
    TopicView,
    TopicVisibilityUpdate,
)
from backend.routers.auth import decode_request_session
from backend.services import public_topic_service
from backend.services import research_follow_service as service
from backend.services import research_topic_service
from backend.services.research_delivery_service import (
    delivery_ready,
    verify_webhook,
    record_suppression,
)
from backend.utils.auth import require_user

router = APIRouter(tags=["research"])


@router.get("/research/follow-suggestions", response_model=FollowSuggestions)
def follow_suggestions(response: Response, db: Session = Depends(get_database_session)):
    response.headers["Cache-Control"] = "public, max-age=300"
    return service.suggestions(db)


@router.get("/me/follows", response_model=list[FollowView])
def list_follows(
    user: dict = Depends(require_user), db: Session = Depends(get_database_session)
):
    return service.follows(db, user["hf_subject"])


@router.put("/me/follows/{kind}/{entity_id}", status_code=204)
def follow(
    kind: FollowKind,
    entity_id: int,
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    service.set_follow(db, user["hf_subject"], kind, entity_id, True)
    service.default_email_on(
        db, user["hf_subject"], verified_email(request), datetime.now(timezone.utc)
    )


@router.delete("/me/follows/{kind}/{entity_id}", status_code=204)
def unfollow(
    kind: FollowKind,
    entity_id: int,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    service.set_follow(db, user["hf_subject"], kind, entity_id, False)


def _topic_text(body: TopicUpdate) -> str:
    text = research_topic_service.display_text(body.text)
    if len(research_topic_service.normalize(text)) < 3:
        raise HTTPException(422, "Describe the topic in a few words")
    return text


def _save_topic(
    db: Session, request: Request, subject: str, body: TopicUpdate, replace: int | None
) -> TopicView:
    now = datetime.now(timezone.utc)
    try:
        topic_id = research_topic_service.follow_topic(
            db, subject, _topic_text(body), now, replace=replace
        )
    except LookupError as exc:
        raise HTTPException(404, "Topic not found") from exc
    except OverflowError as exc:
        raise HTTPException(
            409, f"You can follow up to {research_topic_service.MAX_TOPICS} topics"
        ) from exc
    service.default_email_on(db, subject, verified_email(request), now)
    return research_topic_service.topic_view(db, subject, topic_id)


@router.get("/me/topics", response_model=list[TopicView])
def topics(
    user: dict = Depends(require_user), db: Session = Depends(get_database_session)
):
    return research_topic_service.topic_views(db, user["hf_subject"])


@router.post("/me/topics", response_model=TopicView, status_code=201)
def add_topic(
    body: TopicUpdate,
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    """Follow one more topic; following one already followed returns it."""
    return _save_topic(db, request, user["hf_subject"], body, None)


# Declared before /me/topics/{topic_id} so "order" is not read as an id.
@router.put("/me/topics/order", response_model=list[TopicView])
def reorder_topics(
    body: TopicOrderUpdate,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    """Store the account's topic order; the body lists every followed topic once."""
    try:
        research_topic_service.reorder_topics(db, user["hf_subject"], body.topic_ids)
    except ValueError as exc:
        raise HTTPException(409, "List every followed topic exactly once") from exc
    return research_topic_service.topic_views(db, user["hf_subject"])


@router.put("/me/topics/{topic_id}", response_model=TopicView)
def update_topic(
    topic_id: int,
    body: TopicUpdate,
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    """Replace a followed topic's text; saving the same text retries a failed backfill."""
    return _save_topic(db, request, user["hf_subject"], body, topic_id)


@router.delete("/me/topics/{topic_id}", status_code=204)
def remove_topic(
    topic_id: int,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    research_topic_service.unfollow_topic(db, user["hf_subject"], topic_id)


@router.post("/me/topics/{topic_id}/follow", response_model=TopicView, status_code=201)
def follow_existing_topic(
    topic_id: int,
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    """Follow another account's public topic; following it again returns it."""
    subject = user["hf_subject"]
    now = datetime.now(timezone.utc)
    try:
        research_topic_service.follow_existing_topic(db, subject, topic_id, now)
    except LookupError as exc:
        raise HTTPException(404, "Topic not found") from exc
    except OverflowError as exc:
        raise HTTPException(
            409, f"You can follow up to {research_topic_service.MAX_TOPICS} topics"
        ) from exc
    service.default_email_on(db, subject, verified_email(request), now)
    return research_topic_service.topic_view(db, subject, topic_id)


@router.patch("/me/topics/{topic_id}", response_model=TopicView)
def set_topic_visibility(
    topic_id: int,
    body: TopicVisibilityUpdate,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    """Make a topic you created public or private."""
    try:
        research_topic_service.set_public(
            db, user["hf_subject"], topic_id, body.is_public
        )
    except LookupError as exc:
        raise HTTPException(404, "Only the topic's creator can change it") from exc
    return research_topic_service.topic_view(db, user["hf_subject"], topic_id)


@router.put("/me/topic-follower-visibility", status_code=204)
def set_follower_visibility(
    body: FollowerVisibilityUpdate,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    """Show or hide the account's avatar on public topics it follows."""
    public_topic_service.set_show_as_follower(
        db, user["hf_subject"], body.show_as_follower
    )


def viewer_subject(request: Request) -> str | None:
    subject = (decode_request_session(request) or {}).get("sub")
    return subject.strip() if isinstance(subject, str) and subject.strip() else None


# Declared before /research/topics/{topic_id} so "featured" is not read as an id.
@router.get("/research/topics/featured", response_model=list[TopicBubble])
def featured_topics(response: Response, db: Session = Depends(get_database_session)):
    response.headers["Cache-Control"] = "public, max-age=600"
    return public_topic_service.bubbles(db, datetime.now(timezone.utc))


@router.get("/research/topics/{topic_id}", response_model=PublicTopicView)
def public_topic(
    topic_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_database_session),
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return public_topic_service.topic_view(db, topic_id, viewer_subject(request))
    except LookupError as exc:
        raise HTTPException(404, "Topic not found") from exc


@router.get("/research/topics/{topic_id}/papers", response_model=list[Paper])
def public_topic_papers(
    topic_id: int,
    request: Request,
    response: Response,
    order: Literal["trending", "newest"] = Query("trending"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    start_date: date | None = Query(None, description="Earliest publication date"),
    end_date: date | None = Query(None, description="Latest publication date"),
    db: Session = Depends(get_database_session),
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return public_topic_service.topic_papers(
            db,
            topic_id,
            viewer_subject(request),
            order=order,
            offset=offset,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )
    except LookupError as exc:
        raise HTTPException(404, "Topic not found") from exc


# Single-topic endpoints from before accounts could follow several: they read
# and replace the account's first topic, and DELETE removes every topic.
@router.get("/me/topic", response_model=TopicView | None)
def topic(
    user: dict = Depends(require_user), db: Session = Depends(get_database_session)
):
    return next(iter(research_topic_service.topic_views(db, user["hf_subject"])), None)


@router.put("/me/topic", response_model=TopicView)
def set_topic(
    body: TopicUpdate,
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    first = next(iter(research_topic_service.topic_views(db, user["hf_subject"])), None)
    return _save_topic(db, request, user["hf_subject"], body, first and first.id)


@router.delete("/me/topic", status_code=204)
def clear_topic(
    user: dict = Depends(require_user), db: Session = Depends(get_database_session)
):
    research_topic_service.unfollow_topic(db, user["hf_subject"])


@router.get("/me/following", response_model=list[ResearchFeedEntry])
def following(
    request: Request,
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
    topic_only: bool = Query(False, description="Only papers matching a topic"),
    topic_id: int | None = Query(None, description="Only papers matching this topic"),
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    now = datetime.now(timezone.utc)
    if offset == 0:
        service.default_email_on(db, user["hf_subject"], verified_email(request), now)
    return service.feed_entries(
        db,
        user["hf_subject"],
        now,
        offset,
        limit,
        start_date=start_date,
        end_date=end_date,
        all_time=all_time,
        has_code=has_code,
        has_hf_artifacts=has_hf_artifacts,
        topic_only=topic_only,
        topic_id=topic_id,
    )


def verified_email(request: Request) -> str | None:
    """The session's verified Hugging Face email, normalized, or None."""
    identity = decode_request_session(request) or {}
    email = identity.get("email")
    if (
        identity.get("email_verified") is not True
        or not isinstance(email, str)
        or not email.strip()
        or len(email) > 320
    ):
        return None
    return email.strip().lower()


def subscription_view(db, sub, request):
    email = sub.email or verified_email(request)
    return SubscriptionView(
        enabled=sub.enabled,
        email=email,
        suppressed=service.suppressed(db, email),
        delivery_ready=delivery_ready(),
        show_as_follower=sub.show_as_follower,
    )


@router.get("/me/research-email", response_model=SubscriptionView)
def email_settings(
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    service.default_email_on(
        db, user["hf_subject"], verified_email(request), datetime.now(timezone.utc)
    )
    return subscription_view(db, service.subscription(db, user["hf_subject"]), request)


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
        email = verified_email(request)
        if email is None:
            raise HTTPException(
                409, "Request verified email access from Hugging Face before opting in"
            )
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
