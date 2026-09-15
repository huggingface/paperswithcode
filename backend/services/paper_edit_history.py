"""Publicly attributed paper history and bounded daily admin summaries."""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from backend.models.database import CatalogMutationEvent
from backend.services.catalog_mutation_service import decode_cursor, encode_cursor


def public_snapshot(entity_type, snapshot):
    if snapshot is None:
        return None
    if entity_type == "paper_edit_batch":
        return {
            "sections": {
                key: public_snapshot(f"paper_{key}", value)
                for key, value in snapshot["sections"].items()
            },
            "evaluations": public_snapshot("evaluation", snapshot["evaluations"]),
        }
    if entity_type == "evaluation":
        if isinstance(snapshot, list):
            return [public_snapshot(entity_type, row) for row in snapshot]
        fields = {
            "id",
            "paper_id",
            "task_id",
            "dataset_id",
            "model_name",
            "harness",
            "methodology",
            "metrics",
            "uses_additional_data",
            "is_open",
            "source_url",
            "external_source_url",
            "num_parameters",
            "hf_model_url",
            "evaluated_on",
        }
        return {key: value for key, value in snapshot.items() if key in fields}
    value = snapshot.get("value")
    if entity_type == "paper_tasks":
        return [{"task_id": row["task_id"]} for row in value or []]
    if entity_type == "paper_methods":
        return [
            {"method_id": row["method_id"]} for row in (value or {}).get("links", [])
        ]
    if entity_type == "paper_hf_artifacts":
        return {
            key: (value or {}).get(key, [])
            for key in ("hf_models", "hf_datasets", "hf_spaces")
        }
    if entity_type == "paper_organizations":
        return [{"organization_id": row["organization_id"]} for row in value or []]
    return value


class PaperEditHistory:
    def __init__(self, db: Session):
        self.db = db

    def paper(self, paper_id: int, cursor: str | None, limit: int) -> dict:
        query = select(CatalogMutationEvent).where(
            CatalogMutationEvent.paper_id == paper_id
        )
        if cursor:
            when, event_id = decode_cursor(cursor)
            query = query.where(
                or_(
                    CatalogMutationEvent.created_at < when,
                    and_(
                        CatalogMutationEvent.created_at == when,
                        CatalogMutationEvent.id < event_id,
                    ),
                )
            )
        rows = list(
            self.db.scalars(
                query.order_by(
                    CatalogMutationEvent.created_at.desc(),
                    CatalogMutationEvent.id.desc(),
                ).limit(limit + 1)
            )
        )
        return {
            "events": [
                {
                    "id": str(row.id),
                    "actor_username": row.actor_username,
                    "created_at": row.created_at,
                    "operation": row.operation,
                    "entity_type": row.entity_type,
                    "before": public_snapshot(row.entity_type, row.before_snapshot),
                    "after": public_snapshot(row.entity_type, row.after_snapshot),
                    "rollback_of_event_id": str(row.rollback_of_event_id)
                    if row.rollback_of_event_id
                    else None,
                }
                for row in rows[:limit]
            ],
            "next_cursor": encode_cursor(rows[limit - 1])
            if len(rows) > limit
            else None,
        }

    def digest(self, day: date, page: int) -> dict:
        start = datetime.combine(day, time.min, tzinfo=UTC)
        where = (
            CatalogMutationEvent.created_at >= start,
            CatalogMutationEvent.created_at < start + timedelta(days=1),
            CatalogMutationEvent.paper_id.is_not(None),
        )
        count, people, papers = self.db.execute(
            select(
                func.count(),
                func.count(func.distinct(CatalogMutationEvent.actor_hf_subject)),
                func.count(func.distinct(CatalogMutationEvent.paper_id)),
            ).where(*where)
        ).one()
        rows = self.db.execute(
            select(
                CatalogMutationEvent.paper_id,
                CatalogMutationEvent.actor_username,
                func.count().label("edits"),
            )
            .where(*where)
            .group_by(
                CatalogMutationEvent.paper_id, CatalogMutationEvent.actor_username
            )
            .order_by(
                CatalogMutationEvent.paper_id, CatalogMutationEvent.actor_username
            )
            .offset((page - 1) * 100)
            .limit(101)
        ).all()
        return {
            "day": day.isoformat(),
            "edits": count,
            "contributors": people,
            "papers": papers,
            "rows": [dict(row._mapping) for row in rows[:100]],
            "has_more": len(rows) > 100,
        }
