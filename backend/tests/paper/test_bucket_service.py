import os
from pathlib import Path

import httpx
from huggingface_hub.errors import HfHubHTTPError

from backend.services import paper_bucket_service as bucket_service


class FakeHfApi:
    instances = []

    def __init__(self, *, token):
        self.token = token
        self.calls = []
        self.instances.append(self)

    def create_bucket(self, bucket_id, *, private, exist_ok):
        self.calls.append(("create", bucket_id, private, exist_ok))

    def copy_files(self, source, destination):
        self.hf_hub_download("owner/repo", "README.md")
        self.calls.append(("copy", source, destination))

    def hf_hub_download(self, _repo_id, _filename, *, cache_dir=None):
        self.calls.append(("cache", Path(cache_dir).is_dir()))

    def batch_bucket_files(self, bucket_id, *, add):
        source, destination = add[0]
        self.calls.append(("add", bucket_id, Path(source).read_bytes(), destination))


def test_configures_xet_cache_in_writable_runtime_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("PWC_RUNTIME_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("HF_XET_CACHE", raising=False)

    bucket_service._configure_hugging_face_cache()

    assert os.environ["HF_HOME"] == str(tmp_path / "hf-app-cache")
    assert os.environ["HF_XET_CACHE"] == str(tmp_path / "hf-app-cache" / "xet")


def test_copy_paper_uses_user_token_and_uploads_pdf(monkeypatch):
    FakeHfApi.instances.clear()
    monkeypatch.setattr(bucket_service, "HfApi", FakeHfApi)
    monkeypatch.setattr(
        bucket_service,
        "_download_arxiv_pdf",
        lambda _url, destination: destination.write_bytes(b"%PDF-test"),
    )

    result = bucket_service.copy_paper_to_bucket(
        token="user-oauth-token",
        bucket_id="alice/paper-artifacts",
        create=True,
        private=True,
        artifacts=[bucket_service.HubArtifact("model", "openai/gpt-oss-20b")],
        pdf_url="https://arxiv.org/pdf/2601.00001v1",
        pdf_name="2601.00001",
    )

    api = FakeHfApi.instances[0]
    assert api.token == "user-oauth-token"
    assert api.calls == [
        ("create", "alice/paper-artifacts", True, True),
        ("cache", True),
        (
            "copy",
            "hf://openai/gpt-oss-20b/",
            "hf://buckets/alice/paper-artifacts/models/openai/gpt-oss-20b/",
        ),
        ("add", "alice/paper-artifacts", b"%PDF-test", "paper/2601.00001.pdf"),
    ]
    assert result.copied == ("model:openai/gpt-oss-20b", "pdf")
    assert result.errors == ()


def test_rejects_non_arxiv_pdf_host(tmp_path):
    try:
        bucket_service._download_arxiv_pdf(
            "https://example.com/paper.pdf", tmp_path / "paper.pdf"
        )
    except bucket_service.PaperBucketError as error:
        assert "arXiv-hosted" in str(error)
    else:
        raise AssertionError("expected non-arXiv host to be rejected")


def test_follows_redirects_within_arxiv_hosts(tmp_path, monkeypatch):
    requested_urls = []

    def handler(request):
        requested_urls.append(str(request.url))
        if request.url.path.endswith(".pdf"):
            return httpx.Response(301, headers={"location": "/pdf/2606.03748"})
        return httpx.Response(200, content=b"%PDF-test")

    client = httpx.Client
    monkeypatch.setattr(
        bucket_service.httpx,
        "Client",
        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs),
    )
    destination = tmp_path / "paper.pdf"

    bucket_service._download_arxiv_pdf(
        "https://arxiv.org/pdf/2606.03748.pdf", destination
    )

    assert requested_urls == [
        "https://arxiv.org/pdf/2606.03748.pdf",
        "https://arxiv.org/pdf/2606.03748",
    ]
    assert destination.read_bytes() == b"%PDF-test"


def test_rejects_redirects_away_from_arxiv(tmp_path, monkeypatch):
    client = httpx.Client
    monkeypatch.setattr(
        bucket_service.httpx,
        "Client",
        lambda **kwargs: client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    301, headers={"location": "https://example.com/paper.pdf"}
                )
            ),
            **kwargs,
        ),
    )

    try:
        bucket_service._download_arxiv_pdf(
            "https://arxiv.org/pdf/2606.03748.pdf", tmp_path / "paper.pdf"
        )
    except bucket_service.PaperBucketError as error:
        assert "arXiv-hosted" in str(error)
    else:
        raise AssertionError("expected cross-host redirect to be rejected")


def test_permission_error_does_not_trigger_oauth_loop():
    response = httpx.Response(
        403, request=httpx.Request("POST", "https://huggingface.co")
    )
    error = bucket_service._hub_error(HfHubHTTPError("forbidden", response=response))

    assert error.authorization_required is False
    assert "permission" in str(error)
