"""Synchronize MMEB-v2/v3 scores from the official MMEB Space."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from math import isfinite
from typing import Any
from urllib.parse import urlsplit

import httpx
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

MMEB_SPACE_URL = "https://huggingface.co/spaces/TIGER-Lab/MMEB-Leaderboard"
MMEB_CONFIG_URL = "https://tiger-lab-mmeb-leaderboard.hf.space/config"
MIN_EXPECTED_ENTRIES = 50
MAX_EXPECTED_ENTRIES = 500
MIN_RESOLVED_ENTRIES = {"v2": 5, "v3": 5}
MANAGED_METHODOLOGY_PREFIX = managed_methodology_prefix("MMEB")

LANES = {
    "v2": ("mmeb-v2", "MMEB-v2 Score", "Overall-V2"),
    "v3": ("mmeb-v3", "MMEB-v3 Score", "Overall"),
}

V3_HEADERS = (
    "Rank",
    "Models",
    "Size(B)",
    "Date",
    "Overall",
    "Overall-V3🆕",
    "Text-Overall",
    "Audio-Overall",
    "Agent-Overall",
    "Image-Overall",
    "Video-Overall",
    "Visdoc-Overall",
)
V2_HEADERS = (
    "Rank",
    "Models",
    "Size(B)",
    "Date",
    "Overall-V2",
    "Image-Overall(V2)",
    "Video-Overall",
    "Visdoc-Overall",
)

_LINK_PATTERN = re.compile(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE)


@dataclass(frozen=True)
class MmebEntry:
    model_name: str
    model_url: str
    total_params: int | None
    reported_on: date | None
    scores: dict[str, float | None]
    ranks: dict[str, int]
    is_open: bool
    hf_model_url: str | None


@dataclass
class MmebSyncStats:
    fetched: int = 0
    scored: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    unresolved_models: list[str] = field(default_factory=list)
    ambiguous_models: list[str] = field(default_factory=list)
    unmanaged_conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetched": self.fetched,
            "scored": self.scored,
            "matched": self.matched,
            "created": self.created,
            "updated": self.updated,
            "deleted": self.deleted,
            "unresolved_models": self.unresolved_models,
            "ambiguous_models": self.ambiguous_models,
            "unmanaged_conflicts": self.unmanaged_conflicts,
        }


def _model_link(value: Any) -> tuple[str, str]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("MMEB model names must be non-empty strings")
    match = _LINK_PATTERN.fullmatch(value.strip())
    if match:
        return html.unescape(match.group(2)).strip(), html.unescape(match.group(1))
    return html.unescape(value).strip(), ""


def _score(value: Any, *, model_name: str, version: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise TypeError(f"MMEB {version} score is invalid for {model_name}")
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"MMEB {version} score is invalid for {model_name}") from exc
    if not isfinite(score) or not 0 <= score <= 100:
        raise ValueError(f"MMEB {version} score is out of bounds for {model_name}")
    return score


def _params(value: Any, *, model_name: str) -> int | None:
    if value in (None, "", "unknown"):
        return None
    if isinstance(value, bool):
        raise TypeError(f"MMEB parameter count is invalid for {model_name}")
    try:
        billions = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"MMEB parameter count is invalid for {model_name}") from exc
    if not isfinite(billions) or not 0 <= billions < 1_000_000:
        raise ValueError(f"MMEB parameter count is out of bounds for {model_name}")
    return round(billions * 1_000_000_000)


def _reported_on(value: Any) -> date | None:
    if not isinstance(value, str) or value.strip().lower() == "unknown":
        return None
    try:
        year, month, day = (int(part) for part in value.strip().split("-"))
        return date(2000 + year, month, day)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"MMEB reported date is invalid: {value}") from exc


def _hf_model_url(model_url: str) -> str | None:
    parsed = urlsplit(model_url.rstrip("/"))
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower() != "huggingface.co" or len(parts) < 2:
        return None
    if parts[0] in {"datasets", "spaces"}:
        return None
    return f"https://huggingface.co/{parts[0]}/{parts[1]}"


def _is_open(model_url: str, hf_model_url: str | None) -> bool:
    if hf_model_url:
        return True
    host = urlsplit(model_url).netloc.lower()
    return host in {"github.com", "www.github.com"}


def _table(payload: dict[str, Any], headers: tuple[str, ...]) -> list[list[Any]]:
    for component in payload.get("components", []):
        if not isinstance(component, dict) or component.get("type") != "dataframe":
            continue
        value = component.get("props", {}).get("value")
        if isinstance(value, dict) and value.get("headers") == list(headers):
            rows = value.get("data")
            if not isinstance(rows, list):
                raise TypeError("MMEB dataframe rows must be a list")
            if not MIN_EXPECTED_ENTRIES <= len(rows) <= MAX_EXPECTED_ENTRIES:
                raise ValueError(
                    f"MMEB dataframe returned {len(rows)} rows; expected at least "
                    f"{MIN_EXPECTED_ENTRIES} and at most {MAX_EXPECTED_ENTRIES}"
                )
            return rows
    raise ValueError(f"MMEB dataframe headers not found: {headers}")


def _parse_table(
    payload: dict[str, Any], *, version: str, headers: tuple[str, ...], score_key: str
) -> dict[str, MmebEntry]:
    rows = _table(payload, headers)
    score_index = headers.index(score_key)
    parsed: dict[str, MmebEntry] = {}
    for raw in rows:
        if not isinstance(raw, list) or len(raw) != len(headers):
            raise TypeError("MMEB dataframe rows do not match the published headers")
        model_name, model_url = _model_link(raw[1])
        if len(model_name) > 255 or model_name in parsed:
            raise ValueError("MMEB model names must be unique and at most 255 chars")
        try:
            rank = int(
                str(raw[0]).replace("🏆", "1").replace("🥈", "2").replace("🥉", "3")
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"MMEB rank is invalid for {model_name}") from exc
        if rank < 1:
            raise ValueError(f"MMEB rank is invalid for {model_name}")
        hf_model_url = _hf_model_url(model_url)
        parsed[model_name] = MmebEntry(
            model_name=model_name,
            model_url=model_url,
            total_params=_params(raw[2], model_name=model_name),
            reported_on=_reported_on(raw[3]),
            scores={
                version: _score(
                    raw[score_index], model_name=model_name, version=version
                )
            },
            ranks={version: rank},
            is_open=_is_open(model_url, hf_model_url),
            hf_model_url=hf_model_url,
        )
    return parsed


def parse_mmeb_leaderboard(payload: Any, *, version: str) -> list[MmebEntry]:
    """Strictly parse one precomputed overall table in the Gradio config."""
    if not isinstance(payload, dict):
        raise TypeError("MMEB config payload must be an object")
    if version == "v2":
        parsed = _parse_table(
            payload, version="v2", headers=V2_HEADERS, score_key="Overall-V2"
        )
    elif version == "v3":
        parsed = _parse_table(
            payload, version="v3", headers=V3_HEADERS, score_key="Overall"
        )
    else:
        raise ValueError(f"Unknown MMEB version: {version}")
    return list(parsed.values())


def fetch_mmeb_leaderboard(
    *, version: str, client: httpx.Client | None = None
) -> list[MmebEntry]:
    """Fetch one official MMEB overall leaderboard from the live Space."""
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(60, connect=10),
        follow_redirects=True,
        headers={"User-Agent": "paperswithcode-mmeb-sync/1.0"},
    )
    try:
        response = active_client.get(MMEB_CONFIG_URL)
        response.raise_for_status()
        return parse_mmeb_leaderboard(response.json(), version=version)
    finally:
        if owned_client:
            active_client.close()


_ARXIV_URL = re.compile(
    r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})(?:v[0-9]+)?",
    re.IGNORECASE,
)


def _repo_id(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower() != "huggingface.co" or len(parts) < 2:
        return None
    if parts[0] in {"datasets", "spaces"}:
        return None
    return "/".join(parts[:2])


class MmebSyncService:
    """Replace one MMEB aggregate leaderboard with linked official rows."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self, version: str) -> tuple[Task, Dataset, str, str]:
        try:
            dataset_slug, metric_name, source_label = LANES[version]
        except KeyError as exc:
            raise ValueError(f"Unknown MMEB version: {version}") from exc
        task = self.db.query(Task).filter(Task.slug == "embedding-models").one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == dataset_slug).one_or_none()
        )
        metric = self.db.query(Metric).filter(Metric.name == metric_name).one_or_none()
        if task is None or dataset is None or metric is None:
            raise RuntimeError(
                f"MMEB {version} task, benchmark, or metric is not configured"
            )
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
            raise RuntimeError(f"MMEB {metric_name} is not linked to embedding-models")
        return task, dataset, metric_name, source_label

    def _paper_candidates(self, entry: MmebEntry) -> list[Paper]:
        ids: set[int] = set()
        match = _ARXIV_URL.search(entry.model_url)
        if match:
            ids.update(
                paper_id
                for (paper_id,) in self.db.query(Paper.id)
                .filter(Paper.arxiv_id == match.group(1), Paper.is_latest_version)
                .all()
            )
            if ids:
                return self.db.query(Paper).filter(Paper.id.in_(ids)).all()

        repo_id = _repo_id(entry.hf_model_url)
        if repo_id:
            ids.update(
                paper_id
                for (paper_id,) in self.db.query(PaperHfArtifact.paper_id)
                .join(HfArtifact, HfArtifact.id == PaperHfArtifact.hf_artifact_id)
                .join(Paper, Paper.id == PaperHfArtifact.paper_id)
                .filter(HfArtifact.repo_id == repo_id, Paper.is_latest_version)
                .all()
            )
            ids.update(
                paper_id
                for (paper_id,) in self.db.query(Evaluation.paper_id)
                .join(Paper, Paper.id == Evaluation.paper_id)
                .filter(
                    Evaluation.hf_model_url == entry.hf_model_url,
                    Paper.is_latest_version,
                )
                .distinct()
                .all()
            )

        parsed = urlsplit(entry.model_url.rstrip("/"))
        if parsed.netloc.lower() in {"github.com", "www.github.com"}:
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2:
                canonical = f"https://github.com/{parts[0].lower()}/{parts[1].lower()}"
                ids.update(
                    paper_id
                    for (paper_id,) in self.db.query(PaperRepository.paper_id)
                    .join(Repository, Repository.id == PaperRepository.repository_id)
                    .join(Paper, Paper.id == PaperRepository.paper_id)
                    .filter(
                        Repository.url == canonical,
                        Paper.is_latest_version,
                    )
                    .all()
                )

        if entry.model_url:
            ids.update(
                paper_id
                for (paper_id,) in self.db.query(PaperProjectPage.paper_id)
                .join(ProjectPage, ProjectPage.id == PaperProjectPage.project_page_id)
                .join(Paper, Paper.id == PaperProjectPage.paper_id)
                .filter(
                    ProjectPage.url == entry.model_url,
                    Paper.is_latest_version,
                )
                .all()
            )
            ids.update(
                paper_id
                for (paper_id,) in self.db.query(Paper.id)
                .filter(Paper.source_url == entry.model_url, Paper.is_latest_version)
                .all()
            )
        if not ids:
            return []
        return self.db.query(Paper).filter(Paper.id.in_(ids)).all()

    def _resolve_papers(
        self, entries: list[MmebEntry], stats: MmebSyncStats
    ) -> dict[str, Paper]:
        resolved: dict[str, Paper] = {}
        for entry in entries:
            candidates = self._paper_candidates(entry)
            if len(candidates) == 1:
                resolved[entry.model_name] = candidates[0]
            elif candidates:
                stats.ambiguous_models.append(entry.model_name)
            else:
                stats.unresolved_models.append(entry.model_name)
        return resolved

    @staticmethod
    def _validate_coverage(
        *, version: str, fetched: int, resolved: int, existing_managed: int
    ) -> None:
        if fetched < MIN_EXPECTED_ENTRIES:
            return
        if resolved < MIN_RESOLVED_ENTRIES[version]:
            raise RuntimeError(
                f"MMEB {version} resolved only {resolved} linked rows; refusing "
                "to replace the managed leaderboard"
            )
        if existing_managed and resolved * 2 < existing_managed:
            raise RuntimeError(
                f"MMEB {version} resolved {resolved} rows versus {existing_managed} "
                "managed rows; refusing a drop over 50%"
            )

    def sync(
        self,
        entries: list[MmebEntry],
        *,
        version: str,
        fetched_at: datetime | None = None,
        commit: bool = True,
    ) -> MmebSyncStats:
        if not entries:
            raise ValueError("Refusing to synchronize an empty MMEB leaderboard")
        now = fetched_at or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        stats = MmebSyncStats(fetched=len(entries))

        try:
            task, dataset, metric_name, source_label = self._leaderboard_identity(
                version
            )
            scored = [
                entry for entry in entries if (entry.scores.get(version) or 0) > 0
            ]
            stats.scored = len(scored)
            papers_by_model = self._resolve_papers(scored, stats)
            managed_rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                    Evaluation.best_metric == metric_name,
                    Evaluation.methodology.like(f"{MANAGED_METHODOLOGY_PREFIX}%"),
                )
                .all()
            )
            self._validate_coverage(
                version=version,
                fetched=len(entries),
                resolved=len(papers_by_model),
                existing_managed=len(managed_rows),
            )
            managed_by_name = {row.model_name: row for row in managed_rows}
            managed_ids = {row.id for row in managed_rows}
            unmanaged_names = {
                model_name
                for row_id, model_name in self.db.query(
                    Evaluation.id, Evaluation.model_name
                )
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                    Evaluation.best_metric == metric_name,
                )
                .all()
                if row_id not in managed_ids
            }

            for entry in scored:
                paper = papers_by_model.get(entry.model_name)
                if paper is None:
                    continue
                if (
                    entry.model_name in unmanaged_names
                    and entry.model_name not in managed_by_name
                ):
                    stats.unmanaged_conflicts.append(entry.model_name)
                    continue
                score = entry.scores[version]
                assert score is not None
                methodology = (
                    f"{MANAGED_METHODOLOGY_PREFIX} Official {source_label} aggregate "
                    f"from the MMEB leaderboard Space; source rank "
                    f"{entry.ranks[version]}; fetched {now.isoformat()}. Only rows "
                    "with one unambiguous local paper/resource match are synchronized."
                )
                row = managed_by_name.get(entry.model_name)
                if row is None:
                    row = Evaluation(
                        paper_id=paper.id,
                        task_id=task.id,
                        dataset_id=dataset.id,
                        model_name=entry.model_name,
                    )
                    self.db.add(row)
                    stats.created += 1
                else:
                    stats.updated += 1
                row.paper_id = paper.id
                row.methodology = methodology
                row.metrics = {metric_name: score}
                row.best_metric = metric_name
                row.uses_additional_data = False
                row.is_open = entry.is_open
                row.num_parameters = entry.total_params
                row.hf_model_url = entry.hf_model_url
                row.evaluated_on = entry.reported_on
                row.external_source_url = MMEB_SPACE_URL
                row.source_url = MMEB_SPACE_URL
                row.external = True
                row.updated_at = now
                if entry.hf_model_url:
                    hf_models = list(paper.hf_models or [])
                    if entry.hf_model_url not in hf_models:
                        hf_models.append(entry.hf_model_url)
                        paper.hf_models = hf_models
                stats.matched += 1

            current_names = set(papers_by_model)
            for row in managed_rows:
                if row.model_name not in current_names:
                    self.db.delete(row)
                    stats.deleted += 1

            self.db.flush()
            EvaluationService(self.db).recalculate_ranks(
                task.id,
                dataset.id,
                metric_name=metric_name,
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
