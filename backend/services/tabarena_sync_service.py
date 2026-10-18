"""Synchronize the living TabArena model leaderboard into evaluation rows."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    HfArtifact,
    Metric,
    Paper,
    PaperHfArtifact,
    PaperProjectPage,
    PaperRepository,
    ProjectPage,
    Repository,
    Task,
    TaskDatasetMetric,
)
from backend.services.evaluation_service import EvaluationService
from backend.services.leaderboard_sync_ownership import managed_methodology_prefix

TABARENA_SOURCE_URL = "https://huggingface.co/spaces/TabArena/leaderboard"
TABARENA_CSV_URL = (
    f"{TABARENA_SOURCE_URL}/resolve/main/data/entrants_models/"
    "imputation_yes/splits_all/tasks_all/datasets_all/website_leaderboard.csv"
)
DATASET_SLUG = "tabarena-v0-1"
TASK_SLUG = "tabular-learning"
METRIC_NAME = "Elo"
MANAGED_METHODOLOGY_PREFIX = managed_methodology_prefix("TabArena")
MIN_EXPECTED_ENTRIES = 50
MAX_EXPECTED_ENTRIES = 200

EXPECTED_COLUMNS = (
    "#",
    "Type",
    "TypeName",
    "Model",
    "Elo [⬆️]",
    "Elo 95% CI",
    "Score [⬆️]",
    "Rank [⬇️]",
    "Harmonic Rank [⬇️]",
    "Improvability (%) [⬇️]",
    "Median Train Time (s/1K) [⬇️]",
    "Median Predict Time (s/1K) [⬇️]",
    "Verified",
    "Imputed (%) [⬇️]",
    "Imputed",
    "Hardware",
    "MethodClass",
    "Tags",
    "Commercial",
    "License",
)
MODEL_CELL_RE = re.compile(
    r"^\[(?P<name>.+?) \((?P<variant>default|tuned|tuned \+ ensembled)\)\]"
    r"\((?P<url>https://[^)]+)\)"
    r"(?: \[(?P<imputed>[0-9]+(?:\.[0-9]+)?)% IMPUTED\])?$"
)
CI_RE = re.compile(r"^\+[0-9]+(?:\.[0-9]+)?/-[0-9]+(?:\.[0-9]+)?$")

# Exact upstream links that identify a local arXiv paper through another canonical
# publication surface. Other non-arXiv links resolve only through curated source,
# repository, project-page, or Hugging Face artifact associations in the database.
URL_ARXIV_OVERRIDES = {
    "https://www.nature.com/articles/s41586-024-08328-6": "2207.01848",
    "https://github.com/LAMDA-Tabular/TabSwift": "2606.07345",
    "https://openreview.net/pdf?id=Y00pwFyrHR": "2608.01400",
    # The release blog and subsequent technical report share this repository.
    "https://github.com/google-research/tabfm": "2609.37959",
}


@dataclass(frozen=True)
class TabArenaEntry:
    model_name: str
    model_url: str
    position: int
    elo: float
    elo_ci: str
    score: float
    average_rank: float
    harmonic_rank: float
    improvability_pct: float
    median_train_time: float
    median_predict_time: float
    verified: bool
    imputed_pct: float
    hardware: str
    tags: tuple[str, ...]


@dataclass
class TabArenaSyncStats:
    fetched: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    unmatched_sources: list[str] = field(default_factory=list)
    missing_papers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetched": self.fetched,
            "matched": self.matched,
            "created": self.created,
            "updated": self.updated,
            "deleted": self.deleted,
            "unmatched_sources": self.unmatched_sources,
            "missing_papers": self.missing_papers,
        }


def _number(raw: Any, *, field_name: str, model_name: str) -> float:
    if isinstance(raw, bool):
        raise TypeError(f"TabArena {field_name} is invalid for {model_name}")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"TabArena {field_name} is invalid for {model_name}") from exc
    if not isfinite(value):
        raise ValueError(f"TabArena {field_name} is not finite for {model_name}")
    return value


def parse_tabarena_leaderboard(csv_text: str) -> list[TabArenaEntry]:
    """Parse and strictly validate the Space's canonical default leaderboard."""
    from io import StringIO

    frame = pd.read_csv(StringIO(csv_text))
    if not set(EXPECTED_COLUMNS).issubset(frame.columns):
        raise ValueError("TabArena CSV columns do not match the published contract")
    if not MIN_EXPECTED_ENTRIES <= len(frame) <= MAX_EXPECTED_ENTRIES:
        raise ValueError(
            f"TabArena returned {len(frame)} rows; expected "
            f"{MIN_EXPECTED_ENTRIES}-{MAX_EXPECTED_ENTRIES}"
        )

    entries: list[TabArenaEntry] = []
    names: set[str] = set()
    positions: set[int] = set()
    for raw in frame.to_dict("records"):
        model_cell = raw["Model"]
        if not isinstance(model_cell, str):
            raise TypeError("TabArena model cells must be strings")
        match = MODEL_CELL_RE.fullmatch(model_cell)
        if match is None:
            raise ValueError(f"TabArena model cell is invalid: {model_cell!r}")

        model_name = f"{match.group('name')} ({match.group('variant')})"
        model_url = match.group("url")
        if len(model_name) > 255 or model_name in names:
            raise ValueError(
                "TabArena model names must be unique and at most 255 chars"
            )
        if raw["MethodClass"] != "model":
            raise ValueError(
                f"TabArena default model view contains a non-model: {model_name}"
            )

        try:
            position = int(raw["#"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"TabArena position is invalid for {model_name}") from exc
        if position < 0 or position in positions:
            raise ValueError("TabArena positions must be unique and non-negative")

        elo = _number(raw["Elo [⬆️]"], field_name="Elo", model_name=model_name)
        score = _number(raw["Score [⬆️]"], field_name="score", model_name=model_name)
        average_rank = _number(
            raw["Rank [⬇️]"], field_name="rank", model_name=model_name
        )
        harmonic_rank = _number(
            raw["Harmonic Rank [⬇️]"],
            field_name="harmonic rank",
            model_name=model_name,
        )
        improvability_pct = _number(
            raw["Improvability (%) [⬇️]"],
            field_name="improvability",
            model_name=model_name,
        )
        train_time = _number(
            raw["Median Train Time (s/1K) [⬇️]"],
            field_name="train time",
            model_name=model_name,
        )
        predict_time = _number(
            raw["Median Predict Time (s/1K) [⬇️]"],
            field_name="predict time",
            model_name=model_name,
        )
        imputed_pct = _number(
            raw["Imputed (%) [⬇️]"],
            field_name="imputed percentage",
            model_name=model_name,
        )
        if not 0 < elo < 10_000 or not 0 <= score <= 2:
            raise ValueError(
                f"TabArena quality values are out of bounds for {model_name}"
            )
        if (
            min(
                average_rank, harmonic_rank, improvability_pct, train_time, predict_time
            )
            < 0
        ):
            raise ValueError(f"TabArena values are out of bounds for {model_name}")
        if not 0 <= imputed_pct <= 100:
            raise ValueError(f"TabArena imputation is out of bounds for {model_name}")

        elo_ci = raw["Elo 95% CI"]
        if not isinstance(elo_ci, str) or CI_RE.fullmatch(elo_ci) is None:
            raise ValueError(
                f"TabArena Elo confidence interval is invalid for {model_name}"
            )
        verified_raw = str(raw["Verified"]).strip()
        if verified_raw not in {"✔️", "➖"}:
            raise ValueError(f"TabArena verification flag is invalid for {model_name}")
        hardware = raw["Hardware"]
        if not isinstance(hardware, str) or not hardware.strip():
            raise ValueError(f"TabArena hardware is invalid for {model_name}")

        suffix_pct = float(match.group("imputed") or 0)
        if abs(suffix_pct - imputed_pct) > 0.01:
            raise ValueError(f"TabArena imputation label disagrees for {model_name}")
        imputed_flag = bool(raw["Imputed"])
        if imputed_flag != (imputed_pct > 0):
            raise ValueError(f"TabArena imputation flag disagrees for {model_name}")

        tags_raw = raw["Tags"]
        tags = (
            ()
            if pd.isna(tags_raw)
            else tuple(tag for tag in str(tags_raw).split(";") if tag)
        )
        names.add(model_name)
        positions.add(position)
        entries.append(
            TabArenaEntry(
                model_name=model_name,
                model_url=model_url,
                position=position,
                elo=elo,
                elo_ci=elo_ci,
                score=score,
                average_rank=average_rank,
                harmonic_rank=harmonic_rank,
                improvability_pct=improvability_pct,
                median_train_time=train_time,
                median_predict_time=predict_time,
                verified=verified_raw == "✔️",
                imputed_pct=imputed_pct,
                hardware=hardware.strip(),
                tags=tags,
            )
        )

    if positions != set(range(len(entries))):
        raise ValueError("TabArena positions must be contiguous and start at zero")
    return sorted(entries, key=lambda entry: entry.position)


def fetch_tabarena_leaderboard(
    client: httpx.Client | None = None,
) -> list[TabArenaEntry]:
    """Fetch the canonical CSV used by the Space's default model view."""
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(30, connect=5),
        follow_redirects=True,
        headers={"User-Agent": "paperswithcode-tabarena-sync/1.0"},
    )
    try:
        response = active_client.get(TABARENA_CSV_URL)
        response.raise_for_status()
        return parse_tabarena_leaderboard(response.text)
    finally:
        if owned_client:
            active_client.close()


def _normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    path = parsed.path.rstrip("/")
    if parsed.netloc.lower() == "github.com":
        path = path.lower()
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, "")
    )


def _arxiv_id(url: str) -> str | None:
    match = re.fullmatch(r"https://arxiv\.org/abs/([^/?#]+)", _normalize_url(url))
    return match.group(1).split("v", 1)[0] if match else None


def _hf_repo_id(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.netloc.lower() != "huggingface.co":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parts[0] in {"datasets", "spaces"}:
        return None
    return "/".join(parts)


class TabArenaSyncService:
    """Replace only evaluation rows owned by the TabArena live sync."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        metric = self.db.query(Metric).filter(Metric.name == METRIC_NAME).one_or_none()
        if task is None or dataset is None or metric is None:
            raise RuntimeError("TabArena task, benchmark, or metric is not configured")
        configured = (
            self.db.query(TaskDatasetMetric)
            .filter(
                TaskDatasetMetric.task_id == task.id,
                TaskDatasetMetric.dataset_id == dataset.id,
                TaskDatasetMetric.metric_id == metric.id,
            )
            .one_or_none()
        )
        if configured is None:
            raise RuntimeError("TabArena Elo metric is not linked to the task")
        return task, dataset

    def _paper_ids_by_url(
        self, entries: list[TabArenaEntry]
    ) -> tuple[dict[str, int], set[str]]:
        raw_urls = {entry.model_url for entry in entries}
        normalized_urls = {_normalize_url(url) for url in raw_urls}
        arxiv_by_url = {
            url: _arxiv_id(url) or URL_ARXIV_OVERRIDES.get(url) for url in raw_urls
        }
        arxiv_ids = {value for value in arxiv_by_url.values() if value}
        papers_by_arxiv = {
            paper.arxiv_id: paper.id
            for paper in self.db.query(Paper)
            .filter(Paper.arxiv_id.in_(arxiv_ids), Paper.is_latest_version)
            .all()
        }

        candidates: dict[str, set[int]] = {url: set() for url in normalized_urls}
        for paper in (
            self.db.query(Paper)
            .filter(
                func.lower(Paper.source_url).in_({url.lower() for url in raw_urls}),
                Paper.is_latest_version,
            )
            .all()
        ):
            candidates[_normalize_url(paper.source_url)].add(paper.id)
        for paper_id, url in (
            self.db.query(PaperRepository.paper_id, Repository.url)
            .join(Repository, Repository.id == PaperRepository.repository_id)
            .join(Paper, Paper.id == PaperRepository.paper_id)
            .filter(
                func.lower(Repository.url).in_({url.lower() for url in raw_urls}),
                Paper.is_latest_version,
            )
            .all()
        ):
            candidates[_normalize_url(url)].add(paper_id)
        for paper_id, url in (
            self.db.query(PaperProjectPage.paper_id, ProjectPage.url)
            .join(ProjectPage, ProjectPage.id == PaperProjectPage.project_page_id)
            .join(Paper, Paper.id == PaperProjectPage.paper_id)
            .filter(ProjectPage.url.in_(raw_urls), Paper.is_latest_version)
            .all()
        ):
            candidates[_normalize_url(url)].add(paper_id)

        hf_urls = {url: _hf_repo_id(url) for url in raw_urls}
        hf_repo_ids = {repo_id for repo_id in hf_urls.values() if repo_id}
        for paper_id, repo_id in (
            self.db.query(PaperHfArtifact.paper_id, HfArtifact.repo_id)
            .join(HfArtifact, HfArtifact.id == PaperHfArtifact.hf_artifact_id)
            .join(Paper, Paper.id == PaperHfArtifact.paper_id)
            .filter(HfArtifact.repo_id.in_(hf_repo_ids), Paper.is_latest_version)
            .all()
        ):
            for url, expected_repo_id in hf_urls.items():
                if expected_repo_id == repo_id:
                    candidates[_normalize_url(url)].add(paper_id)

        resolved: dict[str, int] = {}
        missing_arxiv: set[str] = set()
        for raw_url in raw_urls:
            arxiv_id = arxiv_by_url[raw_url]
            if arxiv_id:
                paper_id = papers_by_arxiv.get(arxiv_id)
                if paper_id is None:
                    missing_arxiv.add(f"{raw_url}:{arxiv_id}")
                else:
                    resolved[raw_url] = paper_id
                continue
            matches = candidates[_normalize_url(raw_url)]
            if len(matches) == 1:
                resolved[raw_url] = next(iter(matches))
        return resolved, missing_arxiv

    def sync(
        self,
        entries: list[TabArenaEntry],
        *,
        fetched_at: datetime | None = None,
        commit: bool = True,
    ) -> TabArenaSyncStats:
        if not entries:
            raise ValueError("Refusing to synchronize an empty TabArena leaderboard")
        now = fetched_at or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        stats = TabArenaSyncStats(fetched=len(entries))

        try:
            task, dataset = self._leaderboard_identity()
            paper_ids_by_url, missing_arxiv = self._paper_ids_by_url(entries)
            stats.missing_papers.extend(sorted(missing_arxiv))
            managed_rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                    Evaluation.best_metric == METRIC_NAME,
                    Evaluation.external_source_url == TABARENA_SOURCE_URL,
                    Evaluation.methodology.like(f"{MANAGED_METHODOLOGY_PREFIX}%"),
                )
                .all()
            )
            managed_by_name = {row.model_name: row for row in managed_rows}
            upstream_names = {entry.model_name for entry in entries}

            for entry in entries:
                paper_id = paper_ids_by_url.get(entry.model_url)
                if paper_id is None:
                    if not any(
                        item.startswith(f"{entry.model_url}:") for item in missing_arxiv
                    ):
                        stats.unmatched_sources.append(
                            f"{entry.model_name}:{entry.model_url}"
                        )
                    continue

                methodology = (
                    f"{MANAGED_METHODOLOGY_PREFIX} Canonical default Space view: models only, "
                    f"all 51 datasets, all tasks and splits, imputation enabled. Upstream "
                    f"position {entry.position + 1}; Elo 95% CI {entry.elo_ci}; normalized "
                    f"score {entry.score:g}; average rank {entry.average_rank:g}; harmonic "
                    f"rank {entry.harmonic_rank:g}; improvability {entry.improvability_pct:g}%; "
                    f"median train/predict time {entry.median_train_time:g}/"
                    f"{entry.median_predict_time:g} seconds per 1K rows; hardware "
                    f"{entry.hardware}; verified={'yes' if entry.verified else 'no'}; "
                    f"imputed={entry.imputed_pct:g}%; fetched {now.isoformat()}."
                )
                row = managed_by_name.get(entry.model_name)
                if row is None:
                    row = Evaluation(
                        paper_id=paper_id,
                        task_id=task.id,
                        dataset_id=dataset.id,
                        model_name=entry.model_name,
                    )
                    self.db.add(row)
                    stats.created += 1
                else:
                    stats.updated += 1
                row.paper_id = paper_id
                row.methodology = methodology
                row.metrics = {METRIC_NAME: entry.elo}
                # Upstream imputation estimates missing benchmark scores; it is
                # not evidence that the model used additional training data.
                row.uses_additional_data = False
                row.is_open = "closed-source-api" not in entry.tags
                row.best_metric = METRIC_NAME
                row.evaluated_on = now.date()
                row.external_source_url = TABARENA_SOURCE_URL
                row.source_url = TABARENA_SOURCE_URL
                row.external = True
                row.hf_model_url = (
                    entry.model_url if _hf_repo_id(entry.model_url) else None
                )
                row.updated_at = now
                stats.matched += 1

            for row in managed_rows:
                if row.model_name not in upstream_names:
                    self.db.delete(row)
                    stats.deleted += 1

            self.db.flush()
            EvaluationService(self.db).recalculate_ranks(
                task.id,
                dataset.id,
                metric_name=METRIC_NAME,
                commit=False,
            )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise
