"""Worker proxy and supervisor process contracts."""

from __future__ import annotations

import os


from backend.chat_sandbox_worker import (
    supervisor,
)


def test_supervisor_launch_read_does_not_consume_worker_frame():
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, b"private-launch\nworker-frame\n")
        assert supervisor._readline_unbuffered(read_fd, 64) == b"private-launch\n"
        assert os.read(read_fd, 64) == b"worker-frame\n"
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_supervisor_tolerates_unsupported_proc_remount(monkeypatch):
    monkeypatch.setattr(
        supervisor.Path,
        "read_text",
        lambda *_args, **_kwargs: "none /proc proc rw 0 0\n",
    )

    class Result:
        returncode = 32

    calls: list[list[str]] = []

    def run(command, **options):
        calls.append(command)
        assert options["check"] is False
        return Result()

    monkeypatch.setattr(supervisor.subprocess, "run", run)

    supervisor._harden_proc()
    assert calls == [["mount", "-o", "remount,hidepid=2,nosuid,nodev", "/proc"]]


def test_supervisor_child_environment_preserves_packaged_worker_path(monkeypatch):
    monkeypatch.setenv("PWC_CHAT_MAX_TURNS", "8")
    monkeypatch.setenv("PWC_CHAT_MAX_OUTPUT_TOKENS", "8000")
    monkeypatch.setenv("PYTHONPATH", "/untrusted")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-pass")

    environment = supervisor._safe_environment("/var/empty/pwc-broker")

    assert environment["PYTHONPATH"] == "/opt/pwc"
    assert environment["PWC_CHAT_MAX_TURNS"] == "8"
    assert "ANTHROPIC_API_KEY" not in environment

    agent_environment = supervisor._agent_environment()
    assert agent_environment["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "8000"
    assert agent_environment["HTTPS_PROXY"] == "http://127.0.0.1:8766"
    assert agent_environment["NO_PROXY"] == "127.0.0.1,localhost"
    assert agent_environment["NODE_EXTRA_CA_CERTS"] == "/tmp/pwc-webfetch-ca.pem"
    assert agent_environment["PWC_API_URL"] == "http://127.0.0.1:8765/api/v1"
    assert "PWC_WEBFETCH_TOKEN_FD" not in agent_environment
