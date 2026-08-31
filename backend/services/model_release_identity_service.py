"""Resolve provider model labels onto canonical model-release rows."""

from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.models.database import (
    HfArtifact,
    ModelProviderAlias,
    ModelRelease,
    ModelReleaseArtifact,
)


def _identity_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _chunks(values: list, size: int) -> Iterable[list]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def _suffix_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%/{escaped}"


class ModelReleaseIdentityService:
    def __init__(self, db: Session):
        self.db = db

    def resolve(
        self, provider: str, alias: str, *, name: str | None = None
    ) -> ModelRelease | None:
        return self.resolve_many(provider, [(alias, name)]).get(alias)

    def resolve_many(
        self,
        provider: str,
        models: list[tuple[str, str | None]],
        *,
        batch_size: int = 100,
    ) -> dict[str, ModelRelease]:
        """Resolve an upstream page in bounded batches and persist exact aliases."""
        if not 1 <= batch_size <= 200:
            raise ValueError("batch_size must be between 1 and 200")
        resolved: dict[str, ModelRelease] = {}
        unique_models = list(dict.fromkeys(models))
        for batch in _chunks(unique_models, batch_size):
            aliases = [alias for alias, _name in batch]
            direct_rows = (
                self.db.query(ModelProviderAlias, ModelRelease)
                .join(
                    ModelRelease,
                    ModelRelease.id == ModelProviderAlias.model_release_id,
                )
                .filter(
                    ModelProviderAlias.provider == provider,
                    ModelProviderAlias.alias.in_(aliases),
                )
                .limit(batch_size)
                .all()
            )
            for provider_alias, release in direct_rows:
                if release.paper_id is not None:
                    resolved[provider_alias.alias] = release

            pending = [item for item in batch if item[0] not in resolved]
            if not pending:
                continue
            raw_names = {
                value.casefold()
                for alias, name in pending
                for value in (alias, name or "")
                if value
            }
            canonical_rows = (
                self.db.query(ModelRelease)
                .filter(
                    ModelRelease.paper_id.isnot(None),
                    func.lower(ModelRelease.canonical_name).in_(raw_names),
                )
                .limit(batch_size * 4)
                .all()
            )
            variants = {
                value
                for alias, name in pending
                for value in (
                    alias,
                    name or "",
                    (name or "").replace(" ", "-"),
                )
                if value
            }
            artifact_rows = (
                self.db.query(ModelRelease, HfArtifact)
                .join(
                    ModelReleaseArtifact,
                    ModelReleaseArtifact.model_release_id == ModelRelease.id,
                )
                .join(
                    HfArtifact,
                    HfArtifact.id == ModelReleaseArtifact.hf_artifact_id,
                )
                .filter(
                    ModelRelease.paper_id.isnot(None),
                    HfArtifact.kind == "model",
                    or_(
                        *[
                            HfArtifact.repo_id.ilike(
                                _suffix_pattern(variant), escape="\\"
                            )
                            for variant in sorted(variants)
                        ]
                    ),
                )
                .limit(batch_size * 10)
                .all()
            )
            releases = {release.id: release for release in canonical_rows}
            artifact_keys: dict[int, set[str]] = {}
            for release, artifact in artifact_rows:
                releases[release.id] = release
                artifact_keys.setdefault(release.id, set()).add(
                    _identity_key(artifact.repo_id.rsplit("/", 1)[-1])
                )

            for alias, name in pending:
                keys = {_identity_key(alias)}
                if name:
                    keys.add(_identity_key(name))
                matches = []
                for release in releases.values():
                    release_keys = {_identity_key(release.canonical_name)}
                    release_keys.update(
                        _identity_key(item) for item in (release.aliases or [])
                    )
                    release_keys.update(artifact_keys.get(release.id, set()))
                    if keys & release_keys:
                        matches.append(release)
                if len(matches) != 1:
                    continue
                release = matches[0]
                self.db.add(
                    ModelProviderAlias(
                        model_release_id=release.id,
                        provider=provider,
                        alias=alias,
                    )
                )
                resolved[alias] = release
        self.db.flush()
        return resolved
