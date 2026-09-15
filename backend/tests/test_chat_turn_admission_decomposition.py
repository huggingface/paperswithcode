from __future__ import annotations

import ast
import inspect
import textwrap
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.config import get_settings
from backend.models.database import ChatMessageRecord, ChatSession
from backend.services import chat_session_service as chat_session_module
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    _TranscriptResumeBoundary,
    _build_replacement_plan,
    _calculate_turn_quota,
    _message_projection_bytes,
)
from backend.tests.test_chat_turn_admission_characterization import (
    _Result,
    _ScriptedDB,
    _owned_service,
    _session,
)


_OWNER = ChatOwner("owner-1", "owner")
_SESSION_MUTATION_FIELDS = (
    "last_sequence",
    "message_count",
    "active_turn_id",
    "active_turn_expires_at",
    "projection_bytes",
    "web_search_enabled",
    "updated_at",
)


def _session_state(session) -> dict[str, object]:
    return {name: getattr(session, name) for name in _SESSION_MUTATION_FIELDS}


class _TransactionalScriptedDB(_ScriptedDB):
    """Small transaction fake that exposes durable state at rollback time."""

    def __init__(self, *, execute_results=(), scalar_results=(), tracked=()):
        super().__init__(
            execute_results=execute_results,
            scalar_results=scalar_results,
        )
        self.rows: list[object] = []
        self._pending: list[object] = []
        self._tracked = [(value, vars(value).copy()) for value in tracked]
        self.rows_at_rollback: list[object] = []
        self.states_at_rollback: list[dict[str, object]] = []
        self.rollback_calls = 0

    def add(self, value):
        super().add(value)
        self._pending.append(value)

    def flush(self):
        super().flush()
        for value in self._pending:
            if isinstance(value, ChatSession):
                # These database defaults are materialized by a real flush.
                value.transcript_status = value.transcript_status or "pending"
                value.transcript_bytes = value.transcript_bytes or 0
                value.projection_bytes = value.projection_bytes or 0
                value.message_count = value.message_count or 0
                value.last_sequence = value.last_sequence or 0
                if value.web_search_enabled is None:
                    value.web_search_enabled = False
            self.rows.append(value)
        self._pending.clear()

    def rollback(self):
        self.rollback_calls += 1
        self.rows_at_rollback = list(self.rows)
        self.states_at_rollback = [vars(value).copy() for value, _ in self._tracked]
        self.rows.clear()
        self._pending.clear()
        for value, snapshot in self._tracked:
            vars(value).clear()
            vars(value).update(snapshot)


def _begin_with_outer_rollback(service, db, **kwargs):
    try:
        service.begin_turn(_OWNER, **kwargs)
    except ChatServiceError as exc:
        assert exc.commit_changes is False
        db.rollback()
        return exc
    raise AssertionError("Turn admission unexpectedly succeeded")


@pytest.mark.parametrize(
    ("replacement_prefix_count", "expected_message_count"),
    [(None, 12), (4, 6)],
)
def test_calculate_turn_quota_is_a_pure_append_or_replacement_projection(
    replacement_prefix_count, expected_message_count
):
    calculation = _calculate_turn_quota(
        session_transcript_bytes=100,
        session_projection_bytes=900,
        owner_total_bytes=2_500,
        reclaimed_projection_bytes=400,
        new_projection_bytes=160,
        current_message_count=10,
        replacement_prefix_count=replacement_prefix_count,
    )

    assert calculation.new_projection_bytes == 160
    assert calculation.reclaimed_projection_bytes == 400
    assert calculation.resulting_session_bytes == 760
    assert calculation.resulting_owner_bytes == 2_260
    assert calculation.resulting_message_count == expected_message_count


def test_reader_context_is_reclaimed_with_replaced_user_projection():
    message = SimpleNamespace(
        role="user",
        content="question",
        effective_prompt="grounded prompt",
        paper_mentions=[],
        primary_paper_context={"route_id": "1706.03762"},
        viewer_context={"page": 7},
        paper_selection={"page": 4, "text": "quoted"},
    )

    assert _message_projection_bytes(message) == sum(
        len(value.encode())
        for value in (
            "question",
            "grounded prompt",
            "[]",
            '{"route_id":"1706.03762"}',
            '{"page":7}',
            '{"page":4,"text":"quoted"}',
        )
    )


def _replacement_message(**overrides):
    values = {
        "id": uuid.uuid4(),
        "sequence": 3,
        "revision": 4,
        "status": "complete",
        "sdk_resume_boundary_id": uuid.uuid4(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_build_replacement_plan_is_pure_and_preserves_the_active_suffix():
    prior = _replacement_message()
    suffix_ids = (prior.id, uuid.uuid4(), uuid.uuid4())

    plan = _build_replacement_plan(
        replacement_requested=True,
        prior=prior,
        active_suffix_ids=suffix_ids,
        sdk_session_id=uuid.uuid4(),
        sdk_project_key="project-key",
    )

    assert plan.prior is prior
    assert plan.active_suffix_ids == suffix_ids
    assert isinstance(plan.turn_id, uuid.UUID)
    assert plan.revision == 5
    assert prior.status == "complete"


def test_build_replacement_plan_allows_replacing_the_first_prompt_without_a_boundary():
    prior = _replacement_message(sequence=1, sdk_resume_boundary_id=None)
    suffix_ids = (prior.id, uuid.uuid4())

    plan = _build_replacement_plan(
        replacement_requested=True,
        prior=prior,
        active_suffix_ids=suffix_ids,
        sdk_session_id=uuid.uuid4(),
        sdk_project_key="project-key",
    )

    assert plan.prior is prior
    assert plan.active_suffix_ids == suffix_ids
    assert plan.revision == 5
    assert plan.is_first_prompt is True


def test_build_replacement_plan_allows_reediting_the_logical_first_prompt():
    prior = _replacement_message(
        sequence=3,
        revision=2,
        sdk_resume_boundary_id=None,
        agent_resume_boundary_id=None,
    )

    plan = _build_replacement_plan(
        replacement_requested=True,
        prior=prior,
        active_suffix_ids=(prior.id, uuid.uuid4()),
        sdk_session_id=uuid.uuid4(),
        sdk_project_key="project-key",
        agent_harness="pi",
        is_first_prompt=True,
    )

    assert plan.revision == 3
    assert plan.is_first_prompt is True


def test_load_replacement_plan_recognizes_an_appended_first_prompt_revision():
    prior = _replacement_message(
        sequence=3,
        revision=2,
        sdk_resume_boundary_id=None,
        agent_resume_boundary_id=None,
    )
    answer_id = uuid.uuid4()
    db = _ScriptedDB(
        execute_results=(
            _Result(one=prior),
            _Result(rows=(prior.id, answer_id)),
        )
    )
    session = SimpleNamespace(
        id=uuid.uuid4(),
        message_count=2,
        sdk_session_id=uuid.uuid4(),
        sdk_project_key="project-key",
        agent_harness="pi",
    )

    plan = ChatSessionService(db, get_settings())._load_replacement_plan(
        session,
        replace_message_id=prior.id,
        prior_revision=prior.revision,
    )

    assert plan.active_suffix_ids == (prior.id, answer_id)
    assert plan.is_first_prompt is True


def test_build_replacement_plan_still_requires_a_boundary_for_later_prompts():
    prior = _replacement_message(
        sequence=3,
        revision=2,
        sdk_resume_boundary_id=None,
        agent_resume_boundary_id=None,
    )

    with pytest.raises(ChatServiceError) as exc_info:
        _build_replacement_plan(
            replacement_requested=True,
            prior=prior,
            active_suffix_ids=(prior.id, uuid.uuid4()),
            sdk_session_id=uuid.uuid4(),
            sdk_project_key="project-key",
            agent_harness="pi",
            is_first_prompt=False,
        )

    assert exc_info.value.code == "chat_transcript_unavailable"


def test_first_prompt_replacement_regenerates_the_title_in_the_same_session():
    settings = get_settings()
    prior = _replacement_message(sequence=1, sdk_resume_boundary_id=None)
    replacement = _build_replacement_plan(
        replacement_requested=True,
        prior=prior,
        active_suffix_ids=(prior.id, uuid.uuid4()),
        sdk_session_id=uuid.uuid4(),
        sdk_project_key="project-key",
    )
    session = SimpleNamespace(
        message_count=2,
        title_source="fallback",
        execution_backend="modal_cli",
    )

    plan = ChatSessionService(SimpleNamespace(), settings)._build_turn_creation_plan(
        session,
        replacement=replacement,
        quota=_calculate_turn_quota(
            session_transcript_bytes=100,
            session_projection_bytes=100,
            owner_total_bytes=100,
            reclaimed_projection_bytes=100,
            new_projection_bytes=50,
            current_message_count=2,
            replacement_prefix_count=0,
        ),
        resume_boundary=_TranscriptResumeBoundary(id=None, agent_id=None),
        model=settings.chat_model_choices[0]["id"],
        model_route=settings.chat_model_choices[0]["route"],
        effective_prompt="edited first prompt",
        paper_mentions=[],
    )

    assert plan.is_first_turn is True
    assert plan.title_should_generate is True
    assert plan.replacement.revision == 5


def test_reedited_first_prompt_regenerates_the_title_in_the_same_session():
    settings = get_settings()
    prior = _replacement_message(
        sequence=3,
        revision=2,
        sdk_resume_boundary_id=None,
        agent_resume_boundary_id=None,
    )
    replacement = _build_replacement_plan(
        replacement_requested=True,
        prior=prior,
        active_suffix_ids=(prior.id, uuid.uuid4()),
        sdk_session_id=uuid.uuid4(),
        sdk_project_key="project-key",
        agent_harness="pi",
        is_first_prompt=True,
    )
    session = SimpleNamespace(
        message_count=2,
        title_source="fallback",
        execution_backend="modal_cli",
    )

    plan = ChatSessionService(SimpleNamespace(), settings)._build_turn_creation_plan(
        session,
        replacement=replacement,
        quota=_calculate_turn_quota(
            session_transcript_bytes=100,
            session_projection_bytes=100,
            owner_total_bytes=100,
            reclaimed_projection_bytes=100,
            new_projection_bytes=50,
            current_message_count=2,
            replacement_prefix_count=0,
        ),
        resume_boundary=_TranscriptResumeBoundary(id=None, agent_id=None),
        model=settings.chat_model_choices[0]["id"],
        model_route=settings.chat_model_choices[0]["route"],
        effective_prompt="edited first prompt again",
        paper_mentions=[],
    )

    assert plan.is_first_turn is True
    assert plan.title_should_generate is True
    assert plan.replacement.revision == 3


@pytest.mark.parametrize(
    ("prior", "suffix_ids", "sdk_session_id", "sdk_project_key", "expected_code"),
    [
        (None, (), None, None, "invalid_replacement"),
        (
            _replacement_message(sdk_resume_boundary_id=None),
            (),
            None,
            None,
            "chat_transcript_unavailable",
        ),
    ],
)
def test_build_replacement_plan_rejects_invalid_edits_without_mutation(
    prior, suffix_ids, sdk_session_id, sdk_project_key, expected_code
):
    before = None if prior is None else vars(prior).copy()

    with pytest.raises(ChatServiceError) as exc_info:
        _build_replacement_plan(
            replacement_requested=True,
            prior=prior,
            active_suffix_ids=suffix_ids,
            sdk_session_id=sdk_session_id,
            sdk_project_key=sdk_project_key,
        )

    assert exc_info.value.code == expected_code
    if prior is not None:
        assert vars(prior) == before


def _pre_persistence_case(name: str):
    settings = get_settings()
    session = _session(settings)
    kwargs: dict[str, object] = {}

    if name == "idempotency_conflict":
        existing = SimpleNamespace(web_search_enabled=True)
        db = _ScriptedDB(execute_results=(_Result(one=existing),))
        kwargs["web_search_enabled"] = False
    elif name == "turn_in_progress":
        existing = SimpleNamespace(
            turn_id=uuid.uuid4(),
            status="generating",
            web_search_enabled=False,
        )
        db = _ScriptedDB(execute_results=(_Result(one=existing), _Result(one=None)))
    elif name == "chat_transcript_degraded":
        session.transcript_status = "degraded"
        db = _ScriptedDB(execute_results=(_Result(one=None),))
    elif name == "user_capacity":
        db = _ScriptedDB(
            execute_results=(_Result(one=None), _Result(), _Result()),
            scalar_results=(settings.chat_user_max_concurrency, 0),
        )
    elif name == "global_capacity":
        db = _ScriptedDB(
            execute_results=(_Result(one=None), _Result(), _Result()),
            scalar_results=(0, settings.chat_max_concurrency),
        )
    elif name == "session_busy":
        session.active_turn_id = uuid.uuid4()
        session.active_turn_expires_at = datetime.now(UTC) + timedelta(minutes=1)
        db = _ScriptedDB(
            execute_results=(_Result(one=None), _Result(), _Result()),
            scalar_results=(0, 0),
        )
    elif name == "unresolved_turn":
        db = _ScriptedDB(
            execute_results=(
                _Result(one=None),
                _Result(),
                _Result(),
                _Result(one=SimpleNamespace(status="error")),
            ),
            scalar_results=(0, 0),
        )
    elif name == "invalid_model":
        session.selected_model = "unsupported/model"
        db = _ScriptedDB(
            execute_results=(
                _Result(one=None),
                _Result(),
                _Result(),
                _Result(),
            ),
            scalar_results=(0, 0, 0),
        )
    elif name == "invalid_replacement":
        kwargs.update(replace_message_id=uuid.uuid4(), prior_revision=7)
        db = _ScriptedDB(
            execute_results=(
                _Result(one=None),
                _Result(),
                _Result(),
                _Result(),
                _Result(one=None),
            ),
            scalar_results=(0, 0, 0),
        )
    elif name == "missing_transcript_boundary":
        prior = _replacement_message(sdk_resume_boundary_id=None)
        kwargs.update(replace_message_id=prior.id, prior_revision=prior.revision)
        db = _ScriptedDB(
            execute_results=(
                _Result(one=None),
                _Result(),
                _Result(),
                _Result(),
                _Result(one=prior),
                _Result(rows=(prior.id,)),
            ),
            scalar_results=(0, 0, 0),
        )
    elif name == "storage_quota":
        settings = settings.model_copy(
            update={"chat_session_byte_limit": 1, "chat_user_byte_limit": 1}
        )
        session = _session(settings)
        db = _ScriptedDB(
            execute_results=(
                _Result(one=None),
                _Result(),
                _Result(),
                _Result(),
            ),
            scalar_results=(0, 0, 0),
        )
    elif name == "message_quota":
        settings = settings.model_copy(update={"chat_session_message_limit": 1})
        session = _session(settings)
        db = _ScriptedDB(
            execute_results=(
                _Result(one=None),
                _Result(),
                _Result(),
                _Result(),
            ),
            scalar_results=(0, 0, 0),
        )
    else:  # pragma: no cover - test table and factory must stay in sync
        raise AssertionError(f"Unknown test case: {name}")

    return settings, session, db, kwargs


@pytest.mark.parametrize(
    ("case_name", "expected_code"),
    [
        ("idempotency_conflict", "idempotency_conflict"),
        ("turn_in_progress", "turn_in_progress"),
        ("chat_transcript_degraded", "chat_transcript_degraded"),
        ("user_capacity", "chat_capacity"),
        ("global_capacity", "chat_capacity"),
        ("session_busy", "session_busy"),
        ("unresolved_turn", "turn_requires_retry"),
        ("invalid_model", "invalid_chat_model"),
        ("invalid_replacement", "invalid_replacement"),
        ("missing_transcript_boundary", "chat_transcript_unavailable"),
        ("storage_quota", "chat_storage_quota_exceeded"),
        ("message_quota", "chat_message_quota_exceeded"),
    ],
)
def test_pre_persistence_rejections_leave_no_rows_or_session_mutations(
    case_name, expected_code
):
    settings, session, db, kwargs = _pre_persistence_case(case_name)
    before = _session_state(session)
    service = _owned_service(db, settings, session)

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            _OWNER,
            session_id=session.id,
            client_message_id=f"{case_name}-request",
            text="A prompt that must not be persisted",
            **kwargs,
        )

    assert exc_info.value.code == expected_code
    assert _session_state(session) == before
    assert db.added == []
    assert db.flush_calls == 0


def test_new_chat_capacity_rejection_precedes_session_or_message_creation(
    monkeypatch,
):
    settings = get_settings().model_copy(update={"chat_max_concurrency": 2})
    db = _ScriptedDB(
        execute_results=(_Result(), _Result()),
        scalar_results=(0, 2),
    )
    service = ChatSessionService(db, settings)
    created = []
    monkeypatch.setattr(
        service,
        "create_session",
        lambda *_args, **_kwargs: created.append(True),
    )

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            _OWNER,
            session_id=None,
            client_message_id="capacity-request",
            text="This prompt must not create a chat",
        )

    assert exc_info.value.code == "chat_capacity"
    assert created == []
    assert db.added == []
    assert db.flush_calls == 0


@pytest.mark.parametrize(
    ("settings_update", "expected_code"),
    [
        (
            {"chat_session_byte_limit": 1, "chat_user_byte_limit": 1},
            "chat_storage_quota_exceeded",
        ),
        ({"chat_session_message_limit": 1}, "chat_message_quota_exceeded"),
    ],
)
def test_new_session_flushed_before_quota_rejection_is_removed_by_outer_rollback(
    settings_update, expected_code
):
    settings = get_settings().model_copy(update=settings_update)
    db = _TransactionalScriptedDB(
        execute_results=(_Result(), _Result(), _Result(), _Result()),
        scalar_results=(0, 0, 0, 0),
    )
    service = ChatSessionService(db, settings)

    error = _begin_with_outer_rollback(
        service,
        db,
        session_id=None,
        client_message_id=f"new-session-{expected_code}",
        text="A new-session prompt rejected after session creation",
    )

    assert error.code == expected_code
    assert db.rollback_calls == 1
    assert db.flush_calls == 1
    assert len(db.rows_at_rollback) == 1
    assert isinstance(db.rows_at_rollback[0], ChatSession)
    assert not any(isinstance(row, ChatMessageRecord) for row in db.rows_at_rollback)
    assert db.rows == []


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        ("model", "invalid_chat_model"),
        ("replacement", "invalid_replacement"),
        ("quota", "chat_storage_quota_exceeded"),
    ],
)
def test_expired_lease_mutation_is_restored_when_later_admission_fails(
    failure, expected_code
):
    settings = get_settings()
    if failure == "quota":
        settings = settings.model_copy(
            update={"chat_session_byte_limit": 1, "chat_user_byte_limit": 1}
        )
    turn_id = uuid.uuid4()
    session = _session(
        settings,
        active_turn_id=turn_id,
        active_turn_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        selected_model=(
            "unsupported/model"
            if failure == "model"
            else settings.chat_model_choices[0]["id"]
        ),
    )
    stale = SimpleNamespace(
        id=uuid.uuid4(),
        turn_id=turn_id,
        status="generating",
        error_code=None,
        sequence=1,
        revision=1,
        sdk_resume_boundary_id=None,
    )
    replacement_id = uuid.uuid4() if failure == "replacement" else stale.id
    execute_results = [
        _Result(one=None),
        _Result(),
        _Result(),
        _Result(one=stale),
        _Result(rows=(stale.id,)),
    ]
    if failure == "replacement":
        execute_results.append(_Result(one=None))
    elif failure == "quota":
        execute_results.extend([_Result(one=stale), _Result(rows=(stale.id,))])
    db = _TransactionalScriptedDB(
        execute_results=execute_results,
        scalar_results=(0, 0, 0),
        tracked=(session, stale),
    )
    service = _owned_service(db, settings, session)
    session_before = vars(session).copy()
    stale_before = vars(stale).copy()

    error = _begin_with_outer_rollback(
        service,
        db,
        session_id=session.id,
        client_message_id=f"expired-lease-{failure}",
        text="A replacement rejected after stale-lease recovery",
        replace_message_id=replacement_id,
        prior_revision=1,
    )

    assert error.code == expected_code
    assert db.rollback_calls == 1
    session_at_rollback, stale_at_rollback = db.states_at_rollback
    assert session_at_rollback["active_turn_id"] is None
    assert session_at_rollback["active_turn_expires_at"] is None
    assert stale_at_rollback["status"] == "interrupted"
    assert stale_at_rollback["error_code"] == "lease_expired"
    assert vars(session) == session_before
    assert vars(stale) == stale_before
    assert db.rows == []


def test_owned_session_lock_precedes_user_and_global_admission_locks():
    settings = get_settings().model_copy(update={"chat_max_concurrency": 1})
    session = _session(settings)
    db = _ScriptedDB(
        execute_results=(_Result(one=None), _Result(), _Result()),
        scalar_results=(0, 1),
    )
    service = ChatSessionService(db, settings)

    def owned(*_args, **kwargs):
        db.events.append(("owned", kwargs.get("lock")))
        return session

    service._owned = owned

    with pytest.raises(ChatServiceError):
        service.begin_turn(
            _OWNER,
            session_id=session.id,
            client_message_id="ordered-lock-request",
            text="lock ordering",
        )

    owned_index = db.events.index(("owned", True))
    advisory_locks = [
        (index, _compiled_values(payload))
        for index, (event, payload) in enumerate(db.events)
        if event == "execute"
        and (
            "chat-user:owner-1" in _compiled_values(payload)
            or "chat-global-active-turns" in _compiled_values(payload)
        )
    ]
    user_index = next(
        index for index, values in advisory_locks if "chat-user:owner-1" in values
    )
    global_index = next(
        index
        for index, values in advisory_locks
        if "chat-global-active-turns" in values
    )

    assert owned_index < user_index < global_index


def _compiled_values(query) -> set[object]:
    return set(query.compile().params.values())


def test_completed_replay_is_repeatable_without_adding_rows():
    settings = get_settings()
    session = _session(settings)
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        status="complete",
        model=session.selected_model,
        model_route=settings.chat_model_routes[session.selected_model],
        sequence=1,
        revision=2,
        web_search_enabled=False,
    )
    assistant = SimpleNamespace(content="Persisted answer", followups=["Next?"])
    db = _ScriptedDB(
        execute_results=(
            _Result(one=existing),
            _Result(one=assistant),
            _Result(one=existing),
            _Result(one=assistant),
        )
    )
    service = _owned_service(db, settings, session)
    before = _session_state(session)

    first = service.begin_turn(
        _OWNER,
        session_id=session.id,
        client_message_id="stable-replay-id",
        text="ignored retry body",
    )
    second = service.begin_turn(
        _OWNER,
        session_id=session.id,
        client_message_id="stable-replay-id",
        text="another ignored retry body",
    )

    assert second == first
    assert first.replay_assistant is not None
    assert _session_state(session) == before
    assert db.added == []
    assert db.flush_calls == 0


def test_every_turn_admission_is_constructed_with_keywords():
    source = inspect.getsource(chat_session_module)
    tree = ast.parse(textwrap.dedent(source))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "TurnAdmission"
    ]

    assert calls
    assert all(call.args == [] for call in calls)
    assert all(
        {"session_id", "turn_id", "user_message_id"}
        <= {keyword.arg for keyword in call.keywords}
        for call in calls
    )
