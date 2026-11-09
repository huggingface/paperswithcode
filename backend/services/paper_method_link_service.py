"""Canonical writes and shared history rules for paper-method links."""

from __future__ import annotations

import json
from datetime import date
from typing import Iterable

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from backend.models.database import (
    Method,
    Paper,
    PaperMethod,
    PaperMethodEvidence,
    PaperMethodExclusion,
)

EVIDENCE_TYPES = frozenset(
    {"source", "keyword", "reference", "curation", "manual", "legacy_unknown"}
)


def month_start(value: date) -> date:
    return value.replace(day=1)


def shift_month(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def method_history_start(db: Session, method: Method) -> date | None:
    """Return the deterministic first month shared by backfills and the API."""
    if method.trend_start_date:
        return month_start(method.trend_start_date)
    if method.source_paper_id:
        source_date = (
            db.query(Paper.date_published)
            .filter(Paper.id == method.source_paper_id)
            .scalar()
        )
        if source_date:
            return month_start(source_date)
    if method.introduced_year:
        return date(method.introduced_year, 1, 1)
    earliest = (
        db.query(Paper.date_published)
        .join(PaperMethod, PaperMethod.paper_id == Paper.id)
        .filter(PaperMethod.method_id == method.id, Paper.date_published.isnot(None))
        .order_by(Paper.date_published, Paper.id)
        .first()
    )
    return month_start(earliest[0]) if earliest else None


def upsert_evidence_links(
    db: Session,
    links: Iterable[dict],
    *,
    evidence_type: str,
    details: dict | None = None,
) -> int:
    """Insert allowed parent links and idempotently refresh their evidence."""
    if evidence_type not in EVIDENCE_TYPES:
        raise ValueError(f"Unsupported paper-method evidence type: {evidence_type}")
    rows = [
        {
            "paper_id": int(link["paper_id"]),
            "method_id": int(link["method_id"]),
            "details": details if details is not None else link.get("details"),
        }
        for link in links
    ]
    if not rows:
        return 0
    if db.bind.dialect.name != "postgresql":
        written = 0
        for row in rows:
            if db.get(PaperMethodExclusion, (row["paper_id"], row["method_id"])):
                continue
            if db.get(PaperMethod, (row["paper_id"], row["method_id"])) is None:
                db.add(
                    PaperMethod(paper_id=row["paper_id"], method_id=row["method_id"])
                )
                db.flush()
                written += 1
            evidence = db.get(
                PaperMethodEvidence,
                (row["paper_id"], row["method_id"], evidence_type),
            )
            if evidence is None:
                db.add(
                    PaperMethodEvidence(
                        paper_id=row["paper_id"],
                        method_id=row["method_id"],
                        evidence_type=evidence_type,
                        details=row["details"],
                    )
                )
            else:
                evidence.last_seen_at = func.now()
                evidence.details = row["details"]
        return written
    parent_result = db.execute(
        text("""
            INSERT INTO paper_methods (paper_id, method_id)
            SELECT v.paper_id, v.method_id
            FROM (VALUES (:paper_id, :method_id)) AS v(paper_id, method_id)
            WHERE NOT EXISTS (
                SELECT 1 FROM paper_method_exclusions x
                WHERE x.paper_id = v.paper_id AND x.method_id = v.method_id
            )
            ON CONFLICT (paper_id, method_id) DO NOTHING
            """),
        rows,
    )
    db.execute(
        text("""
            INSERT INTO paper_method_evidence
                (paper_id, method_id, evidence_type, details)
            SELECT :paper_id, :method_id, :evidence_type, CAST(:details AS JSONB)
            WHERE EXISTS (
                SELECT 1 FROM paper_methods pm
                WHERE pm.paper_id = :paper_id AND pm.method_id = :method_id
            )
            ON CONFLICT (paper_id, method_id, evidence_type)
            DO UPDATE SET last_seen_at = now(), details = EXCLUDED.details
            """),
        [
            {
                **row,
                "details": (
                    json.dumps(row["details"]) if row["details"] is not None else None
                ),
                "evidence_type": evidence_type,
            }
            for row in rows
        ],
    )
    return max(parent_result.rowcount or 0, 0)


def sync_method_source_evidence(
    db: Session, *, method_id: int, source_paper_id: int | None
) -> int:
    """Keep `source` evidence aligned with the method's one canonical source."""
    stale_paper_ids = [
        paper_id
        for (paper_id,) in db.query(PaperMethodEvidence.paper_id)
        .filter(
            PaperMethodEvidence.method_id == method_id,
            PaperMethodEvidence.evidence_type == "source",
            (
                PaperMethodEvidence.paper_id != source_paper_id
                if source_paper_id is not None
                else True
            ),
        )
        .all()
    ]
    if stale_paper_ids:
        db.query(PaperMethodEvidence).filter(
            PaperMethodEvidence.method_id == method_id,
            PaperMethodEvidence.evidence_type == "source",
            PaperMethodEvidence.paper_id.in_(stale_paper_ids),
        ).delete(synchronize_session=False)
        db.flush()
        for paper_id in stale_paper_ids:
            has_evidence = (
                db.query(PaperMethodEvidence.paper_id)
                .filter(
                    PaperMethodEvidence.paper_id == paper_id,
                    PaperMethodEvidence.method_id == method_id,
                )
                .first()
            )
            if not has_evidence:
                link = db.get(PaperMethod, (paper_id, method_id))
                if link is not None:
                    db.delete(link)
    if source_paper_id is None:
        return 0
    return upsert_evidence_links(
        db,
        [{"paper_id": source_paper_id, "method_id": method_id}],
        evidence_type="source",
    )


def replace_manual_links(
    db: Session,
    *,
    paper_id: int,
    method_ids: Iterable[int],
    reason: str = "removed by curator",
) -> None:
    """Apply a replace-style manual edit with durable removal vetoes."""
    desired = {int(method_id) for method_id in method_ids}
    existing = {
        row[0]
        for row in db.query(PaperMethod.method_id)
        .filter(PaperMethod.paper_id == paper_id)
        .all()
    }
    removed = existing - desired
    if db.bind.dialect.name != "postgresql":
        for method_id in removed:
            exclusion = db.get(PaperMethodExclusion, (paper_id, method_id))
            if exclusion is None:
                db.add(
                    PaperMethodExclusion(
                        paper_id=paper_id, method_id=method_id, reason=reason
                    )
                )
            else:
                exclusion.reason = reason
                exclusion.updated_at = func.now()
            db.query(PaperMethodEvidence).filter(
                PaperMethodEvidence.paper_id == paper_id,
                PaperMethodEvidence.method_id == method_id,
            ).delete(synchronize_session=False)
            link = db.get(PaperMethod, (paper_id, method_id))
            if link:
                db.delete(link)
        for method_id in desired:
            exclusion = db.get(PaperMethodExclusion, (paper_id, method_id))
            if exclusion:
                db.delete(exclusion)
        db.flush()
        upsert_evidence_links(
            db,
            ({"paper_id": paper_id, "method_id": method_id} for method_id in desired),
            evidence_type="manual",
        )
        return
    if removed:
        db.execute(
            text("""
                INSERT INTO paper_method_exclusions
                    (paper_id, method_id, reason)
                VALUES (:paper_id, :method_id, :reason)
                ON CONFLICT (paper_id, method_id)
                DO UPDATE SET reason = EXCLUDED.reason, updated_at = now()
                """),
            [
                {"paper_id": paper_id, "method_id": method_id, "reason": reason}
                for method_id in removed
            ],
        )
        db.query(PaperMethod).filter(
            PaperMethod.paper_id == paper_id,
            PaperMethod.method_id.in_(removed),
        ).delete(synchronize_session=False)
    if desired:
        db.execute(
            text("""
                DELETE FROM paper_method_exclusions
                WHERE paper_id = :paper_id AND method_id = :method_id
                """),
            [{"paper_id": paper_id, "method_id": method_id} for method_id in desired],
        )
        upsert_evidence_links(
            db,
            ({"paper_id": paper_id, "method_id": method_id} for method_id in desired),
            evidence_type="manual",
        )
