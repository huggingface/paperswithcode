"""Turn unindexed release-radar signals into scoped paper-resolution jobs.

`scan_model_releases` reports releases no paper covers. Each one becomes a
durable `model_release_signals` row; qualifying rows get one
`resolve-model-paper` job (trigger `model-release-radar`). The remote curator
finds the lab's own announcement and resolves the release to an existing
paper, an arXiv paper, or a new external paper. A new external paper then
gets the usual enrich-paper -> add-evals workflow.

The backend, not the curator, enforces the guardrails: an external paper's
source must be the publisher's own site or Hub/GitHub organization, never the
news page that surfaced it, and it must not duplicate an indexed paper or
model release.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.curation import ResolveModelPaperMutation
from backend.models.database import (
    ModelRelease,
    ModelReleaseSignal,
    Paper,
    PaperCurationJob,
    PaperRelation,
)
from backend.services.codex_add_evals_service import RADAR_TRIGGER
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.model_release_radar_service import (
    AA_PROVIDER,
    WEB_SEARCH_PROVIDER,
    RadarReport,
    _escape_like,
    _name_key,
    _url_variants,
)
from backend.services.paper_ingestion_service import PaperIngestionService
from backend.services.trending_model_resolution_service import (
    TrendingModelResolutionService,
    model_family_key,
)

# Web-search extraction is nondeterministic, so a news-only signal must
# reappear in a later run before it costs a curation job. Vendor feeds are
# first-party and qualify on their first sighting.
WEB_SEARCH_MIN_SIGHTINGS = 2
MAX_RADAR_JOBS_PER_DAY = 6
# A failed resolution is retried once the release has been seen again after
# this long, so a transient Job failure does not drop the release.
FAILED_RETRY_AFTER = timedelta(days=2)
PAPER_CANDIDATE_LIMIT = 20

# Hosts whose first path segment names the publishing organization.
_ORGANIZATION_HOSTS = frozenset({"huggingface.co", "github.com", "modelscope.cn"})
_ORGANIZATION_PATH_PREFIXES = frozenset(
    {"models", "datasets", "spaces", "collections", "organizations"}
)
_GENERIC_TOKENS = frozenset(
    {
        "the",
        "inc",
        "lab",
        "labs",
        "research",
        "technologies",
        "technology",
        "group",
        "team",
        "model",
        "models",
        "open",
        "blog",
        "news",
        "docs",
        "www",
        "com",
        "org",
        "net",
        "co",
    }
)


_CORPORATE_SUFFIXES = frozenset({"ai", "labs", "lab", "hq", "inc", "lm", "research"})


def signal_key(lab: str, model_name: str) -> str:
    return f"{_name_key(lab)}/{_name_key(model_name)}"


def record_release_signals(
    db: Session, report: RadarReport, *, now: datetime | None = None
) -> int:
    """Upsert the report's releases; returns how many unindexed rows it saw.

    Artificial Analysis slugs stay report-only: an unmapped leaderboard slug
    has no announcement page to resolve. A signal the catalog now covers is
    closed as resolved.
    """
    now = now or datetime.now(UTC)
    seen = 0
    for signal in report.signals:
        if signal.source == AA_PROVIDER or not signal.url:
            continue
        key = signal_key(signal.lab, signal.model_name)
        row = (
            db.query(ModelReleaseSignal)
            .filter(ModelReleaseSignal.signal_key == key)
            .one_or_none()
        )
        if signal.status == "indexed":
            if row is not None and row.status in {"discovered", "failed"}:
                row.status = "resolved"
                row.paper_id = signal.paper_id
                row.processed_at = now
            continue
        seen += 1
        official = signal.source != WEB_SEARCH_PROVIDER or signal.official_url
        if row is None:
            db.add(
                ModelReleaseSignal(
                    id=uuid.uuid4(),
                    signal_key=key,
                    lab=signal.lab,
                    model_name=signal.model_name,
                    title=signal.title,
                    lead_url=signal.url,
                    source=signal.source,
                    lead_is_official=official,
                    published=signal.published,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
            continue
        row.sightings += 1
        row.last_seen_at = now
        # The lab's own page is a better lead than a news page about the
        # release, and a vendor feed outranks a web hit.
        if (official and not row.lead_is_official) or (
            row.source == WEB_SEARCH_PROVIDER and signal.source != WEB_SEARCH_PROVIDER
        ):
            row.source = signal.source
            row.lead_url = signal.url
            row.title = signal.title
            row.lead_is_official = official
    db.flush()
    return seen


def queue_release_signals(
    db: Session,
    settings: Settings,
    *,
    jobs,
    now: datetime | None = None,
) -> list[ModelReleaseSignal]:
    """Queue resolution jobs for qualifying signals, at most a few per day."""
    now = now or datetime.now(UTC)
    day_start = datetime.combine(now.date(), datetime.min.time(), tzinfo=UTC)
    queued_today = (
        db.query(func.count(PaperCurationJob.id))
        .filter(
            PaperCurationJob.trigger == RADAR_TRIGGER,
            PaperCurationJob.created_at >= day_start,
        )
        .scalar()
    )
    budget = MAX_RADAR_JOBS_PER_DAY - int(queued_today or 0)
    if budget <= 0:
        return []
    rows = (
        db.query(ModelReleaseSignal)
        .filter(
            or_(
                ModelReleaseSignal.status == "discovered",
                (ModelReleaseSignal.status == "failed")
                & (ModelReleaseSignal.processed_at < now - FAILED_RETRY_AFTER)
                & (ModelReleaseSignal.last_seen_at > ModelReleaseSignal.processed_at),
            ),
            or_(
                ModelReleaseSignal.source != WEB_SEARCH_PROVIDER,
                ModelReleaseSignal.sightings >= WEB_SEARCH_MIN_SIGHTINGS,
            ),
        )
        .order_by(
            ModelReleaseSignal.published.desc().nullslast(),
            ModelReleaseSignal.first_seen_at,
        )
        .limit(budget)
        .all()
    )
    for row in rows:
        jobs.enqueue_signal_resolution(
            db,
            signal=row,
            requested_by=RADAR_TRIGGER,
            settings=settings,
            dispatch=False,
            commit=False,
        )
    return rows


def signal_paper_candidates(db: Session, signal: ModelReleaseSignal) -> list[Paper]:
    """Papers the curator should compare before creating a new one.

    Same-family model releases from any publisher spelling, plus latest
    papers whose title names the model or its versioned name token.
    """
    family = model_family_key(signal.model_name)
    candidates: dict[int, Paper] = {}
    releases = (
        db.query(ModelRelease)
        .filter(ModelRelease.paper_id.isnot(None))
        .order_by(ModelRelease.id.desc())
        .yield_per(200)
    )
    for release in releases:
        identities = [release.canonical_name, *(release.aliases or [])]
        if not any(
            (key := model_family_key(identity))
            and (
                key == family
                or (
                    min(len(key), len(family)) >= 5 and (family in key or key in family)
                )
            )
            for identity in identities
        ):
            continue
        paper = db.get(Paper, release.paper_id)
        if paper is not None and paper.is_latest_version:
            candidates.setdefault(paper.id, paper)
        if len(candidates) >= PAPER_CANDIDATE_LIMIT:
            break
    terms = {signal.model_name}
    terms.update(
        token
        for token in re.split(r"\s+", signal.model_name)
        if re.search(r"[a-z]", token, re.I) and re.search(r"\d", token)
    )
    title_matches = (
        db.query(Paper)
        .filter(
            Paper.is_latest_version,
            or_(
                *(
                    func.lower(Paper.title).like(
                        f"%{_escape_like(term.casefold())}%", escape="\\"
                    )
                    for term in sorted(terms)
                )
            ),
        )
        .order_by(Paper.id.desc())
        .limit(PAPER_CANDIDATE_LIMIT)
        .all()
    )
    for paper in title_matches:
        candidates.setdefault(paper.id, paper)
    return list(candidates.values())[: PAPER_CANDIDATE_LIMIT * 2]


def _identity_tokens(*values: str | None) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        if not value:
            continue
        words = [
            word
            for word in re.split(r"[^a-z0-9]+", value.casefold())
            if len(word) >= 3 and word not in _GENERIC_TOKENS
        ]
        tokens.update(words)
        joined = "".join(words)
        if len(joined) >= 3:
            tokens.add(joined)
    return tokens


def _host_tokens(url: str) -> tuple[set[str], bool]:
    """Name tokens of the host, and whether they name a Hub/GitHub account."""
    parts = urlsplit(url)
    host = (parts.hostname or "").casefold().removeprefix("www.")
    if host in _ORGANIZATION_HOSTS:
        segments = [segment for segment in parts.path.split("/") if segment]
        # huggingface.co/collections/<org>/..., modelscope.cn/models/<org>/...
        if segments and segments[0] in _ORGANIZATION_PATH_PREFIXES:
            segments = segments[1:]
        return _identity_tokens(segments[0] if segments else None), True
    labels = host.split(".")
    # Brand TLDs and short names count too: "blog.google", "x.ai" -> "xai".
    pairs = ["".join(labels[index : index + 2]) for index in range(len(labels) - 1)]
    return _identity_tokens(*labels, *pairs), False


def _names_match(token: str, name: str, *, account: bool) -> bool:
    if token == name:
        return True
    if len(name) < 4 or not token.startswith(name):
        return False
    # Accounts append anything ("RecursiveSI"); a domain may append only a
    # corporate suffix ("mistralai"), so "kimiupdates.com" is not Kimi's.
    return account or token[len(name) :] in _CORPORATE_SUFFIXES


def is_first_party_source(
    url: str, *, publisher_names: list[str], lead_url: str | None
) -> bool:
    """Whether ``url`` is hosted by the publisher, not a news or mirror site.

    The host (or the Hub/GitHub organization) must carry the publisher's or
    model's name, and it must not be the host of the news page that surfaced
    the release.
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return False
    host = parts.hostname.casefold().removeprefix("www.")
    if lead_url and host not in _ORGANIZATION_HOSTS:
        lead_host = (urlsplit(lead_url).hostname or "").casefold().removeprefix("www.")
        if host == lead_host:
            return False
    host_tokens, account = _host_tokens(url)
    names = _identity_tokens(*publisher_names)
    return any(
        _names_match(token, name, account=account)
        for token in host_tokens
        for name in names
    )


class ReleaseSignalResolutionService:
    """Apply one validated radar-signal resolution transaction."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def apply(
        self,
        signal_id: uuid.UUID,
        mutation: ResolveModelPaperMutation,
        *,
        commit: bool = True,
    ) -> dict:
        signal = self.db.get(ModelReleaseSignal, signal_id)
        if signal is None:
            raise LookupError("Release signal not found")
        if signal.status not in {"queued", "resolving"}:
            raise RuntimeError("Release signal is not accepting a resolution")
        now = datetime.now(UTC)
        if mutation.decision == "reject":
            signal.status = "rejected"
            signal.rejection_reason = mutation.reason
            signal.processed_at = now
            self._finish(commit)
            return {"status": "rejected", "release_signal_id": str(signal.id)}

        proposal = mutation.model_release
        assert proposal is not None
        paper = self._resolve_paper(signal, mutation)
        predecessor_id = mutation.predecessor_paper_id
        if predecessor_id is not None:
            predecessor = self.db.get(Paper, predecessor_id)
            if predecessor is None:
                raise LookupError("Predecessor paper not found")
            if predecessor.id == paper.id:
                raise ValueError("A release cannot be its own predecessor")
            if not TrendingModelResolutionService._paper_supported_by_evidence(
                predecessor, mutation.evidence_urls
            ):
                raise ValueError(
                    "Predecessor relation requires canonical source evidence"
                )
            if self.db.get(PaperRelation, (predecessor.id, paper.id)) is None:
                self.db.add(
                    PaperRelation(
                        source_paper_id=predecessor.id, target_paper_id=paper.id
                    )
                )
        aliases = list(
            dict.fromkeys(
                alias
                for alias in [*proposal.aliases, signal.model_name]
                if _name_key(alias) != _name_key(proposal.canonical_name)
            )
        )
        release = (
            self.db.query(ModelRelease)
            .filter(
                ModelRelease.paper_id == paper.id,
                ModelRelease.canonical_name == proposal.canonical_name,
            )
            .one_or_none()
        )
        if release is None:
            release = ModelRelease(
                paper_id=paper.id,
                canonical_name=proposal.canonical_name,
                publisher=proposal.publisher,
                canonical_source_url=TrendingModelResolutionService._canonical_paper_url(
                    paper
                ),
                aliases=aliases,
                is_open=proposal.is_open,
            )
            self.db.add(release)
            self.db.flush()
        else:
            release.aliases = list(dict.fromkeys([*(release.aliases or []), *aliases]))
            release.is_open = proposal.is_open
        signal.status = "resolved"
        signal.rejection_reason = None
        signal.paper_id = paper.id
        signal.processed_at = now
        self._finish(commit)
        return {
            "status": "resolved",
            "release_signal_id": str(signal.id),
            "paper_id": int(paper.id),
            "model_release_id": int(release.id),
        }

    def _finish(self, commit: bool) -> None:
        if commit:
            self.db.commit()
        else:
            self.db.flush()

    def _resolve_paper(
        self, signal: ModelReleaseSignal, mutation: ResolveModelPaperMutation
    ) -> Paper:
        evidence = mutation.evidence_urls
        if mutation.existing_paper_id is not None:
            paper = self.db.get(Paper, mutation.existing_paper_id)
            if paper is None:
                raise LookupError("Resolved paper not found")
            if not TrendingModelResolutionService._paper_supported_by_evidence(
                paper, evidence
            ):
                raise ValueError(
                    "Existing paper resolution requires canonical source evidence"
                )
            return paper
        if mutation.arxiv_id is not None:
            if not any(
                TrendingModelResolutionService._canonical_arxiv_evidence(
                    mutation.arxiv_id, url
                )
                for url in evidence
            ):
                raise ValueError("arXiv resolution requires matching source evidence")
            paper, _ = asyncio.run(
                PaperIngestionService(self.db).get_or_import_arxiv_paper(
                    mutation.arxiv_id, commit=False
                )
            )
            return paper
        external = mutation.external_paper
        proposal = mutation.model_release
        assert external is not None and proposal is not None
        if external.source_url.rstrip("/") not in {url.rstrip("/") for url in evidence}:
            raise ValueError(
                "External paper resolution requires matching source evidence"
            )
        if not is_first_party_source(
            external.source_url,
            publisher_names=[
                signal.lab,
                proposal.publisher,
                proposal.canonical_name,
                *proposal.aliases,
            ],
            lead_url=None if signal.lead_is_official else signal.lead_url,
        ):
            raise ValueError(
                "An external paper's source_url must be the publisher's own "
                "announcement, model card, or repository, not a news or mirror page"
            )
        if external.date_published > date.today() + timedelta(days=1):
            raise ValueError("External paper date_published is in the future")
        duplicate = self._duplicate_paper(external.source_url, external.title, proposal)
        if duplicate is not None:
            raise ValueError(
                f"Release is already indexed as paper {duplicate.id} "
                f"({duplicate.title!r}); resolve to existing_paper_id {duplicate.id} "
                "with its source in evidence_urls instead of creating a duplicate"
            )
        result = ExternalResourceService(self.db).add_external_resource(
            ExternalResourceInput(
                source_url=external.source_url,
                title=external.title,
                abstract=external.abstract,
                date_published=external.date_published,
            ),
            commit=False,
            # New external papers queue enrich-paper -> add-evals.
            queue_curation=True,
        )
        paper = self.db.get(Paper, int(result.paper.id))
        if paper is None:
            raise RuntimeError("External paper ingestion returned no database row")
        return paper

    def _duplicate_paper(self, source_url: str, title: str, proposal) -> Paper | None:
        """An indexed paper with this source, title, or model release name."""
        by_source = (
            self.db.query(Paper)
            .filter(Paper.source_url.in_(sorted(_url_variants(source_url))))
            .order_by(Paper.id)
            .first()
        )
        if by_source is not None:
            return by_source
        names = {
            _name_key(value)
            for value in [proposal.canonical_name, *proposal.aliases]
            if _name_key(value)
        }
        for release in (
            self.db.query(ModelRelease)
            .filter(
                ModelRelease.paper_id.isnot(None),
                func.lower(ModelRelease.canonical_name).in_(
                    sorted(
                        value.casefold()
                        for value in [proposal.canonical_name, *proposal.aliases]
                    )
                ),
            )
            .order_by(ModelRelease.id)
            .limit(20)
        ):
            if _name_key(release.canonical_name) in names:
                return self.db.get(Paper, release.paper_id)
        return (
            self.db.query(Paper)
            .filter(
                Paper.is_latest_version,
                func.lower(Paper.title) == title.strip().casefold(),
            )
            .order_by(Paper.id)
            .first()
        )
