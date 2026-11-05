"""Wall-clock expiry dates carried by deployed chat configuration.

Startup validation must not depend on these dates: a date passing would stop
every worker at its next restart and take the whole site down. Each value is
enforced where it is used instead (the affected chat route fails closed), and
the operational alert monitor and deploy preflight warn while there is still
time to renew it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from backend.config import Settings

EXPIRY_WARNING_WINDOW = timedelta(days=7)


@dataclass(frozen=True)
class ConfigExpiry:
    name: str
    expires_at: datetime
    renewal: str

    def remaining(self, now: datetime) -> timedelta:
        return self.expires_at - now


def _pricing_expiry(verified_at: str, max_age_days: int) -> datetime | None:
    """Return the first instant at which a pinned price list counts as stale."""

    try:
        verified = date.fromisoformat(verified_at)
    except ValueError:
        # Startup validation reports malformed dates; there is no expiry to track.
        return None
    first_stale_day = verified + timedelta(days=max_age_days + 1)
    return datetime.combine(first_stale_day, datetime.min.time(), tzinfo=UTC)


def _utc_timestamp(seconds: float) -> datetime | None:
    """Convert a configured epoch value, or ``None`` if it is out of range.

    Startup only bounds key lifetimes, not absolute values, so a value in the
    wrong unit (milliseconds for seconds) must not raise during startup.
    """

    try:
        return datetime.fromtimestamp(seconds, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _authorization_key_expiry(keys_json: str) -> datetime | None:
    try:
        not_after = json.loads(keys_json)["current"]["not_after"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    if not isinstance(not_after, int):
        return None
    return _utc_timestamp(not_after)


def chat_config_expiries(settings: Settings) -> list[ConfigExpiry]:
    """Return every enabled chat configuration value that expires with time."""

    if not settings.chat_enabled:
        return []
    candidates: list[tuple[str, datetime | None, str]] = [
        (
            "openrouter_pricing",
            _pricing_expiry(
                settings.chat_openrouter_pricing_verified_at,
                settings.chat_openrouter_pricing_max_age_days,
            ),
            "PWC_CHAT_OPENROUTER_PRICING_VERIFIED_AT",
        )
    ]
    if settings.chat_openai_direct_enabled:
        candidates.append(
            (
                "openai_pricing",
                _pricing_expiry(
                    settings.chat_openai_pricing_verified_at,
                    settings.chat_openai_pricing_max_age_days,
                ),
                "PWC_CHAT_OPENAI_PRICING_VERIFIED_AT",
            )
        )
    if settings.chat_executor_remote_transport_enabled:
        admission_not_after_ms = settings.chat_executor_admission_key_not_after_ms
        candidates.extend(
            (
                (
                    "executor_admission_key",
                    _utc_timestamp(admission_not_after_ms / 1_000)
                    if admission_not_after_ms > 0
                    else None,
                    "PWC_CHAT_EXECUTOR_ADMISSION_KEY_NOT_AFTER_MS",
                ),
                (
                    "executor_authorization_key",
                    _authorization_key_expiry(
                        settings.chat_executor_authorization_keys_json
                    ),
                    "PWC_CHAT_EXECUTOR_AUTHORIZATION_KEYS_JSON",
                ),
            )
        )
    return [
        ConfigExpiry(name=name, expires_at=expires_at, renewal=renewal)
        for name, expires_at, renewal in candidates
        if expires_at is not None
    ]


def expiring_chat_config(
    settings: Settings,
    now: datetime,
    *,
    within: timedelta = EXPIRY_WARNING_WINDOW,
) -> list[ConfigExpiry]:
    """Return expiries that have passed or will pass within ``within``."""

    return [
        expiry
        for expiry in chat_config_expiries(settings)
        if expiry.remaining(now) <= within
    ]
