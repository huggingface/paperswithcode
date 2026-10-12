"""The paper-Markdown pipeline scripts, loaded once for the markdown test modules.

The hourly scheduler, the remote worker, and the volume probe are standalone
scripts rather than importable packages, so tests import them from here by name.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[3]
BACKEND = Path(__file__).resolve().parents[2]
WORKFLOWS = REPOSITORY / ".github" / "workflows"
sys.path.insert(0, str(WORKFLOWS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT = WORKFLOWS / "scripts" / "hourly" / "backfill_paper_markdown.py"
MODULE = _load("backfill_paper_markdown", SCRIPT)
WORKER_SCRIPT = BACKEND / "scripts" / "generate_missing_paper_markdown.py"
WORKER = _load("generate_missing_paper_markdown", WORKER_SCRIPT)
PROBE_SCRIPT = BACKEND / "scripts" / "probe_paper_markdown_volume.py"
PROBE = _load("probe_paper_markdown_volume", PROBE_SCRIPT)
