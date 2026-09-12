"""Request-independent named Modal image definition.

Importing this module defines the image; publishing it remains an explicit CI
release action and is never performed by a chat request or backend startup.
"""

from __future__ import annotations

from pathlib import Path

import modal

from backend.chat_sandbox_worker.contract import (
    BASE_IMAGE,
    MODAL_APP_NAME,
    PI_MCP_ADAPTER_VERSION,
    PI_NODE_SHA256,
    PI_NODE_VERSION,
    PI_VERSION,
    POSTERLY_CHROMIUM_REVISION,
    POSTERLY_PLAYWRIGHT_VERSION,
    POSTERLY_SOURCE_COMMIT,
    PWC_CLI_INSTALLER_SHA256,
    PWC_CLI_SOURCE_COMMIT,
    PWC_CLI_VERSION,
    RESTRICTED_HF_CLI_VERSION,
    SDK_VERSION,
)

BACKEND = Path(__file__).resolve().parents[1]
REPOSITORY = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).resolve().parent
CLIS = REPOSITORY / "clis"
RESTRICTED_HF = CLIS / "restricted_hf_cli"
S2_CLI = CLIS / "s2_cli"

app = modal.App(MODAL_APP_NAME)
image = (
    modal.Image.from_registry(BASE_IMAGE)
    .apt_install(
        "bash",
        "ripgrep",
        "jq",
        "coreutils",
        "util-linux",
        "procps",
        "curl",
        "xz-utils",
        "ca-certificates",
        "git",
        "poppler-utils",
    )
    .run_commands(
        f"curl -fsSLo /tmp/node.tar.xz https://nodejs.org/dist/v{PI_NODE_VERSION}/node-v{PI_NODE_VERSION}-linux-x64.tar.xz",
        f"echo '{PI_NODE_SHA256}  /tmp/node.tar.xz' | sha256sum -c -",
        "tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 && rm /tmp/node.tar.xz",
        f"node --version | grep -Fx 'v{PI_NODE_VERSION}'",
    )
    .pip_install(
        f"claude-agent-sdk=={SDK_VERSION}",
        "cryptography==48.0.0",
        "websockets==16.0",
        f"playwright=={POSTERLY_PLAYWRIGHT_VERSION}",
        "Pillow==11.3.0",
        "PyMuPDF==1.26.3",
        "qrcode==8.2",
    )
    .run_commands(
        "git init /opt/posterly && git -C /opt/posterly remote add origin https://github.com/Chenruishuo/posterly.git",
        f"git -C /opt/posterly fetch --depth 1 origin {POSTERLY_SOURCE_COMMIT} && git -C /opt/posterly checkout --detach FETCH_HEAD",
        f'test "$(git -C /opt/posterly rev-parse HEAD)" = "{POSTERLY_SOURCE_COMMIT}"',
        "python -m playwright install --with-deps chromium",
        f"python -m playwright install --dry-run chromium | grep -F 'chromium-{POSTERLY_CHROMIUM_REVISION}'",
        "chmod -R a-w,a+rX /opt/posterly",
        "test -r /opt/posterly/LICENSE && test -r /opt/posterly/NOTICE.md && test -r /opt/posterly/SKILL.md",
    )
    .run_commands(
        "mkdir -p /opt/pwc",
        f"curl -fsSLo /opt/pwc/install-pwc.py https://raw.githubusercontent.com/huggingface/pwc-cli/{PWC_CLI_SOURCE_COMMIT}/standalone_cli/install.py",
        f"echo '{PWC_CLI_INSTALLER_SHA256}  /opt/pwc/install-pwc.py' | sha256sum -c -",
        "groupadd --system pwc-broker && useradd --system --gid pwc-broker --home-dir /var/empty/pwc-broker pwc-broker",
        "groupadd --system pwc-chat && useradd --system --gid pwc-chat --create-home --home-dir /home/pwc-chat pwc-chat",
        "mkdir -p /opt/pwc/backend/chat_sandbox_worker /workspace /home/pwc-chat/.claude /var/empty/pwc-broker",
        "chown -R pwc-chat:pwc-chat /workspace /home/pwc-chat",
        "chown pwc-broker:pwc-broker /var/empty/pwc-broker",
        "chmod 0755 /opt/pwc /opt/pwc/backend /opt/pwc/backend/chat_sandbox_worker",
        "chmod 0700 /workspace /home/pwc-chat /home/pwc-chat/.claude /var/empty/pwc-broker",
    )
    .add_local_file(BACKEND / "__init__.py", "/opt/pwc/backend/__init__.py", copy=True)
    .add_local_file(
        BACKEND / "chat_execution_policy.py",
        "/opt/pwc/backend/chat_execution_policy.py",
        copy=True,
    )
    .add_local_dir(
        WORKER,
        "/opt/pwc/backend/chat_sandbox_worker",
        copy=True,
        ignore=lambda path: (
            path.name
            in {
                "image.py",
                "publish_image.py",
                "__pycache__",
                "node_modules",
                "dist",
            }
        ),
    )
    .add_local_file(WORKER / "PWC_CLI_SKILL.md", "/opt/pwc/PWC_CLI_SKILL.md", copy=True)
    .add_local_file(WORKER / "HF_CLI_SKILL.md", "/opt/pwc/HF_CLI_SKILL.md", copy=True)
    .add_local_file(WORKER / "S2_CLI_SKILL.md", "/opt/pwc/S2_CLI_SKILL.md", copy=True)
    .add_local_file(WORKER / "artifact_cli.py", "/opt/pwc/artifact_cli.py", copy=True)
    .add_local_file(WORKER / "paper_cli.py", "/opt/pwc/paper_cli.py", copy=True)
    .add_local_file(
        WORKER / "PAPER_AUTHORING.md", "/opt/pwc/PAPER_AUTHORING.md", copy=True
    )
    .add_local_file(
        WORKER / "POSTERLY_PUBLISH.md", "/opt/pwc/POSTERLY_PUBLISH.md", copy=True
    )
    .add_local_dir(S2_CLI, "/opt/pwc/s2_cli", copy=True)
    .add_local_dir(
        RESTRICTED_HF / "src" / "restricted_hf_cli",
        "/opt/pwc/restricted_hf_cli/restricted_hf_cli",
        copy=True,
    )
    .add_local_file(RESTRICTED_HF / "bin" / "hf", "/opt/pwc/restricted-hf", copy=True)
    .run_commands(
        "chmod -R a+rX /opt/pwc/backend",
        "cd /opt/pwc/backend/chat_sandbox_worker/pi_worker && npm ci --ignore-scripts && npm run build && npm prune --omit=dev --ignore-scripts",
        f"node -e \"const p=require('/opt/pwc/backend/chat_sandbox_worker/pi_worker/node_modules/@earendil-works/pi-coding-agent/package.json'); if(p.version !== '{PI_VERSION}') process.exit(1)\"",
        f"node -e \"const p=require('/opt/pwc/backend/chat_sandbox_worker/pi_worker/node_modules/pi-mcp-adapter/package.json'); if(p.version !== '{PI_MCP_ADAPTER_VERSION}') process.exit(1)\"",
        "PYTHONPATH=/opt/pwc python -m backend.chat_sandbox_worker.render_pi_prompt_asset /opt/pwc/pi-system-prompt.txt",
        "chmod 0644 /opt/pwc/pi-system-prompt.txt",
        "chmod -R a+rX /opt/pwc/restricted_hf_cli",
        "chmod 0644 /opt/pwc/PWC_CLI_SKILL.md /opt/pwc/install-pwc.py",
        "chmod 0644 /opt/pwc/HF_CLI_SKILL.md",
        "chmod 0644 /opt/pwc/S2_CLI_SKILL.md",
        "chmod 0755 /opt/pwc/artifact_cli.py && ln -s /opt/pwc/artifact_cli.py /usr/local/bin/pwc-artifact",
        "chmod 0755 /opt/pwc/paper_cli.py && ln -s /opt/pwc/paper_cli.py /usr/local/bin/pwc-paper",
        "chmod 0644 /opt/pwc/PAPER_AUTHORING.md",
        "chmod 0644 /opt/pwc/POSTERLY_PUBLISH.md",
        "python -m pip install --no-deps /opt/pwc/s2_cli",
        "chmod 0755 /opt/pwc/restricted-hf && ln -s /opt/pwc/restricted-hf /usr/local/bin/hf",
        "PYTHONPATH=/opt/pwc python -c 'import backend.chat_execution_policy'",
        "PYTHONPATH=/opt/pwc python -c \"import backend.chat_sandbox_worker.executor_daemon; import backend.chat_sandbox_worker.executor_relay; from backend.chat_sandbox_worker.executor_daemon import DEFAULT_EXECUTOR_PIDS_MAX, EXECUTOR_USER; assert EXECUTOR_USER == 'pwc-chat' and DEFAULT_EXECUTOR_PIDS_MAX == 64\"",
        "PYTHONPATH=/opt/pwc python -c \"from pathlib import Path; from backend.chat_sandbox_worker.contract import RESTRICTED_HF_CLI_SHA256, restricted_hf_cli_digest; assert restricted_hf_cli_digest(Path('/opt/pwc/restricted_hf_cli/restricted_hf_cli'), Path('/opt/pwc/restricted-hf')) == RESTRICTED_HF_CLI_SHA256\"",
        "PYTHONPATH=/opt/pwc python -c \"from pathlib import Path; import hashlib; from backend.chat_sandbox_worker.contract import HF_CLI_SKILL_SHA256; assert hashlib.sha256(Path('/opt/pwc/HF_CLI_SKILL.md').read_bytes()).hexdigest() == HF_CLI_SKILL_SHA256\"",
        f"python /opt/pwc/install-pwc.py --version {PWC_CLI_VERSION} --prefix /usr/local",
        f"pwc version | grep -F 'pwc {PWC_CLI_VERSION}'",
        "pwc --help >/dev/null",
        "pwc paper --help >/dev/null",
        "pwc paper list --help | grep -F -- '--author' >/dev/null",
        "pwc benchmark --help >/dev/null",
        "pwc benchmark --help | grep -F -- '--max-parameters' >/dev/null",
        "pwc benchmark list --help >/dev/null",
        "S2_API_KEY=sandbox-gateway S2_API_URL=http://127.0.0.1:8765/semantic-scholar/graph/v1 s2 version",
        "runuser -u pwc-chat -- hf --help >/dev/null",
        "runuser -u pwc-chat -- hf collections --help >/dev/null",
        "runuser -u pwc-chat -- hf datasets card --help >/dev/null",
        "runuser -u pwc-chat -- hf datasets list --help >/dev/null",
        "runuser -u pwc-chat -- hf models card --help >/dev/null",
        "runuser -u pwc-chat -- hf models list --help >/dev/null",
        "runuser -u pwc-chat -- hf spaces card --help >/dev/null",
        "runuser -u pwc-chat -- hf spaces list --help >/dev/null",
        f"runuser -u pwc-chat -- hf version | grep -F '{RESTRICTED_HF_CLI_VERSION}' >/dev/null",
        'test "$(runuser -u pwc-chat -- hf auth --help >/dev/null 2>&1; echo $?)" = 2',
        'test "$(runuser -u pwc-chat -- hf upload owner/repo file >/dev/null 2>&1; echo $?)" = 2',
        "runuser -u pwc-chat -- test -r /opt/posterly/SKILL.md",
        "runuser -u pwc-chat -- pwc-artifact --help >/dev/null",
        "runuser -u pwc-chat -- pwc-paper --help >/dev/null",
        "runuser -u pwc-chat -- pwc-paper draft --help >/dev/null",
    )
    .env(
        {
            "PYTHONPATH": "/opt/pwc",
            "PWC_CHAT_MAX_TURNS": "8",
            "PWC_CHAT_SHOW_REASONING": "false",
            "PWC_CHAT_MAX_TOOL_CALLS": "12",
            "PWC_CHAT_MAX_DIRECT_SEARCH_CALLS": "4",
            "PWC_CHAT_MAX_WEB_SEARCH_CALLS": "3",
            "PWC_CHAT_TOOL_RESULT_MAX_BYTES": "24576",
            "PWC_CHAT_TURN_TOOL_OUTPUT_MAX_BYTES": "98304",
            "PWC_CHAT_BASH_TIMEOUT_SECONDS": "30",
            "PWC_CHAT_EXCALIDRAW_ENABLED": "false",
            "PWC_CHAT_MCP_APPS_HOST_ENABLED": "false",
            "PWC_CHAT_AGENT_TIMEOUT_SECONDS": "180",
            "PWC_CHAT_POSTERLY_TIMEOUT_SECONDS": "600",
            "PWC_CHAT_POSTERLY_MAX_TOOL_ROUNDS": "20",
            "PWC_CHAT_POSTERLY_MAX_TOOL_CALLS": "40",
            "PWC_CHAT_POSTERLY_TOOL_RESULT_MAX_BYTES": "196608",
            "PWC_CHAT_POSTERLY_TURN_TOOL_OUTPUT_MAX_BYTES": "1048576",
            "PWC_CHAT_LATEX_PAPER_TIMEOUT_SECONDS": "600",
            "PWC_CHAT_LATEX_PAPER_MAX_TOOL_ROUNDS": "12",
            "PWC_CHAT_LATEX_PAPER_MAX_TOOL_CALLS": "30",
            "PWC_CHAT_LATEX_PAPER_MAX_DIRECT_SEARCH_CALLS": "8",
            "PWC_CHAT_SANDBOX_PIDS_MAX": "64",
            "S2_API_KEY": "sandbox-gateway",
            "S2_API_URL": "http://127.0.0.1:8765/semantic-scholar/graph/v1",
        }
    )
)


def with_executor_binary(base_image: modal.Image, binary: Path) -> modal.Image:
    """Add the locally locked release artifact; never build inside a sandbox."""
    if not binary.is_file():
        raise FileNotFoundError("Pinned executor environment binary is unavailable")
    return base_image.add_local_file(
        binary,
        "/usr/local/bin/pwc-executor-environment",
        copy=True,
    ).run_commands(
        "chmod 0755 /usr/local/bin/pwc-executor-environment",
        "/usr/local/bin/pwc-executor-environment --self-test >/dev/null",
    )
