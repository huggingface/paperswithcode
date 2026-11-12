"""Apply reviewed decisions to pending community submissions.

Dry run by default; pass --apply to write. Run from the repository root:

    uv run --env-file backend/keys.env python \
        .agents/skills/review-submissions/scripts/apply_decisions.py decisions.json [--apply]

decisions.json is a list of objects:

    {"id": 2013, "decision": "approve",
     "resolved_payload": {"date_published": "2026-11-11"},   # optional, merged over proposed_payload
     "result_entity": ["task", 1015],                           # record-only new_* types only
     "admin_note": "internal evidence", "user_review_reason": "shown to the submitter"}

    {"id": 2014, "decision": "reject", "admin_note": "...", "user_review_reason": "..."}

All rows are checked first; nothing is written unless every row is still pending.
"""

import argparse
import json
from pathlib import Path

from backend.database.connection import get_database_session
from backend.services.pending_edit_service import (
    RECORD_ONLY_EDIT_TYPES,
    PendingEditService,
)

REVIEWER = {
    "reviewer_username": "User-directed Claude",
    "reviewer_hf_subject": "interactive-user-directed-review",
}

parser = argparse.ArgumentParser()
parser.add_argument("decisions", type=Path)
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()
decisions = json.loads(args.decisions.read_text())

for db in get_database_session():
    service = PendingEditService(db)
    for item in decisions:
        row = service.get(item["id"])
        assert row.status == "pending", f"{row.id} is already {row.status}"
        assert item["decision"] in {"approve", "reject"}, item
        assert item.get("user_review_reason"), f"{row.id} needs a user_review_reason"
        record_only = row.edit_type in RECORD_ONLY_EDIT_TYPES
        if item["decision"] == "approve" and record_only:
            assert item.get("result_entity"), (
                f"{row.id}: create the entity first, then pass result_entity"
            )
        print(row.id, row.edit_type, item["decision"], item.get("admin_note", ""))
    if not args.apply:
        print("dry run; pass --apply to write")
        break

    for item in decisions:
        review = {
            "edit_id": item["id"],
            "admin_note": item.get("admin_note"),
            "user_review_reason": item["user_review_reason"],
            **REVIEWER,
        }
        if item["decision"] == "reject":
            service.reject(**review)
            continue
        row = service.get(item["id"])
        if item.get("resolved_payload"):
            review["resolved_payload"] = {
                **row.proposed_payload,
                **item["resolved_payload"],
            }
        if row.edit_type not in RECORD_ONLY_EDIT_TYPES:
            service.approve(**review)
            continue
        row = service.approve(**review, commit=False)
        row.result_entity_type, entity_id = item["result_entity"]
        row.result_entity_id = str(entity_id)
        db.commit()

    for item in decisions:
        row = service.get(item["id"])
        print(row.id, row.status, row.result_entity_type, row.result_entity_id)
