"""Read-only daily view of Papers With Code curation activity."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import gradio as gr
import pandas as pd


LOCAL_SNAPSHOT = Path(__file__).parent / "data" / "snapshot.json"


def load_snapshot(path: str | Path | None = None) -> dict[str, Any]:
    """Load the latest snapshot from the configured Hub dataset or local file."""
    snapshot_path = (
        Path(path or os.environ.get("SNAPSHOT_PATH", ""))
        if (path or os.environ.get("SNAPSHOT_PATH"))
        else None
    )
    repo_id = os.environ.get("SNAPSHOT_REPO_ID")
    if snapshot_path is None and repo_id:
        from huggingface_hub import hf_hub_download

        snapshot_path = Path(
            hf_hub_download(
                repo_id=repo_id,
                repo_type="dataset",
                filename="snapshot.json",
                token=os.environ.get("HF_TOKEN"),
            )
        )
    snapshot_path = snapshot_path or LOCAL_SNAPSHOT
    if not snapshot_path.exists():
        raise FileNotFoundError(f"No dashboard snapshot found at {snapshot_path}")
    snapshot = json.loads(snapshot_path.read_text())
    if snapshot.get("schema_version") != 1:
        raise ValueError("Unsupported dashboard snapshot schema")
    return snapshot


def _date_options(snapshot: dict[str, Any]) -> list[str]:
    return [row["day"] for row in reversed(snapshot.get("daily", []))]


def _matches(row: dict[str, Any], query: str) -> bool:
    return not query or query.lower() in json.dumps(row, ensure_ascii=False).lower()


def filter_enrichment(snapshot: dict[str, Any], day: str, query: str) -> pd.DataFrame:
    rows = [
        row
        for row in snapshot.get("papers", [])
        if (not day or row["day"] == day) and _matches(row, query)
    ]
    return pd.DataFrame(
        rows, columns=["day", "paper_id", "title", "status", "mutation_status", "error"]
    )


def filter_evaluations(snapshot: dict[str, Any], day: str, query: str) -> pd.DataFrame:
    rows = [
        row
        for row in snapshot.get("evaluations", [])
        if (not day or row["created_at"][:10] == day) and _matches(row, query)
    ]
    return pd.DataFrame(rows)


def filter_gaps(
    snapshot: dict[str, Any], day: str, query: str, gap_type: str
) -> pd.DataFrame:
    rows = [
        row
        for row in snapshot.get("benchmark_gaps", [])
        if (not day or row["created_at"][:10] == day)
        and (not gap_type or row["gap_type"] == gap_type)
        and _matches(row, query)
    ]
    return pd.DataFrame(rows)


def summary_markdown(snapshot: dict[str, Any], day: str) -> str:
    stats = next((row for row in snapshot.get("daily", []) if row["day"] == day), None)
    if not stats:
        return "No activity for this day."
    return (
        f"### {day}\n"
        f"Enrichment: **{stats['enrichment_applied']} applied**, "
        f"{stats['enrichment_noops']} no-op, {stats['enrichment_failed']} failed  \n"
        f"Evaluations created: **{stats['evaluations_created']}**  \n"
        f"Benchmark-gap reports: **{stats['benchmark_gap_reports']}**"
    )


def refresh_snapshot() -> str:
    latest = load_snapshot()
    snapshot.clear()
    snapshot.update(latest)
    return f"Snapshot refreshed: **{snapshot.get('generated_at', 'unknown')}**"


snapshot = load_snapshot()
dates = _date_options(snapshot)
default_day = dates[0] if dates else ""
gap_types = sorted({row["gap_type"] for row in snapshot.get("benchmark_gaps", [])})

with gr.Blocks(title="PWC Daily Enrichment Dashboard", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        "# Papers With Code · Daily Enrichment\nRead-only operational history of paper enrichment, evaluations, and benchmark gaps."
    )
    snapshot_status = gr.Markdown(
        f"Snapshot generated: **{snapshot.get('generated_at', 'unknown')}**"
    )
    refresh = gr.Button("Refresh snapshot", size="sm")
    refresh.click(refresh_snapshot, outputs=snapshot_status)
    with gr.Tab("Enrichment & evaluations"):
        day = gr.Dropdown(
            dates, value=default_day, label="UTC day", allow_custom_value=True
        )
        query = gr.Textbox(label="Search papers", placeholder="Title or paper ID")
        summary = gr.Markdown(summary_markdown(snapshot, default_day))
        papers = gr.Dataframe(
            filter_enrichment(snapshot, default_day, ""),
            label="Enrichment jobs",
            interactive=False,
        )
        evals = gr.Dataframe(
            filter_evaluations(snapshot, default_day, ""),
            label="Evaluations created",
            interactive=False,
        )
        day.change(lambda value: summary_markdown(snapshot, value), day, summary)
        day.change(
            lambda value, text: filter_enrichment(snapshot, value, text),
            [day, query],
            papers,
        )
        day.change(
            lambda value, text: filter_evaluations(snapshot, value, text),
            [day, query],
            evals,
        )
        query.change(
            lambda value, text: filter_enrichment(snapshot, value, text),
            [day, query],
            papers,
        )
        query.change(
            lambda value, text: filter_evaluations(snapshot, value, text),
            [day, query],
            evals,
        )
    with gr.Tab("Benchmark gaps"):
        gap_day = gr.Dropdown(
            dates, value=default_day, label="UTC day", allow_custom_value=True
        )
        gap_query = gr.Textbox(label="Search gaps or source papers")
        gap_type = gr.Dropdown(gap_types, label="Gap type", allow_custom_value=True)
        gaps = gr.Dataframe(
            filter_gaps(snapshot, default_day, "", ""),
            label="Reported benchmark gaps",
            interactive=False,
        )
        for component in (gap_day, gap_query, gap_type):
            component.change(
                lambda value, text, kind: filter_gaps(snapshot, value, text, kind),
                [gap_day, gap_query, gap_type],
                gaps,
            )


if __name__ == "__main__":
    demo.launch()
