"""Export and optionally publish daily enrichment dashboard data."""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

from backend.database.connection import get_database_session
from backend.services.enrichment_dashboard_export import build_snapshot, write_snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "/var/lib/paperswithcode/shared/enrichment-dashboard/snapshot.json"
        ),
    )
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()

    session = get_database_session()
    db = next(session)
    try:
        snapshot = build_snapshot(db, args.start_date, args.end_date)
    finally:
        try:
            next(session)
        except StopIteration:
            pass

    if not snapshot["daily"]:
        raise SystemExit("refusing to publish an empty dashboard snapshot")
    write_snapshot(snapshot, args.output)

    if args.upload:
        repo_id = os.environ.get("PWC_ENRICHMENT_DASHBOARD_REPO_ID")
        token = (
            os.environ.get("HF_TOKEN")
            or os.environ.get("PWC_HF_TOKEN")
            or os.environ.get("PWC_POSTGRES_BACKUP_HF_TOKEN")
        )
        if not repo_id or not token:
            raise SystemExit(
                "--upload requires PWC_ENRICHMENT_DASHBOARD_REPO_ID and HF_TOKEN"
            )
        from huggingface_hub import HfApi

        HfApi(token=token).upload_file(
            path_or_fileobj=str(args.output),
            path_in_repo="snapshot.json",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"Refresh enrichment dashboard through {snapshot['end_date']}",
        )
        space_repo_id = os.environ.get("PWC_ENRICHMENT_DASHBOARD_SPACE_REPO_ID")
        if space_repo_id:
            HfApi(token=token).upload_file(
                path_or_fileobj=str(args.output),
                path_in_repo="data/snapshot.json",
                repo_id=space_repo_id,
                repo_type="space",
                commit_message=f"Refresh bundled dashboard data through {snapshot['end_date']}",
            )
    print(
        f"exported {len(snapshot['papers'])} papers, {len(snapshot['evaluations'])} evaluations, {len(snapshot['benchmark_gaps'])} benchmark gaps through {snapshot['end_date']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
