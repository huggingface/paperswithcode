# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "httpx>=0.28.1",
#   "huggingface-hub==1.23.0",
#   "pymupdf>=1.24",
# ]
# ///
"""Score Chandra layout blocks against each PDF's own text layer.

For every text block, the block's words are looked up among the PDF words
whose centres fall inside the block's box (scaled from Chandra's 0-1000 grid to
the PDF page). A block is aligned when at least ``--threshold`` of its words
are found there. This is the property reader citations rely on: highlighting a
block's box must cover the text the model cited. PyMuPDF stands in for the
pdf.js text layer the reader uses; both read the same PDF text objects.

Also reports a quote-only baseline (does a sentence from the block occur in the
page text after normalization?) and writes overlay PNGs plus an HTML report.

    uv run --no-project backend/scripts/evaluate_paper_layout.py --run-id <run> --out <dir>
"""

from __future__ import annotations

import argparse
import html
import json
import os
import random
import re
import tempfile
import unicodedata
from pathlib import Path

import fitz
import httpx
from huggingface_hub import HfApi

LAYOUT_BUCKET_ID = "huggingface/pwc-papers-pages"
SOURCE_BUCKET_ID = "huggingface/pwc-papers-content"
TEXT_LABELS = {"Text", "Section-Header", "List-Group", "Caption", "Footnote"}
LABEL_COLORS = {
    "Text": (0.15, 0.4, 0.9),
    "Section-Header": (0.9, 0.3, 0.1),
    "Caption": (0.1, 0.6, 0.3),
    "Equation-Block": (0.6, 0.2, 0.7),
    "Table": (0.8, 0.6, 0.0),
    "Figure": (0.4, 0.4, 0.4),
    "Image": (0.4, 0.4, 0.4),
}
WORD = re.compile(r"[a-z0-9]{3,}")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"-\s*\n\s*", "", text)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def words(text: str) -> list[str]:
    return WORD.findall(normalize(text))


def fetch_pdf(api: HfApi, paper_key: str, directory: Path) -> Path:
    path = directory / "paper.pdf"
    if paper_key.startswith("external/"):
        api.download_bucket_files(SOURCE_BUCKET_ID, [(f"{paper_key}/paper.pdf", path)])
    else:
        arxiv_id = paper_key.split("/", 1)[1]
        response = httpx.get(
            f"https://arxiv.org/pdf/{arxiv_id}",
            headers={"User-Agent": "paperswithcode-layout-eval/1.0"},
            follow_redirects=True,
            timeout=60,
        )
        response.raise_for_status()
        path.write_bytes(response.content)
    return path


def block_rect(page: fitz.Page, bbox: list[int]) -> fitz.Rect:
    width, height = page.rect.width, page.rect.height
    return fitz.Rect(
        bbox[0] * width / 1000,
        bbox[1] * height / 1000,
        bbox[2] * width / 1000,
        bbox[3] * height / 1000,
    )


def score_paper(document: fitz.Document, blocks: dict[str, dict], threshold: float):
    pages: dict[int, list] = {}
    page_text: dict[int, str] = {}
    rows = []
    for anchor, block in blocks.items():
        if block["label"] not in TEXT_LABELS:
            continue
        expected = words(block["text"])
        if len(expected) < 4:
            continue
        number = int(block["page"])
        page = document[number - 1]
        if number not in pages:
            pages[number] = page.get_text("words")
            page_text[number] = normalize(page.get_text())
        if not pages[number]:
            rows.append({"anchor": anchor, "status": "no_text_layer"})
            continue
        rect = block_rect(page, block["bbox"])
        rect = rect + (-2, -2, 2, 2)
        inside = set()
        for x0, y0, x1, y1, word, *_ in pages[number]:
            if rect.contains(fitz.Point((x0 + x1) / 2, (y0 + y1) / 2)):
                inside.update(words(word))
        recall = sum(word in inside for word in expected) / len(expected)
        sentence = normalize(block["text"])
        snippet = " ".join(sentence.split()[:12])
        rows.append(
            {
                "anchor": anchor,
                "label": block["label"],
                "status": "aligned" if recall >= threshold else "misaligned",
                "recall": round(recall, 3),
                "quote_found": snippet in page_text[number],
            }
        )
    return rows


def render_overlay(
    document: fitz.Document, blocks: dict, number: int, out: Path
) -> None:
    page = document[number - 1]
    for block in blocks.values():
        if int(block["page"]) != number:
            continue
        color = LABEL_COLORS.get(block["label"], (0.2, 0.2, 0.2))
        page.draw_rect(block_rect(page, block["bbox"]), color=color, width=1.2)
    page.get_pixmap(dpi=80).save(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--overlays", type=int, default=12)
    args = parser.parse_args()

    api = HfApi(token=os.environ.get("HF_TOKEN"))
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        results = []
        for run_id in args.run_id:
            path = Path(directory) / f"{run_id}.jsonl"
            api.download_bucket_files(
                LAYOUT_BUCKET_ID, [(f"_jobs/results/{run_id}.jsonl", path)]
            )
            results += [json.loads(line) for line in path.read_text().splitlines()]

    papers = []
    overlay_budget = args.overlays
    rng = random.Random(0)
    for result in results:
        if not result.get("ok"):
            papers.append(
                {"paper_key": result["paper_key"], "error": result.get("error")}
            )
            continue
        key = result["paper_key"]
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            api.download_bucket_files(
                LAYOUT_BUCKET_ID, [(f"{key}.blocks.json", work / "blocks.json")]
            )
            blocks = json.loads((work / "blocks.json").read_text())["blocks"]
            with fitz.open(fetch_pdf(api, key, work)) as document:
                rows = score_paper(document, blocks, args.threshold)
                overlay = None
                if overlay_budget > 0 and blocks:
                    number = rng.choice(
                        sorted({int(b["page"]) for b in blocks.values()})
                    )
                    overlay = f"{key.replace('/', '_')}_p{number}.png"
                    render_overlay(document, blocks, number, args.out / overlay)
                    overlay_budget -= 1
        scored = [row for row in rows if row["status"] != "no_text_layer"]
        papers.append(
            {
                "paper_key": key,
                "blocks": len(blocks),
                "sections": sum(
                    b["label"] == "Section-Header" for b in blocks.values()
                ),
                "scored": len(scored),
                "aligned": sum(row["status"] == "aligned" for row in scored),
                "quote_found": sum(row["quote_found"] for row in scored),
                "no_text_layer": len(rows) - len(scored),
                "page_count": result["page_count"],
                "processed_pages": result["processed_pages"],
                "page_errors": result["page_errors"],
                "seconds": result["seconds"],
                "overlay": overlay,
                "worst": sorted(scored, key=lambda row: row["recall"])[:3],
            }
        )
        print(
            json.dumps({k: v for k, v in papers[-1].items() if k != "worst"}),
            flush=True,
        )

    ok = [paper for paper in papers if "error" not in paper]
    scored = sum(paper["scored"] for paper in ok)
    summary = {
        "papers": len(papers),
        "failed": len(papers) - len(ok),
        "scored_blocks": scored,
        "aligned_rate": round(sum(p["aligned"] for p in ok) / max(scored, 1), 4),
        "quote_found_rate": round(
            sum(p["quote_found"] for p in ok) / max(scored, 1), 4
        ),
        "papers_over_30_pages": sum(p["page_count"] > p["processed_pages"] for p in ok),
        "papers_without_text_layer": sum(
            p["scored"] == 0 and p["no_text_layer"] > 0 for p in ok
        ),
        "median_seconds": sorted(p["seconds"] for p in ok)[len(ok) // 2]
        if ok
        else None,
    }
    (args.out / "summary.json").write_text(
        json.dumps({"summary": summary, "papers": papers}, indent=1)
    )
    print(json.dumps(summary))

    cards = "".join(
        f"<figure><img src='{html.escape(p['overlay'])}'><figcaption>{html.escape(p['paper_key'])}"
        f" — {p['aligned']}/{p['scored']} aligned</figcaption></figure>"
        for p in ok
        if p["overlay"]
    )
    (args.out / "overlays.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Layout overlays</title>"
        "<style>body{font:14px system-ui;margin:16px}figure{display:inline-block;margin:8px;"
        "max-width:420px}img{max-width:100%;border:1px solid #ccc}</style>"
        f"<pre>{html.escape(json.dumps(summary, indent=1))}</pre>{cards}"
    )


if __name__ == "__main__":
    main()
