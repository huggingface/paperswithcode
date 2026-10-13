#!/usr/bin/env python3
"""
Import AI conference deadlines from the ai-deadlines YAML data.

Source: https://github.com/huggingface/ai-deadlines (src/data/conferences/*.yml).

Legacy, one-time catch-up tool: the PwC database is now the source of truth
for deadlines, maintained by the `sweep_conference_deadlines` /
`refresh_conference_deadlines` CRONs and the admin API. Re-running this
replaces the deadlines of every imported edition with the YAML values, which
would revert later corrections for those editions.

For each conference-year block this script upserts the `conferences` row keyed
by slug ``{title-lower}-{year}`` (so proceedings rows such as ``cvpr-2026`` get
deadlines attached instead of being duplicated) and replaces its
`conference_deadlines` rows. The parsing and upsert logic lives in
`backend/services/conference_deadline_service.py`.

Usage:
    uv run --env-file backend/keys.env \
        backend/database/conferences_setup/import_ai_deadlines.py \
        [--data-dir /path/to/ai-deadlines/src/data/conferences] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.database.connection import db_manager
from backend.services.conference_deadline_service import import_yaml_directory

DEFAULT_DATA_DIR = "/root/python_projects/ai-deadlines/src/data/conferences"


def main() -> None:
    parser = argparse.ArgumentParser(description="Import AI conference deadlines")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and count only; no DB writes",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        print(f"Data directory not found: {data_dir}")
        sys.exit(1)

    print("=" * 80)
    print("Importing AI conference deadlines" + (" (dry run)" if args.dry_run else ""))
    print(f"Source: {data_dir}")
    print("=" * 80)

    session = db_manager.session_local()
    try:
        stats = import_yaml_directory(session, data_dir, args.dry_run)
        print("\n" + "=" * 80)
        print("Import complete" if not args.dry_run else "Dry run complete")
        print("=" * 80)
        for key, value in stats.items():
            print(f"  {key}: {value}")
    except Exception as exc:
        session.rollback()
        print(f"Import failed: {exc}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
