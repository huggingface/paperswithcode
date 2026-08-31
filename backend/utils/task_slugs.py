"""Canonical task slugs and compatibility aliases."""

TASK_SLUG_ALIASES = {
    "3d-tracking": "3D-tracking",
    "deepfake-and-forensics": "deepfake-detection",
}


def canonical_task_slug(slug: str) -> str:
    """Return the canonical slug while preserving legacy inbound links."""
    return TASK_SLUG_ALIASES.get(slug, slug)


def task_slug_candidates(slug: str) -> tuple[str, ...]:
    """Return canonical-first lookup candidates for rolling migrations."""
    canonical = canonical_task_slug(slug)
    return (canonical,) if canonical == slug else (canonical, slug)
