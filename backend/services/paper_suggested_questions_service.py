"""Starter questions for a paper page, generated once with gpt-6-luna.

The first request for a paper generates three short questions from its title
and abstract and stores them; later requests read the stored row. A
process-wide semaphore bounds concurrent generations, so a crawler sweeping
paper pages cannot fan out OpenAI calls; requests over the bound get no
questions and the page simply omits the section.
"""

import json
import logging
import threading

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.database import Paper as DBPaper
from backend.models.database import PaperSuggestedQuestions
from backend.services.paper_tldr_service import RESPONSES_URL

logger = logging.getLogger(__name__)

MODEL = "gpt-6-luna"
QUESTION_COUNT = 3
MAX_CONCURRENT_GENERATIONS = 4
_generation_slots = threading.BoundedSemaphore(MAX_CONCURRENT_GENERATIONS)

SYSTEM_PROMPT = """You write the three questions a curious ML researcher would most want to ask an AI assistant about a paper they just found, given its title and abstract.

Rules:
- Exactly three questions, each 5-12 words, each ending with "?".
- Each question covers a different angle, such as: how the core method works, how it compares with prior work or baselines, its results or limitations, or how to apply it.
- Refer to the paper's method by name when the abstract names it; otherwise say "this paper". Use concrete nouns from the abstract.
- Ask questions the paper can answer. Never put numbers, results, or claims in a question that the abstract does not state.
- Plain wording, no hype, no markdown."""

RESPONSE_FORMAT = {
    "type": "json_schema",
    "name": "suggested_questions",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": QUESTION_COUNT,
                "maxItems": QUESTION_COUNT,
            }
        },
        "required": ["questions"],
        "additionalProperties": False,
    },
}


def generate_suggested_questions(
    client: httpx.Client, title: str, abstract: str, *, api_key: str
) -> list[str]:
    """Return three short questions; raises httpx.HTTPError on failure."""
    response = client.post(
        RESPONSES_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": MODEL,
            "instructions": SYSTEM_PROMPT,
            "input": f"Title: {title}\nAbstract: {abstract}",
            "store": False,
            "max_output_tokens": 300,
            "reasoning": {"effort": "none"},
            "text": {"format": RESPONSE_FORMAT},
            "prompt_cache_key": "pwc-suggested-questions-v1",
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
    questions = [" ".join(q.split()) for q in json.loads(text)["questions"]]
    return [q for q in questions if q][:QUESTION_COUNT]


def get_suggested_questions(
    db: Session, paper_id: int, *, generate: bool = True
) -> list[str]:
    """Stored questions for a paper, generating them on first request.

    ``generate=False`` only reads: generation spends the server's OpenAI key, so
    anonymous readers get stored questions and the hourly warm job fills gaps.
    """
    stored = db.get(PaperSuggestedQuestions, paper_id)
    if stored is not None:
        return stored.questions
    if not generate:
        return []

    paper = db.get(DBPaper, paper_id)
    api_key = get_settings().openai_api_key
    if paper is None or not (paper.abstract or "").strip() or not api_key:
        return []
    if not _generation_slots.acquire(blocking=False):
        return []
    try:
        with httpx.Client(timeout=20) as client:
            questions = generate_suggested_questions(
                client, paper.title, paper.abstract, api_key=api_key
            )
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("suggested_questions_failed paper_id=%s: %s", paper_id, exc)
        return []
    finally:
        _generation_slots.release()

    if not store_suggested_questions(db, paper_id, questions):
        return []
    return questions


def store_suggested_questions(db: Session, paper_id: int, questions: list[str]) -> bool:
    """Store a complete set of questions; an existing row wins."""
    if len(questions) != QUESTION_COUNT:
        return False
    db.execute(
        insert(PaperSuggestedQuestions)
        .values(paper_id=paper_id, questions=questions, model=MODEL)
        .on_conflict_do_nothing(index_elements=["paper_id"])
    )
    db.commit()
    return True
