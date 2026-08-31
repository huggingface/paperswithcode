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
