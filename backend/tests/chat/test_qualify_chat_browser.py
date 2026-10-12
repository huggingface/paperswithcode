import pytest

from backend.scripts import qualify_chat_browser
from backend.scripts.qualify_chat_browser import (
    CHAT_MODEL_STORAGE_KEY,
    ChromePage,
    ORIGIN,
    pilot_passes,
    qualification_passes,
    reasoning_minimum_reached,
)


def test_devtools_connection_disables_idle_ping_timeout(monkeypatch):
    captured = {}
    expected = object()

    def fake_connect(url, **kwargs):
        captured.update(url=url, **kwargs)
        return expected

    monkeypatch.setattr(qualify_chat_browser, "connect", fake_connect)

    assert qualify_chat_browser._connect_devtools("ws://local") is expected
    assert captured == {
        "url": "ws://local",
        "open_timeout": 5,
        "ping_interval": None,
    }


def test_browser_populates_empty_composer_before_waiting_for_send(monkeypatch):
    page = object.__new__(ChromePage)
    page.timeout = 1
    evaluations: list[str] = []

    def evaluate(expression: str):
        evaluations.append(expression)
        if expression == "location.origin":
            return ORIGIN
        if "querySelectorAll('.chat-msg-assistant').length" in expression:
            return 0
        if "HTMLTextAreaElement.prototype" in expression:
            return True
        if 'button[aria-label="Send message"].click' in expression:
            return None
        return {
            "reasoning": True,
            "tool": False,
            "answer": False,
            "busy": False,
            "error": False,
            "path": "/chat/00000000-0000-0000-0000-000000000001",
        }

    monkeypatch.setattr(page, "evaluate", evaluate)
    monkeypatch.setattr(page, "wait_for", lambda *_args, **_kwargs: True)

    result = page.send_turn("qualification prompt")

    composer = next(
        expression
        for expression in evaluations
        if "HTMLTextAreaElement.prototype" in expression
    )
    assert "if(!input || !send) return false" in composer
    assert "send.disabled) return false" not in composer
    assert result["reasoning"] is True


def test_browser_navigation_waits_for_the_requested_path(monkeypatch):
    page = object.__new__(ChromePage)
    navigated: list[tuple[str, dict]] = []
    waited: list[str] = []
    monkeypatch.setattr(
        page,
        "command",
        lambda method, params: navigated.append((method, params)) or {},
    )
    monkeypatch.setattr(
        page,
        "wait_for",
        lambda expression, **_kwargs: waited.append(expression) or True,
    )

    page.navigate("/chat?model=gpt-5.6-luna%40openai")

    assert navigated == [
        (
            "Page.navigate",
            {"url": f"{ORIGIN}/chat?model=gpt-5.6-luna%40openai"},
        )
    ]
    assert any('location.pathname === "/chat"' in expression for expression in waited)


def test_browser_gate_requires_visible_semantics_and_both_latency_cohorts():
    rendered = {
        "new_pool_hit_semantic": 50,
        "followup_semantic": 50,
    }
    gates = {
        "component": True,
        "model_to_application": True,
        "pool_browser": True,
        "reused_browser": True,
        "reliability": True,
        "accounting": True,
        "isolation": True,
        "hit_rate": False,
    }

    assert qualification_passes(
        rendered=rendered,
        minimum_reasoning=50,
        gates=gates,
        marked=100,
        session_count=50,
    )
    gates["reused_browser"] = False
    assert not qualification_passes(
        rendered=rendered,
        minimum_reasoning=50,
        gates=gates,
        marked=100,
        session_count=50,
    )


def test_browser_gate_excludes_pool_misses_from_new_chat_minimum():
    rendered = {
        "new_pool_hit_semantic": 49,
        "followup_semantic": 50,
    }

    assert not reasoning_minimum_reached(rendered=rendered, minimum_reasoning=50)
    rendered["new_pool_hit_semantic"] = 50
    assert reasoning_minimum_reached(rendered=rendered, minimum_reasoning=50)


def test_browser_pilot_requires_every_pair_and_visible_semantic_render():
    rendered = {
        "new_semantic": 5,
        "followup_semantic": 5,
    }

    assert pilot_passes(rendered=rendered, pairs=5, marked=10, session_count=5)
    rendered["followup_semantic"] = 4
    assert not pilot_passes(rendered=rendered, pairs=5, marked=10, session_count=5)


def test_browser_selects_an_explicit_discovered_model(monkeypatch):
    page = object.__new__(ChromePage)
    page.timeout = 1
    evaluations: list[str] = []

    def evaluate(expression: str):
        evaluations.append(expression)
        return True

    monkeypatch.setattr(page, "evaluate", evaluate)
    monkeypatch.setattr(page, "wait_for", lambda *_args, **_kwargs: True)

    page.select_model("gpt-5.6-luna@openai")

    assert any('select.value="gpt-5.6-luna@openai"' in item for item in evaluations)
    assert any(
        f'sessionStorage.setItem("{CHAT_MODEL_STORAGE_KEY}","gpt-5.6-luna@openai")'
        in item
        for item in evaluations
    )
    waited = []
    monkeypatch.setattr(
        page,
        "wait_for",
        lambda expression, **_kwargs: waited.append(expression) or True,
    )
    page.select_model("gpt-5.6-luna@openai")
    assert any(CHAT_MODEL_STORAGE_KEY in expression for expression in waited)


def test_browser_selects_reasoning_effort(monkeypatch):
    page = object.__new__(ChromePage)
    page.timeout = 1
    evaluations: list[str] = []
    waited: list[str] = []
    evaluation_results = iter((True, True))
    monkeypatch.setattr(
        page,
        "evaluate",
        lambda expression: evaluations.append(expression) or next(evaluation_results),
    )
    monkeypatch.setattr(
        page,
        "wait_for",
        lambda expression, **_kwargs: waited.append(expression) or True,
    )

    page.select_reasoning_effort("high")

    assert any('textContent==="High"' in expression for expression in evaluations)
    assert any(
        'sessionStorage.setItem("pwc:chat-reasoning-effort","high")' in expression
        for expression in evaluations
    )
    assert any('[role="listbox"]' in expression for expression in waited)
    assert any("Reasoning effort:" in expression for expression in waited)


def test_browser_accepts_the_only_discovered_model_without_a_select(monkeypatch):
    page = object.__new__(ChromePage)
    page.timeout = 1
    evaluated: list[str] = []
    waited: list[str] = []
    monkeypatch.setattr(
        page,
        "evaluate",
        lambda expression: evaluated.append(expression) or True,
    )
    monkeypatch.setattr(
        page,
        "wait_for",
        lambda expression, **_kwargs: waited.append(expression) or True,
    )

    page.select_model("deepseek-ai/DeepSeek-V4-Flash-0731", only_available=True)

    assert any('[aria-label="Research model"]' in expression for expression in waited)
    assert any(CHAT_MODEL_STORAGE_KEY in expression for expression in evaluated)
    assert not any("select.value" in expression for expression in evaluated)


def test_browser_rejects_a_release_change(monkeypatch):
    page = object.__new__(ChromePage)
    monkeypatch.setattr(page, "evaluate", lambda _expression: "other-staging")

    with pytest.raises(RuntimeError, match="Staging release changed"):
        page.assert_release("expected-staging")
