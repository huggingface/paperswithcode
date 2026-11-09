"""Fixture evidence that a paper introduces a model.

Leaderboard title matching only considers papers with an evaluation or a
model release, so a fixture "announcement" paper needs one of them.
"""

from sqlalchemy.orm import Session

from backend.models.database import ModelRelease


def add_release_evidence(session: Session, *paper_ids: int) -> None:
    """Record a model release on each paper under a name no board uses."""
    session.add_all(
        ModelRelease(
            paper_id=paper_id, canonical_name=f"evidence-{paper_id}", aliases=[]
        )
        for paper_id in paper_ids
    )
    session.flush()
