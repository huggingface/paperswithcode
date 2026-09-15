"""Shared task detail contract, re-exported by models.api."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Task(BaseModel):
    """
    Task object representing a specific AI/ML task.

    Tasks are hierarchical and can have parent-child relationships.
    Examples: Image Classification, Object Detection, Language Modeling, etc.
    """

    model_config = ConfigDict(from_attributes=True)

    # Core task identification
    id: str = Field(..., description="Task ID")
    name: str = Field(..., description="Task name (e.g., 'Image Classification')")
    description: Optional[str] = Field(None, description="Task description")
    research_trends: List[str] = Field(
        default_factory=list,
        description="Three editorial bullets summarizing the task's research direction",
    )
    slug: Optional[str] = Field(None, description="URL-friendly task slug")
    keywords: Optional[str] = Field(
        None, description="Comma-separated keywords for matching papers to this task"
    )

    # Hierarchical structure
    parent_id: Optional[str] = Field(None, description="ID of the parent task")
    area_id: Optional[str] = Field(None, description="ID of the research area")
    level: int = Field(default=0, description="Depth in task hierarchy (0=top-level)")

    # Metadata
    paper_count: Optional[int] = Field(
        None, description="Number of papers for this task"
    )
    benchmark_count: Optional[int] = Field(
        None, description="Number of benchmarks directly linked to this task"
    )
    evaluation_count: Optional[int] = Field(
        None, description="Number of stored evaluation rows for this task"
    )
    image_url: Optional[str] = Field(
        None, description="URL to task image/visual representation"
    )
    image_credit: Optional[str] = Field(
        None, description="Image source/credit information"
    )

    # Timestamps
    created_at: Optional[datetime] = Field(None, description="Task creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    @field_validator("id", "parent_id", "area_id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure IDs are strings."""
        if v is None:
            return v
        return str(v)
