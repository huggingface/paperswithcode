"""Synchronize explicit paper Hugging Face URLs into normalized artifact rows."""

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.utils.hf_utils import hf_artifact_repo_id


@dataclass(frozen=True)
class ExplicitHfArtifact:
    kind: str
    repo_id: str
    url: str


def collect_explicit_hf_artifacts(
    hf_models: Iterable[str] | None,
    hf_datasets: Iterable[str] | None,
    hf_spaces: Iterable[str] | None,
) -> list[ExplicitHfArtifact]:
    """Return deduplicated, normalized artifacts from the paper URL arrays."""
    artifacts: dict[tuple[str, str], ExplicitHfArtifact] = {}
    for urls in (hf_models, hf_datasets, hf_spaces):
        for url in urls or ():
            parsed = hf_artifact_repo_id(url)
            if parsed is None:
                continue
            kind, repo_id = parsed
            artifacts[(kind, repo_id)] = ExplicitHfArtifact(kind, repo_id, url)
    return list(artifacts.values())


def sync_explicit_hf_artifact_links(
    session: Session,
    paper_id: int,
    hf_models: Iterable[str] | None,
    hf_datasets: Iterable[str] | None,
    hf_spaces: Iterable[str] | None,
) -> dict[str, int]:
    """Upsert every explicit artifact and ensure its paper junction exists.

    This intentionally does not delete other normalized links. ArXiv discovery
    may have attached additional artifacts that cannot be distinguished from
    explicit links in the junction table. The discovery cron remains the
    authoritative exact reconciliation path.
    """
    artifacts = collect_explicit_hf_artifacts(
        hf_models,
        hf_datasets,
        hf_spaces,
    )
    links_added = 0
    for artifact in artifacts:
        artifact_id = session.execute(
            text("""
                INSERT INTO hf_artifacts (kind, repo_id, url, created_at, updated_at)
                VALUES (:kind, :repo_id, :url, NOW(), NOW())
                ON CONFLICT (kind, repo_id)
                DO UPDATE SET url = EXCLUDED.url, updated_at = NOW()
                RETURNING id
            """),
            {
                "kind": artifact.kind,
                "repo_id": artifact.repo_id,
                "url": artifact.url,
            },
        ).scalar_one()
        result = session.execute(
            text("""
                INSERT INTO paper_hf_artifacts
                    (paper_id, hf_artifact_id, created_at)
                VALUES (:paper_id, :artifact_id, NOW())
                ON CONFLICT (paper_id, hf_artifact_id) DO NOTHING
            """),
            {"paper_id": paper_id, "artifact_id": artifact_id},
        )
        if result.rowcount > 0:
            links_added += 1
    return {"artifacts": len(artifacts), "links_added": links_added}


def unlink_replaced_hf_artifact_links(
    session: Session,
    paper_id: int,
    *,
    previous: tuple[Iterable[str] | None, ...],
    current: tuple[Iterable[str] | None, ...],
) -> int:
    """Delete paper junctions for explicit artifacts a replacement dropped.

    Only artifacts that were in the paper's previous explicit URL arrays are
    unlinked, so links attached by arXiv discovery are left alone.
    """
    kept = {(a.kind, a.repo_id) for a in collect_explicit_hf_artifacts(*current)}
    removed = 0
    for artifact in collect_explicit_hf_artifacts(*previous):
        if (artifact.kind, artifact.repo_id) in kept:
            continue
        result = session.execute(
            text("""
                DELETE FROM paper_hf_artifacts AS link
                USING hf_artifacts AS artifact
                WHERE link.paper_id = :paper_id
                  AND link.hf_artifact_id = artifact.id
                  AND artifact.kind = :kind
                  AND artifact.repo_id = :repo_id
            """),
            {
                "paper_id": paper_id,
                "kind": artifact.kind,
                "repo_id": artifact.repo_id,
            },
        )
        removed += result.rowcount
    return removed
