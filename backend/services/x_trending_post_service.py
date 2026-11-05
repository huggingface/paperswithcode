"""Post a trending paper to the Papers with Code X account, when worth it.

Each run looks at the highest-trending recent arXiv papers with a TL;DR that
were not posted yet and posts the first one that is worth it:

* it holds a clear state of the art: first on a Papers with Code leaderboard
  with at least 5 entries, ahead of every other paper by at least 1%
  (`sota_result`); or
* a well-known lab (`NOTABLE_X_HANDLES`) is on it and its official X account
  is known.

Papers with both go first. A SOTA post states the result against the previous
best ("Congrats @lab: <model> is SOTA on <benchmark>!" when the lab is
tagged). Otherwise Luna writes the post from the abstract, TL;DR, and results;
it is kept only if it adds no number or @mention beyond those facts and opens
with a comparison or a claim, never a bare score or a small delta. The
fallback template leads with such a TL;DR sentence. When no candidate is
worth it, the slot is skipped and each reason is logged. The first PDF page is
the image, and the paper page link follows as a reply. `paper_x_posts`
records every posted paper so it is never posted twice.

X calls use OAuth 1.0a user context, whose tokens do not expire.
"""

from __future__ import annotations

import base64
import hashlib
import json
import hmac
import logging
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable
from urllib.parse import quote

import fitz
import httpx
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, aliased

from backend.models.database import (
    Dataset,
    Evaluation,
    Metric,
    Paper,
    PaperXPost,
    PaperXThread,
)
from backend.services.metric_value_service import parse_metric_value
from backend.services.x_thread_discovery_service import short_name
from backend.utils.urls import get_paper_route_identifier

logger = logging.getLogger(__name__)

X_API = "https://api.x.com/2"
CANDIDATE_WINDOW_DAYS = 14
CANDIDATES_PER_RUN = 10
SOTA_MIN_ENTRIES = 5
# The first place must beat every other paper's best by this share of it.
SOTA_MIN_MARGIN = 0.01
ORGANIZATIONS_CHECKED = 3
MAX_TAGS = 2
RESULTS_IN_FACTS = 5
ABSTRACT_CHARS = 3000
RENDER_ZOOM = 2.0
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ELLIPSIS = "…"
# Download failures, unreadable PDFs (PyMuPDF raises FileDataError, a
# RuntimeError, or low-level FzErrorBase), and PDFs without pages.
RENDER_ERRORS = (
    httpx.HTTPError,
    ValueError,
    RuntimeError,
    IndexError,
    fitz.mupdf.FzErrorBase,
)
# A sentence ends at . ! ? followed by whitespace, except after "vs." etc.
_SENTENCE_END = re.compile(
    r"(?<!\bvs\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bal\.)(?<=[.!?])\s+"
)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_MENTION = re.compile(r"@[A-Za-z0-9_]{1,15}")
_X_HANDLE = re.compile(r"[A-Za-z0-9_]{1,15}")
_HF_X_LINK = re.compile(
    r'href="https://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]{1,15})/?"'
)
_IGNORED_HANDLES = {"huggingface", "home", "intent", "share", "x", "twitter"}
# Concrete results: standalone numbers (not "Qwen3" or "27B"), percentages and
# multiples count double, plus comparison words.
_STANDALONE_NUMBER = re.compile(r"(?<![\w.-])\d+(?:\.\d+)?(?![\w.]*[A-Za-z])")
_MEASURE = re.compile(
    r"(?<![\w.-])\d+(?:\.\d+)?\s?(?:%|×|x\b|-fold|points?\b|pp\b|times\b)"
)
_CLAIM = re.compile(
    r"\b(?:outperform|beat|exceed|surpass|state-of-the-art|sota|best|first|"
    r"faster|fewer|cuts?|reduc|doubl|halv|match)",
    re.IGNORECASE,
)
# A lead with a number must compare it with something.
_COMPARISON = re.compile(
    r"\b(?:outperform\w*|beat(?:s|ing|en)?|exceed\w*|surpass\w*|ahead of|than|"
    r"versus|vs|compared|state-of-the-art|sota|first|best|tops?|topped|topping|"
    r"leads?|leading|match(?:es|ed|ing)?|rival(?:s|ed|ing)?|record)\b",
    re.IGNORECASE,
)
_SMALL_DELTA = re.compile(
    r"(?:\+\s?|\bby\s+)0\.\d+\s?(?:points?|pp|%|percent)", re.IGNORECASE
)
# Well-known labs and companies, by organization slug, with their official X
# account. Each handle was looked up on the X API (2026-11-05): a business or
# blue-verified account named after the organization. With None, the handle
# has to come from `organization_x_handle`.
NOTABLE_X_HANDLES: dict[str, str | None] = {
    "adobe": "AdobeResearch",
    "alibabagroup": "AlibabaGroup",
    "alibabatongyilab": "Ali_TongyiLab",
    "allenai": "allen_ai",
    "amazon": "AmazonScience",
    "amd": "AIatAMD",
    "antgroup": "AntGroup",
    "anthropic": "AnthropicAI",
    "apple": "Apple",
    "baidu": "Baidu_Inc",
    "black-forest-labs": "bfl_ai",
    "bytedance": "ByteDanceOSS",
    "bytedance-seed": None,
    "coherelabs": "Cohere_Labs",
    "databricks": "databricks",
    "deepmind": "GoogleDeepMind",
    "deepseek-ai": "deepseek_ai",
    "facebook": "AIatMeta",
    "google": "GoogleResearch",
    "huawei": "Huawei",
    "huawei-noah": None,
    "huggingface": "huggingface",
    "ibm": "IBMResearch",
    "ibm-research": "IBMResearch",
    "inclusionai": None,
    "intel": None,
    "klingteam": "Kling_ai",
    "kuaishou": None,
    "lgai-exaone": "LG_AI_Research",
    "liquidai": "liquidai",
    "meituan": "Meituan_LongCat",
    "microsoft": "MSFTResearch",
    "microsoftresearch": "MSFTResearch",
    "minimaxai": "MiniMax_AI",
    "mistralai": "MistralAI",
    "moonshotai": "Kimi_Moonshot",
    "naver": None,
    "naver-ai": None,
    "nvidia": "NVIDIAAIDev",
    "openai": "OpenAI",
    "perplexity-ai": "perplexity_ai",
    "qwen": "Alibaba_Qwen",
    "sakanaai": "SakanaAILabs",
    "salesforce": "SFResearch",
    "samsung": None,
    "samsungresearch": "samsungresearch",
    "servicenow": "ServiceNowRSRCH",
    "shanghaiailab": None,
    "snap-research": "Snap",
    "snowflake": "Snowflake",
    "sony": None,
    "stabilityai": "StabilityAI",
    "stepfun-ai": "StepFun_ai",
    "tencent": None,
    "tencent-hunyuan": "TencentHunyuan",
    "xai-org": None,
    "xiaohongshuai": None,
    "xiaomi": None,
    "xiaomimimo": "XiaomiMiMo",
    "zai-org": "Zai_org",
}
_PRONOUN_START = re.compile(r"(?:It|Its|They|Their|This|These)\b")
# Luna aims this far below the limit, since it miscounts characters.
LUNA_MARGIN = 30
LUNA_MODEL = "gpt-6-luna"
RESPONSES_URL = "https://api.openai.com/v1/responses"
LUNA_INSTRUCTIONS = """You write posts about new papers for the Papers with \
Code account on X, read by ML researchers and engineers.

Write one post about the paper in the facts, in this shape:

1. One sentence with the paper's single most striking concrete result or \
claim: a number, a head-to-head comparison, or a ranking, stated so a \
researcher scrolling past would stop. Name the model or method in it.
2. Optionally one short sentence of supporting detail.
3. A last line crediting the paper: its short name, then "by" and every \
handle in `mentions` (for example "Apriel Voice 27B by @ServiceNowRSRCH"), or \
"from <organization>" without mentions, or the name alone without either.

The first sentence must compare: against a named baseline, prior model, or \
ranking ("beats GPT-6 by 4.9 points", "ranks first of 27 on MDPBench"), or \
state a claim without numbers. Never lead with a bare score ("scores 79.82 on \
VBench") or a small delta ("+0.3 points"). Plain \
text, no Markdown; plain, specific, confident; no hype words \
("groundbreaking", "game-changer", "revolutionary"), no emojis, hashtags, \
links, or questions to the reader.

Hard rules: use only numbers that appear in the facts, exactly as written \
(write "first", not "1st"); state nothing that is not in the facts. Use each \
handle in `mentions` exactly once and no other @mention. Put an empty line \
between sentences and before the last line. Stay within the character limit. \
Output only the post text."""


@dataclass(frozen=True)
class XCredentials:
    consumer_key: str
    consumer_secret: str
    access_token: str
    access_token_secret: str


def _percent(value: str) -> str:
    return quote(value, safe="-._~")


def oauth1_header(
    method: str,
    url: str,
    credentials: XCredentials,
    *,
    nonce: str | None = None,
    timestamp: str | None = None,
) -> str:
    """OAuth 1.0a HMAC-SHA1 header; JSON and multipart bodies are not signed."""
    params = {
        "oauth_consumer_key": credentials.consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": credentials.access_token,
        "oauth_version": "1.0",
    }
    normalized = "&".join(
        f"{_percent(key)}={_percent(value)}" for key, value in sorted(params.items())
    )
    base = "&".join([method.upper(), _percent(url), _percent(normalized)])
    key = (
        f"{_percent(credentials.consumer_secret)}&"
        f"{_percent(credentials.access_token_secret)}"
    )
    digest = hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    params["oauth_signature"] = base64.b64encode(digest).decode()
    return "OAuth " + ", ".join(
        f'{_percent(key)}="{_percent(value)}"' for key, value in sorted(params.items())
    )


class XPoster:
    """Minimal X API v2 client for image uploads and posts."""

    def __init__(self, credentials: XCredentials, client: httpx.Client) -> None:
        self.credentials = credentials
        self.client = client

    def _post(self, url: str, **kwargs: Any) -> dict:
        headers = {"Authorization": oauth1_header("POST", url, self.credentials)}
        response = self.client.post(url, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(
                f"X HTTP {response.status_code} for {url}: {response.text[:500]}"
            )
        return response.json()

    def upload_image(self, image: bytes) -> str:
        body = self._post(
            f"{X_API}/media/upload",
            files={"media": ("page.png", image, "image/png")},
            data={"media_category": "tweet_image"},
        )
        return body["data"]["id"]

    def post(
        self,
        text: str,
        *,
        media_ids: list[str] | None = None,
        reply_to: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {"text": text}
        if media_ids:
            payload["media"] = {"media_ids": media_ids}
        if reply_to:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to}
        return self._post(f"{X_API}/tweets", json=payload)["data"]["id"]


def weighted_length(text: str) -> int:
    """X's weighted character count: Latin and common punctuation count 1, else 2."""
    return sum(
        1
        if ord(char) <= 0x10FF
        or 0x2000 <= ord(char) <= 0x200D
        or 0x2010 <= ord(char) <= 0x201F
        or 0x2032 <= ord(char) <= 0x2037
        else 2
        for char in text
    )


def _truncate(text: str, limit: int) -> str:
    """Cut at a word boundary so the result plus an ellipsis fits `limit`."""
    limit -= weighted_length(ELLIPSIS)
    while text and weighted_length(text) > limit:
        cut = text.rfind(" ")
        text = text[:cut] if cut > 0 else text[:-1]
    return text.rstrip(" ,;:") + ELLIPSIS


def sentences(text: str) -> list[str]:
    return [part for part in _SENTENCE_END.split(" ".join(text.split())) if part]


def paragraphs(text: str) -> str:
    """One sentence per paragraph, separated by an empty line (reads best on X)."""
    return "\n\n".join(
        sentence
        for block in re.split(r"\n\s*\n", text.strip())
        for sentence in sentences(block)
    )


def paper_label(title: str, *, limit: int = 48) -> str:
    """The name before the colon ("MiMo-V2.6"), else the title, shortened."""
    title = " ".join(title.split())
    name = short_name(title) or title.split(":", 1)[0].strip()
    if ":" in title and len(name) <= 30:
        return name
    if len(title) <= limit:
        return title
    return title[: title.rfind(" ", 0, limit)].rstrip(" ,;:-") + ELLIPSIS


def fmt(value: float) -> str:
    """Compact metric value: at most two decimals, no trailing zeros."""
    text = f"{value:.1f}" if abs(value) >= 100 else f"{value:.2f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def good_lead(sentence: str) -> bool:
    """No small delta, and a number only next to a comparison."""
    if _SMALL_DELTA.search(sentence):
        return False
    return not _STANDALONE_NUMBER.search(sentence) or bool(_COMPARISON.search(sentence))


def result_score(sentence: str) -> int:
    """How many concrete results a sentence states."""
    return (
        len(_STANDALONE_NUMBER.findall(sentence))
        + len(_MEASURE.findall(sentence))
        + len(_CLAIM.findall(sentence))
    )


def striking_sentence(text: str) -> str | None:
    """The first good lead (`good_lead`) with the most concrete results.

    A sentence that opens with a pronoun ("It scores…") reads poorly on its
    own, so it needs more results than one that names its subject.
    """

    def score(sentence: str) -> int:
        return result_score(sentence) - 2 * bool(_PRONOUN_START.match(sentence))

    leads = [sentence for sentence in sentences(text) if good_lead(sentence)]
    return max(leads, key=score, default=None)


def credit_line(title: str, handles: list[str], organization: str | None) -> str:
    label = paper_label(title)
    if handles:
        return f"{label} by " + " and ".join(f"@{handle}" for handle in handles)
    return f"{label} from {organization}" if organization else label


def compose_post(
    title: str,
    tldr: str,
    *,
    handles: list[str] | None = None,
    organization: str | None = None,
    max_chars: int,
) -> str | None:
    """The TL;DR's most striking good lead, then the paper and its organization.

    The sentence is shortened at a word to fit `max_chars`. Without a good
    lead there is nothing worth posting.
    """
    credit = credit_line(title, handles or [], organization)
    hook = striking_sentence(tldr)
    if not hook:
        return None
    text = f"{hook}\n\n{credit}"
    if weighted_length(text) <= max_chars:
        return text
    room = max_chars - weighted_length(f"\n\n{credit}")
    if room >= 60:
        return f"{_truncate(hook, room)}\n\n{credit}"
    return _truncate(hook, max_chars)


def numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(text))


def accept_post(text: str, *, facts: str, mentions: list[str], max_chars: int) -> bool:
    """A written post uses only the facts' numbers and exactly the given mentions."""
    return (
        bool(text)
        and weighted_length(text) <= max_chars
        and numbers(text) <= numbers(facts)
        and set(_MENTION.findall(text)) == {f"@{handle}" for handle in mentions}
        and "http" not in text
        and "#" not in text
        and good_lead(sentences(text.split("\n\n", 1)[0])[0])
    )


def luna_text(
    client: httpx.Client,
    *,
    api_key: str,
    instructions: str,
    prompt: str,
    cache_name: str,
) -> str:
    """Luna's answer; raises httpx.HTTPError, ValueError, KeyError, or TypeError."""
    response = client.post(
        RESPONSES_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": LUNA_MODEL,
            "instructions": instructions,
            "input": prompt,
            "store": False,
            "max_output_tokens": 300,
            "reasoning": {"effort": "none"},
            "prompt_cache_key": cache_name,
        },
    )
    body = response.raise_for_status().json()
    return "".join(
        part["text"]
        for item in body["output"]
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    ).strip()


@dataclass
class Row:
    evaluation_id: int
    paper_id: int
    model: str
    value: float


def leaderboard_rows(db: Session, dataset_id: int, metric: str) -> list[Row]:
    """Every result for this benchmark and metric, across all tasks.

    A benchmark can have a leaderboard under several tasks (IFEval under both
    Instruction Following and Language Modeling); a new SOTA has to beat them
    all, or the site itself would contradict the post.
    """
    rows = db.execute(
        select(
            Evaluation.id,
            Evaluation.paper_id,
            Evaluation.model_name,
            Evaluation.metrics[metric].astext,
        ).where(
            Evaluation.dataset_id == dataset_id,
            Evaluation.metrics.has_key(metric),
        )
    ).all()
    parsed = [
        Row(row[0], row[1], row[2] or "Unnamed model", parse_metric_value(row[3]))
        for row in rows
    ]
    return [row for row in parsed if row.value is not None]


@dataclass
class Sota:
    """A paper's first place on a leaderboard, against the previous best."""

    benchmark: str
    metric: str
    model: str
    value: float
    previous_model: str
    previous_value: float
    entries: int
    margin: float  # share of the previous best


def sota_result(db: Session, paper: Paper) -> Sota | None:
    """The paper's clearest state of the art, if any.

    It has to rank first on a leaderboard with at least `SOTA_MIN_ENTRIES`
    results and beat every other paper's best by `SOTA_MIN_MARGIN` of it.
    """
    best: Sota | None = None
    for evaluation, benchmark in db.execute(
        select(Evaluation, Dataset.name)
        .join(Dataset, Dataset.id == Evaluation.dataset_id)
        .where(
            Evaluation.paper_id == paper.id,
            Evaluation.best_rank == 1,
            Evaluation.best_metric.is_not(None),
        )
    ).all():
        metric = evaluation.best_metric
        rows = leaderboard_rows(db, evaluation.dataset_id, metric)
        mine = next((row for row in rows if row.evaluation_id == evaluation.id), None)
        others = [row for row in rows if row.paper_id != paper.id]
        if len(rows) < SOTA_MIN_ENTRIES or mine is None or not others:
            continue
        direction = db.scalar(select(Metric.direction).where(Metric.name == metric))
        sign = -1 if direction == "lower_is_better" else 1
        previous = max(others, key=lambda row: sign * row.value)
        gain = sign * (mine.value - previous.value)
        if previous.value:
            margin = gain / abs(previous.value)
        else:
            margin = float("inf") if gain > 0 else 0.0
        if margin < SOTA_MIN_MARGIN or (best and margin <= best.margin):
            continue
        best = Sota(
            benchmark=benchmark,
            metric=metric,
            model=mine.model,
            value=mine.value,
            previous_model=previous.model,
            previous_value=previous.value,
            entries=len(rows),
            margin=margin,
        )
    return best


def sota_post(sota: Sota, handles: list[str], *, max_chars: int) -> str:
    """The SOTA against the previous best, congratulating a tagged lab."""
    result = (
        f"{fmt(sota.value)} {sota.metric}, ahead of {sota.previous_model} at "
        f"{fmt(sota.previous_value)}."
    )
    if handles:
        mentions = " and ".join(f"@{handle}" for handle in handles)
        text = (
            f"Congrats {mentions}: {sota.model} is SOTA on {sota.benchmark}!"
            f"\n\nIt scores {result}"
        )
    else:
        text = (
            f"New SOTA on {sota.benchmark}: {sota.model} scores {result}\n\n"
            f"First of {sota.entries} on the Papers with Code leaderboard."
        )
    if weighted_length(text) <= max_chars:
        return text
    return _truncate(text.split("\n\n", 1)[0], max_chars)


@dataclass
class Draft:
    """What a post about one paper may say."""

    paper: Paper
    handles: list[str]
    organization: str | None
    results: list[dict[str, Any]]
    sota: Sota | None = None

    def facts(self) -> str:
        return json.dumps(
            {
                "title": " ".join(self.paper.title.split()),
                "tldr": self.paper.tldr or "",
                "abstract": (self.paper.abstract or "")[:ABSTRACT_CHARS],
                "organization": self.organization,
                "mentions": [f"@{handle}" for handle in self.handles],
                "papers_with_code_results": self.results,
            },
            ensure_ascii=False,
        )

    def template(self, max_chars: int) -> str | None:
        if self.sota:
            return sota_post(self.sota, self.handles, max_chars=max_chars)
        return compose_post(
            self.paper.title,
            self.paper.tldr or "",
            handles=self.handles,
            organization=self.organization,
            max_chars=max_chars,
        )


def write_with_luna(
    client: httpx.Client, draft: Draft, *, api_key: str, max_chars: int
) -> str | None:
    """Luna's post about the paper, or the template if it fails a check.

    SOTA posts keep their template, which states the result exactly.
    """
    if draft.sota:
        return draft.template(max_chars)
    facts = draft.facts()
    try:
        text = luna_text(
            client,
            api_key=api_key,
            instructions=LUNA_INSTRUCTIONS,
            prompt=f"Character limit: {max_chars - LUNA_MARGIN}\n\nFacts:\n{facts}",
            cache_name="pwc-x-trending-v3",
        )
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        logger.warning("x_trending_write_failed paper=%s %s", draft.paper.id, error)
        return draft.template(max_chars)
    text = paragraphs(text)
    if accept_post(text, facts=facts, mentions=draft.handles, max_chars=max_chars):
        return text
    logger.warning(
        "x_trending_write_rejected paper=%s text=%s", draft.paper.id, json.dumps(text)
    )
    return draft.template(max_chars)


def hf_org_x_handle(hf_slug: str) -> str | None:
    """The X account an organization links from its Hugging Face page."""
    try:
        response = httpx.get(f"https://huggingface.co/{hf_slug}", timeout=15)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    handles = {
        handle
        for handle in _HF_X_LINK.findall(response.text)
        if handle.casefold() not in _IGNORED_HANDLES
    }
    return handles.pop() if len(handles) == 1 else None


def paper_threads(db: Session, paper_id: int) -> list[tuple[str, str | None]]:
    """(handle, name) of the reviewed X threads linked to a paper."""
    return [
        (handle, name)
        for handle, name in db.execute(
            select(PaperXThread.author_handle, PaperXThread.author_name)
            .where(PaperXThread.paper_id == paper_id)
            .order_by(PaperXThread.position)
        ).all()
    ]


def organization_x_handle(
    organization: Any,
    threads: list[tuple[str, str | None]],
    fetch_org_handle: Callable[[str], str | None],
) -> str | None:
    """The organization's own X account, never guessed from its name.

    A linked X thread (reviewed as the paper's own) posted by an account named
    after the organization ("ServiceNow AI Research" for ServiceNow), else the
    single X link on the organization's Hugging Face page.
    """
    names = {organization.name.casefold(), (organization.slug or "").casefold()}
    names.discard("")

    def named_after(handle: str, name: str | None) -> bool:
        name = (name or "").casefold()
        return handle.casefold() in names or any(
            name == org or name.startswith(f"{org} ") for org in names
        )

    handle = next((h for h, name in threads if named_after(h, name)), None)
    if handle is None and organization.hf_slug:
        handle = fetch_org_handle(organization.hf_slug)
    return handle if handle and _X_HANDLE.fullmatch(handle) else None


def notable_handles(
    db: Session, paper: Paper, fetch_org_handle: Callable[[str], str | None]
) -> list[str]:
    """Verified X accounts of the paper's well-known labs, at most two."""
    notable = [
        organization
        for organization in paper.organizations
        if organization.slug in NOTABLE_X_HANDLES
    ]
    if not notable:
        return []
    threads = paper_threads(db, paper.id)
    handles: list[str] = []
    for organization in notable[:ORGANIZATIONS_CHECKED]:
        handle = NOTABLE_X_HANDLES[organization.slug] or organization_x_handle(
            organization, threads, fetch_org_handle
        )
        if handle and handle.casefold() not in {h.casefold() for h in handles}:
            handles.append(handle)
    return handles[:MAX_TAGS]


def paper_results(db: Session, paper_id: int) -> list[dict[str, Any]]:
    """The paper's best-ranked Papers with Code leaderboard results."""
    peer = aliased(Evaluation)
    entries = (
        select(func.count(peer.id))
        .where(
            peer.dataset_id == Evaluation.dataset_id,
            peer.task_id == Evaluation.task_id,
            peer.metrics.has_key(Evaluation.best_metric),
        )
        .correlate(Evaluation)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Evaluation, Dataset.name, entries)
        .join(Dataset, Dataset.id == Evaluation.dataset_id)
        .where(
            Evaluation.paper_id == paper_id,
            Evaluation.best_rank.is_not(None),
            Evaluation.best_metric.is_not(None),
        )
        .order_by(Evaluation.best_rank, Evaluation.id)
        .limit(RESULTS_IN_FACTS)
    ).all()
    return [
        {
            "benchmark": name,
            "model": evaluation.model_name,
            "metric": evaluation.best_metric,
            "value": str(evaluation.metrics.get(evaluation.best_metric)),
            "rank": evaluation.best_rank,
            "leaderboard_entries": count,
        }
        for evaluation, name, count in rows
    ]


def render_first_page(pdf: bytes) -> bytes:
    """Render page one as PNG, lowering the resolution until it fits X's limit."""
    zoom = RENDER_ZOOM
    with fitz.open(stream=pdf, filetype="pdf") as document:
        page = document[0]
        while True:
            image = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
            if len(image) <= MAX_IMAGE_BYTES or zoom <= 1:
                return image
            zoom -= 0.25


def paper_url(paper: Paper) -> str:
    route = get_paper_route_identifier(paper.source, paper.arxiv_id, paper.id)
    return f"https://paperswithcode.co/paper/{route}"


def candidate_papers(db: Session, *, today: date, limit: int) -> list[Paper]:
    """Recent trending arXiv papers with a TL;DR that were never posted."""
    since = today - timedelta(days=CANDIDATE_WINDOW_DAYS)
    return list(
        db.scalars(
            select(Paper)
            .where(
                Paper.is_latest_version,
                Paper.source == "arxiv",
                Paper.arxiv_id.is_not(None),
                Paper.date_published >= since,
                Paper.trending_score > 0,
                func.length(func.trim(Paper.tldr)) > 0,
                ~exists().where(PaperXPost.paper_id == Paper.id),
            )
            .order_by(Paper.trending_score.desc(), Paper.id.desc())
            .limit(limit)
        )
    )


@dataclass
class PostReport:
    dry_run: bool
    paper_id: int | None = None
    arxiv_id: str | None = None
    text: str | None = None
    template: str | None = None
    handles: list[str] = field(default_factory=list)
    url: str | None = None
    post_id: str | None = None
    reply_id: str | None = None
    reason: str | None = None
    skipped: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "skipped": self.skipped,
            "dry_run": self.dry_run,
            "paper_id": self.paper_id,
            "arxiv_id": self.arxiv_id,
            "text": self.text,
            "template": self.template,
            "handles": self.handles,
            "url": self.url,
            "post_id": self.post_id,
            "reply_id": self.reply_id,
            "errors": self.errors,
        }


def worth_posting(sota: Sota | None, handles: list[str]) -> str | None:
    if sota and handles:
        return "sota_and_notable_lab"
    if sota:
        return "sota"
    if handles:
        return "notable_lab"
    return None


def post_trending_paper(
    db: Session,
    *,
    poster: XPoster | None,
    fetch_pdf: Callable[[Paper], bytes],
    max_chars: int,
    write: Callable[[Draft], str | None] | None = None,
    find_handles: Callable[[Paper], list[str]] | None = None,
    find_results: Callable[[Paper], list[dict[str, Any]]] | None = None,
    find_sota: Callable[[Paper], Sota | None] | None = None,
    today: date | None = None,
    save_image: Callable[[bytes], None] | None = None,
) -> PostReport:
    """Post the top trending paper worth posting; without a poster, only preview.

    Candidates with neither a clear SOTA nor a verified well-known lab are
    skipped, as are those without a good lead sentence or whose PDF cannot be
    fetched or rendered; `report.skipped` says why. Papers with both a SOTA and
    a tagged lab go first, then trending order. When none is left, the slot is
    skipped. The post is recorded before the link reply, so a failed reply
    never causes the paper to be posted again.
    """
    write = write or (lambda draft: draft.template(max_chars))
    find_handles = find_handles or (
        lambda paper: notable_handles(db, paper, hf_org_x_handle)
    )
    find_results = find_results or (lambda paper: paper_results(db, paper.id))
    find_sota = find_sota or (lambda paper: sota_result(db, paper))
    report = PostReport(dry_run=poster is None)
    today = today or datetime.now(UTC).date()
    candidates = []
    for paper in candidate_papers(db, today=today, limit=CANDIDATES_PER_RUN):
        sota, handles = find_sota(paper), find_handles(paper)
        reason = worth_posting(sota, handles)
        if reason is None:
            report.skipped.append(
                {"paper_id": paper.id, "reason": "no clear SOTA or verified lab"}
            )
            continue
        candidates.append((paper, sota, handles, reason))
    candidates.sort(key=lambda candidate: candidate[3] != "sota_and_notable_lab")
    for paper, sota, handles, reason in candidates:
        draft = Draft(
            paper=paper,
            handles=handles,
            organization=paper.organizations[0].name if paper.organizations else None,
            results=find_results(paper),
            sota=sota,
        )
        text = write(draft)
        if text is None:
            report.skipped.append({"paper_id": paper.id, "reason": "no good lead"})
            continue
        try:
            image = render_first_page(fetch_pdf(paper))
        except RENDER_ERRORS as error:
            report.errors.append({"paper_id": paper.id, "error": str(error)[:300]})
            continue
        report.paper_id = paper.id
        report.arxiv_id = paper.arxiv_id
        report.reason = reason
        report.handles = handles
        report.template = draft.template(max_chars)
        report.text = text
        report.url = paper_url(paper)
        if save_image:
            save_image(image)
        if poster is None:
            return report
        media_id = poster.upload_image(image)
        report.post_id = poster.post(report.text, media_ids=[media_id])
        record = PaperXPost(
            paper_id=paper.id, post_id=report.post_id, posted_at=datetime.now(UTC)
        )
        db.add(record)
        db.commit()
        report.reply_id = poster.post(report.url, reply_to=report.post_id)
        record.reply_id = report.reply_id
        db.commit()
        return report
    logger.info(
        "x_trending_post_skipped_slot %s", json.dumps(report.skipped + report.errors)
    )
    return report
