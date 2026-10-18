"""Ownership marker for evaluation rows written by live leaderboard syncs.

Every live leaderboard sync starts the methodology of the rows it owns with
``Managed by the Papers with Code <source> live sync.``. The sync rewrites
those rows on each run, so other writers (such as remote curators) must leave
them alone.
"""

from __future__ import annotations

import re

SYNC_MANAGED_METHODOLOGY_PREFIX = "Managed by the Papers with Code "
_SYNC_MANAGED_HEAD = re.compile(
    re.escape(SYNC_MANAGED_METHODOLOGY_PREFIX) + r"\S.*? live sync\."
)


def managed_methodology_prefix(source: str) -> str:
    """Return the methodology head a sync writes on the rows it owns."""
    return f"{SYNC_MANAGED_METHODOLOGY_PREFIX}{source} live sync."


def is_sync_managed(methodology: str | None) -> bool:
    """Whether an evaluation methodology marks the row as owned by a live sync."""
    return _SYNC_MANAGED_HEAD.match((methodology or "").strip()) is not None
