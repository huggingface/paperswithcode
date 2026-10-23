import pytest

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


def _shared_lifecycle(tmp_path, monkeypatch) -> DeploymentLifecycle:
    monkeypatch.setenv("PWC_ENVIRONMENT", "production")
    monkeypatch.setenv("PWC_DEPLOYMENT_SLOT", "green")
    monkeypatch.setenv("PWC_RELEASE_ID", "release-1")
    monkeypatch.setenv("PWC_RUNTIME_ID", "runtime-1")
    return DeploymentLifecycle(
        state_root=tmp_path,
        process_id=1001,
        process_start_token="start-1",
        process_is_alive=lambda *_args: True,
    )


def _fail_writes(monkeypatch, lifecycle: DeploymentLifecycle, count: int) -> None:
    write_json = lifecycle._write_json
    remaining = [count]

    def write(path, value):
        if remaining[0]:
            remaining[0] -= 1
            raise OSError(28, "No space left on device")
        write_json(path, value)

    monkeypatch.setattr(lifecycle, "_write_json", write)


def test_failed_admission_publish_does_not_leak_the_request_count(
    tmp_path, monkeypatch
):
    """2026-10-23: ENOSPC on the increment's state write leaked two counts, so
    the drained slot reported active_http_requests=2 until it was stopped."""
    lifecycle = _shared_lifecycle(tmp_path, monkeypatch)
    _fail_writes(monkeypatch, lifecycle, count=1)

    with pytest.raises(OSError):
        with lifecycle.request("/api/v1/papers"):
            pytest.fail("the request must not run without accounting")

    with lifecycle.request("/api/v1/papers"):
        assert lifecycle.status().active_http_requests == 1
    assert lifecycle.status().active_http_requests == 0
    assert not list(tmp_path.rglob("worker-*.json"))


def test_status_retries_a_failed_decrement_publish(tmp_path, monkeypatch):
    lifecycle = _shared_lifecycle(tmp_path, monkeypatch)

    with lifecycle.request("/api/v1/papers"):
        with pytest.raises(OSError):
            with lifecycle.request("/api/v1/papers"):
                _fail_writes(monkeypatch, lifecycle, count=1)
        # The record still says 2; nothing else will rewrite it on an idle slot.
        assert lifecycle._read_json(lifecycle._worker_path)["active_http_requests"] == 2
        assert lifecycle.status().active_http_requests == 1
