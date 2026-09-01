import asyncio
import json

import httpx
import pytest

from backend.config import Settings
from backend.services.chat_scope_guardrail_service import (
    BoundedRawEventQueue,
    ScopeDecision,
    ScopeGuardrailService,
    ScopeMessage,
    build_scope_context,
    validate_scope_payload,
)
from backend.services.runtime_validation import (
    validate_chat_scope_guardrail_configuration,
)
from backend.chat_sandbox_worker.contract import POSTERLY_ENABLED


def _settings(**overrides) -> Settings:
    values = {
        "chat_scope_guardrail_enabled": True,
        "chat_scope_guardrail_hf_token": "hf_server_guardrail",
        "chat_scope_guardrail_hf_bill_to": "pwc-research",
        "chat_scope_guardrail_openai_api_key": "sk-server-guardrail",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_context_uses_only_visible_roles_and_truncates_oldest_first() -> None:
    prior = [
        ScopeMessage(role="user", content="old-" + "x" * 40),
        ScopeMessage(role="assistant", content="middle answer"),
        ScopeMessage(role="user", content="new research question"),
    ]

    context = build_scope_context(
        prior,
        "How does that compare with DPO?",
        max_prior_messages=2,
        max_chars=180,
        selected_paper={"title": "Direct Preference Optimization", "route_id": "dpo"},
    )

    assert [message.role for message in context] == ["assistant", "user", "user"]
    assert "old-" not in "".join(message.content for message in context)
    assert context[-1].content == "How does that compare with DPO?"
    assert context[-1].metadata == {
        "selected_paper_title": "Direct Preference Optimization",
        "selected_paper_route_id": "dpo",
    }
    assert sum(len(message.content) for message in context) <= 180


def test_context_never_truncates_current_request_to_fit_paper_metadata() -> None:
    current = "BLOCK THIS PREFIX: build a GUI. " + "x" * 7967

    context = build_scope_context(
        [ScopeMessage(role="assistant", content="prior research discussion")],
        current,
        max_chars=8_000,
        selected_paper={"title": "A selected paper", "route_id": "paper"},
    )

    assert context[-1] == ScopeMessage(role="user", content=current)
    assert context[-1].metadata == {}


def test_saturated_allowance_fails_open_within_total_gate(monkeypatch) -> None:
    from backend.services import chat_scope_guardrail_service

    class SaturatedAllowance:
        async def enter(self) -> None:
            await asyncio.Event().wait()

        async def exit(self, _cost) -> None:
            raise AssertionError("unacquired allowance must not be released")

    monkeypatch.setattr(
        chat_scope_guardrail_service,
        "_allowance",
        lambda _settings: SaturatedAllowance(),
    )
    service = ScopeGuardrailService(
        _settings(chat_scope_guardrail_attempt_timeout_seconds=0.1)
    )

    decision = asyncio.run(
        service.classify([ScopeMessage(role="user", content="Hello")])
    )

    assert decision.decision == "allow"
    assert decision.fail_open is True
    assert decision.attempt_records[0].outcome == "total_timeout"


@pytest.mark.parametrize(
    ("payload", "decision"),
    [
        ({"reason": "AI benchmark question", "decision": "allow"}, "allow"),
        ({"reason": "unrelated GUI build", "decision": "block"}, "block"),
    ],
)
def test_schema_accepts_reason_then_decision(payload: dict, decision: str) -> None:
    validated = validate_scope_payload(payload)
    assert list(json.loads(validated.model_dump_json()).keys()) == [
        "reason",
        "decision",
    ]
    assert validated.decision == decision


@pytest.mark.parametrize(
    "payload",
    [
        {"decision": "allow", "reason": "wrong order"},
        {"reason": "unknown", "decision": "maybe"},
        {"reason": "extra", "decision": "allow", "debug": True},
        {"reason": "", "decision": "block"},
    ],
)
def test_schema_rejects_invalid_or_reordered_payload(payload: dict) -> None:
    with pytest.raises(ValueError):
        validate_scope_payload(payload)


def test_runtime_requires_server_credentials_and_disables_only_posterly() -> None:
    assert POSTERLY_ENABLED is False
    validate_chat_scope_guardrail_configuration(
        _settings(
            chat_posterly_enabled=False,
            chat_excalidraw_enabled=True,
            chat_mcp_apps_host_enabled=True,
        )
    )
    for update in (
        {"chat_scope_guardrail_hf_token": ""},
        {"chat_scope_guardrail_hf_bill_to": ""},
        {"chat_scope_guardrail_openai_api_key": ""},
        {"chat_posterly_enabled": True},
        {"hf_token": "hf_server_guardrail"},
    ):
        with pytest.raises(RuntimeError):
            validate_chat_scope_guardrail_configuration(_settings(**update))


def test_staging_scope_policy_preserves_non_posterly_artifact_foundation() -> None:
    settings = _settings(
        environment="staging",
        chat_posterly_enabled=False,
        chat_artifacts_enabled=False,
        chat_artifact_shared_preview_enabled=False,
        chat_artifact_storage_backend="hf_bucket",
        chat_artifact_hf_bucket_id="org/staging-artifacts",
    )

    assert settings.chat_artifacts_enabled is True
    assert settings.chat_artifact_shared_preview_enabled is True
    assert settings.chat_posterly_enabled is False
    validate_chat_scope_guardrail_configuration(settings)

    with pytest.raises(RuntimeError, match="preserve staging research artifacts"):
        validate_chat_scope_guardrail_configuration(
            settings.model_copy(update={"chat_artifact_hf_bucket_id": ""})
        )


def test_staging_scope_policy_preserves_private_paper_preview_boundaries() -> None:
    qualification = _settings(
        environment="staging",
        chat_latex_compiler_qualification_mode=True,
        chat_artifacts_enabled=True,
        chat_artifact_shared_preview_enabled=True,
        chat_posterly_enabled=False,
        chat_artifact_storage_backend="hf_bucket",
        chat_artifact_hf_bucket_id="org/staging-artifacts",
    )
    assert qualification.chat_artifacts_enabled is False
    assert qualification.chat_artifact_shared_preview_enabled is False
    validate_chat_scope_guardrail_configuration(qualification)

    activation = _settings(
        environment="staging",
        chat_latex_paper_enabled=True,
        chat_latex_compiler_jobs_enabled=True,
        chat_artifacts_enabled=True,
        chat_artifact_shared_preview_enabled=False,
        chat_posterly_enabled=False,
        chat_artifact_storage_backend="hf_bucket",
        chat_artifact_hf_bucket_id="org/staging-artifacts",
    )
    assert activation.chat_artifacts_enabled is True
    assert activation.chat_artifact_shared_preview_enabled is False
    validate_chat_scope_guardrail_configuration(activation)


def test_valid_glm_decision_is_not_second_guessed_by_luna() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert request.headers["X-HF-Bill-To"] == "pwc-research"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"reason":"AI paper","decision":"allow"}'}}
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8},
            },
        )

    async def scenario() -> ScopeDecision:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await ScopeGuardrailService(_settings(), client=client).classify(
                [ScopeMessage(role="user", content="Explain DPO")]
            )

    result = asyncio.run(scenario())

    assert result == ScopeDecision(
        reason="AI paper",
        decision="allow",
        provider="huggingface-baseten",
        attempts=1,
        fail_open=False,
        usage_input_tokens=20,
        usage_output_tokens=8,
    )
    assert len(calls) == 1


def test_glm_block_is_overruled_by_luna_allow() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "router.huggingface.co":
            content = '{"reason":"finance domain","decision":"block"}'
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": content}}],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 8},
                },
            )
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"reason":"ML research request",'
                                    '"decision":"allow"}'
                                ),
                            }
                        ],
                    }
                ],
                "usage": {"input_tokens": 22, "output_tokens": 7},
            },
        )

    async def scenario() -> ScopeDecision:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await ScopeGuardrailService(_settings(), client=client).classify(
                [
                    ScopeMessage(
                        role="user", content="State-of-the-art volatility models"
                    )
                ]
            )

    result = asyncio.run(scenario())

    assert result.decision == "allow"
    assert result.provider == "openai"
    assert result.attempts == 2
    assert calls == ["router.huggingface.co", "api.openai.com"]
    assert [attempt.decision for attempt in result.attempt_records] == [
        "block",
        "allow",
    ]


def test_glm_and_luna_must_both_block() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "router.huggingface.co":
            content = '{"reason":"application build","decision":"block"}'
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": content}}]},
            )
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"reason":"application build","decision":"block"}'
                                ),
                            }
                        ],
                    }
                ]
            },
        )

    async def scenario() -> ScopeDecision:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await ScopeGuardrailService(_settings(), client=client).classify(
                [ScopeMessage(role="user", content="Build a restaurant booking app")]
            )

    result = asyncio.run(scenario())

    assert result.decision == "block"
    assert result.attempts == 2
    assert calls == ["router.huggingface.co", "api.openai.com"]


def test_unconfirmed_glm_block_fails_open() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "router.huggingface.co":
            content = '{"reason":"ambiguous","decision":"block"}'
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": content}}]},
            )
        return httpx.Response(503, json={"error": "unavailable"})

    async def scenario() -> ScopeDecision:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await ScopeGuardrailService(_settings(), client=client).classify(
                [ScopeMessage(role="user", content="Self-improving agent")]
            )

    result = asyncio.run(scenario())

    assert result.decision == "allow"
    assert result.provider == "fail-open"
    assert result.attempts == 2
    assert result.fail_open is True


def test_invalid_glm_schema_cannot_become_a_confirmed_block() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "router.huggingface.co":
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": '{"decision":"allow","reason":"bad order"}'
                            }
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"reason":"crypto miner","decision":"block"}',
                            }
                        ],
                    }
                ],
                "usage": {"input_tokens": 11, "output_tokens": 5},
            },
        )

    async def scenario() -> ScopeDecision:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await ScopeGuardrailService(_settings(), client=client).classify(
                [ScopeMessage(role="user", content="Build a crypto miner GUI")]
            )

    result = asyncio.run(scenario())

    assert result.decision == "allow"
    assert result.provider == "fail-open"
    assert result.attempts == 2
    assert result.fail_open is True
    assert calls == ["router.huggingface.co", "api.openai.com"]


def test_glm_timeout_cannot_become_a_confirmed_block(monkeypatch) -> None:
    service = ScopeGuardrailService(_settings())

    async def timeout(_messages: list[ScopeMessage]) -> ScopeDecision:
        raise TimeoutError

    async def luna_block(_messages: list[ScopeMessage]) -> ScopeDecision:
        return ScopeDecision("application build", "block", "openai", 2, False)

    monkeypatch.setattr(service, "_glm", timeout)
    monkeypatch.setattr(service, "_luna", luna_block)

    result = asyncio.run(
        service.classify([ScopeMessage(role="user", content="Build a booking app")])
    )

    assert result.decision == "allow"
    assert result.provider == "fail-open"
    assert result.fail_open is True


def test_double_provider_failure_fails_open_after_two_attempts() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    async def scenario() -> ScopeDecision:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await ScopeGuardrailService(_settings(), client=client).classify(
                [ScopeMessage(role="user", content="Explain transformers")]
            )

    result = asyncio.run(scenario())

    assert result.decision == "allow"
    assert result.provider == "fail-open"
    assert result.attempts == 2
    assert result.fail_open is True


def test_both_attempts_obey_independent_timeouts() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    async def scenario() -> ScopeDecision:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await ScopeGuardrailService(
                _settings(chat_scope_guardrail_attempt_timeout_seconds=0.1),
                client=client,
            ).classify([ScopeMessage(role="user", content="Explain DPO")])

    result = asyncio.run(scenario())
    assert result.fail_open is True
    assert [attempt.outcome for attempt in result.attempt_records] == [
        "TimeoutError",
        "TimeoutError",
    ]


def test_raw_event_queue_applies_byte_and_event_backpressure() -> None:
    async def scenario() -> None:
        queue = BoundedRawEventQueue(max_events=2, max_bytes=140)
        await queue.put({"type": "answer_delta", "text": "a" * 20})
        await queue.put({"type": "answer_delta", "text": "b" * 20})
        blocked = asyncio.create_task(
            queue.put({"type": "answer_delta", "text": "c" * 20})
        )
        await asyncio.sleep(0)
        assert not blocked.done()

        assert (await queue.get())["text"] == "a" * 20
        await asyncio.wait_for(blocked, timeout=0.1)
        assert queue.event_count == 2
        assert queue.byte_count <= 140

    asyncio.run(scenario())


def test_discarded_queue_ignores_late_producer_events() -> None:
    async def scenario() -> None:
        queue = BoundedRawEventQueue(max_events=2, max_bytes=200)
        await queue.put({"type": "answer_delta", "text": "private"})
        events, size = await queue.discard()
        assert events == 1
        assert size > 0
        assert queue.closed is True
        await queue.put({"type": "answer_delta", "text": "late private"})
        assert queue.event_count == 0
        assert queue.byte_count == 0

    asyncio.run(scenario())
