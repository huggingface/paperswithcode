"""Runtime storage validation."""

from __future__ import annotations

import os
from pathlib import Path

from backend.config import Settings
from backend.services.runtime_policies.deployment import (
    _resolved_absolute,
)


def validate_runtime_storage(settings: Settings) -> None:
    """Validate deployed read/write paths outside immutable releases."""

    if not Path(settings.frontend_dist_dir).is_absolute():
        raise RuntimeError("PWC_FRONTEND_DIST_DIR must be absolute")
    writable = {
        "RUNTIME_DATA_DIR": settings.runtime_data_dir,
        "CODEX_ADD_EVALS_SPOOL_DIR": settings.codex_add_evals_spool_dir,
        "CHAT_AGENT_CWD": settings.chat_agent_cwd,
        "CHAT_RECOVERY_SPOOL_DIR": settings.chat_recovery_spool_dir,
    }
    for name, value in writable.items():
        path = _resolved_absolute(name, value)
        if not path.is_dir() or not os.access(path, os.W_OK | os.X_OK):
            raise RuntimeError(f"PWC_{name} must be an existing writable directory")

    for name, value in {
        "CRON_LOG_DIR": settings.cron_log_dir,
        "CRON_LOCK_DIR": settings.cron_lock_dir,
    }.items():
        path = _resolved_absolute(name, value)
        if not path.is_dir() or not os.access(path, os.R_OK | os.X_OK):
            raise RuntimeError(f"PWC_{name} must be an existing readable directory")

    thumbnail_store = _resolved_absolute(
        "THUMBNAIL_TEMP_CACHE_DIR", settings.thumbnail_temp_cache_dir
    )
    if not thumbnail_store.is_dir() or not os.access(thumbnail_store, os.R_OK):
        raise RuntimeError(
            "PWC_THUMBNAIL_CACHE_DIR must be an existing readable directory"
        )
