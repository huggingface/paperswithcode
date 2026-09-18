from unittest.mock import Mock

import pytest
import requests

from backend.utils.hf_utils import (
    HfArtifactDiscoveryError,
    fetch_hf_artifact_metrics,
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


def test_metric_refresh_only_treats_404_as_conclusive_missing(monkeypatch):
    monkeypatch.setattr(requests, "get", Mock(return_value=_response(404, {})))

    assert fetch_hf_artifact_metrics("model", "org/missing") is None


@pytest.mark.parametrize("status_code", [401, 403, 429, 500])
def test_metric_refresh_raises_on_auth_throttle_and_server_errors(
    monkeypatch, status_code
):
    monkeypatch.setattr(requests, "get", Mock(return_value=_response(status_code, {})))

    with pytest.raises(HfArtifactDiscoveryError, match=str(status_code)):
        fetch_hf_artifact_metrics("model", "org/model")


def test_metric_refresh_does_not_expand_downloads_for_spaces(monkeypatch):
    get = Mock(return_value=_response(200, {"trendingScore": 137, "likes": 437}))
    monkeypatch.setattr(requests, "get", get)

    metrics = fetch_hf_artifact_metrics("space", "org/space")

    assert metrics == {"trending_score": 137, "likes": 437, "downloads": None}
    assert get.call_args.kwargs["params"] == [
        ("expand[]", "trendingScore"),
        ("expand[]", "likes"),
    ]


@pytest.mark.parametrize("kind", ["model", "dataset"])
def test_metric_refresh_expands_downloads_for_models_and_datasets(monkeypatch, kind):
    get = Mock(
        return_value=_response(200, {"trendingScore": 1, "likes": 2, "downloads": 3})
    )
    monkeypatch.setattr(requests, "get", get)

    metrics = fetch_hf_artifact_metrics(kind, "org/repo")

    assert metrics == {"trending_score": 1, "likes": 2, "downloads": 3}
    assert ("expand[]", "downloads") in get.call_args.kwargs["params"]
