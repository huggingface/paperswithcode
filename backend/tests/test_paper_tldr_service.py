import json

import httpx

from backend.services.paper_tldr_service import (
    MODEL,
    SYSTEM_PROMPT,
    generate_paper_tldr,
)


def test_generate_paper_tldr_posts_prompt_and_returns_output_text():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "output": [
                    {"type": "reasoning", "content": []},
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "  Short TL;DR.  "}
                        ],
                    },
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        tldr = generate_paper_tldr(client, "A Title", "An abstract.", api_key="sk-test")

    assert tldr == "Short TL;DR."
    body = json.loads(requests[0].content)
    assert requests[0].headers["Authorization"] == "Bearer sk-test"
    assert body["model"] == MODEL
    assert body["instructions"] == SYSTEM_PROMPT
    assert body["input"] == "Title: A Title\nAbstract: An abstract."
    assert body["reasoning"] == {"effort": "none"}
    assert body["store"] is False
