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
    # A subtask's parent task slug, so the bubble can borrow the parent's icon.
    parent_slug: str | None = None


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


class TopicPerson(BaseModel):
    """A Hugging Face account shown on a public topic."""

    username: str
    avatar_url: str


class TopicView(BaseModel):
    id: int
    text: str
    # Few-word summary of a long description; null for short ones.
    label: str | None = None
    set_at: datetime | None
    # pending/running while the last 90 days and older recall are judged.
    status: Literal["pending", "running", "done", "failed"]
    judged: int
    total: int | None
    suggestions: list[TopicSuggestion] = Field(default_factory=list)
    # Public topics are listed with their creator's HF username; only the
    # creator may change it.
    is_public: bool = True
    is_creator: bool = False
    # Who made a topic the account follows from someone else; None for its own.
    creator: TopicPerson | None = None


class TopicOrderUpdate(BaseModel):
    """Every followed topic id, in the order the account wants them."""

    topic_ids: list[int] = Field(max_length=100)


class TopicVisibilityUpdate(BaseModel):
    is_public: bool


class PublicTopicView(BaseModel):
    """A topic's page header: what it matches, who made it, who follows it."""

    id: int
    text: str
    # Few-word summary of a long description; null for short ones.
    label: str | None = None
    status: Literal["pending", "running", "done", "failed"]
    creator: TopicPerson | None
    is_public: bool
    # Hidden topics stay followable but leave the homepage and search engines.
    indexable: bool
    followers: int
    # Followers who show their avatar, creator excluded, at most eight.
    follower_avatars: list[TopicPerson] = Field(default_factory=list)
    following: bool = False
    is_creator: bool = False


class TopicBubble(BaseModel):
    """A popular public topic offered on the homepage."""

    id: int
    text: str
    label: str | None = None
    creator: TopicPerson | None
    followers: int


class FollowerVisibilityUpdate(BaseModel):
    show_as_follower: bool


class SubscriptionUpdate(BaseModel):
    enabled: bool


class SubscriptionView(BaseModel):
    enabled: bool
    email: str | None
    suppressed: bool
    delivery_ready: bool
    # Whether the account's avatar may appear on public topics it follows.
    show_as_follower: bool = True


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
    # When the paper joined the catalog; the feed marks papers added since the last visit.
    added_at: datetime | None = None


class NewPaperCount(BaseModel):
    """Following-feed papers added since a time, capped at 100."""

    count: int
