"""Immutable public identifiers for one worker/image contract."""

import hashlib
from pathlib import Path

# Application-owned paper pagination in the Pi MCP tools.
WORKER_CONTRACT_VERSION = "111"
# Web search extends the catalog operation set without changing its request or
# response framing, so it remains on the rollback-compatible gateway protocol.
GATEWAY_CONTRACT_VERSION = 30
GATEWAY_COMPATIBLE_FROM = 29
DIRECT_OPENAI_ENABLED = True
DATABASE_CONTRACT_VERSION = 2
SDK_VERSION = "0.2.115"
PI_VERSION = "1.0.0"
PI_SOURCE_COMMIT = "a13d35a742c6ef8462812a28fbe1d8c8b7431c32"
PI_NPM_INTEGRITY = (
    "sha512-/FtbxoSQU/mEv1QnichJjRjqteqaIaMWxmhB4G367+MwZfX7/DI5B9YAg5lqbN7n"
    "ztFskBEtUSZ+FlmMBECtMw=="
)
PI_NODE_VERSION = "22.19.0"
PI_NODE_SHA256 = "c0649af18e6a24f6fe5535a3e86b341dd49a8e71117c8b68bde973ef834f16f2"
SUPPORTED_AGENT_HARNESSES = ("claude", "pi")
DEFAULT_AGENT_HARNESS = "pi"
NEW_SESSION_PI_PERCENTAGE = 100
PWC_CLI_VERSION = "0.3.0"
PWC_CLI_SOURCE_COMMIT = "231d196f6add49d011e1694a7e4fdcd3c12bf2d7"
PWC_CLI_INSTALLER_SHA256 = (
    "c8e6e9ec67eb5ac0fe4a56e9f62b86b28a9d1a15e8f7b6d1cf90761f5540cc25"
)
RESTRICTED_HF_CLI_VERSION = "0.1.0"
RESTRICTED_HF_CLI_SHA256 = (
    "4151cd20e415958e6ef7b3d15a21d1837feb9867ecbea7e079a09dadef56f4bc"
)
HF_CLI_SKILL_SHA256 = "e338475ea00f23d7c3a700b07226079120e19334e13c977a1c09c166f03ba1fe"
MODAL_APP_NAME = "pwc-chat-sandbox-v1"
IMAGE_PUBLISH_NAME = "pwc-chat-v1"
CHAT_SANDBOX_REGION = "eu-west"
CONTROL_PORT = 8080
PROVIDER_OUTPUT_TOKEN_LIMIT = 8_000
BASE_IMAGE = (
    "python:3.12-slim-bookworm@"
    "sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b"
)
# Immutable image emitted by publish_image.py for the selected worker contract.
MODAL_IMAGE_ID = "im-lRyXnxyanLvf8oHWNOStt2"
# Production uses a distinct immutable image because Modal image IDs are scoped
# to their environment. It must be published by the restricted production
# service identity.
# Includes the fenced bootstrap deadline sent by the current executor client.
PRODUCTION_MODAL_IMAGE_ID = "im-LqrG84SxmXoOrwZUsWQdUY"
DEFAULT_BACKEND = "modal_cli"
NEW_CHAT_MODAL_PERCENTAGE = 100
POSTERLY_SOURCE_COMMIT = "b9f42e5578a49a27525a68f85376bb3bb25af86f"
POSTERLY_SOURCE_URL = (
    f"https://github.com/Chenruishuo/posterly/tree/{POSTERLY_SOURCE_COMMIT}"
)
POSTERLY_LICENSE = "AGPL-3.0-only"
POSTERLY_PLAYWRIGHT_VERSION = "1.62.0"
POSTERLY_CHROMIUM_REVISION = "1234"
POSTERLY_ENABLED = False


def restricted_hf_cli_digest(package_root: Path, wrapper: Path) -> str:
    """Digest the exact restricted CLI sources copied into the worker image."""
    digest = hashlib.sha256()
    files = [
        (f"src/restricted_hf_cli/{path.name}", path)
        for path in package_root.glob("*.py")
    ]
    files.append(("bin/hf", wrapper))
    for relative, path in sorted(files):
        digest.update(relative.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()
