from backend.chat_sandbox_worker.prompt import SCOPE_SYSTEM_PROMPT, TEMPLATE
from backend.services.chat_agent_service import SYSTEM_PROMPT


def test_every_active_research_prompt_contains_scope_refusal_backstop() -> None:
    assert SCOPE_SYSTEM_PROMPT.strip() in SYSTEM_PROMPT
    assert "{scope_system_prompt}" in TEMPLATE
    scope = SCOPE_SYSTEM_PROMPT.lower()
    assert "refuse only when" in scope
    assert "application" in scope
    assert "cryptocurrency mining" in scope
    assert "AI and machine-learning research" in SCOPE_SYSTEM_PROMPT


def test_scope_prompt_allows_domain_research_and_redirects_refusals() -> None:
    scope = " ".join(SCOPE_SYSTEM_PROMPT.split())
    assert "Research intent takes precedence over subject matter" in scope
    assert "A domain keyword alone is never a reason to refuse." in scope
    assert "in the user's language" in scope
    assert "closest in-scope question" in scope
    assert "Use exactly this refusal" not in scope
