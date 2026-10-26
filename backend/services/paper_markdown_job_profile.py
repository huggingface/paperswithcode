"""Measured, bounded execution profiles for paper-Markdown OCR jobs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Literal

PAPER_MARKDOWN_GPU_HOURLY_RATE_USD = Decimal("1.80")
PAPER_MARKDOWN_PROFILE_LABEL = "profile_id"


@dataclass(frozen=True)
class PaperMarkdownJobProfile:
    """One launch and accounting contract shared by every OCR surface."""

    profile_id: str
    mode: Literal["live", "backfill"]
    max_papers: int
    hard_timeout_seconds: int
    soft_deadline_seconds: int
    concurrency: int

    def __post_init__(self) -> None:
        if self.max_papers <= 0 or self.concurrency <= 0:
            raise ValueError("paper Markdown profile bounds must be positive")
        if self.hard_timeout_seconds <= 0:
            raise ValueError("paper Markdown hard timeout must be positive")
        if self.soft_deadline_seconds < 0:
            raise ValueError("paper Markdown soft deadline must not be negative")
        if self.hard_timeout_seconds - self.soft_deadline_seconds < 30 * 60:
            raise ValueError(
                "paper Markdown profile requires at least 30 minutes for cleanup"
            )

    @property
    def hard_timeout(self) -> str:
        hours, remainder = divmod(self.hard_timeout_seconds, 3600)
        if remainder:
            raise ValueError("HF job timeout must be an exact number of hours")
        return f"{hours}h"

    @property
    def reservation_hours(self) -> float:
        return self.hard_timeout_seconds / 3600

    @property
    def reservation_per_job_usd(self) -> float:
        return float(self.reservation_per_job_decimal)

    @property
    def reservation_per_job_decimal(self) -> Decimal:
        return (
            Decimal(self.hard_timeout_seconds)
            / Decimal(3600)
            * PAPER_MARKDOWN_GPU_HOURLY_RATE_USD
        )

    @property
    def labels(self) -> dict[str, str]:
        return {
            PAPER_MARKDOWN_PROFILE_LABEL: self.profile_id,
            "hard_timeout_seconds": str(self.hard_timeout_seconds),
        }

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(
            hard_timeout=self.hard_timeout,
            reservation_hours=self.reservation_hours,
            reservation_per_job_usd=self.reservation_per_job_usd,
        )
        return payload


# Six retained successful production shards included four 100-paper runs; the
# slowest finished in 17,220 seconds (4.78h). The 7h hard bound leaves 2.22h
# above that observed maximum, while the 6.5h worker deadline preserves a
# 30-minute checkpoint/cleanup margin and a $12.60 worst-case reservation.
PAPER_MARKDOWN_LIVE_JOB_PROFILE = PaperMarkdownJobProfile(
    profile_id="live-v1",
    mode="live",
    max_papers=100,
    hard_timeout_seconds=7 * 3600,
    soft_deadline_seconds=int(6.5 * 3600),
    concurrency=1,
)
PAPER_MARKDOWN_BACKFILL_JOB_PROFILE = PaperMarkdownJobProfile(
    profile_id="backfill-v1",
    mode="backfill",
    max_papers=100,
    hard_timeout_seconds=7 * 3600,
    soft_deadline_seconds=int(6.5 * 3600),
    concurrency=4,
)
# The fresh lane is a live-mode slot pair for papers indexed in the last day,
# so reader chat gets page-tagged layout within minutes instead of waiting
# behind a 100-paper live shard (~3h). A five-paper live shard ran 10 minutes
# on 2026-10-25, model start-up included; 2h leaves ample margin at $3.60.
PAPER_MARKDOWN_FRESH_JOB_PROFILE = PaperMarkdownJobProfile(
    profile_id="live-fresh-v1",
    mode="live",
    max_papers=10,
    hard_timeout_seconds=2 * 3600,
    soft_deadline_seconds=int(1.5 * 3600),
    concurrency=2,
)

_PROFILES = {
    profile.profile_id: profile
    for profile in (
        PAPER_MARKDOWN_LIVE_JOB_PROFILE,
        PAPER_MARKDOWN_BACKFILL_JOB_PROFILE,
        PAPER_MARKDOWN_FRESH_JOB_PROFILE,
    )
}


def paper_markdown_job_profile(mode: str) -> PaperMarkdownJobProfile:
    if mode == "live":
        return PAPER_MARKDOWN_LIVE_JOB_PROFILE
    if mode == "backfill":
        return PAPER_MARKDOWN_BACKFILL_JOB_PROFILE
    raise ValueError("paper Markdown job profile mode must be live or backfill")


def paper_markdown_job_profile_from_labels(
    labels: dict[str, str],
) -> PaperMarkdownJobProfile | None:
    """Resolve recognized labels while leaving old/unknown jobs fail-closed."""
    profile_id = labels.get(PAPER_MARKDOWN_PROFILE_LABEL) or labels.get("profile")
    return _PROFILES.get(profile_id or "")
