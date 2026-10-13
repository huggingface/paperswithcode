"""Review X thread matches before they are linked to a paper.

Author and organization matching finds posts by the right people, but not
always about the right paper: a lab's announcement of a sibling project, a
"3 papers accepted" list, or a congratulation reply all pass it. A
gpt-5.6-sol review applies the same judgment a curator would and returns an
approve/reject verdict with a one-line reason.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

MODEL = "gpt-5.6-sol"
RESPONSES_URL = "https://api.openai.com/v1/responses"
MAX_ABSTRACT_CHARS = 1500

INSTRUCTIONS = """You check whether an X post should be shown on a research paper's page as a post in which the paper's own authors or organization introduce that paper.

Approve when the post is mainly about THIS paper: it announces, introduces, explains, demos, or promotes it, or announces that this specific paper was accepted or will be presented and says what it is. A post that introduces this paper together with a closely related sibling paper (for example linking both project pages) is fine.

Reject when:
- the post is about a different paper or project, even by the same authors or lab;
- the post announces several papers at once (e.g. "3 papers accepted at NeurIPS", "Two papers accepted to EMNLP: - X - Y") and this paper is only an item in that list, named but not introduced; a post that mentions other acceptances but is mainly about this paper is fine;
- the post only congratulates, thanks, or reacts to someone else without presenting the paper;
- nothing in the post (name, title, topic, links) ties it to this paper.

Judge from the paper's title, method name, abstract, and the post's text and links. Answer in JSON."""

SCHEMA = {
    "type": "object",
    "properties": {
        "approve": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["approve", "reason"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ReviewVerdict:
    approve: bool
    reason: str


def review_post(
    client: httpx.Client,
    *,
    api_key: str,
    title: str,
    abstract: str | None,
    post_author: str,
    post_handle: str,
    post_text: str,
    post_urls: list[str],
) -> ReviewVerdict:
    """Return the verdict for one post; raises httpx.HTTPError on failure."""
    paper = f"Title: {title}\nAbstract: {(abstract or '')[:MAX_ABSTRACT_CHARS]}"
    post = (
        f"Author: {post_author} (@{post_handle})\nText: {post_text}\n"
        f"Links: {', '.join(post_urls) or 'none'}"
    )
    response = client.post(
        RESPONSES_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": MODEL,
            "instructions": INSTRUCTIONS,
            "input": f"PAPER\n{paper}\n\nPOST\n{post}",
            "store": False,
            "max_output_tokens": 4000,
            "reasoning": {"effort": "medium"},
            "prompt_cache_key": "pwc-x-thread-review-v2",
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "x_thread_review",
                    "schema": SCHEMA,
                    "strict": True,
                }
            },
        },
    )
    body = response.raise_for_status().json()
    text = "".join(
        part["text"]
        for item in body["output"]
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    )
    verdict = json.loads(text)
    return ReviewVerdict(bool(verdict["approve"]), str(verdict["reason"]))
