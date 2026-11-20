"""Join an inventory with classification records and split them for action.

Usage: python3 triage.py <blocks.jsonl> <classifications-dir> <output-dir>

Inventory ids are the zero-based line numbers of ``blocks.jsonl`` formatted as
``c00000``. Writes ``delete.jsonl`` (input for ``backend_comments.py delete``)
plus ``decision.jsonl``, ``excuse.jsonl`` and ``keep.jsonl`` with the comment
text attached, and prints the counts.
"""

import collections
import json
import sys
from pathlib import Path


def main() -> int:
    blocks_path, classified_dir, output_dir = map(Path, sys.argv[1:4])
    blocks = {
        f"c{index:05d}": json.loads(line)
        for index, line in enumerate(blocks_path.read_text().splitlines())
    }
    records = {}
    for path in sorted(classified_dir.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                record = json.loads(line)
                records[record["id"]] = record
    unclassified = sorted(set(blocks) - set(records))
    if unclassified:
        raise SystemExit(
            f"{len(unclassified)} blocks unclassified, e.g. {unclassified[:5]}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    handles = {
        name: (output_dir / f"{name}.jsonl").open("w")
        for name in ("delete", "decision", "excuse", "keep")
    }
    counts = collections.Counter()
    for block_id, block in blocks.items():
        record = records[block_id]
        category = record["category"]
        counts[category] += 1
        if category != "keep":
            location = {key: block[key] for key in ("f", "kind", "start", "end")}
            handles["delete"].write(json.dumps(location) + "\n")
        if category in ("decision", "excuse", "keep"):
            handles[category].write(json.dumps({**record, **block}) + "\n")
    for handle in handles.values():
        handle.close()
    print(dict(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
