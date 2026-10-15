"""Refresh GitHub star snapshots for the fresh and weekly repository queues.

Queue ownership is exclusive:

* ``hot``: official repositories linked to latest papers aged 0-30 days
* ``fresh``: official repositories linked to latest papers aged 31-180 days
* ``weekly``: official repositories whose newest latest paper is older than 180 days
  or whose linked papers have no publication date

The dedicated ``update_hot_github_trending`` job owns the hot queue. This
hourly adapter runs fresh and weekly concurrently with separate credentials.
"""

from __future__ import annotations

import gc
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

import requests
from sqlalchemy import text

from backend.database.connection import db_manager
from backend.services.repository_service import RepositoryService
from backend.utils.github_utils import strip_git_suffix

HOT_PAPER_WINDOW_DAYS = 30
FRESH_PAPER_WINDOW_DAYS = 180
DEFAULT_RATE_LIMIT_RESERVE = 500
MAX_RETRIES = 3
MAX_RETRY_DELAY_SECONDS = 60.0
QUEUE_CREDENTIALS = {
    "fresh": "PWC_GITHUB_TOKEN",
    "weekly": "GITHUB_CLASSIC_TOKEN_AICONSULTANCYNIELSROGGE",
}


def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp} - {message}", flush=True)


def bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def bounded_env_float(
    name: str, default: float, minimum: float, maximum: float
) -> float:
    value = float(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class RateLimit:
    limit: Optional[int] = None
    remaining: Optional[int] = None
    reset: Optional[int] = None
    retry_after: Optional[float] = None


@dataclass(frozen=True)
class GitHubFetchResult:
    stars: Optional[int]
    status_code: Optional[int]
    rate_limit: RateLimit
    retries: int = 0
    failure: Optional[str] = None

    @property
    def http_attempts(self) -> int:
        return self.retries + 1


def _header_int(headers, name: str) -> Optional[int]:
    raw = headers.get(name)
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _retry_after_seconds(headers, now: Optional[datetime] = None) -> Optional[float]:
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        try:
            target = parsedate_to_datetime(raw)
            current = now or datetime.now(target.tzinfo)
            return max(0.0, (target - current).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _rate_limit(response) -> RateLimit:
    return RateLimit(
        limit=_header_int(response.headers, "X-RateLimit-Limit"),
        remaining=_header_int(response.headers, "X-RateLimit-Remaining"),
        reset=_header_int(response.headers, "X-RateLimit-Reset"),
        retry_after=_retry_after_seconds(response.headers),
    )


def _retry_delay(attempt: int, retry_after: Optional[float]) -> float:
    if retry_after is not None:
        return min(retry_after, MAX_RETRY_DELAY_SECONDS)
    return min((2**attempt) + random.uniform(0.0, 0.5), MAX_RETRY_DELAY_SECONDS)


def rate_limit_reserve_reached(remaining: Optional[int], reserve: int) -> bool:
    return remaining is not None and remaining <= reserve


def get_repository_service():
    session = db_manager.session_local()
    return session, RepositoryService(session)


def get_repository_groups(
    session,
    queue: str,
    limit: int,
    threshold_hours_recent: int = 1,
    threshold_days_regular: int = 7,
    hot_threshold_minutes: int = 15,
) -> List[Dict]:
    """Select grouped owner/name repositories for one non-overlapping queue."""
    if queue not in {"hot", "fresh", "weekly"}:
        raise ValueError(f"Unknown GitHub stars queue: {queue}")

    now = datetime.now()
    hot_cutoff = now - timedelta(days=HOT_PAPER_WINDOW_DAYS)
    fresh_cutoff = now - timedelta(days=FRESH_PAPER_WINDOW_DAYS)
    threshold_hot = now - timedelta(minutes=hot_threshold_minutes)
    threshold_recent = now - timedelta(hours=threshold_hours_recent)
    threshold_regular = now - timedelta(days=threshold_days_regular)

    if queue == "hot":
        eligibility_clause = """
            linked.newest_paper_date >= :hot_cutoff
            AND (
                repo_groups.oldest_update IS NULL
                OR repo_groups.oldest_update < :threshold_hot
            )
        """
    elif queue == "fresh":
        eligibility_clause = """
            linked.newest_paper_date < :hot_cutoff
            AND linked.newest_paper_date >= :fresh_cutoff
            AND (
                repo_groups.oldest_update IS NULL
                OR repo_groups.oldest_update < :threshold_recent
            )
        """
    else:
        eligibility_clause = """
            (linked.newest_paper_date < :fresh_cutoff
             OR linked.newest_paper_date IS NULL)
            AND (
                repo_groups.oldest_update IS NULL
                OR repo_groups.oldest_update < :threshold_regular
            )
        """

    query = text(f"""
        WITH repo_groups AS (
            SELECT
                LOWER(r.owner) AS owner_key,
                LOWER(r.name) AS name_key,
                MIN(r.owner) AS owner,
                MIN(r.name) AS name,
                array_agg(r.id ORDER BY r.id) AS repository_ids,
                COUNT(*) AS url_count,
                MIN(r.num_stars_updated_at) AS oldest_update,
                MAX(r.num_stars) AS current_stars
            FROM repositories r
            WHERE COALESCE(r.owner, '') != ''
              AND COALESCE(r.name, '') != ''
            GROUP BY LOWER(r.owner), LOWER(r.name)
        ),
        linked AS (
            SELECT
                LOWER(r.owner) AS owner_key,
                LOWER(r.name) AS name_key,
                MAX(p.date_published) AS newest_paper_date
            FROM repositories r
            JOIN paper_repositories pr ON r.id = pr.repository_id
            JOIN papers p ON pr.paper_id = p.id
            WHERE COALESCE(r.owner, '') != ''
              AND COALESCE(r.name, '') != ''
              AND pr.is_official = TRUE
              AND p.is_latest_version = TRUE
            GROUP BY LOWER(r.owner), LOWER(r.name)
        )
        SELECT
            repo_groups.owner,
            repo_groups.name,
            repo_groups.repository_ids,
            repo_groups.url_count,
            repo_groups.oldest_update,
            repo_groups.current_stars,
            linked.newest_paper_date,
            COUNT(*) OVER() AS eligible_group_count,
            MIN(linked.newest_paper_date) OVER() AS oldest_eligible_paper_date
        FROM repo_groups
        JOIN linked USING (owner_key, name_key)
        WHERE {eligibility_clause}
        ORDER BY
            repo_groups.oldest_update ASC NULLS FIRST,
            linked.newest_paper_date DESC,
            repo_groups.url_count DESC
        LIMIT :group_limit
    """)
    try:
        results = session.execute(
            query,
            {
                "group_limit": limit,
                "hot_cutoff": hot_cutoff,
                "fresh_cutoff": fresh_cutoff,
                "threshold_hot": threshold_hot,
                "threshold_recent": threshold_recent,
                "threshold_regular": threshold_regular,
            },
        ).fetchall()
    finally:
        gc.collect()

    return [
        {
            "owner": row[0],
            "name": row[1],
            "repository_ids": row[2],
            "url_count": row[3],
            "oldest_update": row[4],
            "current_stars": row[5] or 0,
            "newest_paper_date": row[6],
            "eligible_group_count": row[7],
            "oldest_eligible_paper_date": row[8],
        }
        for row in results
    ]


def get_next_repository_group(
    session,
    queue: str,
    threshold_hours_recent: int = 1,
    threshold_days_regular: int = 7,
) -> Optional[Dict]:
    groups = get_repository_groups(
        session,
        queue=queue,
        limit=1,
        threshold_hours_recent=threshold_hours_recent,
        threshold_days_regular=threshold_days_regular,
    )
    return groups[0] if groups else None


def fetch_github_stars(
    owner: str,
    name: str,
    github_token: str,
    http: Optional[requests.Session] = None,
    max_retries: int = MAX_RETRIES,
    sleep=time.sleep,
) -> GitHubFetchResult:
    """Fetch stars with bounded transient retries and rate metadata."""
    client = http or requests.Session()
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "PapersWithCode-Stars/1.0",
    }
    url = f"https://api.github.com/repos/{owner}/{strip_git_suffix(name)}"

    for attempt in range(max_retries + 1):
        try:
            response = client.get(url, headers=headers, timeout=15)
        except requests.RequestException as error:
            if attempt < max_retries:
                sleep(_retry_delay(attempt, None))
                continue
            return GitHubFetchResult(None, None, RateLimit(), attempt, str(error))

        rate = _rate_limit(response)
        if response.status_code == 200:
            return GitHubFetchResult(
                int(response.json().get("stargazers_count", 0)),
                response.status_code,
                rate,
                attempt,
            )
        if response.status_code in {404, 451}:
            # Missing or blocked: report no star count so stored stars survive
            # transient 404s instead of dropping to zero.
            return GitHubFetchResult(
                None, response.status_code, rate, attempt, "unavailable"
            )

        transient = response.status_code >= 500
        throttled = response.status_code in {403, 429} and (
            rate.retry_after is not None or rate.remaining == 0
        )
        if (transient or throttled) and attempt < max_retries:
            # A depleted primary budget cannot recover within this bounded job.
            if rate.remaining == 0 and rate.retry_after is None:
                return GitHubFetchResult(
                    None,
                    response.status_code,
                    rate,
                    attempt,
                    "rate_limit",
                )
            # Do not retry before a long server-directed throttle expires.
            if (
                rate.retry_after is not None
                and rate.retry_after > MAX_RETRY_DELAY_SECONDS
            ):
                return GitHubFetchResult(
                    None,
                    response.status_code,
                    rate,
                    attempt,
                    "rate_limit",
                )
            sleep(_retry_delay(attempt, rate.retry_after))
            continue

        failure = "rate_limit" if throttled else f"http_{response.status_code}"
        return GitHubFetchResult(None, response.status_code, rate, attempt, failure)

    raise AssertionError("unreachable")


def store_star_snapshot(
    session,
    repository_ids: list,
    num_stars: int,
    snapshot_time: Optional[datetime] = None,
) -> int:
    """Upsert one timestamped snapshot for every duplicate repository row."""
    snapshot_time = snapshot_time or datetime.now()
    try:
        session.execute(
            text("""
                INSERT INTO repository_star_history
                    (repository_id, num_stars, snapshot_at)
                SELECT repository_id, :num_stars, :snapshot_at
                FROM unnest(CAST(:repository_ids AS bigint[])) AS repository_id
                ON CONFLICT (repository_id, snapshot_at)
                DO UPDATE SET num_stars = EXCLUDED.num_stars
            """),
            {
                "repository_ids": repository_ids,
                "num_stars": num_stars,
                "snapshot_at": snapshot_time,
            },
        )
        session.commit()
        return len(repository_ids)
    except Exception:
        session.rollback()
        raise


def update_repository_group_stars(
    repo_service: RepositoryService,
    session,
    repository_ids: list,
    num_stars: int,
    snapshot_time: Optional[datetime] = None,
) -> tuple[int, int]:
    updated = repo_service.update_repository_stars_batch(repository_ids, num_stars)
    snapshots = store_star_snapshot(
        session, repository_ids, num_stars, snapshot_time=snapshot_time
    )
    return updated, snapshots


def mark_repository_group_checked(session, repository_ids: list) -> int:
    """Record a missing (404) or blocked (451) repository, keeping its stars."""
    result = session.execute(
        text("""
            UPDATE repositories
            SET num_stars_updated_at = NOW()
            WHERE id = ANY(CAST(:repository_ids AS bigint[]))
        """),
        {"repository_ids": repository_ids},
    )
    session.commit()
    return result.rowcount


def check_memory_usage() -> int:
    try:
        with open("/proc/meminfo", "r") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return 1000


def run_queue(
    queue: str,
    github_token: str,
    max_updates: int,
    max_runtime_seconds: int,
    *,
    delay: float = 1.0,
    rate_limit_reserve: int = 0,
    hot_threshold_minutes: int = 15,
    selection_only: bool = False,
) -> Dict:
    """Process one queue and return structured stage statistics."""
    started = time.monotonic()
    stats: Dict = {
        "queue": queue,
        "eligible_groups": 0,
        "selected_groups": 0,
        "processed_groups": 0,
        "updated_repositories": 0,
        "snapshots_stored": 0,
        "api_calls": 0,
        "successes": 0,
        "failures": 0,
        "credential_failures": 0,
        "terminal_unavailable": 0,
        "not_found": 0,
        "legal_blocked": 0,
        "retries": 0,
        "rate_limit_stops": 0,
        "rate_limit_limit": None,
        "rate_limit_remaining": None,
        "rate_limit_reset": None,
        "touched_repository_ids": [],
        "oldest_eligible_age_days": None,
    }
    try:
        selection_session, _ = get_repository_service()
        try:
            groups = get_repository_groups(
                selection_session,
                queue,
                max_updates,
                hot_threshold_minutes=hot_threshold_minutes,
            )
        finally:
            selection_session.close()
        stats["eligible_groups"] = groups[0]["eligible_group_count"] if groups else 0
        stats["selected_groups"] = len(groups)
        oldest_date = groups[0]["oldest_eligible_paper_date"] if groups else None
        stats["oldest_eligible_age_days"] = (
            (datetime.now().date() - oldest_date).days if oldest_date else None
        )

        if selection_only:
            for group in groups:
                log(
                    f"[DRY RUN][{queue.upper()}] "
                    f"{group['owner']}/{group['name']} ids={group['repository_ids']}"
                )
            return stats

        with requests.Session() as http:
            for group in groups:
                if time.monotonic() - started > max_runtime_seconds:
                    break
                if check_memory_usage() < 200:
                    log(f"[{queue.upper()}] low memory; stopping")
                    break
                remaining = stats["rate_limit_remaining"]
                if rate_limit_reserve_reached(remaining, rate_limit_reserve):
                    stats["rate_limit_stops"] += 1
                    break

                result = fetch_github_stars(
                    group["owner"], group["name"], github_token, http=http
                )
                stats["api_calls"] += result.http_attempts
                stats["retries"] += result.retries
                stats["rate_limit_limit"] = result.rate_limit.limit
                stats["rate_limit_remaining"] = result.rate_limit.remaining
                stats["rate_limit_reset"] = result.rate_limit.reset

                if result.status_code in {404, 451}:
                    write_session, _ = get_repository_service()
                    try:
                        updated = mark_repository_group_checked(
                            write_session, group["repository_ids"]
                        )
                    finally:
                        write_session.close()
                    stats["successes"] += 1
                    stats["terminal_unavailable"] += 1
                    if result.status_code == 404:
                        stats["not_found"] += 1
                    else:
                        stats["legal_blocked"] += 1
                    stats["updated_repositories"] += updated
                    stats["touched_repository_ids"].extend(group["repository_ids"])
                elif result.stars is None:
                    stats["failures"] += 1
                    if result.failure in {"http_401", "http_403"}:
                        stats["credential_failures"] += 1
                    if result.failure == "rate_limit":
                        stats["rate_limit_stops"] += 1
                        break
                else:
                    write_session, repo_service = get_repository_service()
                    try:
                        updated, snapshots = update_repository_group_stars(
                            repo_service,
                            write_session,
                            group["repository_ids"],
                            result.stars,
                        )
                    finally:
                        write_session.close()
                    stats["successes"] += 1
                    stats["updated_repositories"] += updated
                    stats["snapshots_stored"] += snapshots
                    stats["touched_repository_ids"].extend(group["repository_ids"])

                stats["processed_groups"] += 1
                if delay:
                    time.sleep(delay)
    finally:
        stats["fetch_seconds"] = round(time.monotonic() - started, 3)

    log(f"GITHUB_QUEUE_SUMMARY {stats}")
    return stats


def summarize_queues(results: list[Dict]) -> Dict:
    """Flatten per-queue results for log parsing and the admin dashboard."""
    summary: Dict = {}
    fields = (
        "eligible_groups",
        "selected_groups",
        "processed_groups",
        "successes",
        "failures",
        "credential_failures",
        "terminal_unavailable",
        "not_found",
        "legal_blocked",
        "updated_repositories",
        "snapshots_stored",
        "api_calls",
        "rate_limit_stops",
        "rate_limit_remaining",
    )
    for result in results:
        queue = result["queue"]
        summary[f"{queue}_credential"] = QUEUE_CREDENTIALS[queue]
        for field in fields:
            summary[f"{queue}_{field}"] = result.get(field, 0)
    return summary


def require_successful_queues(results: list[Dict]) -> None:
    """Fail when a selected queue produced no usable GitHub response."""
    outages = []
    for result in results:
        if result["selected_groups"] == 0 or result["successes"] > 0:
            continue
        queue = result["queue"]
        credential = QUEUE_CREDENTIALS[queue]
        if result["credential_failures"]:
            outages.append(
                f"{queue} credential {credential} was rejected "
                f"({result['credential_failures']} authentication/authorization failures)"
            )
        else:
            outages.append(
                f"{queue} queue failed every selected repository group "
                f"({result['failures']} failures across {result['api_calls']} API calls)"
            )
    if outages:
        raise RuntimeError("; ".join(outages))


def main():
    log("Starting GitHub Stars Update")
    token_config = {
        "fresh": os.getenv("PWC_GITHUB_TOKEN"),
        "weekly": os.getenv("GITHUB_CLASSIC_TOKEN_AICONSULTANCYNIELSROGGE"),
    }
    missing = [queue for queue, token in token_config.items() if not token]
    if missing:
        raise RuntimeError(f"Missing GitHub token for queue(s): {', '.join(missing)}")

    reserve = bounded_env_int(
        "PWC_GITHUB_RATE_LIMIT_RESERVE",
        DEFAULT_RATE_LIMIT_RESERVE,
        0,
        5_000,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                run_queue,
                "fresh",
                token_config["fresh"],
                2_500,
                48 * 60,
                rate_limit_reserve=reserve,
            ),
            executor.submit(
                run_queue,
                "weekly",
                token_config["weekly"],
                1_000,
                40 * 60,
            ),
        ]
        results = [future.result() for future in futures]

    log(f"GITHUB_STARS_SUMMARY {json.dumps(summarize_queues(results))}")
    require_successful_queues(results)
    log("GitHub Stars Update Completed")
    log(
        "Repositories processed: "
        f"{sum(result['processed_groups'] for result in results)}"
    )
    log(
        "Repository URLs updated: "
        f"{sum(result['updated_repositories'] for result in results)}"
    )
    log(
        "Historical snapshots stored: "
        f"{sum(result['snapshots_stored'] for result in results)}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log(f"GitHub Stars Update job failed: {error}")
        raise
