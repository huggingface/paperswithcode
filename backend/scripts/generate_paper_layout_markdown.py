# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "chandra-ocr==0.2.0",
#   "httpx>=0.28.1",
#   "vllm==0.17.0",
# ]
# ///
"""OCR papers with Chandra OCR 2 and keep page and block layout (HF Job).

Unlike the canonical Markdown generator, this keeps Chandra's per-page layout
blocks so reader citations can point at a page and a paragraph box. Each paper
gets three objects in the layout bucket:

- ``<key>.layout.json``: Chandra's raw per-page output, the source of truth;
- ``<key>.md``: Markdown with a ``<!-- pwc:p{page}b{block} -->`` anchor per block;
- ``<key>.blocks.json``: anchor -> page, label, bbox (0-1000 grid), section.

Papers already present in the layout bucket are skipped, so a run resumes.
A paper without a ``.md`` after its run failed; the job log has the error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

MODEL_ID = os.environ.get("PWC_MARKDOWN_MODEL_ID", "datalab-to/chandra-ocr-2")
MODEL_REVISION = os.environ.get(
    "PWC_MARKDOWN_MODEL_REVISION", "af93b47dba1b47b6640c86ccf487ed2260ab9a09"
)
MAX_PAGES = int(os.environ.get("PWC_MARKDOWN_MAX_PAGES", "30"))
MAX_PDF_BYTES = 150 * 1024 * 1024
PAGE_BATCH_SIZE = 28
MAX_OUTPUT_TOKENS = 12384
LAYOUT_SCHEMA_VERSION = 1
USER_AGENT = "paperswithcode-paper-layout/1.0 (https://paperswithcode.co)"
ARXIV_PDF_HOSTS = {"arxiv.org", "export.arxiv.org"}
SKIPPED_LABELS = {"Blank-Page", "Page-Header", "Page-Footer"}
NON_TEXT_LABELS = {"Image", "Figure"}
BUCKET_BRIDGE_HUB_VERSION = "1.23.0"
BUCKET_BRIDGE_CODE = r"""
import json
import sys
from pathlib import Path

from huggingface_hub import HfApi

request = json.load(sys.stdin)
api = HfApi()
operation = request["operation"]
if operation == "existing":
    paths = api.get_bucket_paths_info(request["bucket_id"], request["keys"])
    response = {"paths": [str(item.path) for item in paths]}
elif operation == "download":
    files = [(key, Path(destination)) for key, destination in request["files"]]
    api.download_bucket_files(request["bucket_id"], files, raise_on_missing_files=True)
    response = {}
elif operation == "upload":
    api.batch_bucket_files(
        request["bucket_id"],
        add=[(Path(source), destination) for source, destination in request["files"]],
    )
    response = {}
else:
    raise ValueError(f"unsupported bucket bridge operation: {operation}")
json.dump(response, sys.stdout)
"""


def bucket_bridge(request: dict[str, object]) -> dict[str, object]:
    """Run bucket I/O in an SDK environment isolated from vLLM's SDK pin."""
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--no-project",
            "--with",
            f"huggingface-hub=={BUCKET_BRIDGE_HUB_VERSION}",
            "python",
            "-c",
            BUCKET_BRIDGE_CODE,
        ],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"bucket bridge failed: {completed.stderr.strip()[-2000:]}")
    return json.loads(completed.stdout)


def start_vllm() -> subprocess.Popen[bytes]:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vllm.entrypoints.openai.api_server",
            "--model",
            MODEL_ID,
            "--revision",
            MODEL_REVISION,
            "--served-model-name",
            "chandra",
            "--max-model-len",
            "18000",
            "--gpu-memory-utilization",
            "0.85",
            "--port",
            "8000",
            "--trust-remote-code",
            "--dtype",
            "bfloat16",
            "--max-num-seqs",
            "32",
            "--max_num_batched_tokens",
            "4096",
            "--enable-prefix-caching",
            "--mm-processor-kwargs",
            '{"min_pixels":3136,"max_pixels":6291456}',
            "--api-key",
            "EMPTY",
            "--no-enable-log-requests",
        ]
    )
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("vLLM exited during startup")
        try:
            if httpx.get("http://127.0.0.1:8000/health", timeout=2).is_success:
                return process
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise TimeoutError("vLLM startup timed out")


def _require_arxiv_host(request: httpx.Request) -> None:
    if request.url.scheme != "https" or request.url.host not in ARXIV_PDF_HOSTS:
        raise ValueError("arXiv PDF redirected off arXiv")


def download_arxiv_pdf(arxiv_id: str, version: str | None) -> bytes:
    url = f"https://arxiv.org/pdf/{arxiv_id}{version or ''}"
    data = bytearray()
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=60,
        follow_redirects=True,
        max_redirects=3,
        event_hooks={"request": [_require_arxiv_host]},
    ) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_PDF_BYTES:
                    raise ValueError("pdf_too_large")
    return bytes(data)


def read_pdf(entry: dict[str, str], source_bucket: str, work: Path) -> Path:
    path = work / "paper.pdf"
    if entry["source"] == "external":
        bucket_bridge(
            {
                "operation": "download",
                "bucket_id": source_bucket,
                "files": [(f"{entry['paper_key']}/paper.pdf", str(path))],
            }
        )
    else:
        path.write_bytes(download_arxiv_pdf(entry["arxiv_id"], entry.get("version")))
    if not path.read_bytes()[:5] == b"%PDF-":
        raise ValueError("not_a_pdf")
    return path


def ocr_pages(pdf: Path) -> tuple[int, list[dict[str, object]]]:
    """Return the PDF page count and Chandra's raw output for the leading pages."""
    import pypdfium2
    from chandra.input import load_pdf_images
    from chandra.model import InferenceManager
    from chandra.model.schema import BatchInputItem

    page_count = len(pypdfium2.PdfDocument(str(pdf)))
    images = load_pdf_images(str(pdf), list(range(min(page_count, MAX_PAGES))))
    model = InferenceManager(method="vllm")
    pages: list[dict[str, object]] = []
    for start in range(0, len(images), PAGE_BATCH_SIZE):
        batch = [
            BatchInputItem(image=image, prompt_type="ocr_layout")
            for image in images[start : start + PAGE_BATCH_SIZE]
        ]
        results = model.generate(batch, max_output_tokens=MAX_OUTPUT_TOKENS)
        for offset, (item, result) in enumerate(zip(batch, results)):
            pages.append(
                {
                    "page": start + offset + 1,
                    "image_size": [item.image.width, item.image.height],
                    "raw": result.raw,
                    "token_count": result.token_count,
                    "error": bool(result.error),
                }
            )
    return page_count, pages


def build_paged_markdown(
    pages: list[dict[str, object]],
) -> tuple[str, dict[str, dict[str, object]]]:
    """Turn raw Chandra pages into anchored Markdown plus a block sidecar.

    Anchors are ``p{page}b{block}`` where ``block`` is the 1-based position of
    the layout block on its page, so they stay stable against the raw layout.
    Bboxes stay on Chandra's 0-1000 grid, which maps onto any rendered page size.
    """
    from bs4 import BeautifulSoup
    from chandra.output import parse_markdown

    parts: list[str] = []
    blocks: dict[str, dict[str, object]] = {}
    section: str | None = None
    for page in pages:
        page_number = int(page["page"])
        parts.append(f"<!-- pwc:page {page_number} -->")
        soup = BeautifulSoup(str(page["raw"]), "html.parser")
        for index, div in enumerate(soup.find_all("div", recursive=False), 1):
            label = div.get("data-label") or "block"
            if label in SKIPPED_LABELS:
                continue
            try:
                bbox = [int(value) for value in str(div.get("data-bbox")).split()]
            except ValueError:
                continue
            if len(bbox) != 4:
                continue
            anchor = f"p{page_number}b{index}"
            if label == "Section-Header":
                section = anchor
            text = BeautifulSoup(div.decode_contents(), "html.parser").get_text(" ")
            blocks[anchor] = {
                "page": page_number,
                "label": label,
                "bbox": bbox,
                "section": section,
                "text": " ".join(text.split())[:2000],
            }
            if label in NON_TEXT_LABELS:
                continue
            body = parse_markdown(str(div), include_images=False)
            if body:
                parts.append(f"<!-- pwc:{anchor} -->\n{body}")
    return "\n\n".join(parts) + "\n", blocks


def process(
    entry: dict[str, str], *, layout_bucket: str, source_bucket: str, run_id: str
) -> dict[str, object]:
    key = entry["paper_key"]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="pwc-layout-") as directory:
        work = Path(directory)
        page_count, pages = ocr_pages(read_pdf(entry, source_bucket, work))
        markdown, blocks = build_paged_markdown(pages)
        # Each paper records its own outcome, so a resumed or killed run never
        # loses results that were already stored.
        meta = {
            "schema_version": LAYOUT_SCHEMA_VERSION,
            "paper_key": key,
            "source": entry["source"],
            "arxiv_version": entry.get("version") or None,
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "page_count": page_count,
            "processed_pages": len(pages),
            "page_errors": sum(1 for page in pages if page["error"]),
            "seconds": round(time.monotonic() - started, 1),
            "bbox_scale": 1000,
            "run_id": run_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        outputs = {
            f"{key}.layout.json": {**meta, "pages": pages},
            f"{key}.blocks.json": {**meta, "blocks": blocks},
        }
        files = []
        for name, payload in outputs.items():
            path = work / Path(name).name
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            files.append((str(path), name))
        markdown_path = work / "paper.md"
        markdown_path.write_text(markdown, encoding="utf-8")
        # The Markdown goes last: its presence marks the paper as complete.
        files.append((str(markdown_path), f"{key}.md"))
        bucket_bridge(
            {"operation": "upload", "bucket_id": layout_bucket, "files": files}
        )
    return {"paper_key": key, "ok": True, "blocks": len(blocks), **meta}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout-bucket", required=True)
    parser.add_argument("--source-bucket", required=True)
    parser.add_argument("--manifest-key", required=True)
    args = parser.parse_args()

    run_id = Path(args.manifest_key).stem
    with tempfile.TemporaryDirectory(prefix="pwc-layout-manifest-") as directory:
        manifest_path = Path(directory) / "manifest.json"
        bucket_bridge(
            {
                "operation": "download",
                "bucket_id": args.layout_bucket,
                "files": [(args.manifest_key, str(manifest_path))],
            }
        )
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))["entries"]

    done = set(
        bucket_bridge(
            {
                "operation": "existing",
                "bucket_id": args.layout_bucket,
                "keys": [f"{entry['paper_key']}.md" for entry in entries],
            }
        )["paths"]
    )
    pending = [entry for entry in entries if f"{entry['paper_key']}.md" not in done]
    print(f"{len(entries)} papers, {len(pending)} pending", flush=True)

    os.environ.update(
        VLLM_API_BASE="http://127.0.0.1:8000/v1",
        VLLM_MODEL_NAME="chandra",
        VLLM_API_KEY="EMPTY",
    )
    vllm = start_vllm()
    try:
        for number, entry in enumerate(pending, 1):
            try:
                result = process(
                    entry,
                    layout_bucket=args.layout_bucket,
                    source_bucket=args.source_bucket,
                    run_id=run_id,
                )
            except Exception as error:  # one bad PDF must not end the run
                result = {
                    "paper_key": entry["paper_key"],
                    "ok": False,
                    "error": repr(error)[:500],
                }
            print(f"[{number}/{len(pending)}] {json.dumps(result)}", flush=True)
    finally:
        vllm.terminate()


if __name__ == "__main__":
    main()
