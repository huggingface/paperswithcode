"""Resolve provider model labels onto canonical model-release rows."""

from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import exists, func, or_
from sqlalchemy.orm import Session

from backend.models.database import (
    Evaluation,
    HfArtifact,
    ModelProviderAlias,
    ModelRelease,
    ModelReleaseArtifact,
    Paper,
)

# Provider labels end in a settings suffix: "Claude Opus 5.5 (Max, Default Fallback)".
_SETTINGS_SUFFIX = re.compile(r"\s*\([^()]*\)\s*$")
# Release pages are titled "<name>", "Introducing <name> and <name>" or
# "<name>: <subtitle>".
_LEAD_VERB = re.compile(r"^(?:(?:introducing|announcing|meet) )?(?:the )?")
# Only a launch headline announces the later members of "<name> and <name>".
_LAUNCH_VERB = re.compile(r"(?:introducing|announcing|meet) ")
_HEADLINE_END = re.compile(r"\s*[:;(|]|\s+[-–—]\s")
_CONJUNCTION = re.compile(r"\s*,\s*(?:and\s+)?|\s*&\s*|\s+and\s+")
# Announcing papers fetched per name before ambiguity can no longer be ruled out.
TITLE_CANDIDATE_LIMIT = 50


def _identity_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _phrase(value: str) -> str:
    return re.sub(r"[\s_-]+", " ", value.casefold()).strip()


def _announced_names(title: str) -> set[str]:
    """The model names a headline announces, as phrases.

    "Introducing GPT-6 Sol and Luna" announces "gpt 6 sol" and "gpt 6 luna";
    "Introducing Claude Fable 5.2 and Claude Mythos 5.2" announces both models.
    """
    phrase = _phrase(title)
    launch = _LAUNCH_VERB.match(phrase) is not None
    headline = _HEADLINE_END.split(_LEAD_VERB.sub("", phrase), maxsplit=1)[0]
    parts = [part for part in _CONJUNCTION.split(headline) if part]
    if not parts:
        return set()
    first, *others = parts
    if not launch:
        # "Comparing GPT-6 Sol and Claude Opus 5.5" announces neither model.
        return {first}
    prefix = first.split()
    later = set()
    for other in others:
        # A later member may drop the shared family prefix ("Sol and Luna").
        later.update(" ".join([*prefix[:size], other]) for size in range(len(prefix)))
    # Later members name versioned models ("Claude Mythos 5.2"), not products
    # launched alongside them ("Claude 3.7 Sonnet and Claude Code").
    return {first} | {name for name in later if re.search(r"\d", name)}


def title_announces_model(title: str, model_name: str) -> bool:
    """Whether ``title`` is the model's own announcement.

    "Kimi K3.1 Pro: ...", "Introducing GPT-6.1 Terra" and "Introducing GPT-6
    Sol and Luna" announce those models; "Kimi K3.1 Pro: ..." does not announce
    "Kimi K3" or "Kimi K3.1", and "Evaluating GPT-6.1 Terra on ..." announces
    nothing.
    """
    return _phrase(model_name) in _announced_names(title)


def announcing_paper_id(db: Session, model_name: str) -> int | None:
    """The one latest paper whose title announces ``model_name``, if unambiguous."""
    tokens = re.findall(r"[a-z0-9]+", model_name.casefold())
    if not tokens:
        return None
    candidates = (
        db.query(Paper.id, Paper.title)
        .filter(
            Paper.is_latest_version,
            Paper.title.ilike(f"%{'%'.join(tokens)}%"),
            # A model's own paper reports results or records its release;
            # "KNN and ANN-based ..." or "GPT-4o: ... in piglets" do not.
            or_(
                exists().where(Evaluation.paper_id == Paper.id),
                exists().where(ModelRelease.paper_id == Paper.id),
            ),
        )
        .order_by(Paper.id)
        .limit(TITLE_CANDIDATE_LIMIT + 1)
        .all()
    )
    # Too many candidates to rule out a second announcement.
    if len(candidates) > TITLE_CANDIDATE_LIMIT:
        return None
    paper_ids = {
        paper_id
        for paper_id, title in candidates
        if title_announces_model(title, model_name)
    }
    return paper_ids.pop() if len(paper_ids) == 1 else None


def _sql_identity_key(column):
    return func.regexp_replace(func.lower(column), "[^a-z0-9]+", "", "g")


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
        only latest paper whose title announces the model (see
        ``title_announces_model``), including joint launches such as
        "Introducing Claude Fable 5.2 and Claude Mythos 5.2".
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
        bound: dict[str, ModelRelease] = {}
        for alias, base in bases.items():
            paper_id = announcing_paper_id(self.db, base)
            if paper_id is None:
                continue
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
