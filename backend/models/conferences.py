"""Conference and deadline API contracts."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConferenceDeadline(BaseModel):
    """A single submission/abstract/rebuttal deadline for a conference."""

    model_config = ConfigDict(from_attributes=True)

    type: Optional[str] = Field(
        None, description="Deadline type (e.g., submission, abstract, rebuttal)"
    )
    label: Optional[str] = Field(None, description="Human-readable deadline label")
    deadline_at: datetime = Field(..., description="Absolute deadline instant (UTC)")
    timezone: Optional[str] = Field(
        None, description="Original source timezone string (e.g., AoE, UTC-8)"
    )


class Conference(BaseModel):
    """Conference object with normalized metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Conference ID")
    name: str = Field(..., description="Conference name (e.g., 'CVPR 2026')")
    slug: str = Field(..., description="URL-friendly slug (e.g., 'cvpr-2026')")
    short_name: Optional[str] = Field(None, description="Short name (e.g., 'CVPR')")
    year: Optional[int] = Field(None, description="Conference year")
    url: Optional[str] = Field(None, description="Official conference website URL")
    start_date: Optional[date] = Field(None, description="Conference start date")
    end_date: Optional[date] = Field(None, description="Conference end date")
    venue: Optional[str] = Field(None, description="Venue name")
    location: Optional[str] = Field(None, description="City / country location")
    description: Optional[str] = Field(None, description="Conference description")
    image_url: Optional[str] = Field(
        None, description="Hero image URL for the conference page"
    )
    image_credit: Optional[str] = Field(
        None, description="Markdown credit for the hero image"
    )
    hf_url: Optional[str] = Field(
        None, description="Hugging Face dataset URL for accepted papers"
    )
    paper_count: Optional[int] = Field(
        0, description="Number of papers linked to this conference"
    )
    tier: Optional[str] = Field(
        None, description="ERA conference ranking (a/b/c); a is top tier"
    )
    tags: List[str] = Field(
        default_factory=list, description="AI-domain tags for filtering"
    )
    country: Optional[str] = Field(
        None, description="Country the conference is held in"
    )
    city: Optional[str] = Field(None, description="City the conference is held in")
    deadlines: List[ConferenceDeadline] = Field(
        default_factory=list, description="Submission/abstract/rebuttal deadlines"
    )
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class Conferences(BaseModel):
    """Container for a list of conferences."""

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Total number of conferences")
    results: List[Conference] = Field(..., description="Conference list")


class ConferenceDeadlines(BaseModel):
    """Container for conferences that have upcoming/past deadlines."""

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Total number of conferences with deadlines")
    results: List[Conference] = Field(
        ..., description="Conferences with their deadline lists"
    )


class ConferenceTaskSummary(BaseModel):
    """Task summary with conference-scoped paper count."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Task ID")
    name: str = Field(..., description="Task name")
    slug: Optional[str] = Field(None, description="Task slug")
    paper_count: int = Field(0, description="Papers in this conference for the task")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class ConferenceAreaWithTasks(BaseModel):
    """Research area with conference-scoped task paper counts."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Area ID")
    name: str = Field(..., description="Area name")
    description: Optional[str] = Field(None, description="Area description")
    tasks: List[ConferenceTaskSummary] = Field(
        default_factory=list,
        description="Visible tasks with conference-scoped paper counts",
    )

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class ConferenceAreasWithTasks(BaseModel):
    """Conference taxonomy: areas and tasks scoped to one conference."""

    model_config = ConfigDict(from_attributes=True)

    conference: Conference = Field(..., description="Conference metadata")
    total_paper_count: int = Field(
        ..., description="Total papers linked to this conference"
    )
    oral_paper_count: int = Field(
        0, description="Papers with an oral presentation at this conference"
    )
    spotlight_paper_count: int = Field(
        0, description="Papers with a spotlight presentation at this conference"
    )
    outstanding_paper_count: int = Field(
        0,
        description="Papers with an outstanding-paper or honorable-mention award",
    )
    best_paper_finalist_paper_count: int = Field(
        0,
        description="Papers with a best-paper-finalist award at this conference",
    )
    results: List[ConferenceAreaWithTasks] = Field(
        ..., description="Areas populated with conference-scoped task counts"
    )


__all__ = [
    "ConferenceDeadline",
    "Conference",
    "Conferences",
    "ConferenceDeadlines",
    "ConferenceTaskSummary",
    "ConferenceAreaWithTasks",
    "ConferenceAreasWithTasks",
]
