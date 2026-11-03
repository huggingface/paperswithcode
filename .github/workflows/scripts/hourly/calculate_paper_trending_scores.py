"""
Calculate Composite Paper Trending Scores

Computes a paper-level trending score that blends the existing GitHub star
velocity EMA (``repositories.trending_score``, stars/hour) with Hugging Face
artifact Hub trending scores (``hf_artifacts.trending_score``). When
``PWC_TRENDING_X_WEIGHT`` is above 0, the like velocity of the paper's fastest
linked X post (``x_post_metrics.like_velocity``) can lift that score. The formula lives in
``backend/utils/trending.py`` so it is unit-testable without a DB.

Pipeline:
  1. Load the scoring population: latest-version papers published in the last
     year, with their best official-repo velocity, linked HF artifact scores,
     and fastest linked X post from the last week.
  2. Derive the quantile-rank corpora for GitHub velocity, per-kind HF
     trending scores, and X like velocity.
  3. Compute the composite score per paper and persist it to
     ``papers.trending_score`` (+ debug components). Papers with no live signal
     are cleared to NULL so they drop out of the composite feed.

This does NOT touch ``repositories.trending_score``: the GitHub-only ranking
remains the instant rollback path (PWC_TRENDING_RANKING_MODE=github).

Schedule: Hourly, after update_github_stars and update_hf_artifacts.
"""

import gc
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.utils.trending import (
    DEFAULT_X_MIN_LIKES_PER_HOUR,
    DEFAULT_X_WEIGHT,
    KIND_WEIGHTS,
    X_POST_WINDOW_DAYS,
    apply_decaying_pin,
    compute_paper_score,
    decaying_pin_floor,
    is_hf_aggregator,
    parse_trending_paper_id_pin_specs,
    parse_trending_pin_specs,
    sorted_positive,
    x_corpus,
)

# Score papers published within this window (bounds the work; older papers fall
# out of the trending feed anyway).
SCORING_WINDOW_DAYS = 365
# GitHub repo scores older than this are treated as stale (no live signal).
GITHUB_FRESHNESS_HOURS = 24
WRITE_CHUNK_SIZE = 500
PIN_STATE_PATH = (
    Path(
        os.getenv(
            "PWC_CRON_LOCK_DIR",
            str(Path(__file__).resolve().parent.parent / "data"),
        )
    )
    / "trending_pin_state.json"
)


def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp} - {message}", flush=True)


def x_settings() -> tuple[float, float]:
    """Return the configured ``(x_weight, x_min_likes_per_hour)``."""
    weight = float(os.getenv("PWC_TRENDING_X_WEIGHT") or DEFAULT_X_WEIGHT)
    if not 0.0 <= weight <= 1.0:
        raise ValueError("PWC_TRENDING_X_WEIGHT must be in [0, 1]")
    min_likes = float(
        os.getenv("PWC_TRENDING_X_MIN_LIKES_PER_HOUR") or DEFAULT_X_MIN_LIKES_PER_HOUR
    )
    return weight, min_likes


def load_population(session, cutoff):
    """Return ``{paper_id: {"github_raw", "existing", "artifacts", "x_raw"}}``.

    - ``github_raw``: best fresh official-repo stars/hour (0.0 if none).
    - ``existing``: whether the paper currently has a non-null trending_score.
    - ``artifacts``: list of ``(kind, trending_score)`` for linked HF artifacts,
      excluding aggregators (see ``is_hf_aggregator``).
    - ``x_raw``: likes/hour of the fastest linked X post from the last week.
    """
    log("Loading paper population (GitHub component)...")
    github_rows = session.execute(
        text("""
            SELECT
                p.id AS paper_id,
                (p.trending_score IS NOT NULL) AS existing,
                gh.github_raw
            FROM papers p
            LEFT JOIN LATERAL (
                SELECT MAX(r.trending_score) AS github_raw
                FROM paper_repositories pr
                JOIN repositories r ON r.id = pr.repository_id
                WHERE pr.paper_id = p.id
                  AND pr.is_official = TRUE
                  AND r.trending_score IS NOT NULL
                  AND r.trending_score_updated_at
                      >= NOW() - (:fresh_hours || ' hours')::interval
            ) gh ON TRUE
            WHERE p.is_latest_version = TRUE
              AND p.date_published >= :cutoff
        """),
        {"cutoff": cutoff, "fresh_hours": str(GITHUB_FRESHNESS_HOURS)},
    ).fetchall()

    population = {}
    for row in github_rows:
        population[row.paper_id] = {
            "github_raw": float(row.github_raw) if row.github_raw is not None else 0.0,
            "existing": bool(row.existing),
            "artifacts": [],
            "x_raw": 0.0,
        }
    log(f"Population size: {len(population)} papers")

    log("Loading HF artifact component...")
    hf_rows = session.execute(
        text("""
            WITH fan_out AS (
                SELECT x.hf_artifact_id, COUNT(*) AS linked_papers
                FROM paper_hf_artifacts x
                JOIN hf_artifacts a ON a.id = x.hf_artifact_id
                JOIN papers p ON p.id = x.paper_id
                WHERE p.is_latest_version = TRUE
                  AND a.trending_score IS NOT NULL
                GROUP BY x.hf_artifact_id
            )
            SELECT pha.paper_id, a.kind, a.repo_id, a.trending_score,
                   f.linked_papers
            FROM paper_hf_artifacts pha
            JOIN hf_artifacts a ON a.id = pha.hf_artifact_id
            JOIN fan_out f ON f.hf_artifact_id = a.id
            JOIN papers p ON p.id = pha.paper_id
            WHERE p.is_latest_version = TRUE
              AND p.date_published >= :cutoff
        """),
        {"cutoff": cutoff},
    ).fetchall()

    hf_links = 0
    aggregator_links = 0
    for row in hf_rows:
        entry = population.get(row.paper_id)
        if entry is None:
            continue
        if is_hf_aggregator(row.kind, row.repo_id, row.linked_papers):
            aggregator_links += 1
            continue
        entry["artifacts"].append((row.kind, float(row.trending_score)))
        hf_links += 1
    log(f"HF artifact score links: {hf_links}")
    log(f"HF aggregator links ignored: {aggregator_links}")

    log("Loading X like velocity component...")
    x_rows = session.execute(
        text("""
            SELECT t.paper_id, MAX(m.like_velocity) AS x_raw
            FROM paper_x_threads t
            JOIN x_post_metrics m ON m.tweet_id = t.tweet_id
            JOIN papers p ON p.id = t.paper_id
            WHERE p.is_latest_version = TRUE
              AND p.date_published >= :cutoff
              AND m.gone_at IS NULL
              AND m.like_velocity > 0
              AND m.posted_at >= NOW() - (:window_days || ' days')::interval
            GROUP BY t.paper_id
        """),
        {"cutoff": cutoff, "window_days": str(X_POST_WINDOW_DAYS)},
    ).fetchall()
    x_papers = 0
    for row in x_rows:
        entry = population.get(row.paper_id)
        if entry is None:
            continue
        entry["x_raw"] = float(row.x_raw)
        x_papers += 1
    log(f"Papers with a live X post: {x_papers}")

    return population


def derive_corpora(population):
    """Build the quantile-rank corpora (sorted positive values) from live signal."""
    github_sorted = sorted_positive(
        entry["github_raw"] for entry in population.values()
    )

    by_kind = {kind: [] for kind in KIND_WEIGHTS}
    for entry in population.values():
        for kind, score in entry["artifacts"]:
            if score > 0 and kind in by_kind:
                by_kind[kind].append(score)
    sorted_by_kind = {kind: sorted_positive(values) for kind, values in by_kind.items()}

    def _summ(values):
        return f"n={len(values)}, max={values[-1]:.2f}" if values else "n=0"

    log(f"GitHub velocity corpus: {_summ(github_sorted)}")
    for kind in KIND_WEIGHTS:
        log(f"HF {kind} trendingScore corpus: {_summ(sorted_by_kind[kind])}")
    return github_sorted, sorted_by_kind


def build_score_changes(
    population,
    github_sorted,
    sorted_by_kind,
    paper_ids=None,
    *,
    x_sorted=(),
    x_weight=DEFAULT_X_WEIGHT,
    x_min_likes_per_hour=DEFAULT_X_MIN_LIKES_PER_HOUR,
):
    """Compute updates/clears for all papers or an explicit target set."""
    selected = sorted(population) if paper_ids is None else sorted(set(paper_ids))
    updates = []
    clears = []
    for paper_id in selected:
        entry = population.get(paper_id)
        if entry is None:
            continue
        score, github_component, hf_component, x_component = compute_paper_score(
            entry["github_raw"],
            github_sorted,
            entry["artifacts"],
            sorted_by_kind,
            x_raw=entry["x_raw"],
            x_sorted=x_sorted,
            x_weight=x_weight,
            x_min_likes_per_hour=x_min_likes_per_hour,
        )
        # With X weighted at 0, an X-only paper scores 0 and stays unscored.
        if score > 0:
            updates.append(
                {
                    "id": paper_id,
                    "score": round(score, 4),
                    "g": round(github_component, 4),
                    "h": round(hf_component, 4),
                    "x": round(x_component, 4),
                }
            )
        elif entry["existing"]:
            clears.append(paper_id)
    return updates, clears


def get_latest_paper_ids_for_repositories(
    session, repository_ids: list[int]
) -> list[int]:
    """Return latest papers linked officially to the touched repository rows."""
    if not repository_ids:
        return []
    rows = session.execute(
        text("""
            SELECT DISTINCT p.id
            FROM papers p
            JOIN paper_repositories pr ON pr.paper_id = p.id
            WHERE pr.repository_id = ANY(:repository_ids)
              AND pr.is_official = TRUE
              AND p.is_latest_version = TRUE
        """),
        {"repository_ids": sorted(set(repository_ids))},
    ).fetchall()
    return [row[0] for row in rows]


def get_aged_out_scored_paper_ids(session, cutoff) -> list[int]:
    """Return papers that left the scoring window but still hold a score."""
    rows = session.execute(
        text("""
            SELECT id
            FROM papers
            WHERE trending_score IS NOT NULL
              AND date_published < :cutoff
        """),
        {"cutoff": cutoff},
    ).fetchall()
    return [row[0] for row in rows]


def calculate_paper_scores(session, paper_ids=None) -> dict:
    """Normalize against the full corpus and write only selected paper rows."""
    cutoff = (datetime.now() - timedelta(days=SCORING_WINDOW_DAYS)).date()
    population = load_population(session, cutoff)
    if not population:
        return {"population": 0, "selected": 0, "written": 0, "cleared": 0}

    github_sorted, sorted_by_kind = derive_corpora(population)
    x_weight, x_min_likes_per_hour = x_settings()
    x_sorted = x_corpus(
        (entry["x_raw"] for entry in population.values()), x_min_likes_per_hour
    )
    log(f"X like velocity corpus: n={len(x_sorted)}, weight={x_weight}")
    updates, clears = build_score_changes(
        population,
        github_sorted,
        sorted_by_kind,
        paper_ids=paper_ids,
        x_sorted=x_sorted,
        x_weight=x_weight,
        x_min_likes_per_hour=x_min_likes_per_hour,
    )
    if paper_ids is None:
        # The population only covers the window, so aged-out scores would
        # otherwise stay frozen forever.
        clears.extend(get_aged_out_scored_paper_ids(session, cutoff))
    written, cleared = write_scores(session, updates, clears)
    selected = len(population) if paper_ids is None else len(set(paper_ids))
    return {
        "population": len(population),
        "selected": selected,
        "written": written,
        "cleared": cleared,
    }


def write_scores(session, updates, clears):
    """Persist computed scores and clear stale ones, in chunks."""
    written = 0
    for start in range(0, len(updates), WRITE_CHUNK_SIZE):
        chunk = updates[start : start + WRITE_CHUNK_SIZE]
        session.execute(
            text("""
                UPDATE papers
                SET trending_score = :score,
                    github_trending_component = :g,
                    hf_trending_component = :h,
                    x_trending_component = :x,
                    trending_score_updated_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
            """),
            chunk,
        )
        session.commit()
        written += len(chunk)
        gc.collect()

    cleared = 0
    for start in range(0, len(clears), WRITE_CHUNK_SIZE):
        chunk_ids = clears[start : start + WRITE_CHUNK_SIZE]
        session.execute(
            text("""
                UPDATE papers
                SET trending_score = NULL,
                    github_trending_component = NULL,
                    hf_trending_component = NULL,
                    x_trending_component = NULL,
                    trending_score_updated_at = NOW(),
                    updated_at = NOW()
                WHERE id = ANY(:ids)
            """),
            {"ids": chunk_ids},
        )
        session.commit()
        cleared += len(chunk_ids)
        gc.collect()

    return written, cleared


def _load_pin_state() -> dict:
    if not PIN_STATE_PATH.exists():
        return {}
    return json.loads(PIN_STATE_PATH.read_text())


def _save_pin_state(state: dict) -> None:
    PIN_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PIN_STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


def apply_decaying_trending_pins(session) -> int:
    """Raise pinned papers toward 100, linearly decaying to their true score.

    ``PWC_TRENDING_PIN_ARXIV_IDS`` entries look like ``2606.16140:72`` (arXiv id
    and decay hours; hours default to 72). ``PWC_TRENDING_PIN_PAPER_IDS`` uses
    the same syntax for internal paper IDs, including external papers. Pin start
    times are persisted in ``trending_pin_state.json`` so the fade continues
    across hourly runs.
    """
    arxiv_specs = parse_trending_pin_specs(os.getenv("PWC_TRENDING_PIN_ARXIV_IDS", ""))
    paper_specs = parse_trending_paper_id_pin_specs(
        os.getenv("PWC_TRENDING_PIN_PAPER_IDS", "")
    )
    state_specs = {
        **arxiv_specs,
        **{
            f"paper:{paper_id}": decay_hours
            for paper_id, decay_hours in paper_specs.items()
        },
    }
    if not state_specs:
        return 0

    state = _load_pin_state()
    now = datetime.now(timezone.utc)

    for pin_key, decay_hours in state_specs.items():
        if pin_key not in state:
            state[pin_key] = {
                "started_at": now.isoformat(),
                "decay_hours": decay_hours,
            }
        else:
            state[pin_key]["decay_hours"] = decay_hours

    state = {pin_key: state[pin_key] for pin_key in state_specs if pin_key in state}
    _save_pin_state(state)

    rows = session.execute(
        text("""
            SELECT id, arxiv_id, trending_score
            FROM papers
            WHERE (
                    arxiv_id = ANY(:arxiv_ids)
                    OR id = ANY(:paper_ids)
                  )
              AND is_latest_version = TRUE
        """),
        {
            "arxiv_ids": list(arxiv_specs.keys()),
            "paper_ids": list(paper_specs.keys()),
        },
    ).fetchall()

    applied = 0
    for row in rows:
        paper_pin_key = f"paper:{row.id}"
        pin_key = paper_pin_key if row.id in paper_specs else row.arxiv_id
        pin = state[pin_key]
        started_at = datetime.fromisoformat(pin["started_at"])
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        hours_elapsed = (now - started_at).total_seconds() / 3600.0
        decay_hours = float(pin["decay_hours"])
        computed = float(row.trending_score) if row.trending_score is not None else None
        floor = decaying_pin_floor(hours_elapsed, decay_hours)
        final = apply_decaying_pin(computed, hours_elapsed, decay_hours)

        if floor <= 0 and computed is not None:
            log(f"Decaying pin finished for {pin_key} (computed={computed:.2f})")
            continue

        if computed is not None and abs(final - computed) < 1e-4:
            continue

        session.execute(
            text("""
                UPDATE papers
                SET trending_score = :score,
                    trending_score_updated_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
            """),
            {"id": row.id, "score": round(final, 4)},
        )
        applied += 1
        computed_label = f"{computed:.2f}" if computed is not None else "none"
        log(
            f"Decaying pin {pin_key}: computed={computed_label}, "
            f"floor={floor:.2f}, final={final:.2f} "
            f"({hours_elapsed:.1f}h / {decay_hours:.0f}h)"
        )

    if applied:
        session.commit()
    return applied


def log_top_papers(session, limit: int = 10):
    """Log top composite and top GitHub-only papers for trial comparison."""
    log("-" * 80)
    log(f"Top {limit} papers by COMPOSITE score:")
    rows = session.execute(
        text("""
            SELECT id, title, trending_score,
                   github_trending_component, hf_trending_component
            FROM papers
            WHERE trending_score IS NOT NULL
            ORDER BY trending_score DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).fetchall()
    for r in rows:
        title = (r.title or "")[:60]
        log(
            f"  [{r.id}] score={float(r.trending_score):.2f} "
            f"(G={float(r.github_trending_component or 0):.2f}, "
            f"H={float(r.hf_trending_component or 0):.2f}) {title}"
        )

    log(f"Top {limit} papers by GITHUB-only repo velocity (current ranking):")
    rows = session.execute(
        text("""
            SELECT p.id, p.title, MAX(r.trending_score) AS github_raw
            FROM papers p
            JOIN paper_repositories pr ON pr.paper_id = p.id AND pr.is_official = TRUE
            JOIN repositories r ON r.id = pr.repository_id
            WHERE r.trending_score IS NOT NULL
              AND r.trending_score_updated_at >= NOW() - INTERVAL '24 hours'
              AND p.is_latest_version = TRUE
            GROUP BY p.id, p.title
            ORDER BY github_raw DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).fetchall()
    for r in rows:
        title = (r.title or "")[:60]
        log(f"  [{r.id}] stars/hr={float(r.github_raw):.2f} {title}")


def main():
    log("=" * 80)
    log("Starting Composite Paper Trending Score Calculation")
    log("=" * 80)

    cutoff = (datetime.now() - timedelta(days=SCORING_WINDOW_DAYS)).date()
    log(f"Scoring window: {SCORING_WINDOW_DAYS} days (cutoff {cutoff})")

    session = None
    start_time = time.time()
    try:
        session = db_manager.session_local()
        result = calculate_paper_scores(session)
        if not result["population"]:
            log("No papers in scoring window - nothing to do")
            return
        written = result["written"]
        cleared = result["cleared"]
        log(f"Scores written: {written}; clearing stale: {cleared}")
        pinned = apply_decaying_trending_pins(session)

        log_top_papers(session)

        elapsed = (time.time() - start_time) / 60
        log("=" * 80)
        log("Composite Paper Trending Score Calculation Completed successfully")
        log("=" * 80)
        log(f"Scores written: {written}")
        log(f"Stale scores cleared: {cleared}")
        log(f"Decaying pins applied: {pinned}")
        log(
            "PAPER_TRENDING_SUMMARY "
            + json.dumps(
                {
                    "eligible_population": result["population"],
                    "selected": result["selected"],
                    "scores_written": written,
                    "stale_scores_cleared": cleared,
                    "decaying_pins_applied": pinned,
                }
            )
        )
        log(f"Runtime: {elapsed:.1f} minutes")
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
