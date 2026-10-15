from datetime import date
from types import SimpleNamespace

import httpx

from backend.services import paper_suggested_questions_warm_service as warm


def _feed(*ids):
    return SimpleNamespace(results=[SimpleNamespace(id=str(i)) for i in ids])


def test_visible_paper_ids_follow_home_then_busiest_entity_pages(monkeypatch):
    home_calls = []

    class Papers:
        def __init__(self, _db):
            pass

        def get_papers(self, **kwargs):
            home_calls.append(kwargs)
            return _feed(*{1: (1, 2), 2: (3,), 3: ()}[kwargs["page"]])

    class Tasks:
        def __init__(self, _db):
            pass

        def get_task_papers(self, task_id, **kwargs):
            assert kwargs == {"page_size": 20, "order_by": "trending"}
            return _feed(2, 10) if task_id == "7" else _feed(11)

    class Methods:
        def __init__(self, _db):
            pass

        def get_method_papers(self, method_id, **kwargs):
            return _feed(12, 1)

    monkeypatch.setattr(warm, "PaperService", Papers)
    monkeypatch.setattr(warm, "TaskService", Tasks)
    monkeypatch.setattr(warm, "MethodService", Methods)
    monkeypatch.setattr(
        warm,
        "_entities_by_paper_count",
        lambda _db: [("task", 7), ("method", 3), ("task", 8)],
    )

    assert warm.visible_paper_ids(None, date(2026, 10, 15)) == [1, 2, 3, 10, 12, 11]
    assert home_calls[0] == {
        "page": 1,
        "page_size": 30,
        "order_by": "trending",
        "start_date": date(2026, 10, 9),
        "end_date": date(2026, 10, 15),
    }


class FakeSession:
    def __init__(self, stored_ids, rows):
        self.stored_ids = stored_ids
        self.rows = rows

    def scalars(self, _statement):
        return iter(self.stored_ids)

    def execute(self, _statement):
        return iter(self.rows)


def _row(paper_id, abstract="An abstract."):
    return SimpleNamespace(id=paper_id, title=f"T{paper_id}", abstract=abstract)


def test_warm_generates_missing_papers_in_order_up_to_limit(monkeypatch):
    generated, stored = [], []

    def fake_generate(_client, title, _abstract, *, api_key):
        generated.append(title)
        if title == "T3":
            raise httpx.ConnectError("down")
        return ["Q1?", "Q2?", "Q3?"]

    def fake_store(_db, paper_id, questions):
        stored.append(paper_id)
        return bool(questions)

    monkeypatch.setattr(warm, "generate_suggested_questions", fake_generate)
    monkeypatch.setattr(warm, "store_suggested_questions", fake_store)
    db = FakeSession(
        stored_ids=[2],
        rows=[_row(5), _row(3), _row(4, abstract=" "), _row(1)],
    )

    stats = warm.warm_suggested_questions(
        db, [1, 2, 3, 4, 5], client=None, api_key="sk", limit=2, workers=2
    )

    assert sorted(generated) == ["T1", "T3"]
    assert stored == [1, 3]
    assert stats == {
        "candidates": 5,
        "already_stored": 1,
        "remaining": 1,
        "generated": 1,
        "failed": 1,
    }
