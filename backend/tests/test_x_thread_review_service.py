from __future__ import annotations

import json

import httpx

from backend.services.x_thread_review_service import MODEL, review_post


def _client(verdict: dict, seen: list) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "output": [
                    {"type": "reasoning"},
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": json.dumps(verdict)}
                        ],
                    },
                ]
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_review_post_returns_verdict_and_sends_paper_and_post():
    seen: list = []
    client = _client({"approve": False, "reason": "Lists three papers."}, seen)

    verdict = review_post(
        client,
        api_key="key",
        title="Dr. Claw: An AI Scientist Workspace",
        abstract="Abstract text",
        post_author="Jane Doe",
        post_handle="janedoe",
        post_text="3 papers accepted at #EMNLP2026!",
        post_urls=["https://arxiv.org/abs/2609.00365"],
    )

    assert verdict.approve is False
    assert verdict.reason == "Lists three papers."
    (request,) = seen
    assert request["model"] == MODEL
    assert request["text"]["format"]["type"] == "json_schema"
    assert "Dr. Claw" in request["input"]
    assert "3 papers accepted" in request["input"]
    assert "https://arxiv.org/abs/2609.00365" in request["input"]
