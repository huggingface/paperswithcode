"""Small fail-together process supervisor for one systemd-managed fleet."""

from __future__ import annotations

import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path


def run_process_fleet(
    commands: Sequence[Sequence[str]],
    environments: Sequence[Mapping[str, str]],
    *,
    cwd: Path,
) -> int:
    if len(commands) != len(environments) or not commands:
        raise ValueError("process fleet commands and environments must align")
    children: list[subprocess.Popen] = []
    stopping = False
    unexpected_exit = False

    def signal_children(signum: int) -> None:
        for child in children:
            if child.poll() is None:
                child.send_signal(signum)

    def stop_children(signum: int, _frame: object | None = None) -> None:
        nonlocal stopping
        stopping = True
        signal_children(signum)

    previous = {
        signum: signal.signal(signum, stop_children)
        for signum in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        for command, environment in zip(commands, environments, strict=True):
            children.append(
                subprocess.Popen(
                    list(command),
                    cwd=cwd,
                    env=dict(environment),
                )
            )
        while True:
            completed = [child for child in children if child.poll() is not None]
            if len(completed) == len(children):
                if stopping and not unexpected_exit:
                    return 0
                codes = [child.returncode or 0 for child in children]
                return max(codes) or 1
            if completed and not stopping:
                unexpected_exit = True
                signal_children(signal.SIGTERM)
            time.sleep(0.1)
    except BaseException:
        signal_children(signal.SIGTERM)
        raise
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


__all__ = ("run_process_fleet",)
