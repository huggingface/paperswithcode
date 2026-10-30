"""
Hugging Face Artifact Discovery + Metric Refresh CRON Job

Populates the normalized `hf_artifacts` table and the `paper_hf_artifacts`
junction, then refreshes Hub popularity metrics (trendingScore, likes,
downloads) for artifacts linked to recent papers. These feed the composite
paper trending score computed by `calculate_paper_trending_scores.py`.

Two phases per run:
  A. Discovery  - for recent latest-version papers, collect linked artifacts from
                  explicit `papers.hf_models/datasets/spaces` arrays and (for
                  arXiv papers) the Hub `arxiv/{id}/repos` endpoint, then sync the
                  `paper_hf_artifacts` links.
  B. Refresh    - fetch `expand[]=trendingScore` metrics for artifacts that are
                  linked to a recent paper and are stale.

Scope is limited to papers published in the last 6 months (latest version), the
same population the trending feed surfaces, to keep API usage and RAM bounded.

Schedule: Hourly. Dependencies: PostgreSQL, optional PWC_HF_TOKEN.

Pass ``--backfill`` to scan historical latest-version arXiv papers whose
``hf_artifacts_scanned_at`` value is NULL. Backfill mode only runs discovery
and is safely resumable by invoking it again.
"""

import argparse
import gc
import json
import os
import time
from datetime import date, datetime, timedelta

from sqlalchemy import text

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.services.hf_artifact_service import sync_explicit_hf_artifact_links
from backend.utils.hf_utils import (
    HfArtifactDiscoveryError,
    fetch_hf_artifact_metrics,
    fetch_hf_artifacts_for_arxiv,
    hf_artifact_repo_id,
)

# Population: latest-version papers published within this window.
RECENT_WINDOW_DAYS = 180
# The public HF artifact trend series starts here. Older papers are outside the
# chart population and do not need historical discovery.
BACKFILL_START_DATE = date(2021, 1, 1)
# Re-scan a paper's artifact links / refresh artifact metrics at most this often.
DISCOVERY_THRESHOLD_HOURS = 12
REFRESH_THRESHOLD_HOURS = 12
# Per-run caps (protect RAM / API budget on the 4GB VPS).
MAX_PAPERS_PER_RUN = 4000
MAX_ARTIFACTS_PER_RUN = 4000
# Cap arxiv-discovered artifacts per paper. The composite H-component is clipped
# regardless, so this only bounds metric-fetch cost for heavily-referenced ids.
MAX_ARTIFACTS_PER_PAPER_ARXIV = 30
# Politeness delay between HF API calls.
API_DELAY_SECONDS = 0.15
MAX_RUNTIME_SECONDS = 50 * 60
MIN_MEMORY_MB = 200


def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp} - {message}", flush=True)


def check_memory_usage() -> int:
    """Return available memory in MB (1000 fallback if unreadable)."""
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if "MemAvailable:" in line:
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 1000


def get_papers_needing_discovery(session, batch_size: int, recent_cutoff) -> list:
    """Recent latest-version papers whose artifact links are stale or missing."""
    threshold = datetime.now() - timedelta(hours=DISCOVERY_THRESHOLD_HOURS)
    query = text("""
        SELECT id, source, arxiv_id, hf_models, hf_datasets, hf_spaces
        FROM papers
        WHERE is_latest_version = TRUE
          -- Undated imports count from their creation instead of never matching.
          AND COALESCE(date_published, created_at::date) >= :recent_cutoff
          AND (
              hf_artifacts_scanned_at IS NULL
              OR hf_artifacts_scanned_at < :threshold
          )
        ORDER BY hf_artifacts_scanned_at NULLS FIRST,
                 COALESCE(date_published, created_at::date) DESC
        LIMIT :batch_size
    """)
    rows = session.execute(
        query,
        {
            "recent_cutoff": recent_cutoff,
            "threshold": threshold,
            "batch_size": batch_size,
        },
    ).fetchall()
    return rows


def get_papers_needing_backfill(session, batch_size: int) -> list:
    """Historical arXiv papers that have never had a conclusive Hub scan."""
    query = text("""
        SELECT id, source, arxiv_id, hf_models, hf_datasets, hf_spaces
        FROM papers
        WHERE is_latest_version = TRUE
          AND source = 'arxiv'
          AND arxiv_id IS NOT NULL
          AND COALESCE(date_published, created_at::date) >= :start_date
          AND hf_artifacts_scanned_at IS NULL
        ORDER BY COALESCE(date_published, created_at::date) ASC, id ASC
        LIMIT :batch_size
    """)
    return session.execute(
        query,
        {"batch_size": batch_size, "start_date": BACKFILL_START_DATE},
    ).fetchall()


def get_papers_with_explicit_artifacts(session, batch_size: int) -> list:
    """Return latest papers with curated HF URLs, regardless of publication age."""
    return session.execute(
        text("""
            SELECT id, hf_models, hf_datasets, hf_spaces
            FROM papers
            WHERE is_latest_version = TRUE
              AND (
                COALESCE(cardinality(hf_models), 0)
                + COALESCE(cardinality(hf_datasets), 0)
                + COALESCE(cardinality(hf_spaces), 0)
              ) > 0
            ORDER BY id
            LIMIT :batch_size
        """),
        {"batch_size": batch_size},
    ).fetchall()


def run_explicit_backfill_phase(session, batch_size: int) -> dict:
    """Idempotently normalize explicit HF URLs without Hub discovery calls."""
    log("-" * 80)
    log("Phase A: explicit artifact link backfill")
    papers = get_papers_with_explicit_artifacts(session, batch_size)
    papers_processed = 0
    links_created = 0
    for paper in papers:
        result = sync_explicit_hf_artifact_links(
            session,
            paper.id,
            paper.hf_models,
            paper.hf_datasets,
            paper.hf_spaces,
        )
        session.commit()
        papers_processed += 1
        links_created += result["links_added"]
    log(
        f"Explicit backfill complete: {papers_processed} papers scanned, "
        f"{links_created} missing links created"
    )
    return {
        "papers_selected": len(papers),
        "papers_processed": papers_processed,
        "papers_failed": 0,
        "links_created": links_created,
    }


def collect_paper_artifacts(row, hf_token) -> list:
    """Return a deduped list of (kind, repo_id, url) for one paper row."""
    artifacts: dict[tuple, tuple] = {}

    # Explicit, curated artifact URLs (external rows and any arxiv rows that have
    # them). These are authoritative for a paper's own released artifacts.
    explicit_urls = []
    for arr in (row.hf_models, row.hf_datasets, row.hf_spaces):
        if arr:
            explicit_urls.extend(arr)
    for url in explicit_urls:
        parsed = hf_artifact_repo_id(url)
        if parsed is None:
            continue
        kind, repo_id = parsed
        artifacts[(kind, repo_id)] = (kind, repo_id, url)

    # ArXiv discovery via the Hub. Capped to bound metric-fetch cost.
    if row.source == "arxiv" and row.arxiv_id:
        discovered = fetch_hf_artifacts_for_arxiv(row.arxiv_id, token=hf_token)
        for kind, repo_id, url in discovered[:MAX_ARTIFACTS_PER_PAPER_ARXIV]:
            artifacts.setdefault((kind, repo_id), (kind, repo_id, url))

    return list(artifacts.values())


def upsert_artifact(session, kind: str, repo_id: str, url: str) -> int:
    """Insert or update an hf_artifacts row, returning its id."""
    result = session.execute(
        text("""
            INSERT INTO hf_artifacts (kind, repo_id, url, created_at, updated_at)
            VALUES (:kind, :repo_id, :url, NOW(), NOW())
            ON CONFLICT (kind, repo_id)
            DO UPDATE SET url = EXCLUDED.url, updated_at = NOW()
            RETURNING id
        """),
        {"kind": kind, "repo_id": repo_id, "url": url},
    )
    return result.scalar_one()


def sync_paper_links(session, paper_id: int, artifact_ids: list):
    """Make paper_hf_artifacts for this paper exactly match artifact_ids."""
    if artifact_ids:
        for artifact_id in artifact_ids:
            session.execute(
                text("""
                    INSERT INTO paper_hf_artifacts (paper_id, hf_artifact_id, created_at)
                    VALUES (:paper_id, :artifact_id, NOW())
                    ON CONFLICT (paper_id, hf_artifact_id) DO NOTHING
                """),
                {"paper_id": paper_id, "artifact_id": artifact_id},
            )
        session.execute(
            text("""
                DELETE FROM paper_hf_artifacts
                WHERE paper_id = :paper_id
                  AND hf_artifact_id <> ALL(:keep_ids)
            """),
            {"paper_id": paper_id, "keep_ids": artifact_ids},
        )
    else:
        session.execute(
            text("DELETE FROM paper_hf_artifacts WHERE paper_id = :paper_id"),
            {"paper_id": paper_id},
        )


def run_discovery_phase(
    session,
    hf_token,
    recent_cutoff,
    start_time,
    *,
    backfill: bool = False,
    batch_size: int = MAX_PAPERS_PER_RUN,
    api_delay_seconds: float = API_DELAY_SECONDS,
    max_runtime_seconds: float = MAX_RUNTIME_SECONDS,
) -> dict:
    """Phase A: discover and sync paper->artifact links."""
    log("-" * 80)
    log(
        "Phase A: historical artifact backfill"
        if backfill
        else "Phase A: artifact discovery"
    )
    if backfill:
        papers = get_papers_needing_backfill(session, batch_size)
    else:
        papers = get_papers_needing_discovery(session, batch_size, recent_cutoff)
    log(f"Papers needing discovery: {len(papers)}")

    papers_processed = 0
    papers_failed = 0
    links_created = 0
    for row in papers:
        if time.time() - start_time > max_runtime_seconds:
            log("Runtime limit reached during discovery - stopping")
            break
        if check_memory_usage() < MIN_MEMORY_MB:
            log("Low memory during discovery - stopping")
            break

        try:
            artifacts = collect_paper_artifacts(row, hf_token)
        except HfArtifactDiscoveryError as exc:
            session.rollback()
            papers_failed += 1
            log(f"Discovery failed for paper {row.id} ({row.arxiv_id}): {exc}")
            time.sleep(api_delay_seconds)
            continue

        artifact_ids = []
        for kind, repo_id, url in artifacts:
            artifact_ids.append(upsert_artifact(session, kind, repo_id, url))

        sync_paper_links(session, row.id, artifact_ids)
        session.execute(
            text("""
                UPDATE papers
                SET hf_artifacts_scanned_at = NOW()
                WHERE id = :paper_id
            """),
            {"paper_id": row.id},
        )
        session.commit()

        links_created += len(artifact_ids)
        papers_processed += 1

        # Sleep only when we actually hit the network (arxiv rows).
        if row.source == "arxiv" and row.arxiv_id:
            time.sleep(api_delay_seconds)

        if papers_processed % 100 == 0:
            log(
                f"Discovery progress: {papers_processed} papers, "
                f"{links_created} links, {check_memory_usage()}MB free"
            )
            gc.collect()

    log(
        f"Phase A complete: {papers_processed} papers scanned, "
        f"{links_created} links synced, {papers_failed} failed"
    )
    return {
        "papers_selected": len(papers),
        "papers_processed": papers_processed,
        "papers_failed": papers_failed,
        "links_created": links_created,
    }


def get_artifacts_needing_refresh(session, batch_size: int, recent_cutoff) -> list:
    """Stale artifacts linked to at least one recent latest-version paper."""
    threshold = datetime.now() - timedelta(hours=REFRESH_THRESHOLD_HOURS)
    query = text("""
        SELECT a.id, a.kind, a.repo_id
        FROM hf_artifacts a
        WHERE (a.fetched_at IS NULL OR a.fetched_at < :threshold)
          AND EXISTS (
              SELECT 1
              FROM paper_hf_artifacts pha
              JOIN papers p ON p.id = pha.paper_id
              WHERE pha.hf_artifact_id = a.id
                AND p.is_latest_version = TRUE
                AND COALESCE(p.date_published, p.created_at::date)
                    >= :recent_cutoff
          )
        ORDER BY a.fetched_at NULLS FIRST
        LIMIT :batch_size
    """)
    return session.execute(
        query,
        {
            "threshold": threshold,
            "recent_cutoff": recent_cutoff,
            "batch_size": batch_size,
        },
    ).fetchall()


def run_refresh_phase(session, hf_token, recent_cutoff, start_time) -> dict:
    """Phase B: refresh Hub metrics for stale linked artifacts."""
    log("-" * 80)
    log("Phase B: artifact metric refresh")
    artifacts = get_artifacts_needing_refresh(
        session, MAX_ARTIFACTS_PER_RUN, recent_cutoff
    )
    log(f"Artifacts needing refresh: {len(artifacts)}")

    refreshed = 0
    failed = 0
    for artifact in artifacts:
        if time.time() - start_time > MAX_RUNTIME_SECONDS:
            log("Runtime limit reached during refresh - stopping")
            break
        if check_memory_usage() < MIN_MEMORY_MB:
            log("Low memory during refresh - stopping")
            break

        try:
            metrics = fetch_hf_artifact_metrics(
                artifact.kind, artifact.repo_id, token=hf_token
            )
        except HfArtifactDiscoveryError as exc:
            session.rollback()
            failed += 1
            log(f"Metric refresh failed for {artifact.kind}/{artifact.repo_id}: {exc}")
            time.sleep(API_DELAY_SECONDS)
            continue
        if metrics is None:
            # Stamp fetched_at so a permanently-missing artifact does not loop.
            session.execute(
                text("UPDATE hf_artifacts SET fetched_at = NOW() WHERE id = :id"),
                {"id": artifact.id},
            )
            session.commit()
            failed += 1
        else:
            session.execute(
                text("""
                    UPDATE hf_artifacts
                    SET trending_score = :trending_score,
                        likes = :likes,
                        downloads = :downloads,
                        fetched_at = NOW(),
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": artifact.id,
                    "trending_score": metrics["trending_score"],
                    "likes": metrics["likes"],
                    "downloads": metrics["downloads"],
                },
            )
            session.commit()
            refreshed += 1

        time.sleep(API_DELAY_SECONDS)

        if (refreshed + failed) % 100 == 0:
            log(
                f"Refresh progress: {refreshed} refreshed, {failed} failed, "
                f"{check_memory_usage()}MB free"
            )
            gc.collect()

    log(f"Phase B complete: {refreshed} refreshed, {failed} failed")
    return {"selected": len(artifacts), "refreshed": refreshed, "failed": failed}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backfill",
        action="store_true",
        help=(
            "Scan historical latest-version arXiv papers that have never been "
            "scanned, then exit without refreshing artifact metrics"
        ),
    )
    parser.add_argument(
        "--backfill-explicit",
        action="store_true",
        help=(
            "Normalize curated paper HF URLs for all publication dates, then "
            "refresh metrics for artifacts linked to recent papers"
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=MAX_PAPERS_PER_RUN,
        help=f"Maximum papers to scan per invocation (default: {MAX_PAPERS_PER_RUN})",
    )
    parser.add_argument(
        "--api-delay-seconds",
        type=float,
        default=API_DELAY_SECONDS,
        help=f"Delay between paper lookups (default: {API_DELAY_SECONDS})",
    )
    parser.add_argument(
        "--max-runtime-seconds",
        type=float,
        default=MAX_RUNTIME_SECONDS,
        help=f"Stop cleanly after this many seconds (default: {MAX_RUNTIME_SECONDS})",
    )
    args = parser.parse_args()
    if args.backfill and args.backfill_explicit:
        parser.error("--backfill and --backfill-explicit are mutually exclusive")
    if args.batch_size <= 0:
        parser.error("--batch-size must be greater than zero")
    if args.api_delay_seconds < 0:
        parser.error("--api-delay-seconds cannot be negative")
    if args.max_runtime_seconds <= 0:
        parser.error("--max-runtime-seconds must be greater than zero")
    return args


def main():
    args = parse_args()
    log("=" * 80)
    log(
        "Starting Hugging Face Artifact Historical Backfill"
        if args.backfill
        else (
            "Starting Hugging Face Explicit Artifact Backfill"
            if args.backfill_explicit
            else "Starting Hugging Face Artifact Refresh"
        )
    )
    log("=" * 80)

    settings = get_settings()
    hf_token = settings.hf_token or os.environ.get("HF_TOKEN") or None
    recent_cutoff = (datetime.now() - timedelta(days=RECENT_WINDOW_DAYS)).date()

    log("Configuration:")
    mode = (
        "historical backfill"
        if args.backfill
        else (
            "explicit artifact backfill" if args.backfill_explicit else "hourly refresh"
        )
    )
    log(f"  - Mode: {mode}")
    log(f"  - Recent window: {RECENT_WINDOW_DAYS} days (cutoff {recent_cutoff})")
    if args.backfill:
        log(f"  - Backfill starts: {BACKFILL_START_DATE}")
    log(f"  - Paper batch size: {args.batch_size}")
    log(f"  - Discovery threshold: {DISCOVERY_THRESHOLD_HOURS}h")
    log(f"  - Refresh threshold: {REFRESH_THRESHOLD_HOURS}h")
    log(f"  - HF token: {'set' if hf_token else 'not set (anonymous)'}")
    if args.backfill and not hf_token:
        raise RuntimeError("PWC_HF_TOKEN or HF_TOKEN is required for backfill mode")

    session = None
    start_time = time.time()
    try:
        session = db_manager.session_local()
        discovery = (
            run_explicit_backfill_phase(session, args.batch_size)
            if args.backfill_explicit
            else run_discovery_phase(
                session,
                hf_token,
                recent_cutoff,
                start_time,
                backfill=args.backfill,
                batch_size=args.batch_size,
                api_delay_seconds=args.api_delay_seconds,
                max_runtime_seconds=args.max_runtime_seconds,
            )
        )
        refresh = (
            {"selected": 0, "refreshed": 0, "failed": 0}
            if args.backfill
            else run_refresh_phase(session, hf_token, recent_cutoff, start_time)
        )

        if (
            discovery.get("papers_selected", 0)
            and discovery["papers_processed"] == 0
            and discovery["papers_failed"]
        ):
            raise RuntimeError("every selected Hugging Face discovery request failed")
        if refresh["selected"] and refresh["refreshed"] == 0 and refresh["failed"]:
            raise RuntimeError("every selected Hugging Face metric request failed")

        elapsed = (time.time() - start_time) / 60
        log("=" * 80)
        log("Hugging Face Artifact Refresh Completed successfully")
        log("=" * 80)
        log(f"Papers scanned: {discovery['papers_processed']}")
        log(f"Papers failed: {discovery['papers_failed']}")
        log(f"Links synced: {discovery['links_created']}")
        log(f"Artifacts refreshed: {refresh['refreshed']}")
        log(f"Artifacts failed: {refresh['failed']}")
        log(
            "HF_ARTIFACTS_SUMMARY "
            + json.dumps(
                {
                    "papers_selected": discovery.get("papers_selected", 0),
                    "papers_scanned": discovery["papers_processed"],
                    "papers_failed": discovery["papers_failed"],
                    "links_created": discovery["links_created"],
                    "artifacts_selected": refresh["selected"],
                    "artifacts_refreshed": refresh["refreshed"],
                    "artifacts_failed": refresh["failed"],
                }
            )
        )
        log(f"Runtime: {elapsed:.1f} minutes")
        log(f"Final memory available: {check_memory_usage()}MB")
        log("=" * 80)
    except Exception as e:
        if session:
            session.rollback()
        log(f"Fatal error: {e}")
        raise
    finally:
        if session:
            session.close()
            log("Database session closed")


if __name__ == "__main__":
    main()
