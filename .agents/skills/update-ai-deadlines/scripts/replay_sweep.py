"""Re-plan a finished sweep's agent proposals against today's rows and rules.

Use after a guard change made earlier rejections acceptable (for example
PR #909 allowed TBA editions), or when a sweep's collection failed but its
Hugging Face Job logs are intact. Proposals go through the same guarded,
audited writer as a normal collection; past editions stay immutable and
nothing is deleted. Dry run unless --apply.

Needs the Job credentials from the production cron env:

    uv run --env-file backend/keys.env --env-file /etc/paperswithcode/production-cron.env \\
      python .agents/skills/update-ai-deadlines/scripts/replay_sweep.py <sweep_id> \\
      --series icml,iccv [--apply]
"""

from __future__ import annotations

import argparse
import json

from huggingface_hub import HfApi
from pydantic import ValidationError

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import ConferenceDeadlineSweep
from backend.services import conference_deadline_agent as agent
from backend.services.catalog_errors import CatalogError
from backend.services.conference_deadline_service import (
    DeadlineValidationError,
    SeriesChangeSet,
    apply_series_change_set,
)
from backend.services.conference_deadline_sweep_service import job_credentials


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sweep_id", type=int)
    parser.add_argument("--series", help="comma-separated series; default all")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    wanted = (
        {s.strip() for s in args.series.split(",") if s.strip()}
        if args.series
        else None
    )

    credentials = job_credentials(get_settings())
    api = HfApi(token=credentials.token)
    with db_manager.session_local() as db:
        sweep = db.get(ConferenceDeadlineSweep, args.sweep_id)
        if sweep is None or not sweep.hf_job_id:
            parser.error(f"sweep {args.sweep_id} has no Hugging Face Job")
        lines = api.fetch_job_logs(
            job_id=sweep.hf_job_id, namespace=credentials.namespace
        )
        failed: list[str] = []
        for result in agent.decode_result_lines(list(lines)):
            series = result.get("series")
            if result.get("status") != "proposed":
                continue
            if wanted is not None and series not in wanted:
                continue
            # Like a normal collection: one invalid proposal is reported and
            # skipped, the other series are still re-planned.
            try:
                plans = apply_series_change_set(
                    db,
                    series,
                    SeriesChangeSet.model_validate(result["change_set"]),
                    dry_run=not args.apply,
                    request_id=f"conference-deadline-sweep:{sweep.id}:{series}:replay",
                )
            except (ValidationError, DeadlineValidationError, CatalogError) as exc:
                db.rollback()
                failed.append(series)
                print(json.dumps({"series": series, "error": str(exc)[:1000]}))
                continue
            for plan in plans:
                print(
                    json.dumps(
                        {
                            "slug": plan.slug,
                            "create": plan.create,
                            "changes": [
                                {"kind": c.kind, "after": c.after} for c in plan.changes
                            ],
                            "rejections": plan.rejections,
                        },
                        default=str,
                    )
                )
    print("applied" if args.apply else "dry run: nothing written (pass --apply)")
    if failed:
        print(f"invalid proposals skipped: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
