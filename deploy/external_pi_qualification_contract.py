"""Stdlib-only fixed contracts shared by fleet qualification consumers."""

from __future__ import annotations

QUALIFICATION_PORTS = tuple(range(8780, 8796))
QUALIFICATION_WORKER_IDS = tuple(
    f"staging-qualification-{index:02d}" for index in range(16)
)
QUALIFICATION_SUPERVISOR_UNITS = tuple(
    f"paperswithcode-staging-external-pi-qualification@{index:02d}.service"
    for index in range(16)
)
QUALIFICATION_WORKER_UNITS = tuple(
    f"paperswithcode-staging-external-pi-qualification-worker@{index:02d}.service"
    for index in range(16)
)
QUALIFICATION_SHAPES = ((5, 32), (8, 16), (16, 8))
CAPACITY_QUALIFICATION_SHAPES = ((2, 32, 32), (4, 16, 48), (3, 32, 64))
QUALIFICATION_SESSION_LIMITS = frozenset(
    sessions for _, sessions in QUALIFICATION_SHAPES
) | frozenset(sessions for _, sessions, _ in CAPACITY_QUALIFICATION_SHAPES)


def qualification_index(index: int, port: int, maximum_sessions: int) -> int:
    if type(index) is not int or not 0 <= index < len(QUALIFICATION_PORTS):
        raise ValueError("external Pi qualification replica index is invalid")
    if port != QUALIFICATION_PORTS[index]:
        raise ValueError("external Pi qualification replica port is invalid")
    if maximum_sessions not in QUALIFICATION_SESSION_LIMITS:
        raise ValueError("external Pi qualification session limit is invalid")
    return index
