from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.chat_sandbox_worker.contract import (
    DATABASE_CONTRACT_VERSION,
    GATEWAY_CONTRACT_VERSION,
    MODAL_IMAGE_ID,
    WORKER_CONTRACT_VERSION,
)
from backend.services.chat_pi_release_window import (
    PiReleaseWindowUnavailable,
    require_pi_release_window,
)


def _write_release(root: Path, pointer: str, **updates) -> None:
    runtime = {
        "database_contract_version": DATABASE_CONTRACT_VERSION,
        "gateway_contract_version": GATEWAY_CONTRACT_VERSION,
        "modal_image_version": MODAL_IMAGE_ID,
        "worker_contract_version": WORKER_CONTRACT_VERSION,
        "supported_agent_harnesses": ["claude", "pi"],
    }
    runtime.update(updates)
    directory = root / pointer
    directory.mkdir()
    (directory / "release.json").write_text(
        json.dumps({"chat_runtime": runtime}), encoding="utf-8"
    )


def test_pi_release_window_requires_matching_current_and_previous(tmp_path: Path):
    _write_release(tmp_path, "current")
    _write_release(tmp_path, "previous")
    require_pi_release_window(tmp_path)


@pytest.mark.parametrize("pointer", ["current", "previous"])
def test_pi_release_window_rejects_an_incompatible_pointer(
    tmp_path: Path, pointer: str
):
    _write_release(tmp_path, "current")
    _write_release(tmp_path, "previous")
    manifest = tmp_path / pointer / "release.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["chat_runtime"]["supported_agent_harnesses"] = ["claude"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PiReleaseWindowUnavailable):
        require_pi_release_window(tmp_path)
