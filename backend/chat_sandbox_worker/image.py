"""Request-independent named Modal image definition.

Importing this module defines the image; publishing it remains an explicit CI
release action and is never performed by a chat request or backend startup.
"""

from __future__ import annotations

from pathlib import Path

import modal

from backend.chat_sandbox_worker.contract import (
    BASE_IMAGE,
    PWC_CLI_VERSION,
    SDK_VERSION,
)

BACKEND = Path(__file__).resolve().parents[1]
REPOSITORY = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).resolve().parent
STANDALONE = REPOSITORY / "standalone_cli"

app = modal.App("pwc-chat-sandbox-v1")
image = (
    modal.Image.from_registry(BASE_IMAGE)
    .apt_install("bash", "ripgrep", "jq", "coreutils", "util-linux", "procps")
    .pip_install(f"claude-agent-sdk=={SDK_VERSION}")
    .run_commands(
        "groupadd --system pwc-broker && useradd --system --gid pwc-broker --home-dir /var/empty/pwc-broker pwc-broker",
        "groupadd --system pwc-chat && useradd --system --gid pwc-chat --create-home --home-dir /home/pwc-chat pwc-chat",
        "mkdir -p /opt/pwc/backend/chat_sandbox_worker /workspace /home/pwc-chat/.claude /var/empty/pwc-broker",
        "chown -R pwc-chat:pwc-chat /workspace /home/pwc-chat",
        "chmod 0755 /opt/pwc /opt/pwc/backend /opt/pwc/backend/chat_sandbox_worker",
        "chmod 0700 /workspace /home/pwc-chat /home/pwc-chat/.claude /var/empty/pwc-broker",
    )
    .add_local_file(BACKEND / "__init__.py", "/opt/pwc/backend/__init__.py", copy=True)
    .add_local_dir(
        WORKER,
        "/opt/pwc/backend/chat_sandbox_worker",
        copy=True,
        ignore=lambda path: path.name
        in {"image.py", "publish_image.py", "__pycache__"},
    )
    .add_local_file(STANDALONE / "install.py", "/opt/pwc/install-pwc.py", copy=True)
    .run_commands(
        f"python /opt/pwc/install-pwc.py --version {PWC_CLI_VERSION} --prefix /usr/local",
        "pwc version",
        "pwc --help >/dev/null",
        "pwc paper --help >/dev/null",
    )
    .env(
        {
            "PYTHONPATH": "/opt/pwc",
            "PWC_CHAT_MAX_TURNS": "8",
            "PWC_CHAT_MAX_TOOL_CALLS": "12",
            "PWC_CHAT_MAX_DIRECT_SEARCH_CALLS": "4",
            "PWC_CHAT_TOOL_RESULT_MAX_BYTES": "24576",
            "PWC_CHAT_TURN_TOOL_OUTPUT_MAX_BYTES": "98304",
            "PWC_CHAT_BASH_TIMEOUT_SECONDS": "30",
            "PWC_CHAT_AGENT_TIMEOUT_SECONDS": "180",
            "PWC_CHAT_SANDBOX_PIDS_MAX": "64",
        }
    )
)
