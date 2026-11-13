"""Match new leaderboard model names to papers, or hand them to the radar.

Leaderboard syncs keep a reviewed name -> paper map. A name outside that map
is matched automatically when the catalog names it unambiguously: a canonical
model release (or one of its aliases or Hub repositories), else exactly one
latest paper whose title announces the model. A name that still has no paper
becomes a `model_release_signals` row. `scan_model_releases` queues its
guarded `resolve-model-paper` job, which links or creates the paper; a new
external paper then gets enrich-paper -> add-evals, and the next sync run
matches the name through the model release the resolution records. Syncs
themselves never create papers.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from backend.models.database import (
    HfArtifact,
    ModelProviderAlias,
    ModelRelease,
    ModelReleaseSignal,
    PaperHfArtifact,
)
from backend.services.model_release_identity_service import (
    ModelReleaseIdentityService,
    announcing_paper_id,
)
from backend.services.model_release_signal_service import signal_key


@dataclass(frozen=True)
class LeaderboardModel:
    name: str
    lab: str


@dataclass(frozen=True)
class MatchedModel:
    paper_id: int
    model_name: str
    is_open: bool
    hf_model_url: str | None = None


# Reasoning-effort settings: "GPT-6 Sol (max)", "DeepSeek V4.1 Flash (xhigh)".
_EFFORT_SUFFIX = re.compile(
    r"\s*\((?:max|xhigh|high|medium|low|minimal)\)\s*$", re.IGNORECASE
)


# Model families whose name alone identifies the lab, for boards that list
# bare model names. A name outside these families reports no signal.
_FAMILY_LABS = (
    (re.compile(r"(?:claude|opus|sonnet|haiku)\b", re.I), "Anthropic"),
    (re.compile(r"(?:gpt|chatgpt|codex)\b|o\d+(?:\b|-)", re.I), "OpenAI"),
    (re.compile(r"(?:gemini|gemma)\b", re.I), "Google DeepMind"),
    (re.compile(r"grok\b", re.I), "xAI"),
    (re.compile(r"(?:qwen|qwq)", re.I), "Alibaba"),
    (re.compile(r"deepseek\b", re.I), "DeepSeek"),
    (re.compile(r"kimi\b", re.I), "Moonshot AI"),
    (re.compile(r"glm\b", re.I), "Z.ai"),
    (re.compile(r"minimax\b", re.I), "MiniMax"),
    (re.compile(r"(?:mistral|magistral|devstral|codestral)\b", re.I), "Mistral AI"),
    (re.compile(r"llama\b", re.I), "Meta"),
    (re.compile(r"amazon nova\b", re.I), "Amazon"),
    (re.compile(r"(?:hunyuan|hy\d)", re.I), "Tencent"),
    (re.compile(r"ernie\b", re.I), "Baidu"),
    (re.compile(r"(?:doubao|seed)\b", re.I), "ByteDance"),
    (re.compile(r"longcat\b", re.I), "Meituan"),
    (re.compile(r"nemotron\b", re.I), "NVIDIA"),
    (re.compile(r"mimo\b", re.I), "Xiaomi"),
)


def family_lab(model_name: str) -> str:
    """The lab a bare model name belongs to, or "" when it is not obvious."""
    name = model_name.strip()
    return next((lab for pattern, lab in _FAMILY_LABS if pattern.match(name)), "")


_VENDORS = {
    "alibaba",
    "amazon",
    "anthropic",
    "deepseek",
    "google",
    "meta",
    "microsoft",
    "mistral",
    "moonshot",
    "nvidia",
    "openai",
    "xai",
}
_SETTINGS = re.compile(r"\s*\([^()]*\)\s*$")


_HF_SECTIONS = {"blog", "datasets", "models", "spaces"}


def link_owner(url: str) -> str | None:
    """The Hub or GitHub account a model link belongs to.

    "" for a Hub paper page, which names no publisher; None for any other
    host, so callers decide whether that host is a publisher.
    """
    parsed = urlsplit(url)
    host = parsed.netloc.lower().removeprefix("www.")
    parts = [part for part in parsed.path.split("/") if part]
    if host not in {"huggingface.co", "github.com"}:
        return None
    if host == "huggingface.co" and parts and parts[0] == "papers":
        return ""
    if host == "huggingface.co" and parts and parts[0] in _HF_SECTIONS:
        parts = parts[1:]
    return parts[0] if parts else ""


def vendor_label_model(label: str, lab: str = "") -> LeaderboardModel:
    """The model a vendor-prefixed board label names.

    "OpenAI GPT-6.1 Sol (Reasoning Low)" is GPT-6.1 Sol by OpenAI, so every
    setting of one model matches, and reaches the radar, as one model.
    """
    name = _SETTINGS.sub("", label).strip() or label
    vendor, _, rest = name.partition(" ")
    if rest and vendor.casefold() in _VENDORS:
        # A known family's canonical lab wins, so "Google Gemini ..." and a
        # bare "Gemini ..." from another board share one radar signal.
        lab, name = lab or family_lab(rest) or vendor, rest
    return LeaderboardModel(name, lab or family_lab(name) or vendor)


def _identity_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


class LeaderboardModelMatcher:
    def __init__(
        self,
        db: Session,
        *,
        provider: str,
        leaderboard_name: str,
        leaderboard_url: str,
    ) -> None:
        self.db = db
        self.provider = provider
        self.leaderboard_name = leaderboard_name
        self.leaderboard_url = leaderboard_url

    def match(self, models: list[LeaderboardModel]) -> dict[str, MatchedModel]:
        """Map each unambiguously indexed model name to its paper."""
        names = list(dict.fromkeys(model.name for model in models))
        releases = ModelReleaseIdentityService(self.db).resolve_many(
            self.provider, [(name, name) for name in names]
        )
        releases.update(
            self._alias_matches([name for name in names if name not in releases])
        )
        # Rows keep the leaderboard's spelling, so a model matched by title
        # today and by its release later keeps one row.
        matched = {
            name: MatchedModel(release.paper_id, name, release.is_open)
            for name, release in releases.items()
        }
        for name in names:
            if name not in matched and (paper_id := announcing_paper_id(self.db, name)):
                # Open only when the paper links the model's own weights.
                hf_model_url = self._weights_url(paper_id, name)
                matched[name] = MatchedModel(
                    paper_id, name, hf_model_url is not None, hf_model_url
                )
        # An effort setting names the same model; its rows share the base
        # name, so the board keeps that model's best setting.
        bases = {
            name: base
            for name in names
            if name not in matched and (base := _EFFORT_SUFFIX.sub("", name)) != name
        }
        if bases:
            base_matches = self.match(
                [LeaderboardModel(base, "") for base in bases.values()]
            )
            for name, base in bases.items():
                if (match := base_matches.get(base)) is not None:
                    matched[name] = match
        return matched

    def _alias_matches(self, names: list[str]) -> dict[str, ModelRelease]:
        """Match names to exactly one release by canonical name or alias.

        A resolve-model-paper job records the leaderboard spelling as an
        alias, whatever canonical spelling it chooses.
        """
        keys = {_identity_key(name): name for name in names}
        if not keys:
            return {}
        candidates: dict[str, dict[int, ModelRelease]] = {}
        releases = (
            self.db.query(ModelRelease)
            .filter(ModelRelease.paper_id.isnot(None))
            .order_by(ModelRelease.id)
            .yield_per(200)
        )
        for release in releases:
            for identity in (release.canonical_name, *(release.aliases or [])):
                if (name := keys.get(_identity_key(identity))) is not None:
                    candidates.setdefault(name, {})[release.id] = release
        matched: dict[str, ModelRelease] = {}
        for name, found in candidates.items():
            if len(found) == 1:
                release = next(iter(found.values()))
                self.db.add(
                    ModelProviderAlias(
                        model_release_id=release.id,
                        provider=self.provider,
                        alias=name,
                    )
                )
                matched[name] = release
        self.db.flush()
        return matched

    def _weights_url(self, paper_id: int, model_name: str) -> str | None:
        artifacts = (
            self.db.query(HfArtifact.repo_id, HfArtifact.url)
            .join(PaperHfArtifact, PaperHfArtifact.hf_artifact_id == HfArtifact.id)
            .filter(PaperHfArtifact.paper_id == paper_id, HfArtifact.kind == "model")
            .order_by(HfArtifact.repo_id)
            .all()
        )
        key = _identity_key(model_name)
        for repo_id, url in artifacts:
            if _identity_key(repo_id.rsplit("/", 1)[-1]) == key:
                return url
        return None

    def report_unmatched(
        self, models: list[LeaderboardModel], *, now: datetime | None = None
    ) -> list[str]:
        """Record a release signal per unmatched model; returns the names."""
        now = now or datetime.now(UTC)
        reported: list[str] = []
        for model in dict.fromkeys(models):
            lab = model.lab.strip() or family_lab(model.name)
            if not lab:
                continue
            key = signal_key(lab, model.name)
            row = (
                self.db.query(ModelReleaseSignal)
                .filter(ModelReleaseSignal.signal_key == key)
                .one_or_none()
            )
            if row is None:
                self.db.add(
                    ModelReleaseSignal(
                        id=uuid.uuid4(),
                        signal_key=key,
                        lab=lab,
                        model_name=model.name,
                        title=f"{model.name} on the {self.leaderboard_name} leaderboard",
                        lead_url=self.leaderboard_url,
                        source=self.leaderboard_url,
                        lead_is_official=False,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
            else:
                row.sightings += 1
                row.last_seen_at = now
            reported.append(model.name)
        self.db.flush()
        return reported
