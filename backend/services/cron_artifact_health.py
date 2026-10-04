"""Bounded, content-free checks for the enrichment dashboard export."""

import json
from pathlib import Path

SNAPSHOT_PATH = Path(
    "/var/lib/paperswithcode/shared/enrichment-dashboard/snapshot.json"
)
MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024


def enrichment_snapshot_metrics(path: Path = SNAPSHOT_PATH) -> dict:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_SNAPSHOT_BYTES + 1)
    except OSError:
        return {"snapshot_valid": False}
    if len(raw) > MAX_SNAPSHOT_BYTES:
        return {"snapshot_valid": False}
    try:
        snapshot = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return {"snapshot_valid": False}
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("schema_version") != 1
        or not isinstance(snapshot.get("generated_at"), str)
        or not all(
            isinstance(snapshot.get(key), list)
            for key in ("daily", "papers", "evaluations")
        )
        or not snapshot["daily"]
    ):
        return {"snapshot_valid": False}
    return {
        "snapshot_valid": True,
        "snapshot_generated_at": snapshot["generated_at"],
        "snapshot_bytes": len(raw),
        "snapshot_papers": len(snapshot["papers"]),
        "snapshot_evaluations": len(snapshot["evaluations"]),
    }
