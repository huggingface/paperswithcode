"""Server-side Hugging Face avatar resolution for the homepage topic cards."""

import httpx
import pytest

from backend.services import hf_avatar_service


@pytest.fixture(autouse=True)
def empty_cache(monkeypatch):
    monkeypatch.setattr(hf_avatar_service, "_cache", {})
    monkeypatch.setattr(hf_avatar_service, "_images", {})


def route(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real = httpx.Client
    monkeypatch.setattr(
        hf_avatar_service.httpx,
        "Client",
        lambda **kwargs: real(transport=transport, **kwargs),
    )

    def get(url, **kwargs):
        with real(transport=transport, **kwargs) as client:
            return client.get(url)

    monkeypatch.setattr(hf_avatar_service.httpx, "get", get)


def test_resolves_uploaded_default_and_missing_avatars_and_caches_hits(monkeypatch):
    calls = []

    def handler(request):
        name = request.url.path.split("/")[3]
        calls.append(name)
        if name == "alice":
            return httpx.Response(
                200, json={"avatarUrl": "https://cdn-avatars.huggingface.co/a.png"}
            )
        if name == "bob":
            # HF redirects lowercased names to the account's own casing.
            return httpx.Response(307, headers={"location": "/api/users/Bob/avatar"})
        if name == "Bob":
            return httpx.Response(200, json={"avatarUrl": "/avatars/b.svg"})
        return httpx.Response(404, json={"error": "not found"})

    route(monkeypatch, handler)
    assert hf_avatar_service.avatar_urls(["alice", "bob", "ghost"]) == {
        "alice": "https://cdn-avatars.huggingface.co/a.png",
        "bob": "https://huggingface.co/avatars/b.svg",
    }
    assert hf_avatar_service.avatar_urls(["alice", "ghost"]) == {
        "alice": "https://cdn-avatars.huggingface.co/a.png"
    }
    # Hits come from the cache; misses are retried.
    assert sorted(calls) == ["Bob", "alice", "bob", "ghost", "ghost"]


def test_skips_unreachable_hub_and_bad_payloads(monkeypatch):
    def handler(request):
        if "down" in request.url.path:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"avatarUrl": "javascript:alert(1)"})

    route(monkeypatch, handler)
    assert hf_avatar_service.avatar_urls(["down", "odd"]) == {}
    assert hf_avatar_service.avatar_urls([]) == {}


def test_serves_avatar_images_and_rejects_non_images(monkeypatch):
    fetched = []

    def handler(request):
        if request.url.path.startswith("/api/users/"):
            name = request.url.path.split("/")[3]
            return httpx.Response(
                200, json={"avatarUrl": f"https://cdn-avatars.huggingface.co/{name}"}
            )
        fetched.append(request.url.path)
        if request.url.path == "/alice":
            return httpx.Response(
                200,
                content=b"<svg/>",
                headers={"content-type": "image/svg+xml; charset=utf-8"},
            )
        return httpx.Response(
            200, content=b"<html>", headers={"content-type": "text/html"}
        )

    route(monkeypatch, handler)
    assert hf_avatar_service.avatar_image("alice") == ("image/svg+xml", b"<svg/>")
    assert hf_avatar_service.avatar_image("alice") == ("image/svg+xml", b"<svg/>")
    assert hf_avatar_service.avatar_image("page") is None
    assert hf_avatar_service.avatar_image("page") is None  # misses are remembered
    assert fetched == ["/alice", "/page"]
