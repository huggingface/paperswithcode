"""Bounded, content-free checks for the enrichment dashboard export."""

from pathlib import Path

import ijson

SNAPSHOT_PATH = Path(
    "/var/lib/paperswithcode/shared/enrichment-dashboard/snapshot.json"
)
SNAPSHOT_LISTS = ("daily", "papers", "evaluations")


def enrichment_snapshot_metrics(path: Path = SNAPSHOT_PATH) -> dict:
    """Validate the snapshot shape by streaming it, counting top-level lists.

    The export grows with the catalog, so it is never loaded whole.
    """

    counts: dict[str, int] = {}
    scalars: dict[str, object] = {}
    try:
        with path.open("rb") as stream:
            size = path.stat().st_size
            events = ijson.parse(stream)
            if next(events, None) != ("", "start_map", None):
                return {"snapshot_valid": False}
            for prefix, event, value in events:
                if event in {"map_key", "end_map", "end_array"}:
                    continue
                parent, _, leaf = prefix.rpartition(".")
                if prefix in SNAPSHOT_LISTS and event == "start_array":
                    counts[prefix] = 0
                elif leaf == "item" and parent in counts:
                    counts[parent] += 1
                elif prefix in {"schema_version", "generated_at"}:
                    scalars[prefix] = value
    except (OSError, ijson.JSONError, UnicodeDecodeError):
        return {"snapshot_valid": False}
    if (
        scalars.get("schema_version") != 1
        or not isinstance(scalars.get("generated_at"), str)
        or set(counts) != set(SNAPSHOT_LISTS)
        or not counts["daily"]
    ):
        return {"snapshot_valid": False}
    return {
        "snapshot_valid": True,
        "snapshot_generated_at": scalars["generated_at"],
        "snapshot_bytes": size,
        "snapshot_papers": counts["papers"],
        "snapshot_evaluations": counts["evaluations"],
    }
