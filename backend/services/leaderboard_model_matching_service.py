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

from sqlalchemy.orm import Session

from backend.models.database import (
    HfArtifact,
    ModelProviderAlias,
    ModelRelease,
    ModelReleaseSignal,
    Paper,
    PaperHfArtifact,
)
from backend.services.model_release_identity_service import (
    ModelReleaseIdentityService,
)
from backend.services.model_release_signal_service import signal_key

TITLE_CANDIDATE_LIMIT = 50


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


def _identity_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _phrase(value: str) -> str:
    return re.sub(r"[\s_-]+", " ", value.casefold()).strip()


def title_announces_model(title: str, model_name: str) -> bool:
    """Whether ``title`` is the model's own announcement.

    "Kimi K3.1 Pro: ..." and "Introducing GPT-6.1 Terra" announce those
    models; "Kimi K3.1 Pro: ..." does not announce "Kimi K3" or "Kimi K3.1",
    and "Evaluating GPT-6.1 Terra on ..." announces nothing.
    """
    name = re.escape(_phrase(model_name))
    pattern = rf"(?:(?:introducing|announcing|meet) )?(?:the )?{name}(?:$|\s*[:,;(|]|\s+[-–—]\s)"
    return re.match(pattern, _phrase(title)) is not None


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
            if name not in matched and (paper_id := self._title_match(name)):
                # Open only when the paper links the model's own weights.
                hf_model_url = self._weights_url(paper_id, name)
                matched[name] = MatchedModel(
                    paper_id, name, hf_model_url is not None, hf_model_url
                )
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

    def _title_match(self, model_name: str) -> int | None:
        tokens = re.findall(r"[a-z0-9]+", model_name.casefold())
        if not tokens:
            return None
        candidates = (
            self.db.query(Paper.id, Paper.title)
            .filter(
                Paper.is_latest_version,
                Paper.title.ilike(f"%{'%'.join(tokens)}%"),
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

    def report_unmatched(
        self, models: list[LeaderboardModel], *, now: datetime | None = None
    ) -> list[str]:
        """Record a release signal per unmatched model; returns the names."""
        now = now or datetime.now(UTC)
        reported: list[str] = []
        for model in dict.fromkeys(models):
            if not model.lab.strip():
                continue
            key = signal_key(model.lab, model.name)
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
                        lab=model.lab,
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
