from unittest.mock import Mock

import pytest
import requests

from backend.utils.hf_utils import (
    HfArtifactDiscoveryError,
    fetch_hf_artifacts_for_arxiv,
)


def _response(status_code: int, payload, headers=None):
    response = Mock()
    response.status_code = status_code
    response.headers = headers or {}
    response.json.return_value = payload
    return response


def test_fetch_hf_artifacts_uses_token_and_collects_all_repo_kinds(monkeypatch):
    get = Mock(
        return_value=_response(
            200,
            {
                "models": [{"id": "org/model"}],
                "datasets": [{"repoId": "org/dataset"}],
                "spaces": ["org/space"],
            },
        )
    )
    monkeypatch.setattr(requests, "get", get)

    artifacts = fetch_hf_artifacts_for_arxiv("2606.23050v2", token="secret")

    assert artifacts == [
        ("model", "org/model", "https://huggingface.co/org/model"),
        ("dataset", "org/dataset", "https://huggingface.co/datasets/org/dataset"),
        ("space", "org/space", "https://huggingface.co/spaces/org/space"),
    ]
    assert get.call_args.args[0].endswith("/api/arxiv/2606.23050/repos")
    assert get.call_args.kwargs["headers"]["authorization"] == "Bearer secret"


def test_fetch_hf_artifacts_accepts_conclusive_empty_response(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        Mock(
            return_value=_response(
                200,
                {"models": [], "datasets": [], "spaces": []},
            )
        ),
    )

    assert fetch_hf_artifacts_for_arxiv("9999.99999") == []


def test_fetch_hf_artifacts_retries_rate_limit_using_reset_header(monkeypatch):
    get = Mock(
        side_effect=[
            _response(429, {}, {"RateLimit": '"api";r=0;t=2'}),
            _response(200, {"models": [], "datasets": [], "spaces": []}),
        ]
    )
    sleep = Mock()
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr("backend.utils.hf_utils.time.sleep", sleep)

    assert fetch_hf_artifacts_for_arxiv("2606.23050") == []
    assert get.call_count == 2
    sleep.assert_called_once_with(2.0)


def test_fetch_hf_artifacts_raises_after_transient_failures(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        Mock(side_effect=requests.Timeout("timed out")),
    )
    monkeypatch.setattr("backend.utils.hf_utils.time.sleep", Mock())

    with pytest.raises(HfArtifactDiscoveryError):
        fetch_hf_artifacts_for_arxiv("2606.23050", max_retries=1)


def test_fetch_hf_artifacts_rejects_incomplete_success_payload(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        Mock(return_value=_response(200, {"models": []})),
    )
    monkeypatch.setattr("backend.utils.hf_utils.time.sleep", Mock())

    with pytest.raises(HfArtifactDiscoveryError):
        fetch_hf_artifacts_for_arxiv("2606.23050", max_retries=1)
