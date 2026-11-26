"""Mirror nginx's public catalog ``limit_req`` zones to report remaining quota.

nginx enforces the limits; this process sees exactly the requests nginx
admits, keyed by the same address, so replaying its leaky-bucket arithmetic
yields the quota nginx will grant next.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RateLimitZone:
    name: str
    per_minute: int
    burst: int
    pattern: re.Pattern[str]
    post_pattern: re.Pattern[str] | None = None

    @property
    def per_second(self) -> float:
        return self.per_minute / 60

    @property
    def policy(self) -> str:
        return f'"{self.name}";q={self.per_minute};w=60'

    def applies(self, method: str, path: str) -> bool:
        if method == "GET":
            return self.pattern.fullmatch(path) is not None
        return (
            method == "POST"
            and self.post_pattern is not None
            and self.post_pattern.fullmatch(path) is not None
        )


CATALOG_ZONE = RateLimitZone(
    "catalog",
    per_minute=120,
    burst=60,
    pattern=re.compile(r"/api/v1/(?:papers|tasks|datasets|evaluations)(?:/.*)?"),
    post_pattern=re.compile(r"/api/v1/papers/lookup/?"),
)
LIST_ZONE = RateLimitZone(
    "list",
    per_minute=60,
    burst=20,
    pattern=re.compile(
        r"/api/v1/(?:(?:papers|tasks|datasets|evaluations)|papers/search(?:/feed)?)/?"
    ),
)
ZONES = (CATALOG_ZONE, LIST_ZONE)


def zones_for(method: str, path: str) -> tuple[RateLimitZone, ...]:
    return tuple(zone for zone in ZONES if zone.applies(method, path))


@dataclass
class _Buckets:
    zone: RateLimitZone
    entries: dict[str, tuple[float, float]] = field(default_factory=dict)
    prune_at: int = 4096

    def take(self, key: str, now: float) -> float:
        previous = self.entries.get(key)
        excess = 0.0
        if previous is not None:
            last_excess, last_seen = previous
            elapsed = max(now - last_seen, 0.0)
            excess = max(last_excess - self.zone.per_second * elapsed + 1, 0.0)
        self.entries[key] = (excess, now)
        if len(self.entries) >= self.prune_at:
            self._prune(now)
        return excess

    def _prune(self, now: float) -> None:
        rate = self.zone.per_second
        self.entries = {
            key: (excess, seen)
            for key, (excess, seen) in self.entries.items()
            if excess - rate * (now - seen) > 0
        }
        self.prune_at = max(4096, 2 * len(self.entries))


class PublicRateLimiter:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.buckets = {zone.name: _Buckets(zone) for zone in ZONES}

    def take(self, key: str, zones: tuple[RateLimitZone, ...]) -> str:
        now = self.clock()
        items = []
        for zone in zones:
            excess = self.buckets[zone.name].take(key, now)
            remaining = max(math.floor(zone.burst - excess + 1e-9), 0)
            reset = math.ceil(excess / zone.per_second - 1e-9)
            items.append(f'"{zone.name}";r={remaining};t={reset}')
        return ", ".join(items)
