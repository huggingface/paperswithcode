#!/usr/bin/env python3
"""Generate the committed systemd units in deploy/systemd/cron/.

Run from the repository root after editing deploy/cron_schedules.py:

    python deploy/generate_cron_units.py

The generated units are committed so that release tooling can install them
byte-for-byte and so the dashboard can discover scheduled duties from source.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cron_schedules import TIMERS, TimerSpec  # noqa: E402

UNIT_DIR = Path(__file__).resolve().parent / "systemd" / "cron"
THROTTLED = "/usr/local/sbin/pwc-cron-throttled"


def render_service(spec: TimerSpec) -> str:
    lines = [
        "[Unit]",
        f"Description={spec.description}",
        "After=network-online.target postgresql@16-main.service",
    ]
    if spec.after:
        lines.append("After=" + " ".join(f"{unit}.service" for unit in spec.after))
    lines += [
        "Wants=network-online.target",
        "",
        "[Service]",
        "Type=oneshot",
    ]
    if spec.unit == "pwc-cron-update-hot-github-trending":
        lines += [
            "# Slot 3 is reserved for this short refresh; bulk jobs use slots 0-2.",
            "Environment=PWC_CRON_THROTTLE_SLOTS=4",
        ]
    for argv in spec.invocations:
        lines.append(f"ExecStart={THROTTLED} " + " ".join(argv))
    lines += [
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "ProtectHome=true",
        "ProtectSystem=strict",
        "ReadWritePaths=/run/paperswithcode/cron-slots",
        "",
    ]
    return "\n".join(lines)


def render_timer(spec: TimerSpec) -> str:
    lines = [
        "[Unit]",
        f"Description=Timer: {spec.description}",
        "",
        "[Timer]",
    ]
    lines += [f"OnCalendar={calendar}" for calendar in spec.on_calendar]
    lines += [
        "RandomizedDelaySec=90",
        "AccuracySec=1m",
        "Persistent=true",
        f"Unit={spec.unit}.service",
        "",
        "[Install]",
        "WantedBy=timers.target",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    UNIT_DIR.mkdir(parents=True, exist_ok=True)
    expected: dict[str, str] = {}
    for spec in TIMERS:
        expected[f"{spec.unit}.service"] = render_service(spec)
        expected[f"{spec.unit}.timer"] = render_timer(spec)
    for stale in UNIT_DIR.iterdir():
        if stale.name not in expected:
            stale.unlink()
            print(f"removed {stale.name}")
    for name, content in sorted(expected.items()):
        target = UNIT_DIR / name
        if not target.exists() or target.read_text() != content:
            target.write_text(content)
            print(f"wrote {name}")
    print(f"{len(expected)} units in {UNIT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
