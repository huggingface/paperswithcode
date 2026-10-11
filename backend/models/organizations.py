"""Organization API contracts."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models.conferences import ConferenceTaskSummary


class OrganizationTopPaper(BaseModel):
    id: str
    arxiv_id: Optional[str] = None
    title: str

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class Organization(BaseModel):
    """Organization object with normalized metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Organization ID")
    name: str = Field(..., description="Organization name (e.g., 'NVIDIA')")
    slug: str = Field(..., description="URL-friendly slug (e.g., 'nvidia')")
    hf_slug: Optional[str] = Field(None, description="Hugging Face namespace")
    hf_url: Optional[str] = Field(
        None, description="Hugging Face organization URL (e.g., huggingface.co/nvidia)"
    )
    logo_url: Optional[str] = Field(None, description="Organization logo image URL")
    website_url: Optional[str] = Field(None, description="Official website URL")
    github_url: Optional[str] = Field(None, description="GitHub organization URL")
    description: Optional[str] = Field(None, description="Organization description")
    paper_count: Optional[int] = Field(
        0, description="Number of papers linked to this organization"
    )
    is_featured: bool = False
    display_order: Optional[int] = None
    organization_trending_score: Optional[float] = None
    trending_rank: Optional[int] = None
    top_trending_paper: Optional[OrganizationTopPaper] = None
    first_paper_year: Optional[int] = None
    latest_paper_year: Optional[int] = None
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class OrganizationSyncRequest(BaseModel):
    """Request an idempotent synchronization from a Hugging Face namespace."""

    model_config = ConfigDict(extra="forbid")

    hf_slug: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    slug: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    skip_missing_papers: bool = False


class OrganizationSyncResult(BaseModel):
    organization: str
    fetched: int = 0
    existing: int = 0
    imported: int = 0
    linked: int = 0
    already_linked: int = 0
    failed: int = 0
    unknown_organizations_seen: int = 0
    upstream_local_delta: int = 0


class Organizations(BaseModel):
    """Container for a list of organizations."""

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Total number of organizations")
    results: List[Organization] = Field(..., description="Organization list")


class OrganizationContributionDay(BaseModel):
    """Paper contributions attributed to an organization on one day."""

    published_date: date = Field(
        ...,
        alias="date",
        description="Paper publication date",
    )
    paper_count: int = Field(..., ge=1, description="Papers published on this date")


class OrganizationContributions(BaseModel):
    """Daily organization paper contributions over a fixed date range."""

    start_date: date
    end_date: date
    total_count: int = Field(..., ge=0)
    results: List[OrganizationContributionDay] = Field(default_factory=list)


class OrganizationAreaWithTasks(BaseModel):
    """Research area with organization-scoped task paper counts."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Area ID")
    name: str = Field(..., description="Area name")
    description: Optional[str] = Field(None, description="Area description")
    tasks: List[ConferenceTaskSummary] = Field(
        default_factory=list,
        description="Visible tasks with organization-scoped paper counts",
    )

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class OrganizationAreasWithTasks(BaseModel):
    """Organization taxonomy: areas and tasks scoped to one organization."""

    model_config = ConfigDict(from_attributes=True)

    organization: Organization = Field(..., description="Organization metadata")
    total_paper_count: int = Field(
        ..., description="Total papers linked to this organization"
    )
    results: List[OrganizationAreaWithTasks] = Field(
        ..., description="Areas populated with organization-scoped task counts"
    )


__all__ = [
    "OrganizationTopPaper",
    "Organization",
    "OrganizationSyncRequest",
    "OrganizationSyncResult",
    "Organizations",
    "OrganizationContributionDay",
    "OrganizationContributions",
    "OrganizationAreaWithTasks",
    "OrganizationAreasWithTasks",
]
