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
    Paper,
)

# Provider labels end in a settings suffix: "Claude Opus 5.5 (Max, Default Fallback)".
_SETTINGS_SUFFIX = re.compile(r"\s*\([^()]*\)\s*$")
# Release pages are titled "<name>", "Introducing <name>" or "<name>: <subtitle>".
_HEADLINE_VERBS = ("", "introducing ", "announcing ", "meet ")
_LEAD_VERB = re.compile(r"^(?:introducing|announcing|meet)\s+", re.IGNORECASE)


def _identity_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _sql_identity_key(column):
    return func.regexp_replace(func.lower(column), "[^a-z0-9]+", "", "g")


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
            # Compare normalized keys, so "gemini-4-carbon" finds "Gemini 4 Carbon".
            name_keys = {
                _identity_key(value)
                for alias, name in pending
                for value in (alias, name or "")
                if value
            }
            canonical_rows = (
                self.db.query(ModelRelease)
                .filter(
                    ModelRelease.paper_id.isnot(None),
                    _sql_identity_key(ModelRelease.canonical_name).in_(name_keys),
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

    def bind_release_pages(
        self,
        provider: str,
        models: list[tuple[str, str]],
    ) -> dict[str, ModelRelease]:
        """Bind provider slugs to the one catalog paper that announces the model.

        Only a slug that spells the model name binds ("claude-opus-5-5" for
        "Claude Opus 5.5 (Max)"); settings variants such as "-xhigh" stay
        unbound, so a leaderboard keeps one row per model. The paper must be the
        only latest paper titled "<name>", "Introducing <name>" (or another
        launch verb), or an external "<name>: <subtitle>" release page.
        """
        bound: dict[str, ModelRelease] = {}
        for batch in _chunks(list(dict.fromkeys(models)), 100):
            bound.update(self._bind_release_page_batch(provider, batch))
        return bound

    def _bind_release_page_batch(
        self, provider: str, models: list[tuple[str, str]]
    ) -> dict[str, ModelRelease]:
        bases: dict[str, str] = {}
        for alias, name in models:
            base = _SETTINGS_SUFFIX.sub("", name).strip()
            if base and _identity_key(alias) == _identity_key(base):
                bases[alias] = base
        if not bases:
            return {}
        taken = {
            alias
            for (alias,) in self.db.query(ModelProviderAlias.alias)
            .filter(
                ModelProviderAlias.provider == provider,
                ModelProviderAlias.alias.in_(sorted(bases)),
            )
            .limit(len(bases))
            .all()
        }
        bases = {alias: base for alias, base in bases.items() if alias not in taken}
        if not bases:
            return {}
        names = sorted({base.casefold() for base in bases.values()})
        headlines = sorted(
            {f"{verb}{name}" for name in names for verb in _HEADLINE_VERBS}
        )
        papers_by_key: dict[str, set[int]] = {}
        for paper_id, title in (
            self.db.query(Paper.id, Paper.title)
            .filter(
                Paper.is_latest_version,
                or_(
                    func.lower(Paper.title).in_(headlines),
                    (Paper.source == "external")
                    & or_(
                        *(
                            func.lower(Paper.title).like(
                                f"{_escape_like(headline)}:%", escape="\\"
                            )
                            for headline in headlines
                        )
                    ),
                ),
            )
            .limit(len(headlines) * 4)
            .all()
        ):
            name = _LEAD_VERB.sub("", title.strip()).split(":", 1)[0]
            papers_by_key.setdefault(_identity_key(name), set()).add(paper_id)

        bound: dict[str, ModelRelease] = {}
        for alias, base in bases.items():
            paper_ids = papers_by_key.get(_identity_key(base), set())
            if len(paper_ids) != 1:
                continue
            paper_id = next(iter(paper_ids))
            release = (
                self.db.query(ModelRelease)
                .filter(
                    ModelRelease.paper_id == paper_id,
                    ModelRelease.canonical_name == base,
                )
                .one_or_none()
            )
            if release is None:
                release = ModelRelease(
                    paper_id=paper_id, canonical_name=base, aliases=[]
                )
                self.db.add(release)
                self.db.flush()
            self.db.add(
                ModelProviderAlias(
                    model_release_id=release.id, provider=provider, alias=alias
                )
            )
            bound[alias] = release
        self.db.flush()
        return bound
