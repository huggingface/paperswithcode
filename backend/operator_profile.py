"""The hosted deployment's operator accounts, read from config/operator.toml.

Keeping every operator-owned account and resource in one checked-in file means
code never hardcodes a person's accounts, and a self-hosted deployment changes
one file. The deploy-tools bundle ships the file next to this module.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

PROFILE_PATH = Path(__file__).resolve().parents[1] / "config" / "operator.toml"


@dataclass(frozen=True)
class OperatorProfile:
    hf_namespace: str
    chat_artifact_bucket: str
    paper_page_assets_repo: str
    curator_image_repository: str
    chat_title_credential_owner: str
    modal_staging_workspace: str
    modal_staging_owner_username: str


def load(path: Path = PROFILE_PATH) -> OperatorProfile:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    huggingface = data["huggingface"]
    modal = data["modal"]
    return OperatorProfile(
        hf_namespace=huggingface["namespace"],
        chat_artifact_bucket=huggingface["chat_artifact_bucket"],
        paper_page_assets_repo=huggingface["paper_page_assets_repo"],
        curator_image_repository=huggingface["curator_image_repository"],
        chat_title_credential_owner=huggingface["chat_title_credential_owner"],
        modal_staging_workspace=modal["staging_workspace"],
        modal_staging_owner_username=modal["staging_owner_username"],
    )


OPERATOR = load()
