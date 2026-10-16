"""Tests for the read-only model-release radar."""

from datetime import date

import httpx
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import Base, ModelProviderAlias, ModelRelease, Paper
from backend.services.artificial_analysis_sync_service import (
    ArtificialAnalysisEntry,
    ArtificialAnalysisLeaderboard,
)
from backend.services.model_release_radar_service import (
    WEB_SEARCH_PROVIDER,
    WEB_SEARCH_QUERIES,
    ExtractedRelease,
    OpenAIReleaseExtractor,
    ReleaseSource,
    SearchHit,
    parse_article,
    parse_rss,
    release_model_name,
    scan_model_releases,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


TODAY = date(2026, 10, 11)

OPENAI = ReleaseSource(
    lab="OpenAI",
    url="https://openai.com/news/rss.xml",
    kind="rss",
    families=("GPT", "o3"),
)
OPENAI_GEMINI = ReleaseSource(
    lab="Google DeepMind",
    url="https://deepmind.google/blog/rss.xml",
    kind="rss",
    families=("Gemini",),
)
MISTRAL = ReleaseSource(
    lab="Mistral AI",
    url="https://mistral.ai/sitemap.xml",
    kind="sitemap",
    families=("Mistral", "Magistral"),
    new_family=r"[A-Z][a-z]*stral",
    path_prefix="/news/",
)
DEEPSEEK = ReleaseSource(
    lab="DeepSeek",
    url="https://api-docs.deepseek.com/sitemap.xml",
    kind="sitemap",
    families=("DeepSeek",),
    path_prefix="/news/",
    slug_date=(r"/news/news(\d{6})$", "%y%m%d"),
)

OPENAI_RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Introducing GPT-6.1 Sol</title>
<link>https://openai.com/index/introducing-gpt-6-1-sol</link>
<pubDate>Tue, 29 Sep 2026 10:00:00 GMT</pubDate></item>
<item><title>Asana cuts model costs 76x in browser tests with GPT-6.1 Sol</title>
<link>https://openai.com/index/asana-browser-agent</link>
<pubDate>Fri, 09 Oct 2026 07:00:00 GMT</pubDate></item>
<item><title>Introducing GPT-5</title>
<link>https://openai.com/index/introducing-gpt-5</link>
<pubDate>Thu, 07 Aug 2025 10:00:00 GMT</pubDate></item>
</channel></rss>"""

MISTRAL_INDEX = b"""<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://mistral.ai/sitemap-0.xml</loc></sitemap>
</sitemapindex>"""

MISTRAL_PAGES = b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://mistral.ai/news/</loc><lastmod>2026-10-07T20:14:24Z</lastmod></url>
<url><loc>https://mistral.ai/news/timestral/</loc><lastmod>2026-10-09T15:00:00Z</lastmod></url>
<url><loc>https://mistral.ai/news/mistral-large-4/</loc><lastmod>2026-10-07T20:14:24Z</lastmod></url>
<url><loc>https://mistral.ai/news/mistral-large-2407/</loc><lastmod>2026-10-05T16:53:47Z</lastmod></url>
<url><loc>https://mistral.ai/news/old-post/</loc><lastmod>2025-01-01T00:00:00Z</lastmod></url>
<url><loc>https://mistral.ai/pricing</loc><lastmod>2026-10-07T00:00:00Z</lastmod></url>
</urlset>"""

DEEPSEEK_SITEMAP = b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://api-docs.deepseek.com/news/news261001</loc></url>
<url><loc>https://api-docs.deepseek.com/news/news1226</loc></url>
</urlset>"""


def _article(title: str, published: str) -> bytes:
    return (
        f'<html><head><meta property="og:title" content="{title} | Lab">'
        f'<script type="application/ld+json">{{"datePublished":"{published}"}}'
        "</script></head></html>"
    ).encode()


PAGES = {
    OPENAI.url: OPENAI_RSS,
    MISTRAL.url: MISTRAL_INDEX,
    "https://mistral.ai/sitemap-0.xml": MISTRAL_PAGES,
    "https://mistral.ai/news/mistral-large-4/": _article(
        "Introducing Mistral Large 4", "2026-10-06T12:00:27.000Z"
    ),
    # Its JSON-LD keeps the draft's date; the page shows the real one.
    "https://mistral.ai/news/timestral/": (
        b'<html><head><meta property="og:title" content="Timestral: Mistral\'s'
        b' time-series foundation models | Mistral">'
        b'<script type="application/ld+json">{"datePublished":"2026-07-15"}'
        b"</script></head><body><p>October 9, 2026</p></body></html>"
    ),
    "https://mistral.ai/news/mistral-large-2407/": _article(
        "Large Enough", "2024-07-24T00:00:00.000Z"
    ),
    DEEPSEEK.url: DEEPSEEK_SITEMAP,
    "https://api-docs.deepseek.com/news/news261001": (
        b"<html><title data-rh='true'>DeepSeek-V4.2 Release | DeepSeek API Docs"
        b"</title></html>"
    ),
}


class FakeFeeds:
    def __init__(self, pages: dict[str, bytes]):
        self.pages = pages
        self.requested: list[str] = []

    def get(self, url: str) -> bytes:
        self.requested.append(url)
        if url not in self.pages:
            raise httpx.HTTPStatusError(
                "404",
                request=httpx.Request("GET", url),
                response=httpx.Response(404),
            )
        return self.pages[url]


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            ModelRelease.__table__,
            ModelProviderAlias.__table__,
        ],
    )
    session = Session(engine)
    session.add(
        Paper(
            id=123033,
            title="Mistral Large 4",
            source="external",
            source_url="https://mistral.ai/news/mistral-large-4/",
            version="v1",
            is_latest_version=True,
        )
    )
    session.add(
        Paper(
            id=500,
            title="Claude Opus 6",
            source="external",
            source_url="https://www.anthropic.com/claude/opus",
            version="v1",
            is_latest_version=True,
        )
    )
    session.add(
        ModelRelease(id=7, paper_id=500, canonical_name="Claude Opus 6", aliases=[])
    )
    session.add(
        ModelProviderAlias(
            model_release_id=7, provider="artificial-analysis", alias="claude-opus-6"
        )
    )
    session.commit()
    return session


def _leaderboard() -> ArtificialAnalysisLeaderboard:
    def entry(slug: str, name: str, released: date) -> ArtificialAnalysisEntry:
        return ArtificialAnalysisEntry(slug, name, {"intelligence": 50.0}, released)

    return ArtificialAnalysisLeaderboard(
        "4",
        [
            entry("claude-opus-6", "Claude Opus 6", date(2026, 10, 1)),
            # Reviewed identity-map slugs are already handled by the AA sync.
            entry("claude-opus-5", "Claude Opus 5", date(2026, 10, 1)),
            entry("grok-5", "Grok 5 (Reasoning)", date(2026, 10, 9)),
            entry("grok-5-non-reasoning", "Grok 5 (Non-reasoning)", date(2026, 10, 9)),
            entry("mistral-large-4", "Mistral Large 4 Preview", date(2026, 10, 6)),
            entry("old-model", "Old Model 1", date(2025, 1, 1)),
        ],
    )


def test_release_model_name_keeps_only_model_announcements():
    assert release_model_name("Introducing GPT-6.1 Sol", OPENAI) == "GPT-6.1 Sol"
    assert (
        release_model_name("Introducing Mistral Large 4 | Mistral", MISTRAL)
        == "Mistral Large 4"
    )
    assert release_model_name(
        "Gemini 4 Argon: our next era of frontier intelligence", OPENAI_GEMINI
    ) == ("Gemini 4 Argon")
    assert release_model_name("🚀 DeepSeek-V4-Pro GA Release", DEEPSEEK) == (
        "DeepSeek-V4-Pro"
    )
    assert release_model_name("Introducing Magistral Medium", MISTRAL) == (
        "Magistral Medium"
    )
    assert release_model_name(
        "Timestral: Mistral's time-series foundation models", MISTRAL
    ) == ("Timestral")
    for headline in (
        "Asana cuts model costs 76x in browser tests with GPT-6.1 Sol",
        "A model guide for the GPT-6 family",
        "GPT-6 and Intelligent UI for everyone",
        "Mistral AI raises 2B to build compute",
        "Introducing dots",
        "Introducing Mistral",
        "Mistral Large",
    ):
        source = MISTRAL if "Mistral" in headline else OPENAI
        assert release_model_name(headline, source) is None, headline
    # A bare known family or a name outside the "-stral" convention is a
    # product page, not a new family.
    for headline in (
        "Magistral: reasoning for everyone",
        "Spaces: A CLI Built for Humans and Agents",
        "Timestral update for everyone",
    ):
        assert release_model_name(headline, MISTRAL) is None, headline


def test_parsers_read_rss_atom_and_article_metadata():
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
    <title>Gemini 4 &amp; more</title><link href="https://example.com/g4"/>
    <published>2026-10-01T00:00:00Z</published></entry></feed>"""
    assert [(e.url, e.title, e.published) for e in parse_rss(atom)] == [
        ("https://example.com/g4", "Gemini 4 & more", date(2026, 10, 1))
    ]
    assert parse_article(
        PAGES["https://mistral.ai/news/mistral-large-4/"].decode()
    ) == (
        "Introducing Mistral Large 4",
        date(2026, 10, 6),
    )


def test_scan_reports_recent_releases_against_the_catalog():
    db = _session()
    feeds = FakeFeeds(PAGES)

    report = scan_model_releases(
        db,
        lookback_days=14,
        sources=(OPENAI, MISTRAL, DEEPSEEK),
        feeds=feeds,
        fetch_leaderboard=_leaderboard,
        today=TODAY,
    )

    by_name = {signal.model_name: signal for signal in report.signals}
    assert set(by_name) == {
        "Mistral Large 4",
        "Timestral",
        "GPT-6.1 Sol",
        "DeepSeek-V4.2",
        "Grok 5",
        "Claude Opus 6",
    }
    mistral = by_name["Mistral Large 4"]
    assert (mistral.status, mistral.paper_id, mistral.matched_by) == (
        "indexed",
        123033,
        "source_url",
    )
    # The vendor post wins over the duplicate leaderboard slug.
    assert mistral.lab == "Mistral AI"
    assert by_name["Claude Opus 6"].matched_by == "provider_alias"
    assert by_name["Grok 5"].status == "unindexed"
    assert by_name["GPT-6.1 Sol"].status == "unindexed"
    deepseek = by_name["DeepSeek-V4.2"]
    assert (deepseek.published, deepseek.status) == (date(2026, 10, 1), "unindexed")
    timestral = by_name["Timestral"]
    assert (timestral.published, timestral.status) == (date(2026, 10, 9), "unindexed")
    assert timestral.title == "Timestral: Mistral's time-series foundation models"
    assert len(report.unindexed) == 4
    assert report.errors == []
    assert report.sources_checked == 4
    # Old sitemap pages, non-article paths and undated slugs are never fetched.
    assert "https://mistral.ai/news/old-post/" not in feeds.requested
    assert "https://mistral.ai/pricing" not in feeds.requested
    assert "https://api-docs.deepseek.com/news/news1226" not in feeds.requested
    # The scan is read-only.
    assert not db.new and not db.dirty


def test_title_match_and_source_failures_are_reported():
    db = _session()
    db.add(
        Paper(
            id=600,
            title="Introducing GPT-6.1 Sol",
            source="external",
            source_url="https://openai.com/index/gpt-6-1-sol-system-card",
            version="v1",
            is_latest_version=True,
        )
    )
    db.add(
        Paper(
            id=601,
            title="Grok 5: Reasoning at scale",
            source="external",
            source_url="https://x.ai/news/grok-5",
            version="v1",
            is_latest_version=True,
        )
    )
    db.commit()
    pages = dict(PAGES)
    del pages[MISTRAL.url]

    report = scan_model_releases(
        db,
        sources=(OPENAI, MISTRAL),
        feeds=FakeFeeds(pages),
        fetch_leaderboard=lambda: ArtificialAnalysisLeaderboard(
            "4",
            [
                ArtificialAnalysisEntry(
                    "grok-5", "Grok 5 (Reasoning)", {"intelligence": 1.0}, TODAY
                )
            ],
        ),
        today=TODAY,
    )

    assert [(s.model_name, s.matched_by, s.paper_id) for s in report.signals] == [
        ("Grok 5", "title", 601),
        ("GPT-6.1 Sol", "title", 600),
    ]
    assert [error["source"] for error in report.errors] == [MISTRAL.url]
    assert report.to_dict()["unindexed"] == 0


WEB_HITS = [
    SearchHit(
        "https://reflection.ai/blog/introducing-beam",
        "Introducing Beam: Reflection's 501B open-weight model",
        date(2026, 10, 9),
    ),
    SearchHit(
        "https://news.example.com/reflection-beam",
        "Reflection releases Beam, a 501B open-weight model",
        date(2026, 10, 10),
    ),
    SearchHit(
        "https://news.example.com/kolibri",
        "Aleph Alpha releases Kolibri weights",
        date(2026, 10, 10),
    ),
    SearchHit(
        "https://odyssey.ml/meet-odyssey-3",
        "Meet Odyssey-3: Our Most Powerful Foundation World Model",
        date(2026, 10, 9),
    ),
]


def _release(lab, name, hit_ids, official=None, published="2026-10-09"):
    return ExtractedRelease(
        lab=lab,
        model_name=name,
        published=published,
        hit_ids=hit_ids,
        official_hit_id=official,
    )


def test_web_search_reports_releases_from_any_lab():
    db = _session()
    db.add(
        Paper(
            id=700,
            title="Meet Odyssey-3: Our Most Powerful Foundation World Model",
            source="external",
            source_url="https://odyssey.ml/blog/odyssey-3",
            version="v1",
            is_latest_version=True,
        )
    )
    db.commit()
    searches: list[tuple[str, date]] = []
    extracted: list[list[SearchHit]] = []

    def search(query: str, since: date) -> list[SearchHit]:
        searches.append((query, since))
        # Every query returns the same coverage; hits are deduplicated.
        return WEB_HITS

    def extract(hits: list[SearchHit]) -> list[ExtractedRelease]:
        extracted.append(hits)
        return [
            _release("Reflection", "Beam", [1], official=0),
            _release("Aleph Alpha", "Kolibri", [2]),
            _release("Odyssey", "Odyssey-3", [3]),
            # Uncited and invented hit ids never become signals.
            _release("Nobody", "Ghost-1", [42]),
        ]

    report = scan_model_releases(
        db,
        sources=(),
        web_search=search,
        extract_releases=extract,
        today=TODAY,
    )

    assert [query for query, _ in searches] == list(WEB_SEARCH_QUERIES)
    assert {since for _, since in searches} == {date(2026, 10, 8)}
    assert len(extracted) == 1 and extracted[0] == WEB_HITS
    by_name = {signal.model_name: signal for signal in report.signals}
    assert set(by_name) == {"Beam", "Kolibri", "Odyssey-3"}
    beam = by_name["Beam"]
    # The lab's own page is the reported URL; the earliest cited hit dates it.
    assert (beam.source, beam.url, beam.published, beam.status) == (
        WEB_SEARCH_PROVIDER,
        "https://reflection.ai/blog/introducing-beam",
        date(2026, 10, 9),
        "unindexed",
    )
    assert by_name["Kolibri"].url == "https://news.example.com/kolibri"
    assert (by_name["Odyssey-3"].matched_by, by_name["Odyssey-3"].paper_id) == (
        "title",
        700,
    )
    assert report.sources_checked == 1 and report.errors == []


def test_web_search_failure_is_reported_and_vendor_feed_wins():
    def failing_search(query: str, since: date) -> list[SearchHit]:
        raise httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=httpx.Request("POST", "https://api.exa.ai/search"),
            response=httpx.Response(429),
        )

    report = scan_model_releases(
        _session(),
        sources=(OPENAI,),
        feeds=FakeFeeds(PAGES),
        web_search=failing_search,
        extract_releases=lambda hits: [],
        today=TODAY,
    )
    assert [error["source"] for error in report.errors] == [WEB_SEARCH_PROVIDER]
    assert report.sources_checked == 2

    gpt_hit = SearchHit(
        "https://news.example.com/gpt-6-1-sol",
        "OpenAI launches GPT-6.1 Sol",
        date(2026, 10, 9),
    )
    report = scan_model_releases(
        _session(),
        sources=(OPENAI,),
        feeds=FakeFeeds(PAGES),
        web_search=lambda query, since: [gpt_hit],
        extract_releases=lambda hits: [_release("OpenAI", "GPT-6.1 Sol", [0])],
        today=TODAY,
    )
    (signal,) = report.signals
    assert (signal.source, signal.url) == (
        OPENAI.url,
        "https://openai.com/index/introducing-gpt-6-1-sol",
    )


def test_refused_extraction_is_reported_as_a_source_error():
    class RefusingResponses:
        def parse(self, **kwargs):
            return type("Response", (), {"output_parsed": None})()

    extractor = OpenAIReleaseExtractor("test-key")
    extractor.client = type("Client", (), {"responses": RefusingResponses()})()

    report = scan_model_releases(
        _session(),
        sources=(),
        web_search=lambda query, since: WEB_HITS,
        extract_releases=extractor,
        today=TODAY,
    )
    assert report.signals == []
    assert [error["source"] for error in report.errors] == [WEB_SEARCH_PROVIDER]
