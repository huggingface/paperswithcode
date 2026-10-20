#!/usr/bin/env python3
"""Raise the staging chat application circuit below the provider budget."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

try:
    from deploy.configure_host_env import assign, decoded_value, read_lines, write_env
except ModuleNotFoundError:
    from configure_host_env import assign, decoded_value, read_lines, write_env

CONFIG_PATH = Path("/etc/paperswithcode/staging.env")
CONFIRMATION = "RAISE_STAGING_CHAT_APPLICATION_CAP_105"


def raised_values(current: dict[str, str]) -> dict[str, str]:
    workspace = decoded_value(
        current.get("PWC_CHAT_SANDBOX_MODAL_WORKSPACE", "")
    ).strip()
    if not workspace:
        raise ValueError("PWC_CHAT_SANDBOX_MODAL_WORKSPACE is required")
    expected = {
        "PWC_ENVIRONMENT": "staging",
        "PWC_CHAT_SANDBOX_MODAL_WORKSPACE": workspace,
        "PWC_CHAT_SANDBOX_WARNING_MICROUSD": "75000000",
        "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD": "100000000",
        "PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD": "0",
        "PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD": "250000000",
        "PWC_CHAT_SANDBOX_PROVIDER_MODE": "starter_workspace",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION": (
            f"modal-workspace-{workspace}-250-staging-starter-v1"
        ),
    }
    actual = {key: decoded_value(current.get(key, "")).strip() for key in expected}
    if actual != expected:
        raise ValueError(
            "staging chat budget does not match reviewed starter policy v1"
        )
    return assign(
        current,
        {
            "PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD": "105000000",
            "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION": (
                f"modal-workspace-{workspace}-250-staging-starter-app105-v2"
            ),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo")
    if args.confirm != CONFIRMATION:
        parser.error(f"--confirm must be {CONFIRMATION}")
    try:
        updated = raised_values(read_lines(CONFIG_PATH))
    except ValueError as error:
        parser.error(str(error))
    write_env(CONFIG_PATH, updated, "pwc-staging")
    print("raised staging chat application cap to $105; warning remains $75")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
