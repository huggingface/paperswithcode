"""Immutable public identifiers for one worker/image contract."""

WORKER_CONTRACT_VERSION = "1"
SDK_VERSION = "0.2.115"
PWC_CLI_VERSION = "0.1.1"
IMAGE_PUBLISH_NAME = "pwc-chat-v1"
BASE_IMAGE = (
    "python:3.12-slim-bookworm@"
    "sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b"
)
# Set this to the immutable ``im-...`` ID emitted by publish_image.py in the
# follow-up bridge commit. An unpublished source revision must not deploy.
MODAL_IMAGE_ID = ""
DEFAULT_BACKEND = "local_mcp"
NEW_CHAT_MODAL_PERCENTAGE = 0
