"""Launch the paged-Markdown layout pilot for recently imported papers.

Writes a manifest of the latest papers created in the last ``--days`` days to the
private layout bucket and starts one HF Job running
``generate_paper_layout_markdown.py``. Without ``--execute`` it only reports the
selection. Canonical Markdown is never touched.

    uv run --env-file backend/keys.env python -m backend.scripts.launch_paper_layout_pilot --days 7 --execute
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from huggingface_hub import HfApi
from sqlalchemy import select

from backend.config import get_settings
from backend.database.connection import get_engine
from backend.models.database import Paper as DBPaper
from backend.services.paper_markdown_service import normalize_markdown_arxiv_id

LAYOUT_BUCKET_ID = "huggingface/pwc-papers-pages"
JOB_SCRIPT = Path(__file__).with_name("generate_paper_layout_markdown.py")


def manifest_entries(days: int) -> list[dict[str, str]]:
    since = datetime.now(UTC) - timedelta(days=days)
    query = (
        select(DBPaper.id, DBPaper.source, DBPaper.arxiv_id, DBPaper.version)
        .where(DBPaper.is_latest_version, DBPaper.created_at >= since)
        .order_by(DBPaper.created_at.desc())
    )
    entries = []
    with get_engine().connect() as connection:
        for paper_id, source, arxiv_id, version in connection.execute(query):
            if source == "external":
                entries.append(
                    {"paper_key": f"external/{paper_id}", "source": "external"}
                )
            elif source == "arxiv" and arxiv_id:
                normalized = normalize_markdown_arxiv_id(arxiv_id)
                entries.append(
                    {
                        "paper_key": f"{normalized[:4]}/{normalized}",
                        "source": "arxiv",
                        "arxiv_id": normalized,
                        "version": version or "",
                    }
                )
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument(
        "--limit", type=int, help="Only the newest N papers (smoke runs)"
    )
    parser.add_argument("--shards", type=int, default=1, help="Parallel HF Jobs")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    entries = manifest_entries(args.days)[: args.limit]
    sources = {
        source: sum(e["source"] == source for e in entries)
        for source in ("arxiv", "external")
    }
    print(json.dumps({"papers": len(entries), **sources}))
    api = HfApi(token=settings.hf_token or None)
    archived = {
        str(item.path)
        for item in api.get_bucket_paths_info(
            settings.paper_markdown_hf_bucket_id,
            [
                f"{e['paper_key']}/paper.pdf"
                for e in entries
                if e["source"] == "external"
            ],
        )
    }
    entries = [
        e
        for e in entries
        if e["source"] == "arxiv" or f"{e['paper_key']}/paper.pdf" in archived
    ]
    print(json.dumps({"papers_with_pdf": len(entries)}))
    if not args.execute:
        return

    api.create_bucket(LAYOUT_BUCKET_ID, private=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for shard in range(args.shards):
        manifest_key = f"_jobs/manifests/{run_id}-{shard}.json"
        with tempfile.TemporaryDirectory(prefix="pwc-layout-pilot-") as directory:
            path = Path(directory) / "manifest.json"
            shard_entries = entries[shard :: args.shards]
            path.write_text(json.dumps({"entries": shard_entries}), encoding="utf-8")
            api.batch_bucket_files(LAYOUT_BUCKET_ID, add=[(path, manifest_key)])
        job = api.run_uv_job(
            str(JOB_SCRIPT),
            script_args=[
                "--layout-bucket",
                LAYOUT_BUCKET_ID,
                "--source-bucket",
                settings.paper_markdown_hf_bucket_id,
                "--manifest-key",
                manifest_key,
            ],
            image=settings.paper_markdown_runtime_image,
            flavor=settings.paper_markdown_hardware,
            timeout="24h",
            labels={"app": "pwc-paper-layout", "run_id": run_id, "shard": str(shard)},
            env={
                "PWC_MARKDOWN_MODEL_ID": settings.paper_markdown_model_id,
                "PWC_MARKDOWN_MODEL_REVISION": settings.paper_markdown_model_revision,
                "PWC_MARKDOWN_MAX_PAGES": str(settings.paper_markdown_max_pages),
            },
            secrets={"HF_TOKEN": settings.hf_token},
            namespace=settings.paper_markdown_hf_namespace,
        )
        print(
            json.dumps(
                {
                    "shard_run_id": Path(manifest_key).stem,
                    "job_id": job.id,
                    "url": job.url,
                }
            )
        )


if __name__ == "__main__":
    main()
