"""Discover globally trending Hugging Face models through the installed CLI."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.database.organizations_setup.organizations import featured_for_hf_handle


CommandRunner = Callable[[list[str]], str]
_CONVERSION_SUFFIXES = (
    "-gguf",
    "-awq",
    "-gptq",
    "-mlx",
    "-fp8",
    "-int8",
    "-int4",
    "-nvfp4",
    "-w4a16",
    "-w8a16",
)


def _run(command: list[str]) -> str:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.stdout


def _hf_cli() -> str:
    sibling = Path(sys.executable).with_name("hf")
    if sibling.is_file() and os.access(sibling, os.X_OK):
        return str(sibling)
    return shutil.which("hf") or "hf"


@dataclass(frozen=True)
class HFTrendingModel:
    repo_id: str
    author: str
    tags: tuple[str, ...]
    trending_score: float
    created_at: str | None = None
    last_modified: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "HFTrendingModel":
        repo_id = str(payload["id"])
        author = str(payload.get("author") or repo_id.partition("/")[0])
        return cls(
            repo_id=repo_id,
            author=author,
            tags=tuple(str(tag) for tag in payload.get("tags") or ()),
            trending_score=float(payload.get("trending_score") or 0),
            created_at=payload.get("created_at"),
            last_modified=payload.get("last_modified"),
        )

    @property
    def featured_publisher(self) -> bool:
        return featured_for_hf_handle(self.author) is not None


class HFTrendingDiscoveryClient:
    def __init__(self, *, run: CommandRunner = _run, hf_cli: str | None = None) -> None:
        self.run = run
        self.hf_cli = hf_cli or _hf_cli()

    def list_top_models(self, *, limit: int = 50) -> list[HFTrendingModel]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        output = self.run(
            [
                self.hf_cli,
                "models",
                "list",
                "--sort",
                "trending_score",
                "--limit",
                str(limit),
                "--expand",
                "author,tags,createdAt,lastModified,trendingScore",
                "--format",
                "json",
            ]
        )
        payload = json.loads(output)
        if not isinstance(payload, list):
            raise ValueError("hf models list did not return a JSON array")
        return [HFTrendingModel.from_payload(item) for item in payload]


@dataclass(frozen=True)
class HFModelCardSnapshot:
    repo_revision: str
    readme_sha: str
    markdown: str


class HFModelCardClient:
    def __init__(self, *, run: CommandRunner = _run, hf_cli: str | None = None) -> None:
        self.run = run
        self.hf_cli = hf_cli or _hf_cli()

    def snapshot(self, repo_id: str) -> HFModelCardSnapshot:
        info = json.loads(
            self.run(
                [
                    self.hf_cli,
                    "models",
                    "info",
                    repo_id,
                    "--expand",
                    "sha",
                    "--format",
                    "json",
                ]
            )
        )
        revision = str(info.get("sha") or "")
        if not revision:
            raise ValueError(f"Hugging Face model {repo_id} has no revision")
        path = Path(
            self.run(
                [
                    self.hf_cli,
                    "download",
                    repo_id,
                    "README.md",
                    "--revision",
                    revision,
                    "--quiet",
                ]
            ).strip()
        )
        markdown = path.read_text(encoding="utf-8")
        return HFModelCardSnapshot(
            repo_revision=revision,
            readme_sha=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            markdown=markdown,
        )


def is_obvious_conversion(model: HFTrendingModel) -> bool:
    """Reject only deterministic repackaging; semantic derivatives go to the LLM."""
    tags = {tag.lower() for tag in model.tags}
    if any(tag.startswith("base_model:quantized:") for tag in tags):
        return True
    name = model.repo_id.rsplit("/", 1)[-1].lower()
    return name.endswith(_CONVERSION_SUFFIXES)


def should_requeue_card(*, previous_sha: str | None, current_sha: str) -> bool:
    if not current_sha:
        raise ValueError("current_sha is required")
    return previous_sha != current_sha
