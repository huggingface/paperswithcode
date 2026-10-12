from backend.chat_sandbox_worker.prompt import TEMPLATE
from backend.services.chat_agent_service import SYSTEM_PROMPT


def test_every_active_research_prompt_contains_scope_refusal_backstop() -> None:
    for prompt in (SYSTEM_PROMPT, TEMPLATE):
        assert "scope is limited" in prompt.lower()
        assert "application" in prompt.lower()
        assert "cryptocurrency" in prompt.lower()
        assert "AI and machine-learning research" in prompt
