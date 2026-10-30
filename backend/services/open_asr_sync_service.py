"""Synchronize the living Open ASR Leaderboard into evaluation rows."""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from gradio_client import Client
from huggingface_hub import HfApi
from huggingface_hub.errors import HFValidationError, HfHubHTTPError
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.database import (
    Dataset,
    Evaluation,
    Metric,
    Paper,
    PaperTask,
    Task,
    TaskDatasetMetric,
)
from backend.services.arxiv_service import ArxivService
from backend.services.evaluation_service import EvaluationService
from backend.services.leaderboard_sync_ownership import managed_methodology_prefix
from backend.services.paper_ingestion_service import (
    PaperIngestionError,
    PaperIngestionService,
    canonical_arxiv_id,
)
from backend.utils.urls import validate_arxiv_id

SPACE_APP_URL = "https://hf-audio-open-asr-leaderboard.hf.space"
SPACE_SOURCE_URL = "https://huggingface.co/spaces/hf-audio/open_asr_leaderboard"
LEGACY_SOURCE_URL = "https://paperswithcode.co/benchmark/open-asr-leaderboard"
DATASET_SLUG = "open-asr-leaderboard"
TASK_SLUG = "automatic-speech-recognition"
WER_METRIC = "WER"
RTFX_METRIC = "RTFx"
MANAGED_METHODOLOGY_PREFIX = managed_methodology_prefix("Open ASR")
MIN_EXPECTED_ENTRIES = 40
MAX_EXPECTED_ENTRIES = 150

DEFAULT_COLUMNS = [
    "RTFx ⬆️️",
    "License",
    "AMI-Cleaned",
    "Earnings22-Cleaned-AA-chunked",
    "Gigaspeech-Cleaned",
    "LS Clean",
    "LS Other",
    "SPGISpeech",
    "URGENT24",
    "Voice Arena Monsoon",
    "Voxpopuli-AA-Cleaned",
    "Private (scripted)",
    "Private (conversational)",
]


def _leaderboard_value(payload: Any) -> Any:
    """Accept the current Gradio component-update response shape."""
    if isinstance(payload, (list, tuple)) and payload:
        # Since 2026-10-28 the endpoint returns (table update, plot update).
        payload = payload[0]
    if isinstance(payload, dict):
        value = payload.get("value")
        if isinstance(value, dict) and "headers" in value and "data" in value:
            return value
    return payload


# Exact, reviewed model-to-paper overrides. Models without a defensible paper
# remain unmatched; legacy importer rows provide additional continuity during
# the first live synchronization.
MODEL_PAPER_ARXIV_IDS: dict[str, str] = {
    "distil-whisper/distil-large-v3.5": "2311.00430",
    "efficient-speech/lite-whisper-large-v3-acc": "2502.20583",
    "espnet/owsm_ctc_v3.1_1B": "2401.16658",
    "espnet/owsm_ctc_v3.2_ft_1B": "2401.16658",
    "espnet/owsm_ctc_v4_1B": "2506.00338",
    "facebook/hubert-large-ls960-ft": "2106.07447",
    "facebook/mms-1b-all": "2305.13516",
    "facebook/wav2vec2-large-960h-lv60-self": "2006.11477",
    "FunAudioLLM/Fun-ASR-Nano-2512-hf": "2509.12508",
    "ibm-granite/granite-4.0-1b-speech": "2505.08699",
    "ibm-granite/granite-speech-3.3-2b": "2505.08699",
    "ibm-granite/granite-speech-3.3-8b": "2505.08699",
    "ibm-granite/granite-speech-4.1-2b": "2505.08699",
    "ibm-granite/granite-speech-4.1-2b-nar": "2505.08699",
    "ibm-granite/granite-speech-5.0-470m-turboctc-nc": "2609.20104",
    "kyutai/stt-2.6b-en": "2410.00037",
    "microsoft/Phi-4-multimodal-instruct": "2503.01743",
    "microsoft/VibeVoice-ASR-HF": "2601.18184",
    "mistralai/Voxtral-Mini-3B-2507": "2507.13264",
    "mistralai/Voxtral-Mini-4B-Realtime-2602": "2602.11298",
    "mistralai/Voxtral-Small-24B-2507": "2507.13264",
    "nvidia/canary-180m-flash": "2503.05931",
    "nvidia/canary-1b-flash": "2503.05931",
    "nvidia/canary-1b-v2": "2509.14128",
    "nvidia/canary-qwen-2.5b": "2503.05931",
    "nvidia/nemotron-3.5-asr-streaming-0.6b": "2312.17279",
    "nvidia/nemotron-speech-streaming-en-0.6b": "2312.17279",
    "nvidia/parakeet-ctc-0.6b": "2305.05084",
    "nvidia/parakeet-ctc-1.1b": "2305.05084",
    "nvidia/parakeet-rnnt-0.6b": "2305.05084",
    "nvidia/parakeet-rnnt-1.1b": "2305.05084",
    "nvidia/parakeet-tdt-0.6b-v2": "2304.06795",
    "nvidia/parakeet-tdt-0.6b-v3": "2509.14128",
    "nvidia/parakeet-tdt-1.1b": "2304.06795",
    "nvidia/parakeet-tdt_ctc-110m": "2304.06795",
    "nyrahealth/CrisperWhisper": "2408.16589",
    "OpenMOSS-Team/MOSS-Transcribe-Diarize": "2601.01554",
    "openai/whisper-large-v3": "2212.04356",
    "openai/whisper-large-v3-turbo": "2212.04356",
    "Qwen/Qwen3-ASR-0.6B": "2601.21337",
    "Qwen/Qwen3-ASR-0.6B-hf": "2601.21337",
    "Qwen/Qwen3-ASR-1.7B": "2601.21337",
    "Qwen/Qwen3-ASR-1.7B-hf": "2601.21337",
    "sophea/asr-k1 (preview)": "2609.13498",
    "soundsgoodai/Zipformer-cr-ctc-transducer-XL-290M": "2410.05101",
    "soundsgoodai/Zipformer-transducer-XL-290M": "2310.11230",
    "speechbrain/asr-conformer-largescaleasr": "2106.04624",
    "usefulsensors/moonshine-streaming-medium": "2602.12241",
    "usefulsensors/moonshine-streaming-small": "2602.12241",
    "usefulsensors/moonshine-streaming-tiny": "2602.12241",
    "usefulsensors/moonshine-tiny": "2410.15608",
}

# Display names for upstream ids whose derived name would drop the vendor.
MODEL_DISPLAY_NAMES: dict[str, str] = {
    "sophea/asr-k1 (preview)": "Sophea ASR K1 (preview)",
}

_TAG_RE = re.compile(r"<[^>]+>")
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?")
_LEGACY_MODEL_RE = re.compile(r"sourced from ([^/]+/[^/]+)/\.eval_results")
_MANAGED_MODEL_RE = re.compile(
    rf"^{re.escape(MANAGED_METHODOLOGY_PREFIX)} Upstream model (.+?); rank \d+;"
)
# Upstream appends the inference runtime, e.g. "(fast-gpu-asr)", to a Hub id.
_RUNTIME_SUFFIX_RE = re.compile(r"\s+\([^()]*\)$")
_HF_SUFFIX_RE = re.compile(r"-hf$", re.IGNORECASE)
_MODEL_TOKEN_RE = re.compile(r"[a-z][a-z0-9]*")
_MODEL_SIZE_RE = re.compile(r"(?<![a-z0-9])\d+(?:\.\d+)?[bm](?![a-z0-9])")
_MODEL_VERSION_RE = re.compile(r"(?<![a-z0-9])v\d+(?:\.\d+)*(?![a-z0-9])")
_GENERIC_MODEL_TOKENS = {
    "asr",
    "audio",
    "base",
    "batch",
    "ctc",
    "english",
    "en",
    "fast",
    "flash",
    "hf",
    "instruct",
    "large",
    "llm",
    "medium",
    "model",
    "multilingual",
    "preview",
    "realtime",
    "rnnt",
    "small",
    "speech",
    "streaming",
    "stt",
    "tdt",
    "tiny",
    "transcribe",
    "transducer",
}


@dataclass(frozen=True)
class OpenAsrEntry:
    model_id: str
    rank: int
    wer: float
    rtfx: float | None
    is_open: bool


@dataclass(frozen=True)
class OpenAsrDiscoveredPaper:
    paper_id: int
    arxiv_id: str
    hf_model_url: str | None = None
    num_parameters: int | None = None


@dataclass
class OpenAsrPaperDiscoveryResult:
    resolved: dict[str, OpenAsrDiscoveredPaper] = field(default_factory=dict)
    discovered_models: list[str] = field(default_factory=list)
    indexed_papers: list[str] = field(default_factory=list)
    would_index: list[str] = field(default_factory=list)
    ambiguous_models: list[str] = field(default_factory=list)
    rejected_papers: list[str] = field(default_factory=list)
    unavailable_models: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolved": len(self.resolved),
            "discovered_models": self.discovered_models,
            "indexed_papers": self.indexed_papers,
            "would_index": self.would_index,
            "ambiguous_models": self.ambiguous_models,
            "rejected_papers": self.rejected_papers,
            "unavailable_models": self.unavailable_models,
            "failures": self.failures,
        }


@dataclass
class OpenAsrSyncStats:
    fetched: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    unmatched_models: list[str] = field(default_factory=list)
    missing_papers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetched": self.fetched,
            "matched": self.matched,
            "created": self.created,
            "updated": self.updated,
            "deleted": self.deleted,
            "unmatched_models": self.unmatched_models,
            "missing_papers": self.missing_papers,
        }


def _number(value: Any, *, optional: bool = False) -> float | None:
    if value is None or str(value).strip().upper() == "NA":
        if optional:
            return None
        raise ValueError("required numeric leaderboard value is missing")
    match = _NUMBER_RE.match(str(value).strip())
    if match is None:
        raise ValueError(f"invalid numeric leaderboard value: {value!r}")
    return float(match.group())


def _model_identity_matches_paper(
    model_id: str, paper_title: str, paper_abstract: str | None
) -> bool:
    """Require a distinctive model token and every explicit size/version marker."""
    model_name = model_id.rsplit("/", 1)[-1].casefold()
    paper_text = f"{paper_title}\n{paper_abstract or ''}".casefold()
    distinctive_tokens = [
        token
        for token in _MODEL_TOKEN_RE.findall(model_name)
        if token not in _GENERIC_MODEL_TOKENS
        and not _MODEL_SIZE_RE.fullmatch(token)
        and not _MODEL_VERSION_RE.fullmatch(token)
        and len(token) >= 3
    ]
    if not distinctive_tokens:
        return False
    family_token = distinctive_tokens[0]
    if (
        re.search(rf"(?<![a-z0-9]){re.escape(family_token)}(?![a-z0-9])", paper_text)
        is None
    ):
        return False
    markers = _MODEL_SIZE_RE.findall(model_name) + _MODEL_VERSION_RE.findall(model_name)
    return all(
        re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])", paper_text)
        is not None
        for marker in markers
    )


def hub_model_id(model_id: str) -> str:
    """Strip an upstream runtime suffix to recover the Hub repository id."""
    return _RUNTIME_SUFFIX_RE.sub("", model_id)


def display_model_names(entries: list[OpenAsrEntry]) -> dict[str, str]:
    """Name rows like other evaluations: "Qwen3-ASR-1.7B", not "Qwen/...-hf"."""
    derived: dict[str, str] = {}
    for entry in entries:
        name = MODEL_DISPLAY_NAMES.get(entry.model_id)
        if name is None:
            hub_id = hub_model_id(entry.model_id)
            name = _HF_SUFFIX_RE.sub("", hub_id.split("/", 1)[1])
            name += entry.model_id[len(hub_id) :]
        derived[entry.model_id] = name
    counts: dict[str, int] = {}
    for name in derived.values():
        counts[name.casefold()] = counts.get(name.casefold(), 0) + 1
    # Two upstream ids that collapse to one name keep their full ids.
    return {
        model_id: name if counts[name.casefold()] == 1 else model_id
        for model_id, name in derived.items()
    }


def _safetensors_total(model_info: Any) -> int | None:
    safetensors = getattr(model_info, "safetensors", None)
    if isinstance(safetensors, dict):
        total = safetensors.get("total")
    else:
        total = getattr(safetensors, "total", None)
    return int(total) if isinstance(total, int) and total >= 0 else None


def parse_open_asr_leaderboard(payload: Any) -> list[OpenAsrEntry]:
    """Validate the public Space table before it can affect persisted rows."""
    if not isinstance(payload, dict):
        raise TypeError("Open ASR response must be a dataframe object")
    headers = payload.get("headers")
    rows = payload.get("data")
    if not isinstance(headers, list) or not isinstance(rows, list):
        raise TypeError("Open ASR response must contain headers and data lists")
    required = {"Rank", "model", "Average WER ⬇️", "RTFx ⬆️️", "License"}
    if not required.issubset(headers):
        raise ValueError("Open ASR response is missing required columns")
    if not MIN_EXPECTED_ENTRIES <= len(rows) <= MAX_EXPECTED_ENTRIES:
        raise ValueError(
            f"Open ASR returned {len(rows)} rows; expected "
            f"{MIN_EXPECTED_ENTRIES}-{MAX_EXPECTED_ENTRIES}"
        )

    indexes = {name: headers.index(name) for name in required}
    entries: list[OpenAsrEntry] = []
    names: set[str] = set()
    ranks: set[int] = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != len(headers):
            raise ValueError("Open ASR response contains a malformed row")
        model_id = html.unescape(_TAG_RE.sub("", str(row[indexes["model"]]))).strip()
        rank_value = _number(row[indexes["Rank"]])
        wer = _number(row[indexes["Average WER ⬇️"]])
        rtfx = _number(row[indexes["RTFx ⬆️️"]], optional=True)
        license_name = str(row[indexes["License"]]).strip()
        rank = int(rank_value) if rank_value is not None else 0
        if not model_id or len(model_id) > 255 or "/" not in model_id:
            raise ValueError("Open ASR row has an invalid model identifier")
        if rank in ranks or model_id.casefold() in names:
            raise ValueError("Open ASR response contains duplicate models or ranks")
        if (
            rank < 1
            or wer is None
            or not 0 < wer < 100
            or (rtfx is not None and rtfx <= 0)
        ):
            raise ValueError(f"Open ASR row is outside accepted bounds for {model_id}")
        ranks.add(rank)
        names.add(model_id.casefold())
        entries.append(
            OpenAsrEntry(
                model_id=model_id,
                rank=rank,
                wer=wer,
                rtfx=rtfx,
                is_open=license_name.casefold() != "proprietary",
            )
        )
    if ranks != set(range(1, len(entries) + 1)):
        raise ValueError("Open ASR ranks must be contiguous and start at one")
    return sorted(entries, key=lambda entry: entry.rank)


def fetch_open_asr_leaderboard(
    client_factory: Callable[..., Any] = Client,
) -> list[OpenAsrEntry]:
    """Fetch the Space's exact default English leaderboard table."""
    client = client_factory(SPACE_APP_URL, verbose=False)
    # Keywords keep the call stable when the Space adds inputs; on 2026-10-22
    # a new leading version_id input made positional arguments misalign.
    payload = client.predict(
        version_id="latest",
        search_query="",
        show_proprietary=True,
        show_llm=False,
        selected_columns=DEFAULT_COLUMNS,
        api_name="/_main_table_update",
    )
    return parse_open_asr_leaderboard(_leaderboard_value(payload))


class OpenAsrPaperDiscoveryService:
    """Resolve only high-confidence arXiv papers declared by exact HF models."""

    def __init__(
        self,
        db: Session,
        *,
        hf_api: HfApi | None = None,
        arxiv_service: ArxivService | None = None,
        ingestion_service: PaperIngestionService | None = None,
    ):
        settings = get_settings()
        self.db = db
        self.hf_api = hf_api or HfApi(token=settings.hf_token or None)
        self.arxiv_service = arxiv_service or ArxivService()
        self.ingestion_service = ingestion_service or PaperIngestionService(db)

    async def discover(
        self, model_ids: list[str], *, persist: bool = True
    ) -> OpenAsrPaperDiscoveryResult:
        result = OpenAsrPaperDiscoveryResult()
        for model_id in model_ids:
            reviewed_arxiv_id = MODEL_PAPER_ARXIV_IDS.get(model_id)
            try:
                model_info = self.hf_api.model_info(
                    model_id,
                    timeout=10,
                    expand=["safetensors", "tags"],
                )
            except HFValidationError:
                # Proprietary display names (for example a preview linked to
                # a documentation Space) are not necessarily Hub model IDs.
                result.unavailable_models.append(model_id)
                continue
            except HfHubHTTPError as exc:
                if reviewed_arxiv_id is None:
                    result.unavailable_models.append(model_id)
                    continue
                model_info = None
                result.failures.append(f"{model_id}:hub_{type(exc).__name__}")

            if reviewed_arxiv_id is not None:
                arxiv_id = reviewed_arxiv_id
            else:
                arxiv_ids = {
                    canonical_arxiv_id(tag.split(":", 1)[1])
                    for tag in (getattr(model_info, "tags", None) or [])
                    if tag.casefold().startswith("arxiv:")
                    and validate_arxiv_id(tag.split(":", 1)[1])
                }
                if len(arxiv_ids) != 1:
                    if len(arxiv_ids) > 1:
                        result.ambiguous_models.append(model_id)
                    else:
                        result.unavailable_models.append(model_id)
                    continue
                arxiv_id = arxiv_ids.pop()

            paper = (
                self.db.query(Paper)
                .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version)
                .order_by(Paper.id.desc())
                .first()
            )
            metadata = None
            if paper is None:
                metadata = await self.arxiv_service.get_paper_metadata(arxiv_id)
                if not metadata.success:
                    result.failures.append(
                        f"{model_id}:{arxiv_id}:{metadata.error_type or 'arxiv_error'}"
                    )
                    continue
                paper_title = metadata.title
                paper_abstract = metadata.abstract
            else:
                paper_title = paper.title
                paper_abstract = paper.abstract

            if reviewed_arxiv_id is None and not _model_identity_matches_paper(
                model_id, paper_title, paper_abstract
            ):
                result.rejected_papers.append(f"{model_id}:{arxiv_id}")
                continue

            canonical_model_id = (
                getattr(model_info, "id", None) if model_info is not None else None
            ) or model_id
            hf_model_url = f"https://huggingface.co/{canonical_model_id}"
            num_parameters = (
                _safetensors_total(model_info) if model_info is not None else None
            )
            if not persist:
                result.would_index.append(f"{model_id}:{arxiv_id}")
                continue

            if paper is None:
                try:
                    (
                        paper,
                        created,
                    ) = await self.ingestion_service.get_or_import_arxiv_paper(arxiv_id)
                except PaperIngestionError as exc:
                    result.failures.append(
                        f"{model_id}:{arxiv_id}:{exc.error_type or 'ingestion_error'}"
                    )
                    continue
                if created:
                    result.indexed_papers.append(arxiv_id)

            hf_models = list(paper.hf_models or [])
            if hf_model_url not in hf_models:
                paper.hf_models = [*hf_models, hf_model_url]
            result.resolved[model_id.casefold()] = OpenAsrDiscoveredPaper(
                paper_id=paper.id,
                arxiv_id=arxiv_id,
                hf_model_url=hf_model_url,
                num_parameters=num_parameters,
            )
            result.discovered_models.append(f"{model_id}:{arxiv_id}")
        return result


class OpenAsrSyncService:
    """Replace only live and legacy-imported Open ASR evaluation rows."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        metrics = {
            metric.name: metric
            for metric in self.db.query(Metric)
            .filter(Metric.name.in_((WER_METRIC, RTFX_METRIC)))
            .all()
        }
        if task is None or dataset is None or set(metrics) != {WER_METRIC, RTFX_METRIC}:
            raise RuntimeError(
                "Open ASR task, benchmark, or metrics are not configured"
            )
        configured = {
            row.metric_id
            for row in self.db.query(TaskDatasetMetric)
            .filter(
                TaskDatasetMetric.task_id == task.id,
                TaskDatasetMetric.dataset_id == dataset.id,
            )
            .all()
        }
        if {metric.id for metric in metrics.values()} - configured:
            raise RuntimeError(
                "Open ASR leaderboard metrics are not linked to the task"
            )
        return task, dataset

    @staticmethod
    def _legacy_model_id(row: Evaluation) -> str | None:
        match = _LEGACY_MODEL_RE.search(row.methodology or "")
        return match.group(1) if match else None

    @staticmethod
    def _managed_model_id(row: Evaluation) -> str:
        """Return the upstream id; rows written before display names used it."""
        match = _MANAGED_MODEL_RE.match(row.methodology or "")
        return match.group(1) if match else row.model_name

    @staticmethod
    def _reviewed_arxiv_id(model_id: str) -> str | None:
        return MODEL_PAPER_ARXIV_IDS.get(model_id) or MODEL_PAPER_ARXIV_IDS.get(
            hub_model_id(model_id)
        )

    def models_needing_discovery(self, entries: list[OpenAsrEntry]) -> list[str]:
        """Return upstream model ids not already resolvable without Hub lookup."""
        task, dataset = self._leaderboard_identity()
        candidate_rows = (
            self.db.query(Evaluation)
            .filter(
                Evaluation.task_id == task.id,
                Evaluation.dataset_id == dataset.id,
            )
            .all()
        )
        resolved_names = {
            self._managed_model_id(row).casefold()
            for row in candidate_rows
            if row.external_source_url == SPACE_SOURCE_URL
            and (row.methodology or "").startswith(MANAGED_METHODOLOGY_PREFIX)
        }
        resolved_names.update(
            legacy_model_id.casefold()
            for row in candidate_rows
            if row.external_source_url == LEGACY_SOURCE_URL
            and (row.methodology or "").startswith("Open ASR Leaderboard rank ")
            and (legacy_model_id := self._legacy_model_id(row)) is not None
        )
        existing_arxiv_ids = {
            arxiv_id
            for (arxiv_id,) in self.db.query(Paper.arxiv_id)
            .filter(
                Paper.arxiv_id.in_(set(MODEL_PAPER_ARXIV_IDS.values())),
                Paper.is_latest_version,
            )
            .all()
        }
        needed = [
            hub_model_id(entry.model_id)
            for entry in entries
            if entry.model_id.casefold() not in resolved_names
            and self._reviewed_arxiv_id(entry.model_id) not in existing_arxiv_ids
        ]
        return list(dict.fromkeys(needed))

    def sync(
        self,
        entries: list[OpenAsrEntry],
        *,
        discovery: OpenAsrPaperDiscoveryResult | None = None,
        fetched_at: datetime | None = None,
        commit: bool = True,
    ) -> OpenAsrSyncStats:
        if not entries:
            raise ValueError("Refusing to synchronize an empty Open ASR leaderboard")
        now = fetched_at or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        stats = OpenAsrSyncStats(fetched=len(entries))

        try:
            task, dataset = self._leaderboard_identity()
            papers_by_arxiv = {
                paper.arxiv_id: paper.id
                for paper in self.db.query(Paper)
                .filter(
                    Paper.arxiv_id.in_(set(MODEL_PAPER_ARXIV_IDS.values())),
                    Paper.is_latest_version,
                )
                .all()
            }
            candidate_rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                )
                .all()
            )
            managed_rows = [
                row
                for row in candidate_rows
                if row.external_source_url == SPACE_SOURCE_URL
                and (row.methodology or "").startswith(MANAGED_METHODOLOGY_PREFIX)
            ]
            legacy_rows = [
                row
                for row in candidate_rows
                if row.external_source_url == LEGACY_SOURCE_URL
                and (row.methodology or "").startswith("Open ASR Leaderboard rank ")
                and self._legacy_model_id(row) is not None
            ]
            managed_by_id = {
                self._managed_model_id(row).casefold(): row for row in managed_rows
            }
            # A curated row naming an upstream model on the same paper (for
            # example a paper-reported score from an older board version) is
            # superseded by the live score instead of shown beside it.
            owned_ids = {row.id for row in [*managed_rows, *legacy_rows]}
            other_rows = {
                (row.paper_id, (row.model_name or "").casefold()): row
                for row in candidate_rows
                if row.id not in owned_ids
            }
            display_names = display_model_names(entries)
            legacy_papers = {
                self._legacy_model_id(row).casefold(): row.paper_id
                for row in legacy_rows
            }
            upstream_names = {entry.model_id.casefold() for entry in entries}

            for entry in entries:
                key = entry.model_id.casefold()
                hub_id = hub_model_id(entry.model_id)
                display_name = display_names[entry.model_id]
                row = managed_by_id.get(key)
                discovered = (
                    discovery.resolved.get(hub_id.casefold()) if discovery else None
                )
                # A reviewed paper corrects rows carried over from the legacy
                # importer; otherwise keep the row's (possibly curated) paper.
                arxiv_id = self._reviewed_arxiv_id(entry.model_id)
                paper_id = papers_by_arxiv.get(arxiv_id) if arxiv_id else None
                if paper_id is None:
                    paper_id = (
                        row.paper_id if row is not None else legacy_papers.get(key)
                    )
                if paper_id is None:
                    if discovered is not None:
                        paper_id = discovered.paper_id
                    if paper_id is None and arxiv_id is None:
                        stats.unmatched_models.append(entry.model_id)
                        continue
                    if paper_id is None:
                        stats.missing_papers.append(f"{entry.model_id}:{arxiv_id}")
                        continue

                methodology = (
                    f"{MANAGED_METHODOLOGY_PREFIX} Upstream model {entry.model_id}; "
                    f"rank {entry.rank}; default Average WER; "
                    f"fetched {now.isoformat()}."
                )
                if row is None:
                    row = other_rows.pop(
                        (paper_id, entry.model_id.casefold()), None
                    ) or other_rows.pop((paper_id, display_name.casefold()), None)
                if row is None:
                    row = Evaluation(
                        paper_id=paper_id,
                        task_id=task.id,
                        dataset_id=dataset.id,
                    )
                    self.db.add(row)
                    stats.created += 1
                else:
                    stats.updated += 1
                row.model_name = display_name
                metrics: dict[str, float] = {WER_METRIC: entry.wer}
                if entry.rtfx is not None:
                    metrics[RTFX_METRIC] = entry.rtfx
                row.paper_id = paper_id
                row.methodology = methodology
                row.metrics = metrics
                row.uses_additional_data = False
                row.is_open = entry.is_open
                row.best_metric = WER_METRIC
                row.evaluated_on = now.date()
                row.external_source_url = SPACE_SOURCE_URL
                row.source_url = SPACE_SOURCE_URL
                row.external = True
                row.updated_at = now
                if entry.is_open and not row.hf_model_url:
                    row.hf_model_url = f"https://huggingface.co/{hub_id}"
                if discovered is not None:
                    row.hf_model_url = discovered.hf_model_url
                    row.num_parameters = discovered.num_parameters
                    if (
                        self.db.query(PaperTask)
                        .filter(
                            PaperTask.paper_id == paper_id,
                            PaperTask.task_id == task.id,
                        )
                        .first()
                        is None
                    ):
                        self.db.add(
                            PaperTask(
                                paper_id=paper_id,
                                task_id=task.id,
                                source="auto",
                            )
                        )
                stats.matched += 1

            for row in managed_rows:
                if self._managed_model_id(row).casefold() not in upstream_names:
                    self.db.delete(row)
                    stats.deleted += 1
            # These rows came from the retired one-shot importer. Once a valid
            # live table has been processed, its replacements are authoritative.
            for row in legacy_rows:
                self.db.delete(row)
                stats.deleted += 1

            self.db.flush()
            # Live rows also carry RTFx, which affects preserved paper-native
            # rows whose primary metric is throughput.
            evaluation_service = EvaluationService(self.db)
            for metric in (WER_METRIC, RTFX_METRIC):
                evaluation_service.recalculate_ranks(
                    task.id, dataset.id, metric_name=metric, commit=False
                )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise
