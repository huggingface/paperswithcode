"""Live boards for the official Physics-IQ Verified video generation leaderboard.

The README lists one table with an image-to-video (I2V) and a multi-frame
(V2V) track. Each track is its own board on the shared benchmark, publishing
its own metric through ``LiveLeaderboardSyncService``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import isfinite

import httpx

from backend.services.leaderboard_sync_catalog import ModelIdentity
from backend.services.live_leaderboard_sync import (
    LeaderboardEntry,
    LiveLeaderboard,
    fetch_text,
)

# physics-iq-verified.anates.ai renders the same table from data compiled into
# its Next.js bundle and exposes no JSON endpoint, so the README is canonical.
PHYSICS_IQ_README_URL = (
    "https://raw.githubusercontent.com/google-deepmind/physics-IQ-benchmark/"
    "main/README.md"
)
PHYSICS_IQ_URL = "https://github.com/google-deepmind/physics-IQ-benchmark"
USER_AGENT = "paperswithcode-physics-iq-verified-sync/1.0"
TASK_SLUG = "video-generation"
DATASET_SLUG = "physics-iq-verified"
METRIC_BY_TRACK = {
    "i2v": "Physics-IQ Verified Score (I2V)",
    "v2v": "Physics-IQ Verified Score (V2V)",
}
TRACK_BY_INPUT_TYPE = {"i2v": "i2v", "multiframe (v2v)": "v2v"}
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
# Refuse to touch a track when its reviewed subset collapses.
MIN_SELECTED_BY_TRACK = {"i2v": 20, "v2v": 5}


_COSMOS_3 = "2606.02800"
_COSMOS_3_SUPER = ModelIdentity(
    "Cosmos3-Super",
    arxiv_id=_COSMOS_3,
    is_open=True,
    hf_model_url="https://huggingface.co/nvidia/Cosmos3-Super",
)
_COSMOS_3_NANO = ModelIdentity(
    "Cosmos3-Nano",
    arxiv_id=_COSMOS_3,
    is_open=True,
    hf_model_url="https://huggingface.co/nvidia/Cosmos3-Nano",
)
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
    # NVIDIA's single-generation runs with GPT-6 Astra upsampled prompts; like
    # the FLUX 3 prompt rows, the prompts change but the model is Cosmos 3.
    ("Cosmos3-Super + Prompt Upsampling", "v2v"): _COSMOS_3_SUPER,
    ("Cosmos3-Super + Prompt Upsampling", "i2v"): _COSMOS_3_SUPER,
    ("Cosmos3-Nano + Prompt Upsampling", "v2v"): _COSMOS_3_NANO,
    ("Cosmos3-Nano + Prompt Upsampling", "i2v"): _COSMOS_3_NANO,
    ("Cosmos3-Super", "v2v"): _COSMOS_3_SUPER,
    ("Cosmos3-Nano", "v2v"): _COSMOS_3_NANO,
    ("Cosmos3-Nano", "i2v"): _COSMOS_3_NANO,
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
    return parse_physics_iq_leaderboard(
        fetch_text(PHYSICS_IQ_README_URL, client, user_agent=USER_AGENT)
    )


def _leaderboard_entry(entry: PhysicsIqEntry) -> LeaderboardEntry:
    return LeaderboardEntry(
        entry.label,
        entry.score,
        f"{entry.score_text} ({entry.track}), added "
        f"{entry.date_added.isoformat()}, report {entry.report_url}",
        source_url=entry.report_url,
        evaluated_on=entry.date_added,
    )


BOARDS = {
    track: LiveLeaderboard(
        source="Physics-IQ Verified",
        provider="physics-iq-verified",
        url=PHYSICS_IQ_URL,
        task_slug=TASK_SLUG,
        dataset_slug=DATASET_SLUG,
        metric=metric,
        identities={
            label: identity
            for (label, identity_track), identity in MODEL_IDENTITIES.items()
            if identity_track == track
        },
        min_selected=MIN_SELECTED_BY_TRACK[track],
    )
    for track, metric in METRIC_BY_TRACK.items()
}


def split_boards(
    entries: list[PhysicsIqEntry],
) -> list[tuple[LiveLeaderboard, list[LeaderboardEntry]]]:
    """Drop excluded rows and hand each track's rows to its board."""
    eligible = [entry for entry in entries if exclusion_reason(entry) is None]
    return [
        (
            board,
            [_leaderboard_entry(entry) for entry in eligible if entry.track == track],
        )
        for track, board in BOARDS.items()
    ]


def fetch_physics_iq_boards(
    client: httpx.Client | None = None,
) -> list[tuple[LiveLeaderboard, list[LeaderboardEntry]]]:
    """Fetch the README once and split its rows into the two track boards."""
    return split_boards(fetch_physics_iq_leaderboard(client))
