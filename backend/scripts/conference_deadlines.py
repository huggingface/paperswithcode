"""Operate the AI conference deadline data (the /ai-deadlines page).

The database is the source of truth. Research runs off-box on Hugging Face
Jobs; this CLI only reads rows, launches/collects Jobs and applies validated
change sets. Scheduled runs use `pwc-cron sweep_conference_deadlines` (weekly)
and `pwc-cron refresh_conference_deadlines` (daily); see
`backend/services/conference_deadline_sweep_service.py`.

    uv run --env-file backend/keys.env python -m backend.scripts.conference_deadlines status
    ... plan --mode weekly
    ... launch --series cvpr,icml,neurips      # research now, off-box
    ... collect [--dry-run]                    # apply finished Jobs
    ... import-yaml --data-dir <ai-deadlines>/src/data/conferences [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import ConferenceDeadlineSweep
from backend.services.conference_deadline_service import (
    FRESHNESS_SQL,
    import_yaml_directory,
)
from backend.services.conference_deadline_sweep_service import (
    ConferenceDeadlineSweeps,
    run_scheduled_sweep,
)


def _print(value) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def status(db) -> dict:
    metrics = dict(db.execute(text(FRESHNESS_SQL)).mappings().one())
    sweeps = (
        db.query(ConferenceDeadlineSweep)
        .order_by(ConferenceDeadlineSweep.id.desc())
        .limit(5)
        .all()
    )
    metrics["recent_sweeps"] = [
        {
            "id": s.id,
            "mode": s.mode,
            "status": s.status,
            "hf_job_id": s.hf_job_id,
            "series": len(s.series),
            "launched_at": s.launched_at,
            "finished_at": s.finished_at,
            "changes_applied": s.changes_applied,
            "cost_usd": s.cost_usd,
            "error": s.error,
        }
        for s in sweeps
    ]
    return metrics


def scheduled_main(mode: str) -> int:
    """Shared body of the two pwc-cron entrypoints."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    db = db_manager.session_local()
    try:
        report = run_scheduled_sweep(db, get_settings(), mode)
    finally:
        db.close()
    _print(report)
    failed = [r for r in report["collected"] if r.get("status") == "failed"]
    for item in failed:
        logging.warning("conference_deadline_sweep_failed %s", item.get("sweep_id"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Freshness metrics and recent sweeps")
    for name in ("plan", "launch"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--mode", choices=("weekly", "daily"), default="weekly")
        cmd.add_argument("--limit", type=int)
        cmd.add_argument(
            "--series", help="Comma-separated series slugs, e.g. cvpr,icml"
        )
    collect = sub.add_parser("collect", help="Apply finished sweeps")
    collect.add_argument("--dry-run", action="store_true")
    importer = sub.add_parser(
        "import-yaml", help="Legacy huggingface/ai-deadlines import"
    )
    importer.add_argument("--data-dir", required=True)
    importer.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    now = datetime.now(timezone.utc)
    db = db_manager.session_local()
    try:
        if args.command == "status":
            _print(status(db))
        elif args.command in ("plan", "launch"):
            only = [s.strip() for s in args.series.split(",")] if args.series else None
            sweeps = ConferenceDeadlineSweeps(db, get_settings())
            manifests = sweeps.plan(args.mode, now=now, limit=args.limit, only=only)
            if args.command == "plan":
                _print(manifests)
            elif not manifests:
                print("no conference selected")
            else:
                sweeps.collect(now=now)
                if sweeps.running():
                    print("a sweep is still running; collect it first", file=sys.stderr)
                    return 1
                sweep = sweeps.launch(
                    "manual" if only else args.mode, manifests, now=now
                )
                _print(
                    {
                        "sweep_id": sweep.id,
                        "hf_job_id": sweep.hf_job_id,
                        "series": sweep.series,
                    }
                )
        elif args.command == "collect":
            _print(
                ConferenceDeadlineSweeps(db, get_settings()).collect(
                    now=now, dry_run=args.dry_run
                )
            )
        elif args.command == "import-yaml":
            data_dir = Path(args.data_dir)
            if not data_dir.is_dir():
                print(f"Data directory not found: {data_dir}", file=sys.stderr)
                return 1
            _print(import_yaml_directory(db, data_dir, args.dry_run))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
