#!/usr/bin/env python3
"""Verify and execute the active immutable MCP release."""

from __future__ import annotations

import os
import sys

try:
    from deploy.mcp_release import MCP_ENVIRONMENTS, MCP_PORTS, validate_release
except ModuleNotFoundError:
    from mcp_release import MCP_ENVIRONMENTS, MCP_PORTS, validate_release


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"production", "staging"}:
        raise SystemExit("usage: mcp_launcher.py production|staging")
    release = (MCP_ENVIRONMENTS / sys.argv[1] / "current").resolve(strict=True)
    validate_release(release)
    project = release / "mcp_server"
    executable = project / ".venv/bin/python"
    os.chdir(project)
    os.execve(
        executable,
        [
            str(executable),
            "-m",
            "uvicorn",
            "pwc_mcp.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(MCP_PORTS[sys.argv[1]]),
            "--no-proxy-headers",
            "--no-access-log",
        ],
        os.environ.copy(),
    )


if __name__ == "__main__":
    main()
