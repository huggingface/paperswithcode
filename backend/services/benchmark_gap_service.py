"""Validation and aggregation for benchmark gaps discovered during add-evals."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.database import (
    BenchmarkCurationCandidate,
    BenchmarkCurationEvidence,
    Dataset,
    Metric,
    Paper,
    PaperCurationJob,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.utils.public_urls import normalize_public_url
from backend.utils.source_urls import source_url_identity
from backend.utils.urls import get_paper_route_identifier

GAP_TYPES = {
    "dataset_missing",
    "task_dataset_association_missing",
    "metric_configuration_missing",
    "task_missing",
}
CONFIDENCE_VALUES = {"low", "medium", "high"}
AUTHORITATIVE_EVIDENCE_KINDS = {
    "github_readme",
    "model_card",
    "paper_markdown",
    "paper_pdf",
    "paper_source",
    "project_page",
}
RESERVED_AGENT_FIELDS = {
    "candidate_id",
    "recurrence_count",
    "review_status",
    "observed_at",
    "trace_sha256",
}


def benchmark_candidate_identity_key(gap: dict) -> str:
    """Return a stable identity for the proposed benchmark, not its evidence."""
    normalized = gap["_normalized"]
    name = re.sub(r"[^a-z0-9]", "", normalized["name"].lower())
    identity_source = f"benchmark-v2:{gap['gap_type']}:{name}"
    return hashlib.sha256(identity_source.encode()).hexdigest()


def _bounded_text(value: Any, name: str, limit: int = 2_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    value = value.strip()
    if len(value) > limit:
        raise ValueError(f"{name} exceeds {limit} characters")
    return value


def _optional_text(value: Any, name: str, limit: int) -> str | None:
    if value is None:
        return None
    return _bounded_text(value, name, limit)


def _bounded_list(value: Any, name: str, limit: int, *, required: bool = False) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    if required and not value:
        raise ValueError(f"{name} must not be empty")
    if len(value) > limit:
        raise ValueError(f"{name} exceeds {limit} items")
    return value


def _entity_id(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _without_query_or_fragment(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _paper_evidence_urls(paper: Paper | None) -> set[str] | None:
    if paper is None:
        return None
    values = set()
    if paper.source_url:
        values.add(normalize_public_url(paper.source_url))
    if paper.arxiv_id:
        values.update(
            {
                f"https://arxiv.org/abs/{paper.arxiv_id}",
                f"https://arxiv.org/html/{paper.arxiv_id}",
                f"https://arxiv.org/pdf/{paper.arxiv_id}",
                f"https://arxiv.org/pdf/{paper.arxiv_id}.pdf",
                f"https://export.arxiv.org/abs/{paper.arxiv_id}",
                f"https://export.arxiv.org/pdf/{paper.arxiv_id}",
                f"https://export.arxiv.org/pdf/{paper.arxiv_id}.pdf",
                f"https://huggingface.co/papers/{paper.arxiv_id}",
            }
        )
    return values


def _paper_evidence_url_aliases(paper: Paper | None) -> dict[str, str]:
    """Map exact same-paper transport URLs onto allowed durable evidence URLs."""
    if paper is None or not paper.arxiv_id:
        return {}
    return {
        f"https://export.arxiv.org/e-print/{paper.arxiv_id}": (
            f"https://arxiv.org/html/{paper.arxiv_id}"
        ),
        f"https://arxiv.org/e-print/{paper.arxiv_id}": (
            f"https://arxiv.org/html/{paper.arxiv_id}"
        ),
    }


def _paper_evidence_kinds(paper: Paper | None) -> dict[str, set[str]] | None:
    if paper is None:
        return None
    kinds: dict[str, set[str]] = {}
    if paper.source_url:
        kinds.setdefault(source_url_identity(paper.source_url), set()).add(
            "paper_source"
        )
    if paper.arxiv_id:
        identity = source_url_identity(f"https://arxiv.org/abs/{paper.arxiv_id}")
        kinds.setdefault(identity, set()).update(
            {"paper_markdown", "paper_pdf", "paper_source"}
        )
    return kinds


class BenchmarkGapService:
    def __init__(self, db: Session):
        self.db = db

    def validate(
        self,
        gaps: list[dict],
        *,
        paper: Paper | None = None,
        source_documents: list[dict] | None = None,
    ) -> tuple[list[dict], list[dict]]:
        accepted: list[dict] = []
        rejected: list[dict] = []
        evidence_urls = _paper_evidence_urls(paper)
        evidence_kinds = _paper_evidence_kinds(paper)
        if evidence_urls is not None:
            evidence_urls = {source_url_identity(url) for url in evidence_urls}
            for item in source_documents or []:
                if not isinstance(item, dict) or not item.get("url"):
                    continue
                identity = source_url_identity(item["url"])
                evidence_urls.add(identity)
                if item.get("kind") in AUTHORITATIVE_EVIDENCE_KINDS:
                    assert evidence_kinds is not None
                    evidence_kinds.setdefault(identity, set()).add(item["kind"])
        evidence_url_aliases = _paper_evidence_url_aliases(paper)
        for index, gap in enumerate(gaps):
            try:
                accepted.append(
                    self._validate_one(
                        gap,
                        evidence_urls=evidence_urls,
                        evidence_url_aliases=evidence_url_aliases,
                        evidence_kinds=evidence_kinds,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                rejected.append({"index": index, "error": str(exc)[:500]})
        return accepted, rejected

    def _validate_one(
        self,
        gap: dict,
        *,
        evidence_urls: set[str] | None = None,
        evidence_url_aliases: dict[str, str] | None = None,
        evidence_kinds: dict[str, set[str]] | None = None,
    ) -> dict:
        if not isinstance(gap, dict):
            raise TypeError("gap must be an object")
        if RESERVED_AGENT_FIELDS.intersection(gap):
            raise ValueError("agent proposal contains server-owned fields")
        result = deepcopy(gap)
        reasoning = _bounded_text(result.get("reasoning"), "reasoning")
        local_ref = _bounded_text(result.get("local_ref"), "local_ref", 100)
        gap_type = gap.get("gap_type")
        if gap_type not in GAP_TYPES:
            raise ValueError("invalid gap_type")
        proposed = result.get("proposed_benchmark")
        if not isinstance(proposed, dict):
            raise ValueError("proposed_benchmark is required")
        name = _bounded_text(proposed.get("name"), "proposed_benchmark.name", 500)
        proposed["description"] = _optional_text(
            proposed.get("description"), "proposed_benchmark.description", 4_000
        )
        aliases = [
            _bounded_text(value, "proposed_benchmark.alias", 500)
            for value in _bounded_list(
                proposed.get("aliases") or [], "proposed_benchmark.aliases", 30
            )
        ]
        task_ids = []
        task_candidates = _bounded_list(
            proposed.get("task_candidates") or [],
            "proposed_benchmark.task_candidates",
            20,
        )
        for task in task_candidates:
            if not isinstance(task, dict):
                raise ValueError("task candidate must be an object")
            task_id = _entity_id(task.get("task_id"), "task_id")
            if self.db.get(Task, task_id) is None:
                raise ValueError(f"unknown task_id {task_id}")
            task["task_name"] = _optional_text(
                task.get("task_name"), "task candidate name", 500
            )
            confidence = task.get("confidence")
            if confidence is not None and confidence not in CONFIDENCE_VALUES:
                raise ValueError("invalid task candidate confidence")
            task["reason"] = _optional_text(
                task.get("reason"), "task candidate reason", 2_000
            )
            task_ids.append(task_id)
        sources = _bounded_list(
            proposed.get("canonical_sources") or [],
            "proposed_benchmark.canonical_sources",
            10,
        )
        normalized_sources = []
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError("canonical source must be an object")
            normalized_sources.append(
                {
                    **source,
                    "kind": _bounded_text(source.get("kind"), "source kind", 100),
                    "url": normalize_public_url(
                        _bounded_text(source.get("url"), "canonical source URL", 2_000)
                    ),
                    "title": _optional_text(source.get("title"), "source title", 500),
                }
            )
        proposed["canonical_sources"] = normalized_sources
        canonical_url = normalized_sources[0]["url"] if normalized_sources else None

        protocol = result.get("protocol")
        if not isinstance(protocol, dict):
            raise ValueError("protocol is required")
        protocol["dataset_version"] = _optional_text(
            protocol.get("dataset_version"), "protocol.dataset_version", 200
        )
        protocol["splits"] = [
            _bounded_text(value, "protocol split", 200)
            for value in _bounded_list(
                protocol.get("splits") or [], "protocol.splits", 20
            )
        ]
        protocol["evaluation_protocol"] = _bounded_text(
            protocol.get("evaluation_protocol"), "protocol.evaluation_protocol", 4_000
        )
        metrics = _bounded_list(
            protocol.get("metrics"), "protocol.metrics", 20, required=True
        )
        metric_names = set()
        for metric in metrics:
            if not isinstance(metric, dict):
                raise ValueError("protocol metric must be an object")
            metric_name = _bounded_text(metric.get("name"), "metric name", 200)
            if metric_name in metric_names:
                raise ValueError("protocol metric names must be unique")
            metric_names.add(metric_name)
            if metric.get("direction") not in {"higher_is_better", "lower_is_better"}:
                raise ValueError("invalid metric direction")
            for field in ("unit", "native_scale"):
                metric[field] = _optional_text(
                    metric.get(field), f"metric {field}", 200
                )
            metric["definition"] = _bounded_text(
                metric.get("definition"), "metric definition", 2_000
            )
        if not isinstance(protocol.get("supports_harness"), bool):
            raise ValueError("protocol.supports_harness must be boolean")

        catalog_search = result.get("catalog_search")
        if not isinstance(catalog_search, dict):
            raise ValueError("catalog_search is required")
        catalog_search["queries"] = [
            _bounded_text(value, "catalog search query", 500)
            for value in _bounded_list(
                catalog_search.get("queries"),
                "catalog_search.queries",
                30,
                required=True,
            )
        ]
        near_matches = _bounded_list(
            catalog_search.get("near_matches") or [],
            "catalog_search.near_matches",
            30,
        )
        for near_match in near_matches:
            if not isinstance(near_match, dict):
                raise ValueError("catalog near-match must be an object")
            task_id = _entity_id(near_match.get("task_id"), "near-match task_id")
            dataset_id = _entity_id(
                near_match.get("dataset_id"), "near-match dataset_id"
            )
            if self.db.get(Task, task_id) is None:
                raise ValueError(f"unknown near-match task_id {task_id}")
            if self.db.get(Dataset, dataset_id) is None:
                raise ValueError(f"unknown near-match dataset_id {dataset_id}")
            near_match["dataset_name"] = _optional_text(
                near_match.get("dataset_name"), "near-match dataset name", 500
            )
            near_match["rejection_reason"] = _bounded_text(
                near_match.get("rejection_reason"), "near-match rejection reason", 2_000
            )
        catalog_search["conclusion"] = _bounded_text(
            catalog_search.get("conclusion"), "catalog_search.conclusion", 2_000
        )

        evidence_values = _bounded_list(
            result.get("evidence"), "evidence", 50, required=True
        )
        normalized_evidence = []
        evidence_ids = set()
        evidence_fingerprints: dict[str, str] = {}
        evidence_aliases: dict[str, str] = {}
        for evidence in evidence_values:
            if not isinstance(evidence, dict):
                raise ValueError("evidence must be an object")
            evidence_id = _bounded_text(evidence.get("evidence_id"), "evidence_id", 100)
            if evidence_id in evidence_ids:
                raise ValueError("evidence_id values must be unique")
            evidence_ids.add(evidence_id)
            source_kind = evidence.get("source_kind")
            if source_kind not in AUTHORITATIVE_EVIDENCE_KINDS:
                raise ValueError("benchmark gaps require authoritative source evidence")
            source_url = normalize_public_url(
                _bounded_text(evidence.get("source_url"), "evidence source URL", 2_000)
            )
            source_url = (evidence_url_aliases or {}).get(
                _without_query_or_fragment(source_url), source_url
            )
            source_identity = source_url_identity(source_url)
            if evidence_urls is not None and source_identity not in evidence_urls:
                raise ValueError("evidence source URL is not the scoped paper")
            if evidence_kinds is not None and source_kind not in evidence_kinds.get(
                source_identity, set()
            ):
                raise ValueError("evidence source kind does not match scoped source")
            normalized = {
                **evidence,
                "evidence_id": evidence_id,
                "source_kind": source_kind,
                "source_url": source_url,
                "section": _optional_text(
                    evidence.get("section"), "evidence section", 500
                ),
                "table": _optional_text(evidence.get("table"), "evidence table", 500),
                "snippet": _bounded_text(
                    evidence.get("snippet"), "evidence snippet", 1_000
                ),
                "supports": sorted(
                    {
                        _bounded_text(value, "evidence support reference", 100)
                        for value in _bounded_list(
                            evidence.get("supports"),
                            "evidence.supports",
                            50,
                            required=True,
                        )
                    }
                ),
            }
            page = evidence.get("page")
            if page is not None and (not isinstance(page, int) or page < 1):
                raise ValueError("evidence page must be a positive integer")
            fingerprint = json.dumps(
                {
                    key: value
                    for key, value in normalized.items()
                    if key != "evidence_id"
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            canonical_evidence_id = evidence_fingerprints.get(fingerprint)
            if canonical_evidence_id is None:
                evidence_fingerprints[fingerprint] = evidence_id
                normalized_evidence.append(normalized)
            else:
                evidence_aliases[evidence_id] = canonical_evidence_id
        result["evidence"] = normalized_evidence

        blocked = _bounded_list(
            result.get("blocked_evaluations"),
            "blocked_evaluations",
            30,
            required=True,
        )
        blocked_refs = set()
        for blocked_evaluation in blocked:
            if not isinstance(blocked_evaluation, dict):
                raise ValueError("blocked evaluation must be an object")
            blocked_ref = _bounded_text(
                blocked_evaluation.get("local_ref"), "blocked evaluation local_ref", 100
            )
            if blocked_ref in blocked_refs:
                raise ValueError("blocked evaluation local_ref values must be unique")
            blocked_refs.add(blocked_ref)
            blocked_evaluation["model_name"] = _bounded_text(
                blocked_evaluation.get("model_name"),
                "blocked evaluation model_name",
                500,
            )
            blocked_evaluation["split"] = _optional_text(
                blocked_evaluation.get("split"), "blocked evaluation split", 200
            )
            blocked_evaluation["harness"] = _optional_text(
                blocked_evaluation.get("harness"), "blocked evaluation harness", 500
            )
            blocked_metrics = blocked_evaluation.get("metrics")
            if not isinstance(blocked_metrics, dict) or not blocked_metrics:
                raise ValueError("blocked evaluation metrics are required")
            if len(blocked_metrics) > 20:
                raise ValueError("blocked evaluation metrics exceeds 20 items")
            for metric_name, value in blocked_metrics.items():
                _bounded_text(metric_name, "blocked metric name", 200)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise ValueError("blocked metric values must be numeric")
                if not math.isfinite(float(value)):
                    raise ValueError("blocked metric values must be finite")
            best_metric = _bounded_text(
                blocked_evaluation.get("best_metric"),
                "blocked evaluation best_metric",
                200,
            )
            if best_metric not in blocked_metrics:
                raise ValueError("blocked best_metric must be present in metrics")
            if best_metric not in metric_names:
                raise ValueError("blocked best_metric must be defined by the protocol")
            blocked_evaluation["methodology"] = _bounded_text(
                blocked_evaluation.get("methodology"),
                "blocked evaluation methodology",
                4_000,
            )
            for flag in ("uses_additional_data", "is_open"):
                if not isinstance(blocked_evaluation.get(flag), bool):
                    raise ValueError(f"blocked evaluation {flag} must be boolean")
            parameters = blocked_evaluation.get("num_parameters")
            if parameters is not None and (
                not isinstance(parameters, int)
                or isinstance(parameters, bool)
                or parameters < 0
            ):
                raise ValueError(
                    "blocked evaluation num_parameters must be non-negative"
                )
            model_url = blocked_evaluation.get("hf_model_url")
            if model_url is not None:
                normalized_model_url = normalize_public_url(
                    _bounded_text(model_url, "blocked evaluation HF model URL", 2_000)
                )
                if urlsplit(normalized_model_url).hostname != "huggingface.co":
                    raise ValueError(
                        "blocked evaluation HF model URL must use huggingface.co"
                    )
                blocked_evaluation["hf_model_url"] = normalized_model_url
            linked_evidence = [
                _bounded_text(value, "blocked evidence_id", 100)
                for value in _bounded_list(
                    blocked_evaluation.get("evidence_ids"),
                    "blocked evaluation evidence_ids",
                    50,
                    required=True,
                )
            ]
            if any(value not in evidence_ids for value in linked_evidence):
                raise ValueError("blocked evaluation references unknown evidence_id")
            blocked_evaluation["evidence_ids"] = list(
                dict.fromkeys(
                    evidence_aliases.get(value, value) for value in linked_evidence
                )
            )
        assessment = result.get("assessment")
        if not isinstance(assessment, dict):
            raise ValueError("assessment is required")
        if assessment.get("recommendation") not in {"add_candidate", "review"}:
            raise ValueError("invalid assessment recommendation")
        if assessment.get("confidence") not in CONFIDENCE_VALUES:
            raise ValueError("invalid assessment confidence")
        assessment["why_worth_adding"] = _bounded_text(
            assessment.get("why_worth_adding"), "assessment.why_worth_adding", 2_000
        )
        assessment["ambiguities"] = [
            _bounded_text(value, "assessment ambiguity", 1_000)
            for value in _bounded_list(
                assessment.get("ambiguities") or [], "assessment.ambiguities", 20
            )
        ]

        result["reasoning"] = reasoning
        result["local_ref"] = local_ref
        result["_normalized"] = {
            "name": name,
            "canonical_url": canonical_url,
            "task_ids": sorted(set(task_ids)),
            "aliases": sorted(set(aliases)),
        }
        return result

    def persist(
        self, *, paper_id: int, job_id: uuid.UUID, gaps: list[dict]
    ) -> list[dict]:
        results = []
        for gap in gaps:
            normalized = gap.pop("_normalized")
            identity_key = benchmark_candidate_identity_key(
                {"gap_type": gap["gap_type"], "_normalized": normalized}
            )
            row = (
                self.db.query(BenchmarkCurationCandidate)
                .filter(BenchmarkCurationCandidate.identity_key == identity_key)
                .with_for_update()
                .one_or_none()
            )
            if row is None:
                # Pre-v2 rows hashed the evidence URL. Reuse a same-name
                # candidate so later papers still aggregate onto it.
                name_key = re.sub(r"[^a-z0-9]", "", normalized["name"].lower())
                row = (
                    self.db.query(BenchmarkCurationCandidate)
                    .filter(BenchmarkCurationCandidate.gap_type == gap["gap_type"])
                    .filter(
                        func.regexp_replace(
                            func.lower(BenchmarkCurationCandidate.canonical_name),
                            "[^a-z0-9]",
                            "",
                            "g",
                        )
                        == name_key
                    )
                    .order_by(BenchmarkCurationCandidate.first_seen_at.asc())
                    .with_for_update()
                    .first()
                )
            if row is None:
                row = BenchmarkCurationCandidate(
                    id=uuid.uuid4(),
                    identity_key=identity_key,
                    canonical_name=normalized["name"],
                    gap_type=gap["gap_type"],
                    canonical_url=normalized["canonical_url"],
                    task_ids=normalized["task_ids"],
                    aliases=normalized["aliases"],
                    confidence=(gap.get("assessment") or {}).get("confidence"),
                )
                self.db.add(row)
                self.db.flush()
            evidence = BenchmarkCurationEvidence(
                id=uuid.uuid4(),
                candidate_id=row.id,
                paper_id=paper_id,
                job_id=job_id,
                payload=json.loads(json.dumps(gap)),
            )
            exists = (
                self.db.query(BenchmarkCurationEvidence.id)
                .filter(
                    BenchmarkCurationEvidence.candidate_id == row.id,
                    BenchmarkCurationEvidence.paper_id == paper_id,
                    BenchmarkCurationEvidence.job_id == job_id,
                )
                .first()
            )
            if not exists:
                self.db.add(evidence)
            row.last_seen_at = datetime.now(UTC)
            self.db.flush()
            row.distinct_paper_count = int(
                self.db.query(
                    func.count(func.distinct(BenchmarkCurationEvidence.paper_id))
                )
                .filter(BenchmarkCurationEvidence.candidate_id == row.id)
                .scalar()
                or 0
            )
            results.append({"candidate_id": str(row.id), "identity_key": identity_key})
        return results

    def promote_and_enqueue(
        self,
        *,
        candidate_id: uuid.UUID,
        dataset_id: int,
        task_id: int,
        best_metric: str,
        settings,
        job_service,
    ) -> dict[str, Any]:
        """Confirm catalog configuration and enqueue only linked evidence papers."""
        candidate = self.db.get(BenchmarkCurationCandidate, candidate_id)
        if candidate is None:
            raise LookupError("Benchmark candidate not found")
        dataset = self.db.get(Dataset, dataset_id)
        task = self.db.get(Task, task_id)
        if dataset is None or task is None:
            raise ValueError("Promotion requires an existing task and dataset")
        leaderboard = self.db.get(TaskDataset, (task_id, dataset_id))
        if leaderboard is None:
            raise ValueError("Promotion requires an existing task/dataset leaderboard")
        metric = (
            self.db.query(Metric)
            .join(TaskDatasetMetric, TaskDatasetMetric.metric_id == Metric.id)
            .filter(
                TaskDatasetMetric.task_id == task_id,
                TaskDatasetMetric.dataset_id == dataset_id,
                Metric.name == best_metric,
            )
            .one_or_none()
        )
        if metric is None:
            raise ValueError("Promotion metric is not configured on the leaderboard")
        if candidate.task_ids and task_id not in set(candidate.task_ids):
            raise ValueError("Promotion task is outside the candidate task evidence")

        evidence_rows = (
            self.db.query(BenchmarkCurationEvidence)
            .filter(BenchmarkCurationEvidence.candidate_id == candidate.id)
            .order_by(BenchmarkCurationEvidence.created_at)
            .all()
        )
        expected_metrics = {
            item.get("name")
            for evidence in evidence_rows
            for item in ((evidence.payload.get("protocol") or {}).get("metrics") or [])
            if isinstance(item, dict)
        }
        if expected_metrics and best_metric not in expected_metrics:
            raise ValueError(
                "Promotion metric does not match the captured paper evidence"
            )

        policy_version = f"benchmark-promotion-{str(candidate.id)[:12]}"
        enqueued = []
        skipped_active: list[int] = []
        paper_ids = sorted({int(item.paper_id) for item in evidence_rows})
        for paper_id in paper_ids:
            existing = (
                self.db.query(PaperCurationJob)
                .filter(
                    PaperCurationJob.paper_id == paper_id,
                    PaperCurationJob.kind == "add-evals",
                    PaperCurationJob.trigger == "benchmark-promotion",
                    PaperCurationJob.policy_version == policy_version,
                    PaperCurationJob.status.in_(
                        {"queued", "dispatching", "running", "completed"}
                    ),
                )
                .order_by(PaperCurationJob.created_at.desc())
                .first()
            )
            if existing is not None:
                enqueued.append(job_service.serialize(existing, settings))
                continue
            active = (
                self.db.query(PaperCurationJob.id)
                .filter(
                    PaperCurationJob.paper_id == paper_id,
                    PaperCurationJob.kind == "add-evals",
                    PaperCurationJob.status.in_({"queued", "dispatching", "running"}),
                )
                .first()
            )
            if active is not None:
                skipped_active.append(paper_id)
                continue
            paper = self.db.get(Paper, paper_id)
            if paper is None:
                continue
            enqueued.append(
                job_service.enqueue(
                    self.db,
                    kind="add-evals",
                    paper_id=paper.id,
                    paper_route=get_paper_route_identifier(
                        paper.source, paper.arxiv_id, paper.id
                    ),
                    paper_title=paper.title,
                    requested_by=f"benchmark-promotion:{candidate.id}",
                    settings=settings,
                    trigger="benchmark-promotion",
                    policy_version=policy_version,
                    priority=50,
                    dispatch=False,
                    commit=False,
                )
            )

        candidate.status = "promoted"
        candidate.promoted_at = datetime.now(UTC)
        self.db.commit()
        job_service.dispatch_next(self.db, settings)
        return {
            "candidate_id": str(candidate.id),
            "dataset_id": dataset_id,
            "task_id": task_id,
            "best_metric": best_metric,
            "enqueued_job_ids": [str(item.id) for item in enqueued],
            "skipped_active_paper_ids": skipped_active,
        }
