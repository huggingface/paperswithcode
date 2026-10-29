"""Synchronize the official Surge AI Chartography (no tools) leaderboard."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    Metric,
    Paper,
    PaperTask,
    Task,
    TaskDatasetMetric,
)
from backend.services.evaluation_service import EvaluationService
from backend.services.leaderboard_model_matching_service import (
    LeaderboardModel,
    LeaderboardModelMatcher,
)
from backend.services.leaderboard_sync_ownership import managed_methodology_prefix

SURGE_CHARTOGRAPHY_URL = "https://surgehq.ai/benchmarks/chartography"
TASK_SLUG = "image-understanding"
# Surge evaluates without tools; the with-tools `chartography` benchmark is
# curated by hand from vendor model cards and is never touched here.
DATASET_SLUG = "chartography-no-tools"
METRIC_NAME = "Pass@1"
MODEL_NAME_SUFFIX = " (no tools)"
MANAGED_METHODOLOGY_PREFIX = managed_methodology_prefix("Surge AI Chartography")
LEADERBOARD_TITLE = "Chartography Leaderboard"
# The page is a Webflow site that rejects non-browser user agents.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36 paperswithcode-surge-chartography-sync/1.0"
)
MIN_EXPECTED_ROWS = 25
MAX_EXPECTED_ROWS = 400
# Refuse to touch the managed leaderboard when the reviewed subset collapses.
MIN_SELECTED_ENTRIES = 30


@dataclass(frozen=True)
class ModelIdentity:
    """A reviewed leaderboard model and the paper that introduces it.

    `model_name` is the catalog name without the " (no tools)" suffix that
    every row on this benchmark carries.
    """

    model_name: str
    arxiv_id: str | None = None
    source_url: str | None = None
    is_open: bool = False
    hf_model_url: str | None = None

    def __post_init__(self) -> None:
        if (self.arxiv_id is None) == (self.source_url is None):
            raise ValueError("ModelIdentity requires exactly one paper identity")

    @property
    def paper_key(self) -> str:
        return self.arxiv_id or self.source_url or ""

    @property
    def row_model_name(self) -> str:
        return f"{self.model_name}{MODEL_NAME_SUFFIX}"


_GEMINI_BLOG = "https://blog.google/innovation-and-ai/models-and-research/gemini-models"
_GPT_5_6 = "https://openai.com/index/gpt-5-6/"
_GPT_6 = "https://openai.com/index/introducing-gpt-6-sol-and-luna/"

# Exact Surge model labels (provider + model, without the reasoning
# configuration) are the trust boundary between a leaderboard row and its
# introducing paper. Model names follow the catalog, reviewed against the 41
# rows hand-imported on 2026-10-17. Other labels are matched automatically when
# the catalog names them unambiguously, and otherwise handed to the release
# radar.
MODEL_IDENTITIES: dict[str, ModelIdentity] = {
    "Gemini 4 Argon": ModelIdentity(
        "Gemini 4 Argon", source_url=f"{_GEMINI_BLOG}/gemini-4-argon/"
    ),
    "GPT 6 Astra": ModelIdentity(
        "GPT-6 Astra", source_url="https://openai.com/index/gpt-6-astra/"
    ),
    "Claude Opus 5.5": ModelIdentity(
        "Claude Opus 5.5", source_url="https://www.anthropic.com/claude-opus-5-5"
    ),
    "GPT 6 Sol": ModelIdentity("GPT-6 Sol", source_url=_GPT_6),
    "Claude Fable 5.1": ModelIdentity(
        "Claude Fable 5.1",
        source_url="https://www.anthropic.com/claude-fable-and-mythos-5-1",
    ),
    "GPT 5.6 Sol": ModelIdentity("GPT-5.6 Sol", source_url=_GPT_5_6),
    "Gemini 3.8 Flash": ModelIdentity(
        "Gemini 3.8 Flash", source_url=f"{_GEMINI_BLOG}/3-8-flash-and-3-8-flash-cyber/"
    ),
    "Gemini 3.7 Flash": ModelIdentity(
        "Gemini 3.7 Flash",
        source_url=f"{_GEMINI_BLOG}/introducing-gemini-3-7-flash/",
    ),
    "Claude Fable 5": ModelIdentity(
        "Claude Fable 5",
        source_url="https://www.anthropic.com/news/claude-fable-5-mythos-5",
    ),
    "Gemini 3.6 Flash": ModelIdentity(
        "Gemini 3.6 Flash",
        source_url=f"{_GEMINI_BLOG}/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/",
    ),
    "GPT 5.6 Terra": ModelIdentity("GPT-5.6 Terra", source_url=_GPT_5_6),
    "Muse Spark 1.2": ModelIdentity(
        "Muse Spark 1.2",
        source_url="https://developer.meta.com/ai/resources/blog/build-with-muse-code/",
    ),
    "GPT 5.6 Luna": ModelIdentity("GPT-5.6 Luna", source_url=_GPT_5_6),
    "GPT 5.5": ModelIdentity(
        "GPT-5.5", source_url="https://openai.com/index/introducing-gpt-5-5/"
    ),
    "GPT 5.4": ModelIdentity(
        "GPT-5.4", source_url="https://openai.com/index/introducing-gpt-5-4/"
    ),
    "GPT 6 Luna": ModelIdentity("GPT-6 Luna", source_url=_GPT_6),
    "Qwen 3.8 Max": ModelIdentity(
        "Qwen3.8-Max", source_url="https://qwen.ai/blog?id=qwen3.8", is_open=True
    ),
    "Muse Spark 1.3": ModelIdentity(
        "Muse Spark 1.3",
        source_url="https://research.meta.ai/blog/introducing-muse-spark-1-3",
    ),
    "Claude Opus 5": ModelIdentity(
        "Claude Opus 5", source_url="https://www.anthropic.com/news/claude-opus-5"
    ),
    "Kimi K3": ModelIdentity(
        "Kimi K3",
        arxiv_id="2607.24653",
        is_open=True,
        hf_model_url="https://huggingface.co/moonshotai/Kimi-K3",
    ),
    "Gemini 3.1 Pro": ModelIdentity(
        "Gemini 3.1 Pro", source_url=f"{_GEMINI_BLOG}/gemini-3-1-pro/"
    ),
    "Muse Spark 1.1": ModelIdentity(
        "Muse Spark 1.1",
        source_url="https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/",
    ),
    "Grok 4.6": ModelIdentity("Grok 4.6", source_url="https://x.ai/news/grok-4-6"),
    # The Qwen Cloud API version of the open-weight Qwen3.8-Flash-Next.
    "Qwen 3.8 Flash": ModelIdentity(
        "Qwen3.8-Flash", source_url="https://huggingface.co/Qwen/Qwen3.8-Flash-Next"
    ),
    "Muse Glimmer 30B": ModelIdentity(
        "Muse Glimmer-30B",
        arxiv_id="2610.24628",
        is_open=True,
        hf_model_url="https://huggingface.co/meta-models/Muse-Glimmer-30B",
    ),
    "Grok 4.5": ModelIdentity("Grok 4.5", source_url="https://x.ai/news/grok-4-5"),
    "Claude Sonnet 5": ModelIdentity(
        "Claude Sonnet 5", source_url="https://www.anthropic.com/news/claude-sonnet-5"
    ),
    "Claude Opus 4.7": ModelIdentity(
        "Claude Opus 4.7", source_url="https://www.anthropic.com/news/claude-opus-4-7"
    ),
    "GLM 5.3 Flash": ModelIdentity(
        "GLM-5.3-Flash",
        source_url="https://z.ai/blog/glm-5.3-flash",
        is_open=True,
        hf_model_url="https://huggingface.co/zai-org/GLM-5.3-Flash",
    ),
    "Claude Opus 4.8": ModelIdentity(
        "Claude Opus 4.8", source_url="https://www.anthropic.com/news/claude-opus-4-8"
    ),
    "Qwen 3.5 Plus": ModelIdentity(
        "Qwen3.5-Plus", source_url="https://qwen.ai/blog?id=qwen3.5"
    ),
    "Qwen 3.7 Plus": ModelIdentity(
        "Qwen3.7-Plus", source_url="https://www.qwencloud.com/models/qwen3.7-plus"
    ),
    "Grok 4.7": ModelIdentity("Grok 4.7", source_url="https://x.ai/news/grok-4-7"),
    "Grok 4.3": ModelIdentity(
        "Grok 4.3", source_url="https://docs.x.ai/developers/models/grok-4.3"
    ),
    "Kimi K2.5": ModelIdentity(
        "Kimi K2.5",
        arxiv_id="2602.02276",
        is_open=True,
        hf_model_url="https://huggingface.co/moonshotai/Kimi-K2.5",
    ),
    "Kimi K2.6": ModelIdentity(
        "Kimi K2.6",
        source_url="https://www.kimi.com/blog/kimi-k2-6",
        is_open=True,
        hf_model_url="https://huggingface.co/moonshotai/Kimi-K2.6",
    ),
    "DeepSeek V4.1 Flash": ModelIdentity(
        "DeepSeek-V4.1-Flash",
        arxiv_id="2609.19969",
        is_open=True,
        hf_model_url="https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash",
    ),
    "Gemini 3.5 Flash-Lite": ModelIdentity(
        "Gemini 3.5 Flash-Lite",
        source_url=f"{_GEMINI_BLOG}/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/",
    ),
    "Inkling": ModelIdentity(
        "Inkling",
        source_url="https://thinkingmachines.ai/news/introducing-inkling/",
        is_open=True,
        hf_model_url="https://huggingface.co/thinkingmachines/inkling",
    ),
    "Inkling Small": ModelIdentity(
        "Inkling-Small",
        source_url="https://huggingface.co/thinkingmachines/Inkling-Small",
        is_open=True,
        hf_model_url="https://huggingface.co/thinkingmachines/Inkling-Small",
    ),
    "Mistral Large 3": ModelIdentity(
        "Mistral Large 3",
        source_url="https://docs.mistral.ai/models/model-cards/mistral-large-3-25-12",
        is_open=True,
    ),
}

# Reviewed labels that are deliberately not published.
EXCLUDED_LABELS: dict[str, str] = {
    "DeepSeek V4 Flash Vision (experimental)": (
        "experimental checkpoint; its catalog paper was deleted on 2026-10-17"
    ),
}


@dataclass(frozen=True)
class SurgeEntry:
    position: int
    label: str
    configuration: str
    score: Decimal
    lab: str = ""


@dataclass
class SurgeSyncStats:
    fetched: int = 0
    matched: int = 0
    created: int = 0
    changed: int = 0
    adopted: int = 0
    excluded: list[str] = field(default_factory=list)
    # Labels outside MODEL_IDENTITIES that the catalog matched on its own.
    auto_matched: list[str] = field(default_factory=list)
    # Labels with no paper yet; each is a release signal for the radar.
    unreviewed: list[str] = field(default_factory=list)
    missing_papers: list[str] = field(default_factory=list)
    missing_upstream: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _text(node) -> str:
    return " ".join(node.get_text(" ").split())


_CONFIGURATION = re.compile(r"^(?P<model>.+?) \((?P<configuration>[^()]+)\)$")


def _split_label(brand: str, name: str) -> tuple[str, str]:
    """Join the provider and model, separating the trailing reasoning setup.

    Surge shows a model as provider + "<model> (<reasoning configuration>)"
    (e.g. "Gemini" + "4 Argon (High reasoning)"); a model without a listed
    configuration ("Mistral" + "Large 3") uses "default".
    """
    match = _CONFIGURATION.match(name)
    model, configuration = (
        (match["model"], match["configuration"]) if match else (name, "default")
    )
    # "Inkling" + "Inkling" is the model Inkling, not "Inkling Inkling".
    label = (
        model
        if model == brand or model.startswith(f"{brand} ")
        else (f"{brand} {model}")
    )
    return label, configuration


def parse_surge_chartography(html: str) -> list[SurgeEntry]:
    """Parse the server-rendered leaderboard, failing on any layout change."""
    if not isinstance(html, str) or not html.strip():
        raise TypeError("Surge AI response must be non-empty HTML")
    soup = BeautifulSoup(html, "html.parser")
    titles = [
        node
        for node in soup.select(".lead-rank-table-title")
        if _text(node) == LEADERBOARD_TITLE
    ]
    if len(titles) != 1:
        raise ValueError(
            f"Surge AI page has {len(titles)} {LEADERBOARD_TITLE!r} blocks; expected 1"
        )
    block = titles[0].find_parent(class_="lead-rank-table-list-inner")
    if block is None:
        raise ValueError("Surge AI leaderboard block layout changed")
    entries: list[SurgeEntry] = []
    seen: set[str] = set()
    for position, row in enumerate(block.select("[data-leaderboard-row]"), start=1):
        brand = row.select_one(".head-rank-table-brand")
        name = row.select_one(".head-rank-table-name")
        score = row.select_one("[data-score]")
        if brand is None or name is None or score is None:
            raise ValueError(f"Surge AI row {position} layout changed")
        # The logo's alt text ("Google logo") names the lab, when present.
        logo = row.select_one(".lead-model-logo img[alt]")
        alt = " ".join(logo["alt"].split()) if logo is not None else ""
        lab = alt.removesuffix(" logo") if alt.endswith(" logo") else ""
        label, configuration = _split_label(_text(brand), _text(name))
        if not label or len(label) > 200:
            raise ValueError(f"Surge AI row {position} is malformed: {label!r}")
        # The bar width and the visible text must agree, followed by "%".
        visible = _text(score.parent)
        try:
            value = Decimal(score["data-score"])
        except InvalidOperation as exc:
            raise ValueError(f"Surge AI score is invalid for {label!r}") from exc
        if visible.replace(" ", "") != f"{score['data-score']}%":
            raise ValueError(f"Surge AI score is not a percentage: {visible!r}")
        if not 0 <= value <= 100:
            raise ValueError(f"Surge AI score is outside 0-100 for {label!r}")
        if label in seen:
            raise ValueError(f"Surge AI lists {label!r} twice")
        seen.add(label)
        entries.append(SurgeEntry(position, label, configuration, value, lab[:200]))
    if not MIN_EXPECTED_ROWS <= len(entries) <= MAX_EXPECTED_ROWS:
        raise ValueError(
            f"Surge AI Chartography has {len(entries)} rows; expected "
            f"{MIN_EXPECTED_ROWS}-{MAX_EXPECTED_ROWS}"
        )
    return entries


def fetch_surge_chartography(client: httpx.Client | None = None) -> list[SurgeEntry]:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(30, connect=5),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        response = active_client.get(SURGE_CHARTOGRAPHY_URL)
        response.raise_for_status()
        return parse_surge_chartography(response.text)
    finally:
        if owned_client:
            active_client.close()


_MANAGED_HEAD = re.compile(
    re.escape(MANAGED_METHODOLOGY_PREFIX)
    + r' Official leaderboard entry "(?P<label>.+?)" \((?P<configuration>.+?)\): '
    r"(?P<score>[^,]+)% Pass@1, listed at (?P<url>\S+)\.(?: (?P<notes>.*))?$",
    re.DOTALL,
)


def _methodology(entry: SurgeEntry, notes: str) -> str:
    head = (
        f"{MANAGED_METHODOLOGY_PREFIX} Official leaderboard entry "
        f'"{entry.label}" ({entry.configuration}): {entry.score}% Pass@1, '
        f"listed at {SURGE_CHARTOGRAPHY_URL}."
    )
    return f"{head} {notes}" if notes else head


def _curated_notes(row: Evaluation) -> str:
    """Return the reviewer-written methodology kept beneath the managed head."""
    methodology = (row.methodology or "").strip()
    head = _MANAGED_HEAD.match(methodology)
    if head is not None:
        return head.group("notes") or ""
    return methodology


def _fraction(score: Decimal) -> Decimal:
    return score / 100


def _score_matches(stored: Any, published: Decimal) -> bool:
    """A stored fraction is current when it rounds to the published percent."""
    if isinstance(stored, bool) or not isinstance(stored, (int, float)):
        return False
    exponent = published.as_tuple().exponent
    places = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    percent = Decimal(str(stored)) * 100
    return percent.quantize(Decimal(1).scaleb(-places)) == published


class SurgeChartographySyncService:
    """Create and revise reviewed Chartography rows; never create papers."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        if task is None or dataset is None:
            raise RuntimeError("Chartography task or benchmark is not configured")
        configured = (
            self.db.query(TaskDatasetMetric)
            .join(Metric, Metric.id == TaskDatasetMetric.metric_id)
            .filter(
                TaskDatasetMetric.task_id == task.id,
                TaskDatasetMetric.dataset_id == dataset.id,
                Metric.name == METRIC_NAME,
            )
            .count()
        )
        if configured != 1:
            raise RuntimeError("Chartography Pass@1 is not linked to the task")
        return task, dataset

    def _paper_ids(self) -> dict[str, int]:
        """Resolve reviewed paper identities without ever creating papers."""
        identities = MODEL_IDENTITIES.values()
        arxiv_ids = {i.arxiv_id for i in identities if i.arxiv_id}
        source_urls = {i.source_url for i in identities if i.source_url}
        papers = (
            self.db.query(Paper.id, Paper.arxiv_id, Paper.source_url)
            .filter(
                Paper.is_latest_version,
                (Paper.arxiv_id.in_(arxiv_ids))
                | ((Paper.source == "external") & Paper.source_url.in_(source_urls)),
            )
            .order_by(Paper.id)
            .all()
        )
        resolved: dict[str, int] = {}
        for paper_id, arxiv_id, source_url in papers:
            key = arxiv_id if arxiv_id in arxiv_ids else source_url
            resolved[key] = paper_id
        return resolved

    def sync(self, entries: list[SurgeEntry], *, commit: bool = True) -> SurgeSyncStats:
        selected = [
            (MODEL_IDENTITIES[entry.label], entry)
            for entry in entries
            if entry.label in MODEL_IDENTITIES
        ]
        if len(selected) < MIN_SELECTED_ENTRIES:
            raise RuntimeError(
                f"Chartography has only {len(selected)} reviewed rows; "
                "refusing to update the managed leaderboard"
            )
        stats = SurgeSyncStats(
            fetched=len(entries),
            excluded=[e.label for e in entries if e.label in EXCLUDED_LABELS],
        )
        try:
            task, dataset = self._leaderboard_identity()
            paper_ids = self._paper_ids()
            new_entries = [
                e
                for e in entries
                if e.label not in MODEL_IDENTITIES and e.label not in EXCLUDED_LABELS
            ]
            matcher = LeaderboardModelMatcher(
                self.db,
                provider="surge-chartography",
                leaderboard_name="Surge AI Chartography",
                leaderboard_url=SURGE_CHARTOGRAPHY_URL,
            )
            matched = matcher.match(
                [LeaderboardModel(e.label, e.lab) for e in new_entries]
            )
            # (paper id, row model name, is_open, HF model URL, entry)
            published_entries = [
                (
                    paper_ids.get(identity.paper_key),
                    identity.row_model_name,
                    identity.is_open,
                    identity.hf_model_url,
                    entry,
                )
                for identity, entry in selected
            ]
            for entry in new_entries:
                if (match := matched.get(entry.label)) is None:
                    stats.unreviewed.append(entry.label)
                    continue
                # Auto-matched rows keep Surge's spelling.
                published_entries.append(
                    (
                        match.paper_id,
                        f"{entry.label}{MODEL_NAME_SUFFIX}",
                        match.is_open,
                        match.hf_model_url,
                        entry,
                    )
                )
                stats.auto_matched.append(entry.label)
            matcher.report_unmatched(
                [
                    LeaderboardModel(e.label, e.lab)
                    for e in new_entries
                    if e.label not in matched
                ]
            )
            rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                )
                .order_by(Evaluation.id)
                .all()
            )
            rows_by_identity: dict[tuple[int, str], Evaluation] = {}
            for row in rows:
                if METRIC_NAME in (row.metrics or {}):
                    rows_by_identity.setdefault((row.paper_id, row.model_name), row)
            linked_paper_ids = {
                paper_id
                for (paper_id,) in self.db.query(PaperTask.paper_id)
                .filter(PaperTask.task_id == task.id)
                .all()
            }
            now = datetime.now(UTC)
            published: set[int] = set()
            for (
                paper_id,
                model_name,
                is_open,
                hf_model_url,
                entry,
            ) in published_entries:
                if paper_id is None:
                    stats.missing_papers.append(entry.label)
                    continue
                metrics = {METRIC_NAME: float(_fraction(entry.score))}
                row = rows_by_identity.get((paper_id, model_name))
                if row is None:
                    row = Evaluation(
                        paper_id=paper_id,
                        task_id=task.id,
                        dataset_id=dataset.id,
                        model_name=model_name,
                        metrics=metrics,
                        is_open=is_open,
                        hf_model_url=hf_model_url,
                        external_source_url=SURGE_CHARTOGRAPHY_URL,
                        source_url=SURGE_CHARTOGRAPHY_URL,
                        external=True,
                        uses_additional_data=False,
                        evaluated_on=now.date(),
                    )
                    self.db.add(row)
                    rows_by_identity[(paper_id, model_name)] = row
                    stats.created += 1
                    notes = ""
                else:
                    # Adopted rows keep their reviewed provenance fields; only
                    # the leaderboard-owned score and methodology head change.
                    notes = _curated_notes(row)
                    managed = _MANAGED_HEAD.match((row.methodology or "").strip())
                    current = _score_matches(
                        (row.metrics or {}).get(METRIC_NAME), entry.score
                    )
                    if managed is None:
                        stats.adopted += 1
                    revised_head = row.methodology != _methodology(entry, notes)
                    if not current or (managed is not None and revised_head):
                        stats.changed += 1
                    if not current:
                        row.metrics = {**(row.metrics or {}), **metrics}
                row.methodology = _methodology(entry, notes)
                row.best_metric = METRIC_NAME
                row.updated_at = now
                if paper_id not in linked_paper_ids:
                    self.db.add(
                        PaperTask(paper_id=paper_id, task_id=task.id, source="auto")
                    )
                    linked_paper_ids.add(paper_id)
                published.add(id(row))
                stats.matched += 1

            stats.missing_upstream = sorted(
                row.model_name
                for row in rows
                if id(row) not in published
                and _MANAGED_HEAD.match((row.methodology or "").strip())
            )
            self.db.flush()
            EvaluationService(self.db).recalculate_ranks(
                task.id, dataset.id, metric_name=METRIC_NAME, commit=False
            )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise
