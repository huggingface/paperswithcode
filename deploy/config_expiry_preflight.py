"""Refuse a deploy whose chat configuration expires within a week.

The installed deployment tooling runs as root under the system interpreter
without the backend's dependencies, so this module mirrors
``backend/services/chat_config_expiry.py`` using only the standard library. It
reads the environment file and the candidate release's settings defaults with
``ast``; it never imports release code. A parity test keeps the two in step.
"""

from __future__ import annotations

import ast
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

EXPIRY_WARNING_WINDOW = timedelta(days=7)
SETTINGS_PATH = Path("backend/chat_configuration/settings.py")
FIELDS = (
    "chat_openrouter_pricing_verified_at",
    "chat_openrouter_pricing_max_age_days",
    "chat_openai_direct_enabled",
    "chat_openai_pricing_verified_at",
    "chat_openai_pricing_max_age_days",
    "chat_executor_remote_transport_enabled",
    "chat_executor_admission_key_not_after_ms",
    "chat_executor_authorization_keys_json",
)


def release_defaults(release_dir: Path) -> dict[str, object]:
    """Return literal ``Field(default=...)`` values for the tracked fields."""

    tree = ast.parse((release_dir / SETTINGS_PATH).read_text(encoding="utf-8"))
    defaults: dict[str, object] = {}
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in FIELDS
            and node.value is not None
        ):
            continue
        value = node.value
        if isinstance(value, ast.Call):
            value = next((k.value for k in value.keywords if k.arg == "default"), None)
        if value is not None:
            defaults[node.target.id] = ast.literal_eval(value)
    return defaults


def environment_values(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_file.is_file():
        return values
    wanted = {f"PWC_{name.upper()}": name for name in FIELDS}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        key, separator, raw = raw_line.strip().partition("=")
        if separator and key.strip() in wanted:
            values[wanted[key.strip()]] = raw.strip().strip("\"'")
    return values


def _flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _pricing_expiry(verified_at: object, max_age_days: object) -> datetime | None:
    try:
        verified = date.fromisoformat(str(verified_at))
        first_stale_day = verified + timedelta(days=int(str(max_age_days)) + 1)
    except ValueError:
        return None
    return datetime.combine(first_stale_day, datetime.min.time(), tzinfo=timezone.utc)


def _utc_timestamp(seconds: float) -> datetime | None:
    try:
        return datetime.fromtimestamp(seconds, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def config_expiries(
    defaults: dict[str, object], overrides: dict[str, str]
) -> dict[str, datetime]:
    """Return ``{name: expires_at}`` for enabled chat configuration."""

    values = {**defaults, **overrides}
    expiries = {
        "openrouter_pricing": _pricing_expiry(
            values.get("chat_openrouter_pricing_verified_at"),
            values.get("chat_openrouter_pricing_max_age_days"),
        )
    }
    if _flag(values.get("chat_openai_direct_enabled", False)):
        expiries["openai_pricing"] = _pricing_expiry(
            values.get("chat_openai_pricing_verified_at"),
            values.get("chat_openai_pricing_max_age_days"),
        )
    if _flag(values.get("chat_executor_remote_transport_enabled", False)):
        try:
            admission_ms = int(
                str(values.get("chat_executor_admission_key_not_after_ms", 0))
            )
        except ValueError:
            admission_ms = 0
        expiries["executor_admission_key"] = (
            _utc_timestamp(admission_ms / 1_000) if admission_ms > 0 else None
        )
        try:
            not_after = json.loads(
                str(values.get("chat_executor_authorization_keys_json", ""))
            )["current"]["not_after"]
        except (json.JSONDecodeError, KeyError, TypeError):
            not_after = None
        expiries["executor_authorization_key"] = (
            _utc_timestamp(not_after) if isinstance(not_after, int) else None
        )
    return {name: when for name, when in expiries.items() if when is not None}


def expiring(release_dir: Path, env_file: Path, now: datetime) -> dict[str, datetime]:
    """Return expiries that have passed or fall within the warning window."""

    return {
        name: expires_at
        for name, expires_at in config_expiries(
            release_defaults(release_dir), environment_values(env_file)
        ).items()
        if expires_at - now <= EXPIRY_WARNING_WINDOW
    }
