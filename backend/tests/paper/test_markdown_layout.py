"""Page-aware layout from the paper-Markdown OCR worker and its scheduler."""

from __future__ import annotations

import json
import sys
from io import BytesIO
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from backend.tests.paper.markdown_harness import MODULE, WORKER
from backend.tests.paper.test_markdown_dispatch import _candidates, _scheduler

PAGE_RAW = (
    '<div data-label="Page-Header" data-bbox="0 0 1000 40">arXiv</div>'
    '<div data-label="Section-Header" data-bbox="80 60 900 90">1 Intro</div>'
    '<div data-label="Text" data-bbox="80 100 900 300">Layout aware paper.</div>'
    '<div data-label="Figure" data-bbox="80 320 900 600"><img alt="f"/></div>'
)
TITLE = "Layout Aware Paper"
BODY = "Layout aware paper body. " * 120


@pytest.fixture
def fake_chandra(monkeypatch):
    """Install a stand-in for the Chandra package the HF Job image provides."""
    generated: list[list[object]] = []

    class InferenceManager:
        def __init__(self, method):
            assert method == "vllm"

        def generate(self, batch, **kwargs):
            assert kwargs == {
                "max_output_tokens": WORKER.CHANDRA_MAX_OUTPUT_TOKENS,
                "include_images": True,
                "include_headers_footers": False,
            }
            generated.append(batch)
            return [
                SimpleNamespace(
                    markdown=f"page-{item.image.width}\n",
                    raw=PAGE_RAW,
                    token_count=7,
                    error=False,
                    images={"f_4_img.webp": Image.new("RGB", (2, 2))},
                )
                for item in batch
            ]

    modules = {
        "chandra": ModuleType("chandra"),
        "chandra.input": SimpleNamespace(
            load_pdf_images=lambda _path, pages: [
                Image.new("RGB", (page + 1, 10)) for page in pages
            ]
        ),
        "chandra.model": SimpleNamespace(InferenceManager=InferenceManager),
        "chandra.model.schema": SimpleNamespace(
            BatchInputItem=lambda image, prompt_type: SimpleNamespace(
                image=image, prompt_type=prompt_type
            )
        ),
        "chandra.output": SimpleNamespace(
            parse_markdown=lambda html, include_images: html.split(">", 1)[1].split(
                "<", 1
            )[0]
        ),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return generated


def test_run_chandra_returns_canonical_markdown_assets_and_layout(fake_chandra):
    body, assets, pages = WORKER.run_chandra(None, 30)

    assert [len(batch) for batch in fake_chandra] == [28, 2]
    assert body == "".join(f"page-{page}\n" for page in range(1, 31))
    with Image.open(BytesIO(assets["f_4_img.webp"])) as image:
        assert image.format == "WEBP"
    assert [page["page"] for page in pages] == list(range(1, 31))
    assert pages[0] == {
        "page": 1,
        "image_size": [1, 10],
        "raw": PAGE_RAW,
        "token_count": 7,
        "error": False,
    }


def test_build_paged_markdown_anchors_blocks_and_skips_page_furniture(fake_chandra):
    markdown, blocks = WORKER.build_paged_markdown([{"page": 2, "raw": PAGE_RAW}])

    assert markdown == (
        "<!-- pwc:page 2 -->\n\n<!-- pwc:p2b2 -->\n1 Intro\n\n"
        "<!-- pwc:p2b3 -->\nLayout aware paper.\n"
    )
    assert list(blocks) == ["p2b2", "p2b3", "p2b4"]
    assert blocks["p2b3"] == {
        "page": 2,
        "label": "Text",
        "bbox": [80, 100, 900, 300],
        "section": "p2b2",
        "text": "Layout aware paper.",
    }


def _entry(**extra):
    return {
        "paper_key": "2610.00001",
        "paper_id": "1",
        "source": "arxiv",
        "arxiv_id": "2610.00001",
        "version": "v2",
        "title": TITLE,
        "pdf_key": None,
        "output_key": "2610/2610.00001.md",
        **extra,
    }


@pytest.fixture
def ocr_inputs(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "pypdf",
        SimpleNamespace(PdfReader=lambda *a, **k: SimpleNamespace(pages=[1, 2])),
    )
    monkeypatch.setattr(
        WORKER, "download_pdf_for_entry", lambda _entry: (b"%PDF-x", "v1")
    )
    monkeypatch.setattr(
        WORKER,
        "run_chandra",
        lambda _path, pages: (BODY, {}, [{"page": 1, "raw": "", "error": False}]),
    )
    monkeypatch.setattr(
        WORKER, "build_paged_markdown", lambda pages: ("<!-- pwc:page 1 -->\n", {})
    )


def test_process_publishes_canonical_markdown_and_layout_from_one_pass(
    tmp_path, ocr_inputs
):
    content, layout = tmp_path / "content", tmp_path / "layout"

    result = WORKER.process(_entry(), content, tmp_path / "run", layout_root=layout)

    assert result["status"] == "succeeded"
    assert (content / "2610/2610.00001.md").read_text().startswith(f"Title: {TITLE}")
    # The anchored Markdown goes last: it marks the layout as complete.
    assert result["layout_keys"] == [
        "2610/2610.00001.layout.json",
        "2610/2610.00001.blocks.json",
        "2610/2610.00001.md",
    ]
    blocks = json.loads((layout / "2610/2610.00001.blocks.json").read_text())
    assert blocks["page_count"] == 2
    assert blocks["processed_pages"] == 1
    assert blocks["arxiv_version"] == "v1"
    assert blocks["blocks"] == {}


def test_layout_only_entry_keeps_existing_canonical_markdown(tmp_path, ocr_inputs):
    content, layout = tmp_path / "content", tmp_path / "layout"
    canonical = content / "2610/2610.00001.md"
    WORKER.atomic_write(canonical, b"Title: x\n\nURL Source: arxiv html copy")

    result = WORKER.process(
        _entry(layout_only=True), content, tmp_path / "run", layout_root=layout
    )

    assert result["status"] == "succeeded"
    assert result["layout_only"] is True
    assert "markdown_content_key" not in result
    assert canonical.read_bytes() == b"Title: x\n\nURL Source: arxiv html copy"
    assert (layout / "2610/2610.00001.md").read_text() == "<!-- pwc:page 1 -->\n"
    assert WORKER.entry_status_key(_entry(layout_only=True)) == (
        "_jobs/layout-status/2610.00001.json"
    )


def test_layout_only_entry_rejects_the_wrong_pdf(tmp_path, ocr_inputs, monkeypatch):
    monkeypatch.setattr(
        WORKER, "run_chandra", lambda _path, pages: ("unrelated", {}, [])
    )
    with pytest.raises(ValueError, match="semantic_markdown_mismatch"):
        WORKER.process(
            _entry(layout_only=True),
            tmp_path,
            tmp_path / "run",
            layout_root=tmp_path / "layout",
        )
    with pytest.raises(ValueError, match="layout_bucket_required"):
        WORKER.process(_entry(layout_only=True), tmp_path, tmp_path / "run")


def test_ocr_job_stores_layout_in_the_layout_bucket():
    job = _scheduler(execute=True, confirm=True)
    job.api = Mock()

    job._run_ocr_job(run_id="r", shard_id="00000", manifest_key="m", provider_attempt=1)

    script_args = job.api.run_uv_job.call_args.kwargs["script_args"]
    assert script_args[script_args.index("--layout-bucket-id") + 1] == (
        "test/paper-pages"
    )


def test_layout_candidates_skip_existing_layout_and_permanent_failures():
    job = _scheduler(execute=False, confirm=False)
    papers = _candidates(4)
    job._existing_paths = Mock(return_value={"2607/2607.00000.blocks.json": object()})
    job._status_records = Mock(
        return_value={
            "_jobs/layout-status/2607.00001.json": {
                "status": "failed",
                "schema_version": 2,
                "attempt_count": 1,
                "retryable": False,
            },
            "_jobs/layout-status/2607.00002.json": {
                "status": "failed",
                "schema_version": 2,
                "attempt_count": 1,
                "retryable": True,
            },
        }
    )

    selected, missing = job._layout_candidates(papers, limit=5)

    assert missing == 3
    assert [(item["arxiv_id"], item["retry"]) for item in selected] == [
        ("2607.00002", True),
        ("2607.00003", False),
    ]
    assert all(item["layout_only"] for item in selected)
    assert job._existing_paths.call_args.args[0] == "test/paper-pages"


def test_launch_skips_papers_already_in_an_active_shard():
    job = _scheduler(execute=False, confirm=False)
    papers = _candidates(3)
    job._remote_jobs = lambda: [
        SimpleNamespace(
            id="job-1",
            status=SimpleNamespace(stage="RUNNING"),
            labels={"mode": "live", "job_type": "ocr", "run_id": "r", "shard_id": "s"},
        )
    ]
    job.filesystem = Mock()
    job.filesystem.open.return_value = BytesIO(
        (json.dumps({**papers[0], "layout_only": True}) + "\n").encode()
    )
    job._budget_decision = lambda desired, _jobs: {"affordable_jobs": desired}
    job.budget_affordable_jobs = 1

    launched = job._launch(papers)

    assert job.filesystem.open.call_args.args[0] == (
        "hf://buckets/test/paper-markdown/_jobs/manifests/r/s.jsonl"
    )
    assert [item["papers"] for item in launched] == ["2"]


def test_entry_layout_key_matches_the_reader_sidecar():
    assert MODULE.layout_blocks_key({"output_key": "external/12.md"}) == (
        "external/12.blocks.json"
    )


def test_live_lane_queues_layout_after_missing_canonical_work(tmp_path, monkeypatch):
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    papers = _candidates(3)
    job = _scheduler(execute=False, confirm=False, full=False)
    job.repair_invalid_limit = 0
    job._papers = Mock(return_value=papers)
    canonical = {item["output_key"]: object() for item in papers[:2]}
    job._existing_paths = Mock(
        side_effect=lambda bucket, _paths: (
            {"2607/2607.00000.blocks.json": object()}
            if bucket == "test/paper-pages"
            else canonical
        )
    )
    job._copy_upstream = Mock(return_value=([papers[2]], 0))
    job._status_records = Mock(return_value={})
    job._semantic_records = Mock(return_value={})
    job._launch = Mock(return_value=[])

    job.run()

    assert [
        (item["arxiv_id"], bool(item.get("layout_only")))
        for item in job._launch.call_args.args[0]
    ] == [("2607.00002", False), ("2607.00001", True)]
