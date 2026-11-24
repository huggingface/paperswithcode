"""Task "Start here" reading path API contract."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from backend.models.papers import Paper

ReadingPathSource = Literal["curated", "automatic"]
ReadingPathStepKind = Literal["overview", "foundations", "recent"]


class ReadingPathPaper(BaseModel):
    """One paper in a reading-path step, with an optional curator note."""

    paper: Paper = Field(..., description="Paper summary, as in task paper feeds")
    note: Optional[str] = Field(
        None, description="Curator note on why this paper is worth reading"
    )


class ReadingPathStep(BaseModel):
    """One ordered step of a reading path."""

    kind: ReadingPathStepKind = Field(..., description="Step identifier")
    title: str = Field(..., description="Display title for the step")
    description: str = Field(..., description="What the reader gets from this step")
    source: ReadingPathSource = Field(
        ..., description="Whether the step was hand-curated or chosen automatically"
    )
    papers: List[ReadingPathPaper] = Field(..., description="Papers in reading order")


class TaskReadingPath(BaseModel):
    """An ordered "Start here" path through a task's literature."""

    task_id: str = Field(..., description="Task ID")
    task_slug: Optional[str] = Field(None, description="Task slug")
    source: ReadingPathSource = Field(
        ...,
        description=("'curated' when any step is hand-curated, otherwise 'automatic'"),
    )
    steps: List[ReadingPathStep] = Field(
        ..., description="Non-empty steps in reading order; empty when no path exists"
    )
