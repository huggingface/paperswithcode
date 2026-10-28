"""Release-radar signals queue scoped resolution jobs with backend guardrails."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.orm import Session

from backend.models.curation import ApplyMutationRequest, ResolveModelPaperMutation
from backend.models.database import (
    ModelRelease,
    ModelReleaseSignal,
    Paper,
    PaperCurationBootstrapBundle,
    PaperCurationJob,
    PaperCurationSchedulerState,
    PaperCurationWorkflow,
    PaperRelation,
)
from backend.services import model_release_signal_service as signals
from backend.services.codex_add_evals_service import (
    RADAR_POLICY_VERSION,
    RADAR_TRIGGER,
    CodexPaperJobService,
)
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
)
from backend.services.curation_autonomy import curation_primary_authorization
from backend.services.autonomous_capabilities import (
    CAPABILITY_RESOURCE_KINDS,
    Capability,
    ResourceKind,
)
from backend.services.model_release_radar_service import (
    AA_PROVIDER,
    WEB_SEARCH_PROVIDER,
    RadarReport,
    ReleaseSignal,
)

SETTINGS = SimpleNamespace(
    codex_jobs_enabled=False,
    codex_jobs_model="gpt-test",
    codex_jobs_reasoning_effort="high",
    codex_jobs_cli_version="0.0.0",
)
NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)
FEED = "https://mistral.ai/sitemap.xml"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    # Only storage is simplified; service queries and ORM mappings are real.
    for model in (
        Paper,
        ModelRelease,
        ModelReleaseSignal,
        PaperRelation,
        PaperCurationBootstrapBundle,
        PaperCurationJob,
        PaperCurationWorkflow,
        PaperCurationSchedulerState,
    ):
        columns = []
        for column in model.__table__.columns:
            kind = column.type
            if kind.__class__.__name__ == "JSONB":
                kind = JSON()
            elif kind.__class__.__name__ in {"ARRAY", "TSVECTOR", "Vector"}:
                kind = String()
            elif column.primary_key and kind.__class__.__name__ == "BigInteger":
                kind = Integer()  # SQLite autoincrements only INTEGER keys
            default = column.server_default if column.name.endswith("_at") else None
            columns.append(
                Column(
                    column.name,
                    kind,
                    primary_key=column.primary_key,
                    server_default=default,
                )
            )
        Table(model.__tablename__, metadata, *columns)
    metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        yield session
    engine.dispose()


def _paper(db, number, title, source_url, *, source="external"):
    paper = Paper(
        id=number,
        arxiv_id=None,
        title=title,
        source=source,
        source_url=source_url,
        is_latest_version=True,
    )
    db.add(paper)
    db.flush()
    return paper


def _radar_signal(model, *, lab="Moonshot AI", source=WEB_SEARCH_PROVIDER, url=None):
    return ReleaseSignal(
        lab=lab,
        source=source,
        model_name=model,
        title=f"{lab} launches {model}",
        url=url or f"https://news.example.com/{model.replace(' ', '-').lower()}",
        published=date(2026, 10, 23),
    )


def _signal_row(db, model="Kimi K3.1 Pro", *, status="queued", lead=None):
    row = ModelReleaseSignal(
        id=uuid.uuid4(),
        signal_key=signals.signal_key("Moonshot AI", model),
        lab="Moonshot AI",
        model_name=model,
        title=f"Moonshot AI launches {model}",
        lead_url=lead or "https://siliconangle.com/2026/10/23/kimi-k3-1-pro",
        source=WEB_SEARCH_PROVIDER,
        lead_is_official=False,
        published=date(2026, 10, 23),
        sightings=2,
        status=status,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    db.add(row)
    db.flush()
    return row


def _accept(source_url, **overrides):
    payload = {
        "decision": "accept",
        "reason": "Moonshot's own tech blog announces the new flagship model.",
        "novelty_kind": "new_release",
        "evidence_urls": [source_url],
        "external_paper": {
            "source_url": source_url,
            "title": "Kimi K3.1 Pro: Advancing Open Intelligence",
            "abstract": "Today we release Kimi K3.1 Pro.",
            "date_published": "2026-10-23",
        },
        "model_release": {
            "canonical_name": "Kimi K3.1 Pro",
            "publisher": "Moonshot AI",
            "is_open": False,
            "aliases": ["kimi-k3.1-pro"],
        },
    }
    payload.update(overrides)
    return ResolveModelPaperMutation.model_validate(payload)


class _FakeExternalResources:
    created: list[dict] = []

    def __init__(self, db):
        self.db = db

    def add_external_resource(self, payload, *, commit, queue_curation):
        assert commit is False and queue_curation is True
        paper = _paper(self.db, 900, payload.title, payload.source_url)
        type(self).created.append({"source_url": payload.source_url})
        return SimpleNamespace(paper=SimpleNamespace(id=paper.id))


@pytest.fixture
def fake_external(monkeypatch):
    _FakeExternalResources.created = []
    monkeypatch.setattr(signals, "ExternalResourceService", _FakeExternalResources)
    return _FakeExternalResources


@pytest.mark.parametrize(
    ("url", "names", "lead", "expected"),
    [
        (
            "https://www.kimi.com/blog/kimi-k3-1-pro",
            ["Moonshot AI", "Kimi K3.1 Pro"],
            None,
            True,
        ),
        (
            "https://www.minimax.io/blog/minimax-m31f",
            ["MiniMax", "MiniMax M3.1 Flash"],
            None,
            True,
        ),
        (
            "https://www.recursive.com/updates/introducing-recursive-flint",
            ["Recursive", "Flint"],
            None,
            True,
        ),
        (
            "https://deepmind.google/models/gemini",
            ["Google DeepMind", "Gemini 4"],
            None,
            True,
        ),
        ("https://huggingface.co/tencent/Hy3", ["Tencent", "Hunyuan Hy3"], None, True),
        (
            "https://github.com/MoonshotAI/Kimi-K3",
            ["Moonshot AI", "Kimi K3"],
            None,
            True,
        ),
        # News sites, mirrors, and the lead's own host are never sources.
        (
            "https://siliconangle.com/2026/10/23/kimi-k3-1-pro",
            ["Moonshot AI", "Kimi K3.1 Pro"],
            None,
            False,
        ),
        (
            "https://huggingface.co/unsloth/Hy3-GGUF",
            ["Tencent", "Hunyuan Hy3"],
            None,
            False,
        ),
        (
            "https://huggingface.co/RecursiveSI/flint",
            ["Recursive", "Flint"],
            None,
            True,
        ),
        ("https://mistralnews.com/voxtral-3", ["Mistral AI", "Voxtral 3"], None, False),
        ("https://x.ai/news/grok-5", ["xAI", "Grok 5"], None, True),
        # A public TLD is not a name: a ".pro" news site is not Kimi's.
        ("https://ainews.pro/kimi-k3-1", ["Moonshot AI", "Kimi K3.1 Pro"], None, False),
        (
            "https://blog.google/technology/gemini-4",
            ["Google DeepMind", "Gemini 4"],
            None,
            True,
        ),
        (
            "https://research.google/blog/a-model",
            ["Google Research", "A Model"],
            None,
            True,
        ),
        (
            "https://modelscope.cn/models/Tencent-Hunyuan/Hy3",
            ["Tencent", "Hunyuan Hy3"],
            None,
            True,
        ),
        (
            "https://huggingface.co/collections/tencent/hy3",
            ["Tencent", "Hunyuan Hy3"],
            None,
            True,
        ),
        (
            "https://kimiupdates.com/b",
            ["Moonshot AI", "Kimi K3.1 Pro"],
            "https://kimiupdates.com/a",
            False,
        ),
        (
            "http://www.kimi.com/blog/kimi-k3-1-pro",
            ["Moonshot AI", "Kimi K3.1 Pro"],
            None,
            False,
        ),
    ],
)
def test_first_party_source_requires_publisher_host(url, names, lead, expected):
    assert (
        signals.is_first_party_source(url, publisher_names=names, lead_url=lead)
        is expected
    )


def test_record_upserts_unindexed_signals_and_closes_indexed_ones(db):
    report = RadarReport(
        lookback_days=14,
        signals=[
            _radar_signal("Kimi K3.1 Pro"),
            _radar_signal(
                "Voxtral 3",
                lab="Mistral AI",
                source=FEED,
                url="https://mistral.ai/news/voxtral-3",
            ),
            ReleaseSignal(
                lab="MiniMax",
                source=AA_PROVIDER,
                model_name="M3.1",
                title="minimax-m3-1",
                url=None,
                published=date(2026, 10, 23),
            ),
        ],
    )
    assert signals.record_release_signals(db, report, now=NOW) == 2
    assert signals.record_release_signals(db, report, now=NOW) == 2
    kimi = db.query(ModelReleaseSignal).filter_by(model_name="Kimi K3.1 Pro").one()
    assert kimi.sightings == 2
    assert (
        db.query(ModelReleaseSignal).count() == 2
    )  # Artificial Analysis stays report-only

    # A vendor feed sighting replaces the news lead.
    feed = _radar_signal(
        "Kimi K3.1 Pro",
        source="https://kimi.com/feed",
        url="https://www.kimi.com/blog/kimi-k3-1-pro",
    )
    signals.record_release_signals(db, RadarReport(14, [feed]), now=NOW)
    assert kimi.lead_url == "https://www.kimi.com/blog/kimi-k3-1-pro"
    assert kimi.source == "https://kimi.com/feed"

    indexed = _radar_signal("Kimi K3.1 Pro")
    indexed.status, indexed.paper_id = "indexed", 124110
    signals.record_release_signals(db, RadarReport(14, [indexed]), now=NOW)
    assert (kimi.status, kimi.paper_id) == ("resolved", 124110)


class _Jobs(CodexPaperJobService):
    def _bootstrap(self):  # pragma: no cover - not reached without a git sha
        return None


def test_queue_waits_for_a_second_web_sighting_and_caps_each_day(db):
    jobs = _Jobs()
    report = RadarReport(
        14,
        [
            _radar_signal("Kimi K3.1 Pro"),
            _radar_signal(
                "Voxtral 3",
                lab="Mistral AI",
                source=FEED,
                url="https://mistral.ai/news/voxtral-3",
            ),
        ],
    )
    signals.record_release_signals(db, report, now=NOW)
    first = signals.queue_release_signals(db, SETTINGS, jobs=jobs, now=NOW)
    # The vendor feed qualifies at once; the news-only signal waits.
    assert [row.model_name for row in first] == ["Voxtral 3"]

    signals.record_release_signals(db, report, now=NOW)
    second = signals.queue_release_signals(db, SETTINGS, jobs=jobs, now=NOW)
    assert [row.model_name for row in second] == ["Kimi K3.1 Pro"]

    job = db.query(PaperCurationJob).filter_by(release_signal_id=second[0].id).one()
    assert job.kind == "resolve-model-paper"
    assert job.trigger == RADAR_TRIGGER
    assert job.policy_version == RADAR_POLICY_VERSION
    assert job.candidate_id is None and job.paper_id is None
    assert second[0].status == "queued"

    for number in range(signals.MAX_RADAR_JOBS_PER_DAY):
        signals.record_release_signals(
            db,
            RadarReport(
                14,
                [
                    _radar_signal(
                        f"Model {number}",
                        source=FEED,
                        url=f"https://lab.example/{number}",
                    )
                ],
            ),
            now=NOW,
        )
    db.flush()
    capped = signals.queue_release_signals(db, SETTINGS, jobs=jobs, now=NOW)
    assert len(capped) == signals.MAX_RADAR_JOBS_PER_DAY - 2


def test_failed_signal_retries_only_after_a_later_sighting(db):
    row = _signal_row(db, status="failed")
    row.processed_at = NOW - timedelta(days=3)
    row.last_seen_at = NOW - timedelta(days=4)
    db.flush()
    jobs = _Jobs()
    assert signals.queue_release_signals(db, SETTINGS, jobs=jobs, now=NOW) == []
    row.last_seen_at = NOW
    db.flush()
    assert signals.queue_release_signals(db, SETTINGS, jobs=jobs, now=NOW) == [row]


def test_reject_closes_the_signal(db):
    row = _signal_row(db)
    result = signals.ReleaseSignalResolutionService(db).apply(
        row.id,
        ResolveModelPaperMutation.model_validate(
            {
                "decision": "reject",
                "reason": "Only an SDK update; no new model.",
                "novelty_kind": "uncertain",
                "evidence_urls": ["https://www.kimi.com/blog"],
            }
        ),
        commit=False,
    )
    assert result["status"] == "rejected"
    assert row.status == "rejected"


def test_external_paper_from_news_page_is_refused(db, fake_external):
    row = _signal_row(db)
    with pytest.raises(ValueError, match="publisher's own announcement"):
        signals.ReleaseSignalResolutionService(db).apply(
            row.id, _accept(row.lead_url), commit=False
        )
    assert fake_external.created == []


def test_duplicate_release_resolves_to_the_indexed_paper(db, fake_external):
    row = _signal_row(db, "Hunyuan Hy3")
    _paper(db, 102554, "Hy3", "https://huggingface.co/tencent/Hy3")
    with pytest.raises(ValueError, match="already indexed as paper 102554"):
        signals.ReleaseSignalResolutionService(db).apply(
            row.id,
            _accept(
                "https://huggingface.co/tencent/Hy3",
                model_release={
                    "canonical_name": "Hy3",
                    "publisher": "Tencent",
                    "is_open": True,
                    "aliases": ["Hunyuan Hy3"],
                },
            ),
            commit=False,
        )
    assert fake_external.created == []

    result = signals.ReleaseSignalResolutionService(db).apply(
        row.id,
        _accept(
            "https://huggingface.co/tencent/Hy3",
            external_paper=None,
            existing_paper_id=102554,
            model_release={
                "canonical_name": "Hy3",
                "publisher": "Tencent",
                "is_open": True,
                "aliases": [],
            },
        ),
        commit=False,
    )
    assert result["paper_id"] == 102554
    release = db.query(ModelRelease).one()
    # The radar's name becomes an alias, so later scans match the release.
    assert release.aliases == ["Hunyuan Hy3"]
    assert row.status == "resolved" and row.paper_id == 102554


def test_duplicate_model_release_name_is_refused(db, fake_external):
    row = _signal_row(db)
    _paper(
        db, 7, "Kimi K3.1 Pro tech blog", "https://www.kimi.com/en/blog/kimi-k3-1-pro"
    )
    db.add(ModelRelease(paper_id=7, canonical_name="Kimi K3.1 Pro", aliases=[]))
    db.flush()
    with pytest.raises(ValueError, match="already indexed as paper 7"):
        signals.ReleaseSignalResolutionService(db).apply(
            row.id, _accept("https://www.kimi.com/blog/kimi-k3-1-pro"), commit=False
        )


def test_first_party_external_paper_is_created_with_release_and_predecessor(
    db, fake_external
):
    row = _signal_row(db)
    _paper(
        db,
        104584,
        "Kimi K3: Open Frontier Intelligence",
        "https://arxiv.org/abs/2607.24653",
        source="arxiv",
    )
    db.get(Paper, 104584).arxiv_id = "2607.24653"
    source = "https://www.kimi.com/blog/kimi-k3-1-pro"
    result = signals.ReleaseSignalResolutionService(db).apply(
        row.id,
        _accept(
            source,
            evidence_urls=[source, "https://arxiv.org/abs/2607.24653"],
            predecessor_paper_id=104584,
        ),
        commit=False,
    )
    assert fake_external.created == [{"source_url": source}]
    assert result["status"] == "resolved" and result["paper_id"] == 900
    release = db.query(ModelRelease).one()
    assert (release.paper_id, release.canonical_name, release.is_open) == (
        900,
        "Kimi K3.1 Pro",
        False,
    )
    assert db.get(PaperRelation, (104584, 900)) is not None
    assert row.status == "resolved" and row.paper_id == 900


def test_radar_jobs_may_propose_external_papers_but_trending_jobs_may_not(db):
    service = CodexCurationCallbackService(db)
    body = ApplyMutationRequest(
        resolve_model_paper=_accept("https://www.kimi.com/blog/kimi-k3-1-pro")
    )
    pending = {"status": "running", "submitted_at": None, "applied_at": None}
    radar = SimpleNamespace(
        kind="resolve-model-paper", trigger=RADAR_TRIGGER, **pending
    )
    service._validate_mutation(radar, body)
    trending = SimpleNamespace(
        kind="resolve-model-paper", trigger="hf-trending-cron", **pending
    )
    with pytest.raises(ValueError, match="cannot create external papers"):
        service._validate_mutation(trending, body)


def test_radar_context_serves_the_runner_candidate_fields(db):
    row = _signal_row(db)
    _paper(
        db,
        104584,
        "Kimi K3: Open Frontier Intelligence",
        "https://arxiv.org/abs/2607.24653",
    )
    job = PaperCurationJob(
        id=uuid.uuid4(),
        kind="resolve-model-paper",
        release_signal_id=row.id,
        requested_by=RADAR_TRIGGER,
        status="running",
        trigger=RADAR_TRIGGER,
        policy_version=RADAR_POLICY_VERSION,
        priority=25,
        attempt_count=1,
        model="gpt-test",
        reasoning_effort="high",
        codex_cli_version="0.0.0",
        validator_version="release-radar-policy-v1",
    )
    db.add(job)
    db.flush()
    context = CodexCurationCallbackService(db).context(job, SETTINGS)
    assert context["candidate"] == {
        "id": str(row.id),
        "repo_id": "Moonshot AI: Kimi K3.1 Pro",
        "readme_sha": None,
        "model_card_url": row.lead_url,
    }
    assert context["release_signal"]["lead_is_first_party"] is False
    assert [paper["id"] for paper in context["paper_candidates"]] == []

    capability, resource = curation_primary_authorization(db, job)
    assert capability == Capability.RESOLVE_MODEL_PAPER
    assert resource.kind == ResourceKind.MODEL_RELEASE_SIGNAL and resource.exists
    assert ResourceKind.MODEL_RELEASE_SIGNAL in CAPABILITY_RESOURCE_KINDS[capability]


def test_paper_candidates_include_family_releases_and_title_matches(db):
    row = _signal_row(db)
    _paper(
        db, 1, "Kimi K3: Open Frontier Intelligence", "https://arxiv.org/abs/2607.24653"
    )
    _paper(db, 2, "Kimi K3.1 Pro in practice", "https://example.org/k31")
    _paper(db, 3, "Unrelated", "https://example.org/x")
    db.add(ModelRelease(paper_id=1, canonical_name="Kimi K3", aliases=[]))
    db.flush()
    ids = {paper.id for paper in signals.signal_paper_candidates(db, row)}
    assert ids == {1, 2}


def test_launch_failure_and_cancel_mark_the_signal_failed(db):
    row = _signal_row(db)
    job = SimpleNamespace(
        kind="resolve-model-paper", release_signal_id=row.id, error="boom"
    )
    CodexPaperJobService._fail_release_signal(db, job)
    assert row.status == "failed" and row.rejection_reason == "boom"
    row.status = "resolved"
    CodexPaperJobService._fail_release_signal(db, job)
    assert row.status == "resolved"


def test_radar_jobs_dispatch_in_the_trending_resolution_lane(db):
    row = _signal_row(db, status="discovered")
    CodexPaperJobService().enqueue_signal_resolution(
        db,
        signal=row,
        requested_by=RADAR_TRIGGER,
        settings=SETTINGS,
        dispatch=False,
        commit=False,
    )
    picked = CodexPaperJobService._next_trending_row(db)
    assert picked is not None and picked.release_signal_id == row.id


def test_official_web_lead_may_be_the_source(db, fake_external):
    source = "https://www.kimi.com/blog/kimi-k3-1-pro"
    row = _signal_row(db, lead=source)
    row.lead_is_official = True
    db.flush()
    result = signals.ReleaseSignalResolutionService(db).apply(
        row.id, _accept(source), commit=False
    )
    assert result["status"] == "resolved"
    assert fake_external.created == [{"source_url": source}]


def test_news_lead_is_upgraded_to_an_official_web_hit(db):
    news = _radar_signal("Kimi K3.1 Pro")
    signals.record_release_signals(db, RadarReport(14, [news]), now=NOW)
    row = db.query(ModelReleaseSignal).one()
    assert row.lead_is_official is False

    official = _radar_signal(
        "Kimi K3.1 Pro", url="https://www.kimi.com/blog/kimi-k3-1-pro"
    )
    official.official_url = True
    signals.record_release_signals(db, RadarReport(14, [official]), now=NOW)
    assert row.lead_url == "https://www.kimi.com/blog/kimi-k3-1-pro"
    assert row.lead_is_official is True
    # A later news-only sighting keeps the official lead.
    signals.record_release_signals(db, RadarReport(14, [news]), now=NOW)
    assert row.lead_url == "https://www.kimi.com/blog/kimi-k3-1-pro"


def test_radar_resolution_refuses_another_versions_paper(db, fake_external):
    row = _signal_row(db)
    _paper(
        db,
        104584,
        "Kimi K3: Open Frontier Intelligence",
        "https://www.kimi.com/blog/kimi-k3",
    )
    with pytest.raises(ValueError, match="not this release's kimik 3.1"):
        signals.ReleaseSignalResolutionService(db).apply(
            row.id,
            _accept(
                "https://www.kimi.com/blog/kimi-k3",
                external_paper=None,
                existing_paper_id=104584,
            ),
            commit=False,
        )
