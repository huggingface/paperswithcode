"""Paper-Markdown semantic validation of OCR output: images, titles, and canonical formatting."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.tests.paper.markdown_harness import (
    MODULE,
    WORKER,
)


def test_worker_collects_nested_chandra_images(tmp_path, monkeypatch):
    output = tmp_path / "ocr"
    observed_timeout = None

    def fake_run(*_args, **kwargs):
        nonlocal observed_timeout
        observed_timeout = kwargs.get("timeout")
        document = output / "paper"
        images = document / "images"
        images.mkdir(parents=True)
        (document / "paper.md").write_text("![figure](images/figure.webp)")
        (images / "figure.webp").write_bytes(b"nested-image")

    monkeypatch.setattr(WORKER.subprocess, "run", fake_run)

    body, assets = WORKER.run_chandra(tmp_path / "paper.pdf", output, 1)

    assert body == "![figure](images/figure.webp)"
    assert assets == {"figure.webp": b"nested-image"}
    assert observed_timeout == WORKER.CHANDRA_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    ("title", "body"),
    [
        (
            "Kimi K3: Agentic Intelligence",
            "We introduce Kimi K3 and evaluate its agentic reasoning abilities.",
        ),
        (
            "Mamba",
            "MAMBA is a selective state-space architecture for sequence modeling.",
        ),
        (
            "Étude—Über Vision!",
            "This étude presents über vision models for robust recognition.",
        ),
        (
            "The, And: Graph Networks",
            "Graph networks learn relational structure from sparse observations.",
        ),
    ],
)
def test_worker_accepts_semantically_matching_chandra_body(title, body):
    WORKER.validate_markdown_semantics(title, body)


@pytest.mark.parametrize(
    "body",
    [
        "page_001_image_01.png",
        "![page](page_001_image_01.png)",
        "Kimi_image.png\nK3_diagram.webp",
        "A generic photograph of a chart with colored boxes and arrows.",
    ],
)
def test_worker_rejects_image_description_or_title_mismatch(body):
    with pytest.raises(ValueError, match="^semantic_markdown_mismatch$"):
        WORKER.validate_markdown_semantics("Kimi K3 Agentic Intelligence", body)


def test_worker_semantic_mismatch_retries_until_max_attempts():
    mismatch = ValueError("semantic_markdown_mismatch")

    assert WORKER.classify_failure(mismatch, 1) == (
        "semantic_markdown_mismatch",
        True,
    )
    assert WORKER.classify_failure(mismatch, WORKER.MAX_ATTEMPTS) == (
        "semantic_markdown_mismatch",
        False,
    )


def test_worker_semantic_rejection_writes_no_canonical_artifacts(tmp_path):
    entry = {
        "arxiv_id": "2607.00001",
        "version": "v1",
        "title": "Kimi K3 Agentic Intelligence",
        "output_key": "2607/2607.00001.md",
    }

    with pytest.raises(ValueError, match="^semantic_markdown_mismatch$"):
        WORKER.publish(
            entry,
            "page_001_image_01.png",
            {},
            tmp_path,
        )

    assert not (tmp_path / entry["output_key"]).exists()
    assert not list(tmp_path.rglob("images"))


def test_worker_rejects_missing_extracted_image_before_final_attempt(tmp_path):
    with pytest.raises(ValueError, match="missing_extracted_image:missing_figure.webp"):
        WORKER.publish(
            {
                "arxiv_id": "2607.00001",
                "version": "v1",
                "title": "Missing figure",
                "output_key": "2607/2607.00001.md",
            },
            "Missing figure analysis.\n\n![figure](missing_figure.webp)",
            {},
            tmp_path,
        )


def test_worker_omits_missing_extracted_image_on_final_attempt(tmp_path):
    result = WORKER.publish(
        {
            "arxiv_id": "2607.00001",
            "version": "v1",
            "title": "Missing figure",
            "output_key": "2607/2607.00001.md",
        },
        (
            "Missing figure analysis.\n\n![figure](missing_figure.webp)\n\n"
            '<img src="missing_plot.webp" alt="plot">\n\n'
            + "Missing figure analysis continues. "
            * 60
        ),
        {},
        tmp_path,
        allow_missing_images=True,
    )

    markdown = (tmp_path / "2607/2607.00001.md").read_text()
    assert "Missing figure analysis." in markdown
    assert "2 generated image references were omitted" in markdown
    assert "missing_figure.webp" not in markdown
    assert "missing_plot.webp" not in markdown
    assert 'alt="plot">' not in markdown
    assert result["omitted_image_count"] == 2
    assert result["omitted_image_sources"] == [
        "missing_figure.webp",
        "missing_plot.webp",
    ]


def _scheduler(*, execute: bool, confirm: bool, full: bool = True):
    job = object.__new__(MODULE.PaperMarkdownBackfillJob)
    job.settings = type(
        "Settings",
        (),
        {
            "paper_markdown_backfill_concurrency": 4,
            "paper_markdown_incremental_batch_size": 100,
            "paper_markdown_backfill_batch_size": 100,
            "paper_markdown_hf_bucket_id": "test/paper-markdown",
            "paper_markdown_hf_namespace": "test-owner",
            "paper_markdown_runtime_image": "test-image",
            "paper_markdown_hardware": "l40sx1",
            "paper_markdown_model_id": "test-model",
            "paper_markdown_model_revision": "test-revision",
            "paper_markdown_max_pages": 30,
            "paper_markdown_paid_dispatch_enabled": False,
            "paper_markdown_cost_policy": "metered",
            "hf_token": "test-token",
        },
    )()
    job.full = full
    job.should_execute = execute
    job.confirm = confirm
    job.max_jobs = None
    job.batch_size = None
    job.logger = Mock()
    job.budget_desired_jobs = 0
    job.budget_affordable_jobs = 0
    job.retryable_papers_blocked_by_budget = 0
    job.paid_authorization_required = False
    job.stalled_scheduling_jobs = 0
    job.paid_canary = False
    job.probe_volume = False
    job.recover_mount_failures = False
    job.retry_only = False
    job.budget_projected_usd = None
    job.budget_ceiling_usd = None
    job._remote_jobs = list
    return job


def _candidates(count: int):
    return [
        {
            "arxiv_id": f"2607.{index:05d}",
            "version": "v1",
            "title": f"Paper {index}",
            "output_key": f"2607/2607.{index:05d}.md",
        }
        for index in range(count)
    ]


@pytest.mark.parametrize("newline", ["\n", "\n\n", "\r\n"])
def test_canonical_markdown_accepts_upstream_header_spacing(newline):
    body = "Adaptive Expert Routing for Robust Object Detection. " * 40
    WORKER.validate_canonical_markdown(
        "Adaptive Expert Routing for Robust Object Detection",
        "Title: Detector\n\nMarkdown Content:" + newline + body,
    )


def test_canonical_markdown_header_spacing_does_not_bypass_semantics():
    with pytest.raises(ValueError, match="semantic_markdown_mismatch"):
        WORKER.validate_canonical_markdown(
            "Adaptive Expert Routing for Robust Object Detection",
            "Title: Detector\n\nMarkdown Content:\n" + "An unrelated image. " * 20,
        )


def test_upstream_copy_rejects_caption_and_unavailable_objects():
    job = _scheduler(execute=True, confirm=True)
    job.settings.paper_markdown_upstream_bucket_id = "upstream/papers"
    job.api = Mock()
    entries = _candidates(3)
    paths = [item["output_key"] for item in entries]
    job._existing_paths = Mock(
        return_value={
            path: SimpleNamespace(xet_hash=f"hash-{index}")
            for index, path in enumerate(paths)
        }
    )
    job._semantic_records = Mock(
        return_value={
            paths[0]: "valid",
            paths[1]: "invalid",
            paths[2]: "unavailable",
        }
    )
    remaining, copied = job._copy_upstream(entries)
    assert remaining == entries[1:]
    assert copied == 1
    assert job.api.batch_bucket_files.call_args.kwargs["copy"] == [
        ("bucket", "upstream/papers", "hash-0", paths[0])
    ]


_PAPER_TITLE = "Principia: Principled Benchmarking of Vision Language Models"
_PAPER_BODY = "Principia benchmarks vision language models on principled tasks. " * 40


def _canonical(title_line: str, body: str) -> str:
    return (
        f"Title: {title_line}\n\nURL Source: https://arxiv.org/html/2609.04200\n\n"
        f"Markdown Content:\n{body}"
    )


@pytest.mark.parametrize(
    ("title_line", "body", "error"),
    [
        # Production stub: arXiv HTML conversion failed, leaving a figure caption.
        (
            "principia_summary_arxiv_final.svg",
            "We present a textual comparison of principia predictions for "
            "benchmarking vision language models.",
            "scraped_figure_markdown",
        ),
        ("f7.PNG ", _PAPER_BODY, "scraped_figure_markdown"),
        (
            _PAPER_TITLE,
            "Principia benchmarks vision language models. " * 10,
            "markdown_body_too_short",
        ),
        (
            _PAPER_TITLE,
            "Principia vision language models.\n\n"
            + "![Image 1: Refer to caption](https://arxiv.org/html/x1.png)\n" * 80,
            "markdown_body_too_short",
        ),
        (
            "1",
            "Principia vision language models.\n\n"
            "Instructions for reporting errors\n---------------------------------\n\n"
            + "We are continuing to improve HTML versions of papers. "
            * 40,
            "markdown_body_too_short",
        ),
    ],
)
def test_canonical_markdown_rejects_html_scrape_failures(title_line, body, error):
    with pytest.raises(ValueError, match=f"^{error}$"):
        WORKER.validate_canonical_markdown(_PAPER_TITLE, _canonical(title_line, body))


def test_canonical_markdown_accepts_full_paper_with_arxiv_feedback_footer():
    WORKER.validate_canonical_markdown(
        _PAPER_TITLE,
        _canonical(
            _PAPER_TITLE,
            _PAPER_BODY
            + "\nInstructions for reporting errors\n---------------------------------\n"
            + "We are continuing to improve HTML versions of papers.\n",
        ),
    )


@pytest.mark.parametrize(
    "message", ["markdown_body_too_short", "scraped_figure_markdown"]
)
def test_short_or_scraped_markdown_is_a_permanent_failure(message):
    assert WORKER.classify_failure(ValueError(message), 1) == (message, False)


def test_worker_refuses_to_publish_short_ocr_output(tmp_path):
    entry = {
        "arxiv_id": "2607.00001",
        "version": "v1",
        "title": "Short paper",
        "output_key": "2607/2607.00001.md",
    }
    with pytest.raises(ValueError, match="^markdown_body_too_short$"):
        WORKER.publish(entry, "Short paper abstract only. " * 20, {}, tmp_path)
    assert not (tmp_path / entry["output_key"]).exists()
