"""Synchronize the official Physics-IQ Verified video generation leaderboard."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from math import isfinite
from typing import Any

import httpx
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
from backend.services.leaderboard_sync_ownership import managed_methodology_prefix

# physics-iq-verified.anates.ai renders the same table from data compiled into
# its Next.js bundle and exposes no JSON endpoint, so the README is canonical.
PHYSICS_IQ_README_URL = (
    "https://raw.githubusercontent.com/google-deepmind/physics-IQ-benchmark/"
    "main/README.md"
)
TASK_SLUG = "video-generation"
DATASET_SLUG = "physics-iq-verified"
METRIC_BY_TRACK = {
    "i2v": "Physics-IQ Verified Score (I2V)",
    "v2v": "Physics-IQ Verified Score (V2V)",
}
TRACK_BY_INPUT_TYPE = {"i2v": "i2v", "multiframe (v2v)": "v2v"}
MANAGED_METHODOLOGY_PREFIX = managed_methodology_prefix("Physics-IQ Verified")
LEADERBOARD_HEADING = "### Physics-IQ Verified Leaderboard"
TABLE_HEADER = (
    "#",
    "Model",
    "input type",
    "Physics-IQ verified",
    "date added (YYYY-MM-DD)",
)
MIN_EXPECTED_ROWS = 30
MAX_EXPECTED_ROWS = 300
# Refuse to touch the managed leaderboard when the reviewed subset collapses.
MIN_SELECTED_ENTRIES = 25


@dataclass(frozen=True)
class ModelIdentity:
    """A reviewed leaderboard model and the paper that introduces it."""

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


_COSMOS_3 = "2606.02800"
_MAGI_1 = ModelIdentity("MAGI-1 24B", arxiv_id="2505.13211", is_open=True)
_GEOPHYS = ModelIdentity(
    "MAGI-1 24B + GeoPhys (BoN)", arxiv_id="2606.20707", is_open=True
)
_FLUX_3 = ModelIdentity("FLUX 3 [large]", source_url="https://bfl.ai/blog/flux-3")
_ODYSSEY = "https://odyssey.systems/meet-odyssey-3"
_ODYSSEY_3 = ModelIdentity("Odyssey-3", source_url=_ODYSSEY)
_ODYSSEY_3_PRO = ModelIdentity("Odyssey-3 Pro", source_url=_ODYSSEY)
_PHYSICS_IQ_PAPER_I2V = "https://arxiv.org/abs/2606.18943"

# Exact plain-text leaderboard labels (links reduced to their text, <small>
# notes kept in parentheses) per track are the trust boundary between a README
# row and its introducing paper. Several labels may resolve to one model when
# the leaderboard lists more than one single-generation run of it; the best of
# those runs is published. Unreviewed labels are reported, never imported.
MODEL_IDENTITIES: dict[tuple[str, str], ModelIdentity] = {
    ("Odyssey-3 Pro (custom prompts)", "v2v"): _ODYSSEY_3_PRO,
    ("Odyssey-3 Pro (custom prompts)", "i2v"): _ODYSSEY_3_PRO,
    ("Odyssey-3 (custom prompts)", "v2v"): _ODYSSEY_3,
    ("Odyssey-3 (custom prompts)", "i2v"): _ODYSSEY_3,
    ("Odyssey-3 (bpp)", "v2v"): _ODYSSEY_3,
    ("Odyssey-3 (bpp)", "i2v"): _ODYSSEY_3,
    ("FLUX 3 [large] (Claude Opus 5.5 prompts)", "v2v"): _FLUX_3,
    ("FLUX 3 [large] (Claude Opus 5.5 prompts)", "i2v"): _FLUX_3,
    # GeoPhys's best-of-N reranker is the paper's own contribution, unlike the
    # third-party WMReward rerankers excluded below.
    ("Magi-1 24B + GeoPhys (BoN) (op)", "v2v"): _GEOPHYS,
    ("Magi-1 24B + GeoPhys (BoN) (op)", "i2v"): _GEOPHYS,
    ("Magi-1 24B (op)", "v2v"): _MAGI_1,
    ("Magi-1 24B (op)", "i2v"): _MAGI_1,
    ("Cosmos3-Super", "v2v"): ModelIdentity(
        "Cosmos3-Super",
        arxiv_id=_COSMOS_3,
        is_open=True,
        hf_model_url="https://huggingface.co/nvidia/Cosmos3-Super",
    ),
    ("Cosmos3-Nano", "v2v"): ModelIdentity(
        "Cosmos3-Nano",
        arxiv_id=_COSMOS_3,
        is_open=True,
        hf_model_url="https://huggingface.co/nvidia/Cosmos3-Nano",
    ),
    ("Cosmos3-Nano", "i2v"): ModelIdentity(
        "Cosmos3-Nano",
        arxiv_id=_COSMOS_3,
        is_open=True,
        hf_model_url="https://huggingface.co/nvidia/Cosmos3-Nano",
    ),
    ("Cosmos3-Super-Image2Video", "i2v"): ModelIdentity(
        "Cosmos3-Super-Image2Video",
        arxiv_id=_COSMOS_3,
        is_open=True,
        hf_model_url="https://huggingface.co/nvidia/Cosmos3-Super-Image2Video",
    ),
    ("Cosmos3-Edge", "i2v"): ModelIdentity(
        "Cosmos3-Edge",
        arxiv_id=_COSMOS_3,
        is_open=True,
        hf_model_url="https://huggingface.co/nvidia/Cosmos3-Edge",
    ),
    ("Physis-Lang (Cosmos3 Super)", "i2v"): ModelIdentity(
        "Physis-Lang (Cosmos3 Super)", arxiv_id="2609.40358"
    ),
    ("Physis-Lang (Cosmos3 Nano)", "i2v"): ModelIdentity(
        "Physis-Lang (Cosmos3 Nano)", arxiv_id="2609.40358"
    ),
    ("StrucPhysVideo-TI2V", "i2v"): ModelIdentity(
        "StrucPhysVideo-TI2V", arxiv_id="2609.18430"
    ),
    ("Seedance 2.5", "i2v"): ModelIdentity(
        "Seedance 2.5",
        source_url=(
            "https://seed.bytedance.com/en/blog/"
            "one-take-creation-flexible-referencing-introducing-seedance-2-5"
        ),
    ),
    ("MiniMax H3 (FL2VA)", "i2v"): ModelIdentity(
        "MiniMax H3",
        source_url="https://www.minimax.io/blog/minimax-h3",
        is_open=True,
        hf_model_url="https://huggingface.co/MiniMaxAI/MiniMax-H3",
    ),
    ("MiniMax H3 Max", "i2v"): ModelIdentity(
        "MiniMax H3 Max", source_url="https://blog.fal.ai/introducing-h3-max-by-fal/"
    ),
    ("Gemini Omni 1.1 Flash", "i2v"): ModelIdentity(
        "Gemini Omni 1.1 Flash",
        source_url=(
            "https://blog.google/innovation-and-ai/technology/developers-tools/"
            "build-with-gemini-omni-1-1-flash/"
        ),
    ),
    ("Gemini Omni Flash Preview", "i2v"): ModelIdentity(
        "Gemini Omni Flash Preview",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/gemini-omni/"
        ),
    ),
    ("Grok Imagine Video", "i2v"): ModelIdentity(
        "Grok Imagine Video", source_url="https://x.ai/news/grok-imagine-api"
    ),
    ("Hunyuan Video 1.5", "i2v"): ModelIdentity(
        "HunyuanVideo 1.5", arxiv_id="2511.18870", is_open=True
    ),
    # Wan 2.2 has no report of its own; its README cites the Wan paper.
    ("Wan 2.2 14B", "i2v"): ModelIdentity(
        "Wan2.2-I2V-A14B",
        arxiv_id="2503.20314",
        is_open=True,
        hf_model_url="https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B",
    ),
    ("Wan 2.2 5B", "i2v"): ModelIdentity(
        "Wan2.2-TI2V-5B",
        arxiv_id="2503.20314",
        is_open=True,
        hf_model_url="https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B",
    ),
    ("Veo 3.1 Lite", "i2v"): ModelIdentity(
        "Veo 3.1 Lite",
        source_url="https://blog.google/innovation-and-ai/technology/ai/veo-3-1-lite/",
    ),
    ("Veo 3.1 Fast", "i2v"): ModelIdentity(
        "Veo 3.1 Fast",
        source_url=("https://blog.google/innovation-and-ai/products/veo-updates-flow/"),
    ),
    ("CogVideoX-5B", "i2v"): ModelIdentity(
        "CogVideoX-5B",
        arxiv_id="2408.06072",
        is_open=True,
        hf_model_url="https://huggingface.co/zai-org/CogVideoX-5b-I2V",
    ),
    ("Kandinsky-WM 1.0", "i2v"): ModelIdentity(
        "Kandinsky-WM 1.0",
        source_url="https://github.com/kandinskylab/kandinsky-wm",
        is_open=True,
        hf_model_url=("https://huggingface.co/kandinskylab/Kandinsky-WM-1.0-I2V-5s-PH"),
    ),
    ("Sora 2", "i2v"): ModelIdentity(
        "Sora 2", source_url="https://openai.com/index/sora-2/"
    ),
    ("P-Video", "i2v"): ModelIdentity(
        "P-Video", source_url="https://www.pruna.ai/blog/p-video-fast-cheap-draft"
    ),
}


@dataclass(frozen=True)
class PhysicsIqEntry:
    position: int
    label: str
    track: str
    score: Decimal
    sd: Decimal | None
    date_added: date
    model_url: str
    report_url: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.label, self.track)

    @property
    def score_text(self) -> str:
        return f"{self.score} ± {self.sd}" if self.sd is not None else str(self.score)


def exclusion_reason(entry: PhysicsIqEntry) -> str | None:
    """Return why a row is never imported, or None when it is eligible.

    - Best-of-N runs that rerank with a third-party reward model (WMReward or
      MBR consensus) measure the reranker, not the model. GeoPhys's own BoN is
      reviewed in MODEL_IDENTITIES instead.
    - Physical Registry entries cite only an anonymous manuscript.
    """
    if "WMReward" in entry.label or "MBR consensus" in entry.label:
        return "third_party_best_of_n"
    if entry.label.startswith("Physical Registry"):
        return "anonymous_manuscript"
    return None


@dataclass
class PhysicsIqSyncStats:
    fetched: int = 0
    matched: int = 0
    created: int = 0
    changed: int = 0
    adopted: int = 0
    excluded: dict[str, int] = field(default_factory=dict)
    superseded: list[str] = field(default_factory=list)
    unreviewed: list[str] = field(default_factory=list)
    missing_papers: list[str] = field(default_factory=list)
    missing_upstream: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


_LINK = re.compile(r"\[((?:\\.|[^\]\\])*)\]\(([^)\s]+)\)")
_SMALL = re.compile(r"<small>(.*?)</small>")
_REPORTED = re.compile(r"^(?P<model>.+?)\s+reported \[here\]\((?P<url>[^)\s]+)\)$")
_SCORE = re.compile(
    r"^(?:\*\*)?(?P<score>\d{1,3}(?:\.\d+)?)(?:\*\*)?"
    r"(?:\s*<small>±\s*(?P<sd>\d+(?:\.\d+)?)</small>)?"
    r"(?:\s*<br>.*)?$"
)


def _cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        raise ValueError(f"Physics-IQ table row is malformed: {line!r}")
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _plain(markdown: str) -> str:
    text = _LINK.sub(lambda match: match.group(1), markdown)
    text = _SMALL.sub(lambda match: f" {match.group(1)} ", text)
    text = re.sub(r"\\(.)", r"\1", text)
    return " ".join(text.split())


def _entry(line: str) -> PhysicsIqEntry:
    cells = _cells(line)
    if len(cells) != len(TABLE_HEADER):
        raise ValueError(f"Physics-IQ row has {len(cells)} columns: {line!r}")
    raw_position, raw_model, raw_input, raw_score, raw_date = cells
    if not raw_position.isdigit():
        raise ValueError(f"Physics-IQ row position is invalid: {line!r}")
    reported = _REPORTED.match(raw_model)
    if reported is None:
        raise ValueError(f"Physics-IQ model cell has no report link: {line!r}")
    model_markdown = reported.group("model")
    first_link = _LINK.search(model_markdown)
    if first_link is None or first_link.start() != 0:
        raise ValueError(f"Physics-IQ model cell must start with a link: {line!r}")
    label = _plain(model_markdown)
    if not label or len(label) > 255 or ";" in label:
        raise ValueError(f"Physics-IQ model label is invalid: {label!r}")
    track = TRACK_BY_INPUT_TYPE.get(raw_input)
    if track is None:
        raise ValueError(f"Physics-IQ input type is unknown: {raw_input!r}")
    score_match = _SCORE.match(raw_score)
    if score_match is None:
        raise ValueError(f"Physics-IQ score is invalid for {label!r}: {raw_score!r}")
    score = Decimal(score_match.group("score"))
    if not isfinite(score) or not 0 <= score <= 100:
        raise ValueError(f"Physics-IQ score is outside 0-100 for {label!r}")
    sd = score_match.group("sd")
    return PhysicsIqEntry(
        position=int(raw_position),
        label=label,
        track=track,
        score=score,
        sd=Decimal(sd) if sd is not None else None,
        date_added=date.fromisoformat(raw_date),
        model_url=first_link.group(2),
        report_url=reported.group("url"),
    )


def parse_physics_iq_leaderboard(markdown: str) -> list[PhysicsIqEntry]:
    """Parse the Verified table from the README, failing on any layout change."""
    if not isinstance(markdown, str) or not markdown.strip():
        raise TypeError("Physics-IQ README response must be non-empty Markdown")
    lines = markdown.splitlines()
    try:
        start = next(
            index
            for index, line in enumerate(lines)
            if line.strip() == LEADERBOARD_HEADING
        )
    except StopIteration as exc:
        raise ValueError("Physics-IQ README has no Verified leaderboard") from exc
    header_index = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].lstrip().startswith("|") or lines[index].startswith("#")
        ),
        None,
    )
    if header_index is None or tuple(_cells(lines[header_index])) != TABLE_HEADER:
        raise ValueError("Physics-IQ Verified table header changed")
    if set(_cells(lines[header_index + 1])) != {"---"}:
        raise ValueError("Physics-IQ Verified table separator changed")

    entries: list[PhysicsIqEntry] = []
    seen: set[tuple[str, str]] = set()
    for line in lines[header_index + 2 :]:
        if not line.strip().startswith("|"):
            break
        entry = _entry(line)
        if entry.key in seen:
            raise ValueError(f"Physics-IQ README repeats {entry.key!r}")
        seen.add(entry.key)
        entries.append(entry)
    if not MIN_EXPECTED_ROWS <= len(entries) <= MAX_EXPECTED_ROWS:
        raise ValueError(
            f"Physics-IQ Verified has {len(entries)} rows; expected "
            f"{MIN_EXPECTED_ROWS}-{MAX_EXPECTED_ROWS}"
        )
    if {entry.track for entry in entries} != set(METRIC_BY_TRACK):
        raise ValueError("Physics-IQ Verified must list both i2v and v2v rows")
    return entries


def fetch_physics_iq_leaderboard(
    client: httpx.Client | None = None,
) -> list[PhysicsIqEntry]:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(20, connect=5),
        follow_redirects=True,
        headers={"User-Agent": "paperswithcode-physics-iq-verified-sync/1.0"},
    )
    try:
        response = active_client.get(PHYSICS_IQ_README_URL)
        response.raise_for_status()
        return parse_physics_iq_leaderboard(response.text)
    finally:
        if owned_client:
            active_client.close()


@dataclass(frozen=True)
class Selection:
    """Leaderboard rows to publish, one per reviewed model and track."""

    entries: dict[tuple[ModelIdentity, str], PhysicsIqEntry]
    excluded: dict[str, int]
    superseded: list[str]
    unreviewed: list[str]


def select_entries(entries: list[PhysicsIqEntry]) -> Selection:
    """Apply the import policy and keep each model's best single-generation run."""
    selected: dict[tuple[ModelIdentity, str], PhysicsIqEntry] = {}
    excluded: dict[str, int] = {}
    superseded: list[str] = []
    unreviewed: list[str] = []
    for entry in entries:
        reason = exclusion_reason(entry)
        if reason is not None:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        identity = MODEL_IDENTITIES.get(entry.key)
        if identity is None:
            unreviewed.append(f"{entry.label} [{entry.track}]")
            continue
        key = (identity, entry.track)
        current = selected.get(key)
        if current is None or entry.score > current.score:
            if current is not None:
                superseded.append(f"{current.label} [{current.track}]")
            selected[key] = entry
        else:
            superseded.append(f"{entry.label} [{entry.track}]")
    return Selection(selected, excluded, superseded, unreviewed)


_MANAGED_HEAD = re.compile(
    re.escape(MANAGED_METHODOLOGY_PREFIX)
    + r" Official leaderboard entry \"(?P<label>.+?)\" \((?P<track>i2v|v2v)\): "
    r"(?P<score>[^,]+), added (?P<added>\d{4}-\d{2}-\d{2}), "
    r"reported at (?P<report>\S+)\.(?: (?P<notes>.*))?$",
    re.DOTALL,
)


def _methodology(entry: PhysicsIqEntry, notes: str) -> str:
    head = (
        f"{MANAGED_METHODOLOGY_PREFIX} Official leaderboard entry "
        f'"{entry.label}" ({entry.track}): {entry.score_text}, added '
        f"{entry.date_added.isoformat()}, reported at {entry.report_url}."
    )
    return f"{head} {notes}" if notes else head


def _curated_notes(row: Evaluation) -> str:
    """Return the reviewer-written methodology kept beneath the managed head."""
    methodology = (row.methodology or "").strip()
    head = _MANAGED_HEAD.match(methodology)
    if head is not None:
        return head.group("notes") or ""
    return methodology


def _score_matches(stored: Any, published: Decimal) -> bool:
    """Treat a stored value as current when it rounds to the published one.

    Reviewers sometimes import the unrounded submission value (48.23) that the
    README lists at lower precision (48.2); that is not a revision.
    """
    if isinstance(stored, bool) or not isinstance(stored, (int, float)):
        return False
    exponent = published.as_tuple().exponent
    places = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    return Decimal(str(stored)).quantize(Decimal(1).scaleb(-places)) == published


class PhysicsIqSyncService:
    """Create and revise reviewed Physics-IQ Verified rows; never create papers."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        if task is None or dataset is None:
            raise RuntimeError(
                "Physics-IQ Verified task or benchmark is not configured"
            )
        metric_ids = [
            metric_id
            for (metric_id,) in self.db.query(Metric.id)
            .filter(Metric.name.in_(METRIC_BY_TRACK.values()))
            .all()
        ]
        configured = (
            self.db.query(TaskDatasetMetric)
            .filter(
                TaskDatasetMetric.task_id == task.id,
                TaskDatasetMetric.dataset_id == dataset.id,
                TaskDatasetMetric.metric_id.in_(metric_ids),
            )
            .count()
        )
        if len(metric_ids) != len(METRIC_BY_TRACK) or configured != len(metric_ids):
            raise RuntimeError("Physics-IQ Verified metrics are not linked to the task")
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

    def sync(
        self, entries: list[PhysicsIqEntry], *, commit: bool = True
    ) -> PhysicsIqSyncStats:
        selection = select_entries(entries)
        if len(selection.entries) < MIN_SELECTED_ENTRIES:
            raise RuntimeError(
                f"Physics-IQ Verified has only {len(selection.entries)} reviewed "
                "rows; refusing to update the managed leaderboard"
            )
        stats = PhysicsIqSyncStats(
            fetched=len(entries),
            excluded=selection.excluded,
            superseded=selection.superseded,
            unreviewed=selection.unreviewed,
        )
        try:
            task, dataset = self._leaderboard_identity()
            paper_ids = self._paper_ids()
            rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                )
                .order_by(Evaluation.id)
                .all()
            )
            rows_by_identity: dict[tuple[int, str, str], Evaluation] = {}
            for row in rows:
                for metric_name in row.metrics or {}:
                    rows_by_identity.setdefault(
                        (row.paper_id, row.model_name, metric_name), row
                    )
            linked_paper_ids = {
                paper_id
                for (paper_id,) in self.db.query(PaperTask.paper_id)
                .filter(PaperTask.task_id == task.id)
                .all()
            }
            now = datetime.now(UTC)
            published: set[int] = set()
            for (identity, track), entry in selection.entries.items():
                paper_id = paper_ids.get(identity.paper_key)
                if paper_id is None:
                    stats.missing_papers.append(f"{entry.label} [{track}]")
                    continue
                metric_name = METRIC_BY_TRACK[track]
                metrics = {metric_name: float(entry.score)}
                row = rows_by_identity.get((paper_id, identity.model_name, metric_name))
                if row is None:
                    row = Evaluation(
                        paper_id=paper_id,
                        task_id=task.id,
                        dataset_id=dataset.id,
                        model_name=identity.model_name,
                        metrics=metrics,
                        is_open=identity.is_open,
                        hf_model_url=identity.hf_model_url,
                        external_source_url=entry.report_url,
                        source_url=entry.report_url,
                        external=True,
                        uses_additional_data=False,
                    )
                    self.db.add(row)
                    stats.created += 1
                    notes = ""
                else:
                    # Adopted rows keep their reviewed provenance fields; only
                    # the leaderboard-owned score and methodology head change.
                    notes = _curated_notes(row)
                    managed = _MANAGED_HEAD.match((row.methodology or "").strip())
                    current = _score_matches(
                        (row.metrics or {}).get(metric_name), entry.score
                    )
                    if managed is None:
                        stats.adopted += 1
                    revised_head = row.methodology != _methodology(entry, notes)
                    if not current or (managed is not None and revised_head):
                        stats.changed += 1
                    if not current:
                        row.metrics = metrics
                row.methodology = _methodology(entry, notes)
                row.best_metric = metric_name
                row.evaluated_on = entry.date_added
                row.updated_at = now
                if paper_id not in linked_paper_ids:
                    self.db.add(
                        PaperTask(paper_id=paper_id, task_id=task.id, source="auto")
                    )
                    linked_paper_ids.add(paper_id)
                published.add(id(row))
                stats.matched += 1

            stats.missing_upstream = sorted(
                f"{row.model_name} [{row.best_metric}]"
                for row in rows
                if id(row) not in published
                and _MANAGED_HEAD.match((row.methodology or "").strip())
            )
            self.db.flush()
            ranking = EvaluationService(self.db)
            for metric_name in METRIC_BY_TRACK.values():
                ranking.recalculate_ranks(
                    task.id, dataset.id, metric_name=metric_name, commit=False
                )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise
