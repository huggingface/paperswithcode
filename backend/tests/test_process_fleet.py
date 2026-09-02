import signal
from pathlib import Path

import deploy.process_fleet as process_fleet


def test_process_fleet_fails_together_when_one_child_exits(monkeypatch) -> None:
    created = []

    class Child:
        def __init__(self, *, fail: bool) -> None:
            self.returncode = None
            self.fail = fail
            self.polls = 0
            self.signals = []

        def poll(self):
            self.polls += 1
            if self.fail and self.polls >= 2:
                self.returncode = 1
            return self.returncode

        def send_signal(self, signum):
            self.signals.append(signum)
            self.returncode = 0

    def popen(command, *, cwd, env):
        child = Child(fail=not created)
        created.append((command, cwd, env, child))
        return child

    monkeypatch.setattr(process_fleet.subprocess, "Popen", popen)
    monkeypatch.setattr(process_fleet.signal, "signal", lambda *_args: signal.SIG_DFL)
    monkeypatch.setattr(process_fleet.time, "sleep", lambda _seconds: None)

    result = process_fleet.run_process_fleet(
        (("node", "a"), ("node", "b")),
        ({"WORKER": "a"}, {"WORKER": "b"}),
        cwd=Path("/release"),
    )

    assert result == 1
    assert created[1][3].signals == [signal.SIGTERM]
    assert [item[2]["WORKER"] for item in created] == ["a", "b"]


def test_process_fleet_exits_cleanly_after_systemd_stop(monkeypatch) -> None:
    handlers = {}
    children = []

    class Child:
        returncode = None

        def poll(self):
            return self.returncode

        def send_signal(self, _signum):
            self.returncode = -signal.SIGTERM

    def popen(_command, *, cwd, env):
        child = Child()
        children.append(child)
        return child

    def install_handler(signum, handler):
        previous = handlers.get(signum, signal.SIG_DFL)
        handlers[signum] = handler
        return previous

    monkeypatch.setattr(process_fleet.subprocess, "Popen", popen)
    monkeypatch.setattr(process_fleet.signal, "signal", install_handler)

    def stop_once(_seconds):
        handlers[signal.SIGTERM](signal.SIGTERM)

    monkeypatch.setattr(process_fleet.time, "sleep", stop_once)

    result = process_fleet.run_process_fleet(
        (("node", "a"), ("node", "b")),
        ({"WORKER": "a"}, {"WORKER": "b"}),
        cwd=Path("/release"),
    )

    assert result == 0
    assert [child.returncode for child in children] == [-signal.SIGTERM] * 2


def test_process_fleet_staggers_child_startup(monkeypatch) -> None:
    launches = []
    sleeps = []

    class Child:
        returncode = None

        def poll(self):
            if len(launches) == 3:
                self.returncode = 0
            return self.returncode

        def send_signal(self, _signum):
            self.returncode = -signal.SIGTERM

    monkeypatch.setattr(
        process_fleet.subprocess,
        "Popen",
        lambda command, *, cwd, env: launches.append((command, cwd, env)) or Child(),
    )
    monkeypatch.setattr(process_fleet.signal, "signal", lambda *_args: signal.SIG_DFL)
    monkeypatch.setattr(process_fleet.time, "sleep", sleeps.append)

    result = process_fleet.run_process_fleet(
        (("node", "a"), ("node", "b"), ("node", "c")),
        ({"WORKER": "a"}, {"WORKER": "b"}, {"WORKER": "c"}),
        cwd=Path("/release"),
        launch_interval_seconds=0.5,
    )

    assert result == 1
    assert len(launches) == 3
    assert sleeps == [0.5, 0.5]
