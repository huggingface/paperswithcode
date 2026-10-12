from types import SimpleNamespace

import pytest

from backend.services import chat_semantic_scholar_service as service


def test_fetch_semantic_scholar_uses_primary_key(monkeypatch):
    request = {}

    class Response:
        content = b'{"data":[]}'
        status_code = 200
        headers = {"content-type": "application/json"}

    class Client:
        def __init__(self, **options):
            request["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url, **options):
            request["url"] = url
            request["request"] = options
            return Response()

    monkeypatch.setattr(service.httpx, "Client", Client)
    result = service.fetch_semantic_scholar(
        SimpleNamespace(semantic_scholar_api_key="primary-secret"),
        "paper/search",
        {"query": "vision transformers", "limit": "20"},
    )

    assert result == {"data": []}
    assert request["url"] == ("https://api.semanticscholar.org/graph/v1/paper/search")
    assert request["request"]["headers"]["x-api-key"] == "primary-secret"


@pytest.mark.parametrize(
    "path",
    ["author/search", "paper/ARXIV:1706.03762", "paper/id/recommendations"],
)
def test_fetch_semantic_scholar_rejects_unsupported_paths(path):
    with pytest.raises(ValueError, match="Unsupported Semantic Scholar operation"):
        service.fetch_semantic_scholar(
            SimpleNamespace(semantic_scholar_api_key="secret"), path, {}
        )


def test_semantic_scholar_graph_path_accepts_encoded_doi(monkeypatch):
    class Response:
        content = b'{"data":[]}'
        status_code = 200
        headers = {"content-type": "application/json"}

    class Client:
        def __init__(self, **_options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url, **_options):
            assert "paper/DOI:10.1000%2Fexample/citations" in url
            return Response()

    monkeypatch.setattr(service.httpx, "Client", Client)
    service.fetch_semantic_scholar(
        SimpleNamespace(semantic_scholar_api_key="secret"),
        "paper/DOI:10.1000%2Fexample/citations",
        {"limit": "20"},
    )
