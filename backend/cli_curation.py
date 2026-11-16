"""``pwc curation``: judge Codex/Pi shadow curation pairs and report the gates."""

from __future__ import annotations

import argparse
import json

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import PaperCurationJob
from backend.services.curation_pair_judge import gate_report, judge_pending_pairs


def judge_pairs(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        counts = judge_pending_pairs(
            db, get_settings(), limit=args.limit, kind=args.kind
        )
    print(json.dumps(counts, indent=2))
    return 1 if counts["failed"] else 0


def pair_report(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        print(json.dumps(gate_report(db), indent=2))
        if args.verdicts:
            rows = db.query(PaperCurationJob).filter(
                PaperCurationJob.runner == "pi",
                PaperCurationJob.pair_judgment.isnot(None),
            )
            for row in rows.order_by(PaperCurationJob.created_at):
                paper = (row.context_snapshot or {}).get("paper") or {}
                for candidate in row.pair_judgment["candidates"]:
                    if args.verdicts != "all" and candidate["verdict"] == "correct":
                        continue
                    print(
                        f"{row.kind}\tpaper {paper.get('id')}\t{candidate['origin']}"
                        f"\t{candidate['verdict']}\t{candidate['field']}"
                        f"\t{json.dumps(candidate['value'])}\t{candidate['reason']}"
                    )
    return 0


def register_curation_commands(commands: argparse._SubParsersAction) -> None:
    curation = commands.add_parser("curation", help="Pi shadow curation evaluation")
    curation_commands = curation.add_subparsers(dest="curation_command", required=True)
    judge = curation_commands.add_parser(
        "judge-pairs", help="Blind-judge compared Codex/Pi pairs that lack a verdict"
    )
    judge.add_argument("--limit", type=int, default=20)
    judge.add_argument("--kind", choices=["enrich-paper", "add-evals"])
    judge.set_defaults(handler=judge_pairs)
    report = curation_commands.add_parser(
        "pair-report", help="Per-stage cutover gates from stored diffs and verdicts"
    )
    report.add_argument(
        "--verdicts",
        choices=["disputed", "all"],
        help="Also print verdict lines for spot-checks (disputed: not 'correct')",
    )
    report.set_defaults(handler=pair_report)
