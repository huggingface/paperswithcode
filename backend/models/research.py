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
    # An author's face or an organization's logo, for follow chips.
    image_url: str | None = None


class FollowSuggestion(BaseModel):
    entity_id: int
    name: str
    url: str
    image_url: str | None = None


class FollowSuggestions(BaseModel):
    """Popular authors and organizations offered when building a research feed."""

    authors: list[FollowSuggestion]
    organizations: list[FollowSuggestion]


class TopicUpdate(BaseModel):
    text: str = Field(min_length=3, max_length=300)


class TopicSuggestion(BaseModel):
    """A catalog entity named exactly like the topic, which matches papers exactly."""

    kind: FollowKind
    entity_id: int
    name: str
    url: str


class TopicView(BaseModel):
    text: str
    # Few-word summary of a long description; null for short ones.
    label: str | None = None
    set_at: datetime | None
    # pending/running while the last 90 days and older recall are judged.
    status: Literal["pending", "running", "done", "failed"]
    judged: int
    total: int | None
    suggestions: list[TopicSuggestion] = Field(default_factory=list)


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
