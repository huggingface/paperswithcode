"""Move per-job curation bootstrap bundles into the shared content-addressed store.

Report-only unless --apply. Jobs that still carry a legacy `bootstrap_bundle`
are read --batch-size at a time; each bundle is stored once in
`paper_curation_bootstrap_bundles`, the job is pointed at it, and its legacy
copy is cleared. Moved jobs drop out of the selection, so a rerun resumes.
Run after the release that reads `bootstrap_bundle_sha256` is live, then
`VACUUM (FULL) paper_curation_jobs` to return the freed space to the disk.
"""

from __future__ import annotations

import argparse
import logging

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database.connection import get_database_session
from backend.models.database import PaperCurationBootstrapBundle, PaperCurationJob
from backend.services.codex_add_evals_service import _bootstrap_bundle_key

logger = logging.getLogger("backfill_curation_bootstrap_bundles")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Move the bundles")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    session = get_database_session()
    db = next(session)
    jobs = 0
    keys: set[str] = set()
    last_id = None
    try:
        while True:
            query = (
                select(PaperCurationJob.id, PaperCurationJob.bootstrap_bundle)
                .where(PaperCurationJob.bootstrap_bundle.is_not(None))
                .order_by(PaperCurationJob.id)
                .limit(args.batch_size)
            )
            if last_id is not None:
                query = query.where(PaperCurationJob.id > last_id)
            batch = db.execute(query).all()
            if not batch:
                break
            last_id = batch[-1].id
            for job_id, bundle in batch:
                key = _bootstrap_bundle_key(bundle)
                jobs += 1
                is_new = key not in keys
                keys.add(key)
                if not args.apply:
                    continue
                if is_new:
                    db.execute(
                        pg_insert(PaperCurationBootstrapBundle)
                        .values(sha256=key, bundle=bundle)
                        .on_conflict_do_nothing()
                    )
                db.execute(
                    update(PaperCurationJob)
                    .where(
                        PaperCurationJob.id == job_id,
                        PaperCurationJob.bootstrap_bundle.is_not(None),
                    )
                    .values(bootstrap_bundle_sha256=key, bootstrap_bundle=None)
                )
            if args.apply:
                db.commit()
            else:
                db.rollback()
            logger.info("%d jobs read, %d distinct bundles", jobs, len(keys))
    finally:
        session.close()
    action = "moved" if args.apply else "would move"
    print(f"{action} {jobs} job bundles into {len(keys)} shared bundles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
