from __future__ import annotations

import pytest

from backend.config import Settings


def test_reconciliation_requires_an_enabled_staging_compiler() -> None:
    from backend.scripts.reconcile_latex_compiler_jobs import validate_settings

    with pytest.raises(ValueError, match="staging"):
        validate_settings(
            Settings(environment="development", chat_latex_compiler_jobs_enabled=True)
        )
    with pytest.raises(ValueError, match="kill switch"):
        validate_settings(Settings(environment="staging"))

    validate_settings(
        Settings(environment="staging", chat_latex_compiler_jobs_enabled=True)
    )
    validate_settings(Settings(environment="staging"), cleanup_only=True)
