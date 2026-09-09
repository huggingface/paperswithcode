from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import httpx
import pytest
from PIL import Image

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
sys.path.insert(0, str(WORKFLOWS))
SCRIPT = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "scripts"
    / "hourly"
    / "backfill_paper_markdown.py"
)
SPEC = importlib.util.spec_from_file_location("backfill_paper_markdown", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
WORKER_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "generate_missing_paper_markdown.py"
)
WORKER_SPEC = importlib.util.spec_from_file_location(
    "generate_missing_paper_markdown", WORKER_SCRIPT
)
assert WORKER_SPEC and WORKER_SPEC.loader
WORKER = importlib.util.module_from_spec(WORKER_SPEC)
WORKER_SPEC.loader.exec_module(WORKER)
PROBE_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "probe_paper_markdown_volume.py"
)
PROBE_SPEC = importlib.util.spec_from_file_location(
    "probe_paper_markdown_volume", PROBE_SCRIPT
)
assert PROBE_SPEC and PROBE_SPEC.loader
PROBE = importlib.util.module_from_spec(PROBE_SPEC)
PROBE_SPEC.loader.exec_module(PROBE)


def test_bucket_bridge_uses_isolated_sdk_without_exposing_token(monkeypatch):
    observed = {}

    def run(command, **kwargs):
        observed.update(command=command, **kwargs)
        return SimpleNamespace(returncode=0, stdout='{"paths": []}', stderr="")

    monkeypatch.setattr(WORKER.subprocess, "run", run)

    result = WORKER.run_bucket_bridge(
        "secret-token",
        {
            "operation": "existing",
            "bucket_id": "test/paper-markdown",
            "keys": ["paper.md"],
        },
    )

    assert result == {"paths": []}
    assert observed["command"][:6] == [
        "uv",
        "run",
        "--no-project",
        "--with",
        "huggingface-hub==1.23.0",
        "python",
    ]
    assert "secret-token" not in observed["command"]
    assert observed["env"]["HF_TOKEN"] == "secret-token"
    assert json.loads(observed["input"])["operation"] == "existing"
    assert observed["capture_output"] is True


def test_bucket_bridge_code_uses_bucket_apis_for_all_operations(tmp_path, monkeypatch):
    remote = {"manifest.jsonl": b'{"arxiv_id":"2608.00001"}\n'}
    uploads = []

    class Api:
        def get_bucket_paths_info(self, bucket_id, keys):
            assert bucket_id == "test/paper-markdown"
            return [SimpleNamespace(path=key) for key in keys if key in remote]

        def download_bucket_files(self, bucket_id, files, *, raise_on_missing_files):
            assert bucket_id == "test/paper-markdown"
            assert raise_on_missing_files is True
            for key, destination in files:
                Path(destination).write_bytes(remote[key])

        def batch_bucket_files(self, bucket_id, *, add):
            assert bucket_id == "test/paper-markdown"
            uploads.extend(
                (Path(source).read_bytes(), destination) for source, destination in add
            )

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(HfApi=Api))

    def execute(request):
        output = StringIO()
        monkeypatch.setattr(sys, "stdin", StringIO(json.dumps(request)))
        monkeypatch.setattr(sys, "stdout", output)
        exec(WORKER.BUCKET_BRIDGE_CODE, {})  # noqa: S102 - exercise trusted code
        return json.loads(output.getvalue())

    assert execute(
        {
            "operation": "existing",
            "bucket_id": "test/paper-markdown",
            "keys": ["manifest.jsonl", "missing.json"],
        }
    ) == {"paths": ["manifest.jsonl"]}

    downloaded = tmp_path / "downloaded.jsonl"
    assert (
        execute(
            {
                "operation": "download",
                "bucket_id": "test/paper-markdown",
                "files": [["manifest.jsonl", str(downloaded)]],
            }
        )
        == {}
    )
    assert downloaded.read_bytes() == remote["manifest.jsonl"]

    upload = tmp_path / "result.json"
    upload.write_text('{"status":"succeeded"}')
    assert (
        execute(
            {
                "operation": "upload",
                "bucket_id": "test/paper-markdown",
                "files": [[str(upload), "_jobs/results/result.json"]],
            }
        )
        == {}
    )
    assert uploads == [(upload.read_bytes(), "_jobs/results/result.json")]


def test_worker_download_pdf_falls_back_to_existing_arxiv_version(monkeypatch):
    requested_urls: list[str] = []

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url: str):
            requested_urls.append(url)
            status = 200 if url.endswith("v1.pdf") else 404
            content = b"%PDF-valid" if status == 200 else b"missing"
            return httpx.Response(
                status, content=content, request=httpx.Request("GET", url)
            )

    monkeypatch.setattr(WORKER.httpx, "Client", Client)

    pdf, resolved_version = WORKER.download_pdf("1401.3590", "v3")

    assert pdf == b"%PDF-valid"
    assert resolved_version == "v1"
    assert [url.rsplit("v", 1)[-1] for url in requested_urls] == [
        "3.pdf",
        "2.pdf",
        "1.pdf",
    ]


def test_worker_download_pdf_does_not_fallback_on_rate_limit(monkeypatch):
    client = Mock()
    url = "https://arxiv.org/pdf/1401.3590v3.pdf"
    client.get.return_value = httpx.Response(
        429, content=b"rate limited", request=httpx.Request("GET", url)
    )
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=None)
    monkeypatch.setattr(WORKER.httpx, "Client", Mock(return_value=client))

    with pytest.raises(httpx.HTTPStatusError):
        WORKER.download_pdf("1401.3590", "v3")

    client.get.assert_called_once_with(url)


def test_worker_resolves_external_repository_pdf_urls():
    assert WORKER.normalize_external_pdf_url(
        "https://github.com/QwenLM/Qwen3.8-Flash-Next/blob/main/tech_report.pdf"
    ) == (
        "https://raw.githubusercontent.com/"
        "QwenLM/Qwen3.8-Flash-Next/main/tech_report.pdf"
    )
    assert (
        WORKER.normalize_external_pdf_url(
            "https://huggingface.co/acme/report/blob/main/report.pdf"
        )
        == "https://huggingface.co/acme/report/resolve/main/report.pdf"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/report.pdf",
        "http://169.254.169.254/latest/meta-data/report.pdf",
        "https://localhost/report.pdf",
        "https://user:password@example.com/report.pdf",
    ],
)
def test_worker_rejects_unsafe_external_pdf_urls(url):
    with pytest.raises(ValueError, match="invalid_external_pdf_url"):
        WORKER.normalize_external_pdf_url(url)


def test_worker_rejects_unsafe_external_pdf_redirects(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            self.request_hook = kwargs["event_hooks"]["request"][0]

        def __enter__(self):
            self.request_hook(httpx.Request("GET", "http://127.0.0.1/report.pdf"))
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(WORKER.httpx, "Client", Client)

    with pytest.raises(ValueError, match="invalid_external_pdf_url"):
        WORKER.download_external_pdf("https://example.com/report.pdf")


def test_worker_rejects_external_pdf_hostname_resolving_to_private_ip(monkeypatch):
    monkeypatch.setattr(
        WORKER.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (WORKER.socket.AF_INET, WORKER.socket.SOCK_STREAM, 6, "", ("10.0.0.4", 443))
        ],
    )

    with pytest.raises(ValueError, match="invalid_external_pdf_url"):
        WORKER.validate_external_pdf_network_target("https://example.com/report.pdf")


def test_worker_streams_external_pdf_with_a_hard_size_cap(monkeypatch):
    read_past_limit = False

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def raise_for_status(self):
            return None

        def iter_bytes(self):
            nonlocal read_past_limit
            yield b"%PDF-"
            yield b"1234"
            read_past_limit = True
            yield b"must-not-be-read"

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def stream(self, method, url):
            assert method == "GET"
            assert url == "https://example.com/report.pdf"
            return Response()

    monkeypatch.setattr(
        WORKER, "validate_external_pdf_network_target", lambda value: value
    )
    monkeypatch.setattr(WORKER, "MAX_PDF_BYTES", 8, raising=False)
    monkeypatch.setattr(WORKER.httpx, "Client", Client)

    with pytest.raises(ValueError, match="invalid_pdf"):
        WORKER.download_external_pdf("https://example.com/report.pdf")

    assert read_past_limit is False


def test_worker_archives_external_pdf_and_publishes_source_aware_markdown(
    tmp_path, monkeypatch
):
    entry = {
        "paper_key": "external/109743",
        "paper_id": "109743",
        "source": "external",
        "arxiv_id": None,
        "version": "v1",
        "title": "External report",
        "source_url": "https://github.com/acme/report/blob/main/report.pdf",
        "pdf_url": "https://github.com/acme/report/blob/main/report.pdf",
        "pdf_key": "external/109743/paper.pdf",
        "output_key": "external/109743.md",
    }
    pdf = b"%PDF-external"

    class Reader:
        def __init__(self, stream, strict):
            assert stream.read() == pdf
            assert strict is True
            self.pages = [object(), object()]

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=Reader))
    monkeypatch.setattr(WORKER, "download_pdf_for_entry", lambda _entry: (pdf, "v1"))
    monkeypatch.setattr(
        WORKER,
        "run_chandra",
        lambda path, _output, pages: (
            (
                "External report Markdown body " * 12,
                {},
            )
            if path.read_bytes() == pdf and pages == 2
            else (_ for _ in ()).throw(AssertionError("unexpected OCR input"))
        ),
    )

    result = WORKER.process(entry, tmp_path / "content", tmp_path / "run")

    assert (tmp_path / "content/external/109743/paper.pdf").read_bytes() == pdf
    markdown = (tmp_path / "content/external/109743.md").read_text()
    assert "URL Source: https://github.com/acme/report/blob/main/report.pdf" in markdown
    assert result["paper_key"] == "external/109743"
    assert result["pdf_key"] == "external/109743/paper.pdf"


def test_worker_does_not_archive_external_pdf_before_document_validation(
    tmp_path, monkeypatch
):
    entry = {
        "paper_key": "external/109743",
        "paper_id": "109743",
        "source": "external",
        "arxiv_id": None,
        "version": "v1",
        "title": "Invalid external report",
        "source_url": "https://example.com/report.pdf",
        "pdf_url": "https://example.com/report.pdf",
        "pdf_key": "external/109743/paper.pdf",
        "output_key": "external/109743.md",
    }

    class InvalidReader:
        def __init__(self, *_args, **_kwargs):
            raise ValueError("broken PDF structure")

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=InvalidReader))
    monkeypatch.setattr(
        WORKER,
        "download_pdf_for_entry",
        lambda _entry: (b"%PDF-broken", "v1"),
    )

    with pytest.raises(ValueError, match="broken PDF structure"):
        WORKER.process(entry, tmp_path / "content", tmp_path / "run")

    assert not (tmp_path / "content/external/109743/paper.pdf").exists()


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
            '<img src="missing_plot.webp" alt="plot">'
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


def test_bucket_worker_downloads_manifest_and_uploads_outputs_without_mount(
    tmp_path, monkeypatch
):
    manifest_key = "_jobs/manifests/backfill-20260824T120000-12345678/00000.jsonl"
    entry = {
        "arxiv_id": "2608.00001",
        "version": "v1",
        "title": "Bucket transport",
        "output_key": "2608/2608.00001.md",
    }
    remote = {manifest_key: (json.dumps(entry) + "\n").encode()}
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "2608.00001.md").write_text("Bucket transport paper text. " * 12)

    def bucket_bridge(token, request):
        assert token == "secret"
        assert request["bucket_id"] == "test/paper-markdown"
        if request["operation"] == "existing":
            return {"paths": [key for key in request["keys"] if key in remote]}
        if request["operation"] == "download":
            for key, destination_value in request["files"]:
                destination = Path(destination_value)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(remote[key])
            return {}
        if request["operation"] == "upload":
            for source, key in request["files"]:
                remote[key] = Path(source).read_bytes()
            return {}
        raise AssertionError(f"unexpected bridge operation: {request['operation']}")

    monkeypatch.setattr(WORKER, "run_bucket_bridge", bucket_bridge)
    monkeypatch.setenv("HF_TOKEN", "secret")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(WORKER_SCRIPT),
            "--bucket-id",
            "test/paper-markdown",
            "--manifest-key",
            manifest_key,
            "--stub-root",
            str(stub),
            "--soft-deadline-seconds",
            "60",
        ],
    )

    WORKER.main()

    assert remote[entry["output_key"]].startswith(b"Title: Bucket transport")
    status = json.loads(remote["_jobs/status/2608.00001.json"])
    assert status["status"] == "succeeded"
    progress = json.loads(
        remote["_jobs/progress/backfill-20260824T120000-12345678/00000.json"]
    )
    assert progress["status"] == "completed"


def test_arxiv_identity_and_markdown_key():
    assert MODULE.normalize_arxiv_id("2607.24653v2") == "2607.24653"
    assert MODULE.markdown_key("2607.24653") == "2607/2607.24653.md"
    assert MODULE.normalize_arxiv_id("hep-th/9901001") is None


def test_external_manifest_entry_prefers_pdf_source_url_then_explicit_pdf():
    explicit = SimpleNamespace(
        id=109743,
        source="external",
        arxiv_id=None,
        version="v1",
        title="External report",
        source_url="https://example.com/report",
        conference_url_pdf="https://example.com/report.pdf",
    )
    source_only = SimpleNamespace(
        id=109744,
        source="external",
        arxiv_id=None,
        version="v1",
        title="Source PDF",
        source_url="https://openreview.net/pdf?id=abc",
        conference_url_pdf=None,
    )
    both = SimpleNamespace(
        id=109746,
        source="external",
        arxiv_id=None,
        version="v1",
        title="Canonical source PDF",
        source_url="https://example.com/canonical.pdf",
        conference_url_pdf="https://example.com/conference-copy.pdf",
    )
    html_only = SimpleNamespace(
        id=109745,
        source="external",
        arxiv_id=None,
        version="v1",
        title="Web page",
        source_url="https://example.com/report",
        conference_url_pdf=None,
    )

    assert MODULE.paper_manifest_entry(explicit) == {
        "paper_key": "external/109743",
        "paper_id": "109743",
        "source": "external",
        "arxiv_id": None,
        "version": "v1",
        "title": "External report",
        "source_url": "https://example.com/report",
        "pdf_url": "https://example.com/report.pdf",
        "pdf_key": "external/109743/paper.pdf",
        "output_key": "external/109743.md",
    }
    assert MODULE.paper_manifest_entry(source_only)["pdf_url"] == source_only.source_url
    assert MODULE.paper_manifest_entry(both)["pdf_url"] == both.source_url
    assert MODULE.paper_manifest_entry(html_only) is None


def test_arxiv_manifest_entry_preserves_canonical_bucket_contract():
    paper = SimpleNamespace(
        id=42,
        source="arxiv",
        arxiv_id="2607.24653v2",
        version="v2",
        title="ArXiv paper",
        source_url=None,
        conference_url_pdf=None,
    )

    entry = MODULE.paper_manifest_entry(paper)

    assert entry["paper_key"] == "2607.24653"
    assert entry["output_key"] == "2607/2607.24653.md"
    assert entry["pdf_key"] is None


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


def test_paid_dispatch_requires_confirmation(monkeypatch):
    job = _scheduler(execute=True, confirm=False, full=False)
    monkeypatch.setattr(
        job,
        "_budget_decision",
        lambda desired, _jobs: {"affordable_jobs": desired},
    )
    with pytest.raises(ValueError, match="requires --confirm"):
        job._launch(_candidates(1))


def test_budget_exhaustion_is_a_successful_noop(monkeypatch):
    job = _scheduler(execute=True, confirm=True, full=False)
    monkeypatch.setattr(
        job, "_budget_decision", lambda _desired, _jobs: {"affordable_jobs": 0}
    )
    assert job._launch(_candidates(1)) == []


def test_measured_profile_paid_dispatch_requires_explicit_gate(monkeypatch):
    job = _scheduler(execute=True, confirm=True, full=False)

    def budget_decision(desired, _jobs):
        job.budget_desired_jobs = desired
        job.budget_affordable_jobs = desired
        return {"affordable_jobs": desired}

    monkeypatch.setattr(
        job,
        "_budget_decision",
        budget_decision,
    )

    assert job._launch(_candidates(1)) == []
    assert job.paid_authorization_required is True
    job.logger.info.assert_called_with(
        "paper Markdown admission: desired=%s affordable=%s planned_or_launched=0",
        1,
        1,
    )


def test_launch_request_uses_the_shared_profile_and_bucket_api_contract():
    job = _scheduler(execute=True, confirm=True, full=False)
    job.api = Mock()
    job.api.run_uv_job.return_value = SimpleNamespace(id="job-1")

    job._run_ocr_job(
        run_id="live-20260821T120000-12345678",
        shard_id="00000",
        manifest_key="_jobs/manifests/live/00000.jsonl",
        provider_attempt=1,
    )

    kwargs = job.api.run_uv_job.call_args.kwargs
    assert kwargs["timeout"] == job.profile.hard_timeout == "7h"
    assert kwargs["script_args"][-1] == str(job.profile.soft_deadline_seconds)
    assert kwargs["labels"]["profile_id"] == job.profile.profile_id
    assert kwargs["labels"]["hard_timeout_seconds"] == str(
        job.profile.hard_timeout_seconds
    )
    assert kwargs["volumes"] == []
    assert kwargs["script_args"][:4] == [
        "--bucket-id",
        "test/paper-markdown",
        "--manifest-key",
        "_jobs/manifests/live/00000.jsonl",
    ]


def test_unmetered_hf_dispatch_does_not_require_paid_gate(monkeypatch):
    job = _scheduler(execute=True, confirm=True, full=False)
    job.settings.paper_markdown_cost_policy = "unmetered_hf"
    job.api = Mock()
    job._persist_dispatch = Mock()
    job._run_ocr_job = Mock(return_value=SimpleNamespace(id="job-1"))

    def budget_decision(desired, _jobs):
        job.budget_desired_jobs = desired
        job.budget_affordable_jobs = desired
        return {"affordable_jobs": desired}

    monkeypatch.setattr(job, "_budget_decision", budget_decision)

    launched = job._launch(_candidates(1))

    assert len(launched) == 1
    assert job.paid_authorization_required is False


def test_dry_reconciliation_appends_coverage_history(tmp_path, monkeypatch):
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    papers = _candidates(2)
    job = _scheduler(execute=False, confirm=False)
    job._papers = Mock(return_value=papers)
    job._existing_paths = Mock(return_value={papers[0]["output_key"]: object()})
    job._copy_upstream = Mock(return_value=([papers[1]], 0))
    job._status_records = Mock(return_value={})
    job._semantic_records = Mock(return_value={papers[0]["output_key"]: "valid"})
    job._launch = Mock(return_value=[])

    job.run()
    job.run()

    history = tmp_path / MODULE.COVERAGE_HISTORY_NAME
    rows = [json.loads(line) for line in history.read_text().splitlines()]
    assert len(rows) == 2
    assert all(
        row
        | {
            "observed_at": None,
            "selected_profile": None,
        }
        == {
            "observed_at": None,
            "scope": "full",
            "eligible_papers": 2,
            "canonical_markdown_count": 1,
            "usable_markdown_count": 1,
            "semantic_invalid_existing": 0,
            "semantic_evidence_unavailable": 0,
            "copied_from_upstream_count": 0,
            "planned_upstream_copy_count": 0,
            "missing_count": 1,
            "coverage_percentage": 50.0,
            "retryable_due": 0,
            "retryable_deferred": 0,
            "permanent_failures": 0,
            "attempts_exhausted": 0,
            "semantic_validation_failures": 0,
            "retryable_papers_blocked_by_budget": 0,
            "paid_authorization_required": False,
            "selected_profile": None,
        }
        for row in rows
    )
    job._launch.assert_called_with([{**papers[1], "retry": False}])


def test_dry_run_does_not_count_unvalidated_upstream_as_usable(tmp_path, monkeypatch):
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    papers = _candidates(2)
    job = _scheduler(execute=False, confirm=False, full=False)
    job._papers = Mock(return_value=papers)
    job._existing_paths = Mock(return_value={papers[0]["output_key"]: object()})
    job._copy_upstream = Mock(return_value=([], 1))
    job._status_records = Mock(return_value={})
    job._semantic_records = Mock(return_value={papers[0]["output_key"]: "valid"})
    job._launch = Mock(return_value=[])

    job.run()

    coverage = json.loads(
        (tmp_path / MODULE.COVERAGE_HISTORY_NAME).read_text().splitlines()[-1]
    )
    assert coverage["canonical_markdown_count"] == 1
    assert coverage["usable_markdown_count"] == 1
    assert coverage["copied_from_upstream_count"] == 0
    assert coverage["planned_upstream_copy_count"] == 1


def test_recent_semantic_invalid_object_is_not_usable_or_dispatched(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    papers = _candidates(2)
    job = _scheduler(execute=False, confirm=False, full=False)
    job._papers = Mock(return_value=papers)
    job._existing_paths = Mock(return_value={papers[0]["output_key"]: object()})
    job._copy_upstream = Mock(return_value=([papers[1]], 0))
    job._status_records = Mock(return_value={})
    job._semantic_records = Mock(return_value={papers[0]["output_key"]: "invalid"})
    job._launch = Mock(return_value=[])

    job.run()

    summary_call = next(
        call
        for call in job.logger.info.call_args_list
        if call.args and call.args[0] == "PAPER_MARKDOWN_SUMMARY %s"
    )
    summary = json.loads(summary_call.args[1])
    assert summary["semantic_invalid_existing"] == 1
    assert summary["semantic_evidence_unavailable"] == 0
    assert summary["usable_markdown"] == 0
    assert summary["coverage_percentage"] == 0.0
    job._launch.assert_called_once_with([{**papers[1], "retry": False}])


def test_retry_only_canary_selects_only_persisted_retryable_due(tmp_path, monkeypatch):
    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    papers = _candidates(2)
    job = _scheduler(execute=False, confirm=False)
    job.retry_only = True
    job._papers = Mock(return_value=papers)
    job._existing_paths = Mock(return_value={})
    job._copy_upstream = Mock(return_value=(papers, 0))
    job._status_records = Mock(
        return_value={
            f"_jobs/status/{papers[1]['arxiv_id']}.json": {
                "schema_version": 2,
                "status": "failed",
                "retryable": True,
            }
        }
    )
    job._launch = Mock(return_value=[])

    job.run()

    job._launch.assert_called_once_with([{**papers[1], "retry": True}])


@pytest.mark.parametrize("affordable", [0, 1, 3, 4])
def test_scheduler_launches_exact_affordable_prefix(monkeypatch, affordable):
    job = _scheduler(execute=False, confirm=False)
    monkeypatch.setattr(
        job,
        "_budget_decision",
        lambda _desired, _jobs: {"affordable_jobs": affordable},
    )
    launched = job._launch(_candidates(400))
    assert len(launched) == affordable
    assert sum(int(item["papers"]) for item in launched) == affordable * 100


def _remote_job(
    job_id: str,
    *,
    stage: str,
    message: str | None,
    provider_attempt: int = 0,
    run_id: str = "backfill-20260820T030610-65423592",
):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=job_id,
        status=SimpleNamespace(stage=stage, message=message),
        labels={
            "app": "pwc-paper-markdown",
            "mode": "backfill",
            "run_id": run_id,
            "shard_id": "00000",
            "job_type": "ocr",
            "provider_attempt": str(provider_attempt),
        },
        created_at=now - timedelta(hours=1),
        started_at=None,
        finished_at=now - timedelta(minutes=30),
    )


def test_prestart_mount_failure_is_retryable_without_paper_attempt(monkeypatch):
    job = _scheduler(execute=False, confirm=False)
    failure = _remote_job("failed-0", stage="ERROR", message="Volume mount failed")
    job.filesystem = SimpleNamespace(exists=lambda _path: True)
    monkeypatch.setattr(job, "_bucket_json", lambda _key: {})

    candidates, acknowledgement = job._mount_recovery_candidates(
        [failure], now=datetime.now(UTC)
    )

    assert acknowledgement == 0
    assert candidates == [
        {
            "run_id": "backfill-20260820T030610-65423592",
            "shard_id": "00000",
            "manifest_key": (
                "_jobs/manifests/backfill-20260820T030610-65423592/00000.jsonl"
            ),
            "failed_provider_job_id": "failed-0",
            "failed_at": failure.finished_at.isoformat(),
        }
    ]
    # Candidate recognition reads only logical dispatch/checkpoint evidence; it
    # never creates or edits a per-paper status/attempt record.


def test_successful_probe_allows_exactly_one_replacement(monkeypatch):
    job = _scheduler(execute=True, confirm=True)
    candidate = {
        "run_id": "backfill-20260820T030610-65423592",
        "shard_id": "00000",
        "manifest_key": (
            "_jobs/manifests/backfill-20260820T030610-65423592/00000.jsonl"
        ),
        "failed_provider_job_id": "failed-0",
        "failed_at": datetime.now(UTC).isoformat(),
    }
    job._remote_jobs = Mock(return_value=[])
    job._mount_recovery_candidates = Mock(return_value=([candidate], 0))
    job._latest_successful_mount_probe = Mock(
        return_value={"probe_id": "probe-ok", "provider_job_id": "probe-job"}
    )
    job._budget_decision = Mock(return_value={"affordable_jobs": 1})
    job._run_ocr_job = Mock(return_value=SimpleNamespace(id="replacement-1"))
    job._persist_dispatch = Mock()

    result = job._recover_mount_failures()

    assert result["launched_replacements"] == 1
    job._run_ocr_job.assert_called_once_with(
        run_id=candidate["run_id"],
        shard_id="00000",
        manifest_key=candidate["manifest_key"],
        provider_attempt=2,
        replacement_for="failed-0",
    )
    assert (
        job._persist_dispatch.call_args.kwargs["provider_attempts"][1][
            "capability_probe_id"
        ]
        == "probe-ok"
    )


def test_two_mount_failures_require_operator_ack_and_late_success_recovers(
    monkeypatch,
):
    job = _scheduler(execute=False, confirm=False)
    first = _remote_job("failed-0", stage="ERROR", message="Volume mount failed")
    second = _remote_job(
        "failed-1",
        stage="ERROR",
        message="Volume mount failed",
        provider_attempt=1,
    )
    candidates, acknowledgement = job._mount_recovery_candidates(
        [first, second], now=datetime.now(UTC)
    )
    assert candidates == []
    assert acknowledgement == 1

    late_success = _remote_job(
        "late-success",
        stage="COMPLETED",
        message=None,
        provider_attempt=1,
    )
    candidates, acknowledgement = job._mount_recovery_candidates(
        [first, late_success], now=datetime.now(UTC)
    )
    assert candidates == []
    assert acknowledgement == 0


def test_mountless_recovery_does_not_require_a_volume_probe():
    job = _scheduler(execute=True, confirm=True)
    job._remote_jobs = Mock(return_value=[])
    job._mount_recovery_candidates = Mock(
        return_value=(
            [
                {
                    "run_id": "backfill-20260820T030610-65423592",
                    "shard_id": "00000",
                    "manifest_key": "manifest.jsonl",
                    "failed_provider_job_id": "failed-0",
                    "failed_at": datetime.now(UTC).isoformat(),
                }
            ],
            0,
        )
    )
    job._budget_decision = Mock(return_value={"affordable_jobs": 1})
    job._run_ocr_job = Mock(return_value=SimpleNamespace(id="replacement-1"))
    job._persist_dispatch = Mock()

    result = job._recover_mount_failures()

    assert result["launched_replacements"] == 1
    assert result["storage_transport"] == "bucket_api"


def test_full_reconciliation_recovers_mount_failure_and_fills_remaining_slots():
    job = _scheduler(execute=True, confirm=True)
    job._recover_mount_failures = Mock(
        return_value={
            "operation": "mount_recovery",
            "storage_transport": "bucket_api",
            "launched_replacements": 1,
            "replacement_attempts": [{"provider_job_id": "replacement-1"}],
        }
    )
    job._papers = Mock(return_value=[])
    job._existing_paths = Mock(return_value={})
    job._copy_upstream = Mock(return_value=([], 0))
    job._status_records = Mock(return_value={})
    job._launch = Mock(return_value=[])

    job.run()

    job._recover_mount_failures.assert_called_once_with()
    assert job._papers.call_args_list == [call(), call(recent_only=True)]
    job._launch.assert_called_once_with([], additional_active_job_ids={"replacement-1"})


def test_hourly_workflow_refills_recent_and_full_markdown_lanes():
    workflow = (WORKFLOWS / "cron-paper-markdown.yml").read_text()

    assert (
        'REMOTE_COMMAND="sudo /usr/local/sbin/pwc-cron paper_markdown_backfill"'
        in workflow
    )
    assert 'BACKFILL_COMMAND="$REMOTE_COMMAND --full"' in workflow
    assert (
        'ssh -o StrictHostKeyChecking=yes "${VPS_USER}@${VPS_HOST}" "$REMOTE_COMMAND"'
        in workflow
    )
    assert (
        'ssh -o StrictHostKeyChecking=yes "${VPS_USER}@${VPS_HOST}" "$BACKFILL_COMMAND"'
        in workflow
    )


def test_volume_probe_reads_writes_verifies_and_cleans_only_temporary_object(
    tmp_path,
):
    content = tmp_path / "content"
    manifest = content / "_jobs/capabilities/probe-test.manifest.json"
    result = content / "_jobs/capabilities/probe-test.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "probe_id": "probe-test",
                "nonce": "a" * 32,
                "bucket_id": "test/paper-markdown",
                "namespace": "test-owner",
                "mount_path": "/content",
                "read_only": False,
            }
        )
    )

    evidence = PROBE.run_probe(
        content_root=content, manifest_path=manifest, result_path=result
    )

    assert evidence["status"] == "succeeded"
    assert evidence["temporary_object_cleaned"] is True
    assert manifest.exists()
    assert result.exists()
    assert list(manifest.parent.glob("*.probe")) == []


def test_retry_disposition_uses_persisted_fields():
    now = MODULE.datetime(2026, 8, 18, tzinfo=MODULE.UTC)
    assert (
        MODULE.status_disposition({"status": "failed", "error": "legacy"}, now=now)
        == "retryable_due"
    )
    assert (
        MODULE.status_disposition(
            {"schema_version": 2, "status": "failed", "retryable": True}, now=now
        )
        == "retryable_due"
    )
    assert (
        MODULE.status_disposition(
            {
                "schema_version": 2,
                "status": "failed",
                "retryable": True,
                "next_retry_at": "2026-08-19T00:00:00Z",
            },
            now=now,
        )
        == "retryable_deferred"
    )
    assert (
        MODULE.status_disposition(
            {
                "schema_version": 2,
                "status": "failed",
                "retryable": True,
                "attempt_count": 3,
            },
            now=now,
        )
        == "attempts_exhausted"
    )
    assert (
        MODULE.status_disposition(
            {"schema_version": 2, "status": "failed", "retryable": False},
            now=now,
        )
        == "permanent_failure"
    )
    assert (
        MODULE.status_disposition(
            {
                "schema_version": 2,
                "status": "failed",
                "attempt_count": 1,
                "error_class": "arxiv_http_404",
                "retryable": False,
            },
            now=now,
        )
        == "retryable_due"
    )
    assert (
        MODULE.status_disposition(
            {
                "schema_version": 2,
                "status": "failed",
                "attempt_count": 2,
                "error_class": "arxiv_http_404",
                "retryable": False,
                "version_fallback_attempted": True,
            },
            now=now,
        )
        == "permanent_failure"
    )


def test_chandra_worker_stub_writes_canonical_markdown_and_checkpoint(tmp_path):
    content = tmp_path / "content"
    stub = tmp_path / "stub"
    manifest = content / "_jobs" / "manifests" / "run-1" / "00000.jsonl"
    manifest.parent.mkdir(parents=True)
    stub.mkdir()
    entry = {
        "arxiv_id": "2607.24653",
        "version": "v1",
        "title": "Kimi K3",
        "output_key": "2607/2607.24653.md",
    }
    manifest.write_text(json.dumps(entry) + "\n")
    (stub / "2607.24653.md").write_text(
        "Kimi K3 paper text.\n\n![figure](figure.webp)\n\nAfter image. " * 20
    )
    asset_dir = stub / "2607.24653"
    asset_dir.mkdir()
    image_buffer = BytesIO()
    Image.new("RGB", (16, 12), "navy").save(image_buffer, format="WEBP")
    (asset_dir / "figure.webp").write_bytes(image_buffer.getvalue())
    worker = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "generate_missing_paper_markdown.py"
    )

    subprocess.run(
        [
            sys.executable,
            str(worker),
            "--manifest",
            str(manifest),
            "--content-root",
            str(content),
            "--stub-root",
            str(stub),
            "--soft-deadline-seconds",
            "30",
        ],
        check=True,
    )

    markdown = (content / entry["output_key"]).read_text()
    assert markdown.startswith("Title: Kimi K3\n\nURL Source:")
    assert "https://paperswithcode.co/paper-assets/2607/2607.24653/images/" in markdown
    assert "figure.webp" not in markdown
    status = json.loads((content / "_jobs" / "status" / "2607.24653.json").read_text())
    assert status["status"] == "succeeded"
    assert status["schema_version"] == 2
    assert status["attempt_count"] == 1
    assert status["retryable"] is False
    assert status["model_id"] == "datalab-to/chandra-ocr-2"
    assert status["image_count"] == 1
    assert len(status["asset_keys"]) == 1
    assert (content / status["asset_keys"][0]).is_file()
    progress = json.loads(
        (content / "_jobs" / "progress" / "run-1" / "00000.json").read_text()
    )
    assert progress["status"] == "completed"
    assert progress["total_papers"] == 1
    assert progress["processed_papers"] == 1
    assert progress["succeeded_papers"] == 1
    assert progress["failed_papers"] == 0
    assert progress["extracted_images"] == 1
    assert progress["omitted_images"] == 0


def test_chandra_worker_failure_records_duration(tmp_path):
    content = tmp_path / "content"
    stub = tmp_path / "stub"
    manifest = content / "_jobs" / "manifests" / "run-failure" / "00000.jsonl"
    manifest.parent.mkdir(parents=True)
    stub.mkdir()
    entry = {
        "arxiv_id": "2607.24653",
        "version": "v1",
        "title": "Kimi K3",
        "output_key": "2607/2607.24653.md",
    }
    manifest.write_text(json.dumps(entry) + "\n")
    (stub / "2607.24653.md").write_text(
        "Kimi K3 paper text.\n\n![figure](missing.webp)\n\nAfter image. " * 20
    )

    subprocess.run(
        [
            sys.executable,
            str(WORKER_SCRIPT),
            "--manifest",
            str(manifest),
            "--content-root",
            str(content),
            "--stub-root",
            str(stub),
            "--soft-deadline-seconds",
            "30",
        ],
        check=True,
    )

    status = json.loads((content / "_jobs" / "status" / "2607.24653.json").read_text())
    assert status["status"] == "failed"
    assert status["duration_seconds"] >= 0
    progress = json.loads(
        (content / "_jobs" / "progress" / "run-failure" / "00000.json").read_text()
    )
    assert progress["paper_duration_p50_seconds"] is not None
    assert progress["paper_duration_p95_seconds"] is not None


def test_chandra_worker_final_attempt_omits_missing_image(tmp_path):
    content = tmp_path / "content"
    stub = tmp_path / "stub"
    manifest = content / "_jobs" / "manifests" / "run-final" / "00000.jsonl"
    status_path = content / "_jobs" / "status" / "2607.24653.json"
    manifest.parent.mkdir(parents=True)
    status_path.parent.mkdir(parents=True)
    stub.mkdir()
    entry = {
        "arxiv_id": "2607.24653",
        "version": "v1",
        "title": "Kimi K3",
        "output_key": "2607/2607.24653.md",
    }
    manifest.write_text(json.dumps(entry) + "\n")
    (stub / "2607.24653.md").write_text(
        "Kimi K3 paper text.\n\n![figure](missing.webp)\n\nAfter image. " * 20
    )
    status_path.write_text(json.dumps({"status": "failed", "attempt_count": 2}))

    subprocess.run(
        [
            sys.executable,
            str(WORKER_SCRIPT),
            "--manifest",
            str(manifest),
            "--content-root",
            str(content),
            "--stub-root",
            str(stub),
            "--soft-deadline-seconds",
            "30",
        ],
        check=True,
    )

    markdown = (content / entry["output_key"]).read_text()
    status = json.loads(status_path.read_text())
    assert "missing.webp" not in markdown
    assert "1 generated image reference was omitted" in markdown
    assert status["status"] == "succeeded"
    assert status["attempt_count"] == 3
    assert status["omitted_image_count"] == 1
    progress = json.loads(
        (content / "_jobs" / "progress" / "run-final" / "00000.json").read_text()
    )
    assert progress["omitted_images"] == 1


def test_chandra_worker_omits_missing_image_after_one_retry(tmp_path):
    content = tmp_path / "content"
    stub = tmp_path / "stub"
    manifest = content / "_jobs" / "manifests" / "run-retry" / "00000.jsonl"
    status_path = content / "_jobs" / "status" / "2607.24653.json"
    manifest.parent.mkdir(parents=True)
    status_path.parent.mkdir(parents=True)
    stub.mkdir()
    entry = {
        "arxiv_id": "2607.24653",
        "version": "v1",
        "title": "Kimi K3",
        "output_key": "2607/2607.24653.md",
    }
    manifest.write_text(json.dumps(entry) + "\n")
    (stub / "2607.24653.md").write_text(
        "Kimi K3 paper text.\n\n![figure](missing.webp)\n\nAfter image. " * 20
    )
    status_path.write_text(
        json.dumps(
            {
                "status": "failed",
                "attempt_count": 1,
                "error_class": "missing_extracted_image",
                "retryable": True,
            }
        )
    )

    subprocess.run(
        [
            sys.executable,
            str(WORKER_SCRIPT),
            "--manifest",
            str(manifest),
            "--content-root",
            str(content),
            "--stub-root",
            str(stub),
            "--soft-deadline-seconds",
            "30",
        ],
        check=True,
    )

    markdown = (content / entry["output_key"]).read_text()
    status = json.loads(status_path.read_text())
    assert "missing.webp" not in markdown
    assert "1 generated image reference was omitted" in markdown
    assert status["status"] == "succeeded"
    assert status["attempt_count"] == 2
    assert status["omitted_image_count"] == 1


def _write_stub_manifest(tmp_path: Path, count: int = 2):
    content = tmp_path / "content"
    stub = tmp_path / "stub"
    manifest = content / "_jobs" / "manifests" / "run-2" / "00000.jsonl"
    manifest.parent.mkdir(parents=True)
    stub.mkdir()
    entries = _candidates(count)
    manifest.write_text("".join(json.dumps(item) + "\n" for item in entries))
    for entry in entries:
        (stub / f"{entry['arxiv_id']}.md").write_text(
            f"{entry['title']} valid Markdown body. " * 20
        )
    return content, stub, manifest, entries


def test_worker_soft_deadline_before_first_paper_is_clean_partial(tmp_path):
    content, stub, manifest, entries = _write_stub_manifest(tmp_path, 1)
    subprocess.run(
        [
            sys.executable,
            str(WORKER_SCRIPT),
            "--manifest",
            str(manifest),
            "--content-root",
            str(content),
            "--stub-root",
            str(stub),
            "--soft-deadline-seconds",
            "0",
        ],
        check=True,
    )
    progress = json.loads(
        (content / "_jobs" / "progress" / "run-2" / "00000.json").read_text()
    )
    assert progress["status"] == "partial"
    assert progress["processed_papers"] == 0
    assert not (content / entries[0]["output_key"]).exists()


def test_worker_partial_checkpoint_resumes_from_result_jsonl(tmp_path):
    content, stub, manifest, entries = _write_stub_manifest(tmp_path, 2)
    command = [
        sys.executable,
        str(WORKER_SCRIPT),
        "--manifest",
        str(manifest),
        "--content-root",
        str(content),
        "--stub-root",
        str(stub),
    ]
    subprocess.run(
        [*command, "--soft-deadline-seconds", "1", "--stub-delay-seconds", "1.1"],
        check=True,
    )
    progress_path = content / "_jobs" / "progress" / "run-2" / "00000.json"
    progress = json.loads(progress_path.read_text())
    assert progress["status"] == "partial"
    assert progress["processed_papers"] == 1

    subprocess.run([*command, "--soft-deadline-seconds", "30"], check=True)
    progress = json.loads(progress_path.read_text())
    assert progress["status"] == "completed"
    assert progress["processed_papers"] == 2
    results = (
        (content / "_jobs" / "results" / "run-2" / "00000.jsonl")
        .read_text()
        .splitlines()
    )
    assert len(results) == 2
    assert all((content / entry["output_key"]).exists() for entry in entries)


def test_worker_failure_classification_and_forced_cleanup():
    missing = ValueError("missing_extracted_image:figure.webp")
    assert WORKER.classify_failure(missing, 1) == ("missing_extracted_image", True)
    assert WORKER.classify_failure(missing, 3) == ("missing_extracted_image", False)
    PdfReadError = type("PdfReadError", (Exception,), {})
    assert WORKER.classify_failure(PdfReadError("invalid PDF"), 1) == (
        "PdfReadError",
        False,
    )
    assert WORKER.classify_failure(ValueError("immutable_asset_conflict:key"), 1) == (
        "immutable_asset_conflict",
        False,
    )
    assert WORKER.classify_failure(
        subprocess.TimeoutExpired("chandra", WORKER.CHANDRA_TIMEOUT_SECONDS), 1
    ) == ("chandra_timeout", True)

    class StubbornProcess:
        def __init__(self):
            self.killed = False
            self.waits = 0

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout):
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("vllm", timeout)
            return 0

        def kill(self):
            self.killed = True

    process = StubbornProcess()
    assert WORKER.stop_vllm(process) == "killed"
    assert process.killed is True


def test_worker_gracefully_terminates_vllm():
    class GracefulProcess:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            assert timeout == WORKER.VLLM_SHUTDOWN_TIMEOUT_SECONDS
            return 0

        def kill(self):
            raise AssertionError("graceful shutdown must not kill vLLM")

    process = GracefulProcess()
    assert WORKER.stop_vllm(process) == "terminated"
    assert process.terminated is True


def test_worker_startup_failure_writes_failed_checkpoint(tmp_path, monkeypatch):
    content, _, manifest, _ = _write_stub_manifest(tmp_path, 1)

    def fail_startup():
        raise RuntimeError("vLLM startup failed")

    monkeypatch.setattr(WORKER, "start_vllm", fail_startup)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(WORKER_SCRIPT),
            "--manifest",
            str(manifest),
            "--content-root",
            str(content),
            "--soft-deadline-seconds",
            "30",
        ],
    )

    with pytest.raises(RuntimeError, match="vLLM startup failed"):
        WORKER.main()

    progress = json.loads(
        (content / "_jobs" / "progress" / "run-2" / "00000.json").read_text()
    )
    assert progress["status"] == "failed"
    assert progress["processed_papers"] == 0
    assert progress["fatal_error"] == "vLLM startup failed"
    assert progress["cleanup_state"] == "not_started"


@pytest.mark.parametrize("newline", ["\n", "\n\n", "\r\n"])
def test_canonical_markdown_accepts_upstream_header_spacing(newline):
    body = "Adaptive Expert Routing for Robust Object Detection. " * 8
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


@pytest.mark.parametrize(
    "failure", [None, "changed", "valid_original", "invalid_replacement"]
)
def test_repair_upload_backs_up_original_before_validated_replacement(
    tmp_path, monkeypatch, failure
):
    import hashlib

    key = "2607/2607.00000.md"
    original = b"figure caption only"
    replacement = (
        "Title: Paper zero\n\nMarkdown Content:\n\n"
        + "Paper zero explains the proposed method. " * 5
    ).encode()
    if failure == "valid_original":
        original = replacement
    entry = {
        "output_key": key,
        "title": "Paper zero",
        "replace_invalid_sha256": hashlib.sha256(original).hexdigest(),
    }
    remote = {key: original if failure != "changed" else b"concurrently changed"}
    events = []
    store = WORKER.BucketContentStore("test/bucket", "secret", tmp_path)
    store.repairs = {key: entry}
    WORKER.atomic_write(
        tmp_path / key,
        b"bad replacement" if failure == "invalid_replacement" else replacement + b"\n",
    )
    monkeypatch.setattr(store, "existing", lambda keys: set(keys) & remote.keys())
    monkeypatch.setattr(store, "read", lambda path: remote[path])

    def bridge(_token, request):
        for source, destination in request["files"]:
            events.append(destination)
            remote[destination] = Path(source).read_bytes()
        return {}

    monkeypatch.setattr(WORKER, "run_bucket_bridge", bridge)
    if failure:
        with pytest.raises(ValueError):
            store.upload([key])
        assert events == []
    else:
        store.upload([key])
        backup = f"_jobs/repair-originals/{entry['replace_invalid_sha256']}/{key}"
        assert events == [backup, key]
        assert remote[backup] == original
        assert remote[key] == replacement + b"\n"


def test_failed_repair_keeps_existing_canonical_object(tmp_path, monkeypatch):
    import hashlib

    entry = _candidates(1)[0]
    original = b"only a figure caption"
    entry["replace_invalid_sha256"] = hashlib.sha256(original).hexdigest()
    output = tmp_path / entry["output_key"]
    WORKER.atomic_write(output, original)
    monkeypatch.setitem(
        sys.modules,
        "pypdf",
        SimpleNamespace(PdfReader=lambda *a, **k: SimpleNamespace(pages=[1])),
    )
    monkeypatch.setattr(WORKER, "download_pdf_for_entry", lambda entry: (b"pdf", "v1"))
    monkeypatch.setattr(WORKER, "run_chandra", lambda *a: ("irrelevant caption", {}))
    with pytest.raises(ValueError, match="semantic_markdown_mismatch"):
        WORKER.process(entry, tmp_path, tmp_path / "run")
    assert output.read_bytes() == original


def test_repair_selection_is_bounded_and_pins_original(tmp_path, monkeypatch):
    import hashlib

    monkeypatch.setenv("PWC_CRON_LOG_DIR", str(tmp_path))
    papers = _candidates(3)
    job = _scheduler(execute=False, confirm=False, full=False)
    job.repair_invalid_limit = 1
    job._papers = Mock(return_value=papers)
    job._existing_paths = Mock(
        return_value={item["output_key"]: object() for item in papers}
    )
    job._copy_upstream = Mock()
    job._status_records = Mock(return_value={})
    job._semantic_records = Mock(
        return_value={item["output_key"]: "invalid" for item in papers}
    )
    job.filesystem = Mock()
    original = b"figure caption only"
    job.filesystem.open.side_effect = lambda *a, **k: BytesIO(original)
    job._launch = Mock(return_value=[])
    job.run()
    job._copy_upstream.assert_not_called()
    candidates = job._launch.call_args.args[0]
    assert len(candidates) == 1
    assert (
        candidates[0]["replace_invalid_sha256"] == hashlib.sha256(original).hexdigest()
    )
