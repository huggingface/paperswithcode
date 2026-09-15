#!/usr/bin/env python3
"""Enable the reviewed first-party MCP tools for one protected environment."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from deploy.configure_host_env import assign, decoded_value, read_lines, write_env


def enabled_values(current: dict[str, str], environment: str) -> dict[str, str]:
    if environment not in {"staging", "production"}:
        raise ValueError("invalid environment")
    if decoded_value(current.get("PWC_ENVIRONMENT", "")) != environment:
        raise ValueError("protected environment does not match")
    key = "PWC_CHAT_PWC_MCP_ENABLED"
    if decoded_value(current.get(key, f"{key}=false")) != "false":
        raise ValueError("MCP tools must be disabled before this transition")
    return assign(current, {key: "true"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("environment", choices=["staging", "production"])
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run as root")
    if args.confirm != f"ENABLE_{args.environment.upper()}_PWC_MCP":
        parser.error("explicit environment confirmation required")
    path = Path("/etc/paperswithcode") / f"{args.environment}.env"
    updated = enabled_values(read_lines(path), args.environment)
    write_env(path, updated, f"pwc-{args.environment}")
    print(f"Enabled {args.environment} PwC MCP; deploy/refresh to apply")


if __name__ == "__main__":
    main()
