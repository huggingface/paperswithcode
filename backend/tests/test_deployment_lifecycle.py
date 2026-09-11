from backend.services.deployment_lifecycle import DeploymentLifecycle


def test_deployment_status_exposes_exact_immutable_git_sha(monkeypatch):
    sha = "a" * 40
    monkeypatch.setenv("PWC_ENVIRONMENT", "staging")
    monkeypatch.setenv("PWC_GIT_SHA", sha)
    monkeypatch.setenv("PWC_RELEASE_ID", f"{sha[:12]}-staging")

    status = DeploymentLifecycle().status()

    assert status.environment == "staging"
    assert status.git_sha == sha
    assert status.release_id == f"{sha[:12]}-staging"


def test_openai_responses_request_is_counted_as_an_active_gateway_stream():
    lifecycle = DeploymentLifecycle()

    with lifecycle.request("/api/internal/chat-gateway/v1/responses"):
        assert lifecycle.status().active_gateway_streams == 1

    assert lifecycle.status().active_gateway_streams == 0
