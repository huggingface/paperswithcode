"""List public free-text topics, or hide one from the homepage and search engines.

    uv run --env-file backend/keys.env python -m backend.scripts.moderate_research_topics list
    uv run --env-file backend/keys.env python -m backend.scripts.moderate_research_topics hide 41
    uv run --env-file backend/keys.env python -m backend.scripts.moderate_research_topics unhide 41

Hiding keeps the topic's followers and their feeds; it only leaves the homepage
bubbles and gets a noindex topic page. Making a topic private is the creator's
switch in Settings.
"""

import argparse
from datetime import datetime, timezone

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.services import public_topic_service

LIST_SQL = """
SELECT t.id, t.hidden_at IS NOT NULL hidden, t.backfill_status status,
 u.current_username creator, count(f.hf_subject) followers,
 coalesce(t.label, t.text) name
FROM research_topics t
LEFT JOIN user_profiles u ON u.hf_subject=t.created_by_hf_subject
LEFT JOIN research_topic_follows f ON f.topic_id=t.id
WHERE t.is_public GROUP BY t.id, u.current_username ORDER BY followers DESC, t.id
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="Public topics, most followed first")
    for name in ("hide", "unhide"):
        sub.add_parser(name).add_argument("topic_id", type=int)
    args = parser.parse_args()
    with db_manager.session_local() as db:
        if args.command == "list":
            for row in db.execute(text(LIST_SQL)).mappings():
                flag = " [hidden]" if row["hidden"] else ""
                print(
                    f"{row['id']:>6}  {row['followers']:>4} followers  "
                    f"@{row['creator'] or '-'}  {row['status']}{flag}  {row['name']}"
                )
            return
        public_topic_service.set_hidden(
            db, args.topic_id, args.command == "hide", datetime.now(timezone.utc)
        )
        print(f"Topic {args.topic_id} {args.command}d")


if __name__ == "__main__":
    main()
