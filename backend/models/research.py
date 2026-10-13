"""Research follow and feed API contracts."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

from backend.models.papers import Paper

FollowKind = Literal["task", "method", "benchmark", "author", "organization"]


class FollowView(BaseModel):
    kind: FollowKind
    entity_id: int
    name: str
    url: str
    created_at: datetime


class SubscriptionUpdate(BaseModel):
    enabled: bool


class SubscriptionView(BaseModel):
    enabled: bool
    email: str | None
    suppressed: bool
    delivery_ready: bool


class ResearchEntry(BaseModel):
    paper_key: str
    title: str
    url: str
    summary: str
    published: str
    popularity: float = 0
    reasons: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    strength: int = 0
    scores: list[dict] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)


class ResearchFeedEntry(ResearchEntry):
    paper: Paper
