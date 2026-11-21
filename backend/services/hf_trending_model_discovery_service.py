"""Discover globally trending Hugging Face models through huggingface_hub."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi

from backend.database.organizations_setup.organizations import featured_for_hf_handle


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
_TRENDING_EXPAND = ["author", "tags", "createdAt", "lastModified", "trendingScore"]


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


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
    def __init__(self, *, api: HfApi | None = None) -> None:
        self.api = api or HfApi()

    def list_top_models(
        self, *, limit: int = 50, featured_limit: int = 100
    ) -> list[HFTrendingModel]:
        """Return the global top `limit`, plus featured publishers up to `featured_limit`."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        models = [
            HFTrendingModel.from_payload(
                {
                    "id": info.id,
                    "author": info.author,
                    "tags": info.tags,
                    "trending_score": info.trending_score,
                    "created_at": _isoformat(info.created_at),
                    "last_modified": _isoformat(info.last_modified),
                }
            )
            for info in self.api.list_models(
                sort="trending_score",
                limit=max(limit, featured_limit),
                expand=_TRENDING_EXPAND,
            )
        ]
        return models[:limit] + [
            model for model in models[limit:] if model.featured_publisher
        ]


@dataclass(frozen=True)
class HFModelCardSnapshot:
    repo_revision: str
    readme_sha: str
    markdown: str


class HFModelCardClient:
    def __init__(self, *, api: HfApi | None = None) -> None:
        self.api = api or HfApi()

    def snapshot(self, repo_id: str) -> HFModelCardSnapshot:
        revision = str(self.api.model_info(repo_id, expand=["sha"]).sha or "")
        if not revision:
            raise ValueError(f"Hugging Face model {repo_id} has no revision")
        path = Path(self.api.hf_hub_download(repo_id, "README.md", revision=revision))
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
