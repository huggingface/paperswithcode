"""Release fixtures shared by external Pi slot lifecycle tests."""

from __future__ import annotations

import json
from pathlib import Path


def _release(
    root: Path,
    slot: str,
    runtime_id: str = "a" * 64,
    *,
    environment: str = "staging",
) -> Path:
    release = root / "releases" / f"release-{slot}"
    release.mkdir(parents=True)
    (release / "release.json").write_text(
        json.dumps(
            {
                "release_id": f"release-{slot}",
                "external_pi_runtime": {
                    "identity_schema": 1,
                    "runtime_id": runtime_id,
                    "contract": "external-pi-v1",
                },
            }
        )
    )
    slot_root = root / "environments" / environment / "slots" / slot
    slot_root.mkdir(parents=True)
    (slot_root / "release").symlink_to(release)
    runtime = root / "runtimes/external-pi" / runtime_id
    (runtime / "node" / "bin").mkdir(parents=True)
    (runtime / "app" / "dist" / "src").mkdir(parents=True)
    (runtime / "assets").mkdir()
    (runtime / "node" / "bin" / "node").write_text("node")
    (runtime / "app" / "dist" / "src" / "external_http_main.js").write_text("main")
    (runtime / "assets" / "pi-system-prompt.txt").write_text("prompt")
    return release
