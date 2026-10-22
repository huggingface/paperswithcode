import json
from types import SimpleNamespace

import httpx
import pytest

from backend.models.database import Paper as DBPaper
from backend.models.database import PaperSuggestedQuestions
from backend.services import paper_suggested_questions_service as service


def _luna_response(questions):
    return httpx.Response(
        200,
        json={
            "output": [
                {"type": "reasoning", "content": []},
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({"questions": questions}),
                        }
                    ],
                },
            ]
        },
    )


def test_generate_posts_structured_prompt_and_normalizes_questions():
    requests = []

    def handler(request):
        requests.append(request)
        return _luna_response(["How does  PoolDINO pool?", "Why DINO?", "Limits?"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        questions = service.generate_suggested_questions(
            client, "A Title", "An abstract.", api_key="sk-test"
        )

    assert questions == ["How does PoolDINO pool?", "Why DINO?", "Limits?"]
    body = json.loads(requests[0].content)
    assert requests[0].headers["Authorization"] == "Bearer sk-test"
    assert body["model"] == service.MODEL
    assert body["instructions"] == service.SYSTEM_PROMPT
    assert body["input"] == "Title: A Title\nAbstract: An abstract."
    assert body["text"]["format"]["name"] == "suggested_questions"
    assert body["store"] is False


class FakeSession:
    def __init__(self, stored=None, paper=None):
        self.rows = {PaperSuggestedQuestions: stored, DBPaper: paper}
        self.executed = []

    def get(self, model, _id):
        return self.rows[model]

    def execute(self, statement):
        self.executed.append(statement)

    def commit(self):
        pass


@pytest.fixture
def openai_key(monkeypatch):
    monkeypatch.setattr(
        service, "get_settings", lambda: SimpleNamespace(openai_api_key="sk-test")
    )


@pytest.fixture
def luna(monkeypatch):
    calls = []

    def fake_generate(client, title, abstract, *, api_key):
        calls.append(title)
        return ["Q1?", "Q2?", "Q3?"]

    monkeypatch.setattr(service, "generate_suggested_questions", fake_generate)
    return calls


def test_stored_questions_skip_generation(openai_key, luna):
    db = FakeSession(stored=SimpleNamespace(questions=["A?", "B?", "C?"]))

    assert service.get_suggested_questions(db, 1) == ["A?", "B?", "C?"]
    assert luna == []


def test_first_request_generates_and_stores(openai_key, luna):
    db = FakeSession(paper=SimpleNamespace(title="T", abstract="An abstract."))

    assert service.get_suggested_questions(db, 1) == ["Q1?", "Q2?", "Q3?"]
    assert luna == ["T"]
    assert len(db.executed) == 1


def test_papers_without_abstract_get_no_questions(openai_key, luna):
    db = FakeSession(paper=SimpleNamespace(title="T", abstract="  "))

    assert service.get_suggested_questions(db, 1) == []
    assert luna == []


def test_saturated_generation_slots_return_nothing(openai_key, luna, monkeypatch):
    monkeypatch.setattr(service, "_generation_slots", service.threading.Semaphore(0))
    db = FakeSession(paper=SimpleNamespace(title="T", abstract="An abstract."))

    assert service.get_suggested_questions(db, 1) == []
    assert luna == []
    assert db.executed == []


def test_upstream_failure_is_not_stored(openai_key, monkeypatch):
    def failing(*_args, **_kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(service, "generate_suggested_questions", failing)
    db = FakeSession(paper=SimpleNamespace(title="T", abstract="An abstract."))

    assert service.get_suggested_questions(db, 1) == []
    assert db.executed == []


def test_reading_without_generation_never_calls_openai(openai_key, luna):
    db = FakeSession(paper=SimpleNamespace(title="T", abstract="An abstract."))

    assert service.get_suggested_questions(db, 1, generate=False) == []
    assert luna == []
    assert db.executed == []


def test_route_generates_only_for_signed_in_readers(monkeypatch):
    from backend.routers import papers as papers_router

    calls = []
    monkeypatch.setattr(
        papers_router,
        "get_suggested_questions",
        lambda _db, _paper_id, *, generate: calls.append(generate) or [],
    )
    for signed_in in (False, True):
        monkeypatch.setattr(
            papers_router, "has_session", lambda _request, s=signed_in: s
        )
        papers_router.get_paper_suggested_questions(object(), 1, object())

    assert calls == [False, True]
