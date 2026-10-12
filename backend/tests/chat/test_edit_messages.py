from __future__ import annotations

import asyncio
import copy
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from claude_agent_sdk import fork_session_via_store
from claude_agent_sdk._internal.session_store import project_key_for_directory

from backend.config import get_settings
from backend.services import chat_stream_service
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    TurnAdmission,
)


class MemorySessionStore:
    def __init__(self):
        self.entries: dict[tuple[str, str, str], list[dict]] = {}
        self.deleted: list[dict] = []

    @staticmethod
    def _key(key: dict) -> tuple[str, str, str]:
        return (
            key["project_key"],
            str(key["session_id"]),
            key.get("subpath", ""),
        )

    async def load(self, key: dict) -> list[dict] | None:
        entries = self.entries.get(self._key(key))
        return copy.deepcopy(entries) if entries else None

    async def append(self, key: dict, entries: list[dict]) -> None:
        self.entries.setdefault(self._key(key), []).extend(copy.deepcopy(entries))

    async def delete(self, key: dict) -> None:
        prefix = (key["project_key"], str(key["session_id"]))
        for stored_key in list(self.entries):
            if stored_key[:2] == prefix and (
                "subpath" not in key or stored_key[2] == key["subpath"]
            ):
                del self.entries[stored_key]
        self.deleted.append(dict(key))


def _opaque_transcript(session_id: str) -> tuple[list[dict], str]:
    ids = [str(uuid.uuid4()) for _ in range(6)]
    entries = [
        {
            "type": "user",
            "uuid": ids[0],
            "parentUuid": None,
            "sessionId": session_id,
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {"role": "user", "content": "first prompt"},
        },
        {
            "type": "assistant",
            "uuid": ids[1],
            "parentUuid": ids[0],
            "sessionId": session_id,
            "timestamp": "2026-01-01T00:00:01Z",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "opaque reasoning",
                        "signature": "signed-thinking-payload",
                    },
                    {
                        "type": "tool_use",
                        "id": "tool-1",
                        "name": "Bash",
                        "input": {"command": "pwc task list"},
                    },
                ],
            },
        },
        {
            "type": "user",
            "uuid": ids[2],
            "parentUuid": ids[1],
            "sessionId": session_id,
            "timestamp": "2026-01-01T00:00:02Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-1",
                        "content": "opaque tool result",
                    }
                ],
            },
        },
        {
            "type": "assistant",
            "uuid": ids[3],
            "parentUuid": ids[2],
            "sessionId": session_id,
            "timestamp": "2026-01-01T00:00:03Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "first answer"}],
            },
        },
        {
            "type": "user",
            "uuid": ids[4],
            "parentUuid": ids[3],
            "sessionId": session_id,
            "timestamp": "2026-01-01T00:00:04Z",
            "message": {"role": "user", "content": "old target prompt"},
        },
        {
            "type": "assistant",
            "uuid": ids[5],
            "parentUuid": ids[4],
            "sessionId": session_id,
            "timestamp": "2026-01-01T00:00:05Z",
            "message": {"role": "assistant", "content": "obsolete suffix"},
        },
    ]
    return entries, ids[3]


def test_store_fork_preserves_opaque_interleaved_prefix():
    source_id = str(uuid.uuid4())
    directory = "/tmp/pwc-chat-edit-test"
    project_key = project_key_for_directory(directory)
    source, boundary_id = _opaque_transcript(source_id)
    store = MemorySessionStore()
    store.entries[(project_key, source_id, "")] = copy.deepcopy(source)

    result = asyncio.run(
        fork_session_via_store(
            store,
            source_id,
            directory=directory,
            up_to_message_id=boundary_id,
        )
    )

    forked = store.entries[(project_key, result.session_id, "")]
    transcript = forked[:4]
    assert [entry["type"] for entry in transcript] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert [entry["message"] for entry in transcript] == [
        entry["message"] for entry in source[:4]
    ]
    assert transcript[1]["message"]["content"][0]["signature"] == (
        "signed-thinking-payload"
    )
    assert transcript[2]["message"]["content"][0]["type"] == "tool_result"
    assert all(entry["sessionId"] == result.session_id for entry in transcript)
    assert [entry["forkedFrom"]["messageUuid"] for entry in transcript] == [
        entry["uuid"] for entry in source[:4]
    ]
    assert "old target prompt" not in repr(forked)
    assert "obsolete suffix" not in repr(forked)


@pytest.mark.parametrize(
    ("execution_backend", "directory"),
    [("local_mcp", None), ("modal_cli", "/workspace")],
)
def test_prepare_edit_forks_at_boundary_and_activates_for_each_runner(
    monkeypatch, execution_backend: str, directory: str | None
):
    settings = get_settings()
    sdk_directory = directory or settings.chat_agent_cwd
    project_key = project_key_for_directory(sdk_directory)
    source_id = uuid.uuid4()
    source, boundary = _opaque_transcript(str(source_id))
    store = MemorySessionStore()
    store.entries[(project_key, str(source_id), "")] = source
    calls: list[tuple] = []

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def commit(self):
            calls.append(("commit",))

        def rollback(self):
            calls.append(("rollback",))

    class FakeService:
        def __init__(self, *_args):
            pass

        def record_prepared_fork(
            self, _owner, _admission, fork_id, recorded_project_key
        ):
            calls.append(("record", fork_id, recorded_project_key))
            return True

        def activate_edit(
            self, _owner, _admission, replacement_id, activated_project_key
        ):
            calls.append(("activate", replacement_id, activated_project_key))
            return True

    monkeypatch.setattr(chat_stream_service.db_manager, "_session_local", FakeDB)
    monkeypatch.setattr(chat_stream_service, "ChatSessionService", FakeService)
    admission = SimpleNamespace(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        sdk_session_id=source_id,
        sdk_project_key=project_key,
        is_replacement=True,
        replacement_target_id=uuid.uuid4(),
        resume_boundary_id=uuid.UUID(boundary),
        execution_backend=execution_backend,
    )

    resume_id = asyncio.run(
        chat_stream_service._prepare_replacement(
            ChatOwner("hf-user", "tester"),
            settings,
            admission,
            store,
        )
    )

    assert resume_id is not None and resume_id != source_id
    assert ("record", resume_id, project_key) in calls
    assert ("activate", resume_id, project_key) in calls
    forked = store.entries[(project_key, str(resume_id), "")]
    assert [entry["message"] for entry in forked[:4]] == [
        entry["message"] for entry in source[:4]
    ]
    assert (project_key, str(source_id), "") not in store.entries


def test_activation_race_deletes_unbound_fork_but_keeps_source(monkeypatch):
    settings = get_settings()
    directory = settings.chat_agent_cwd
    project_key = project_key_for_directory(directory)
    source_id = uuid.uuid4()
    source, boundary = _opaque_transcript(str(source_id))
    store = MemorySessionStore()
    store.entries[(project_key, str(source_id), "")] = source

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

    class RacingService:
        def __init__(self, *_args):
            pass

        def record_prepared_fork(self, *_args):
            return True

        def activate_edit(self, *_args):
            return False

    monkeypatch.setattr(chat_stream_service.db_manager, "_session_local", FakeDB)
    monkeypatch.setattr(chat_stream_service, "ChatSessionService", RacingService)
    admission = SimpleNamespace(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        sdk_session_id=source_id,
        sdk_project_key=project_key,
        is_replacement=True,
        replacement_target_id=uuid.uuid4(),
        resume_boundary_id=uuid.UUID(boundary),
        execution_backend="local_mcp",
    )

    with pytest.raises(ChatServiceError, match="edit turn changed"):
        asyncio.run(
            chat_stream_service._prepare_replacement(
                ChatOwner("hf-user", "tester"),
                settings,
                admission,
                store,
            )
        )

    assert store.entries[(project_key, str(source_id), "")] == source
    assert list(store.entries) == [(project_key, str(source_id), "")]


def test_activation_callback_precedes_cancellable_old_transcript_cleanup(monkeypatch):
    settings = get_settings()
    project_key = project_key_for_directory(settings.chat_agent_cwd)
    source_id = uuid.uuid4()
    source, boundary = _opaque_transcript(str(source_id))

    class CancellableCleanupStore(MemorySessionStore):
        async def delete(self, key: dict) -> None:
            if str(key["session_id"]) == str(source_id):
                raise asyncio.CancelledError
            await super().delete(key)

    store = CancellableCleanupStore()
    store.entries[(project_key, str(source_id), "")] = source

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

    class FakeService:
        def __init__(self, *_args):
            pass

        def record_prepared_fork(self, *_args):
            return True

        def activate_edit(self, *_args):
            return True

    monkeypatch.setattr(chat_stream_service.db_manager, "_session_local", FakeDB)
    monkeypatch.setattr(chat_stream_service, "ChatSessionService", FakeService)
    admission = SimpleNamespace(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        sdk_session_id=source_id,
        sdk_project_key=project_key,
        is_replacement=True,
        replacement_target_id=uuid.uuid4(),
        resume_boundary_id=uuid.UUID(boundary),
        execution_backend="local_mcp",
    )
    activated = False

    def mark_activated():
        nonlocal activated
        activated = True

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            chat_stream_service._prepare_replacement(
                ChatOwner("hf-user", "tester"),
                settings,
                admission,
                store,
                mark_activated,
            )
        )

    assert activated is True


class FakeResult:
    def __init__(self, *, one=None, rows=()):
        self.one = one
        self.rows = list(rows)

    def scalar_one_or_none(self):
        return self.one

    def scalars(self):
        return iter(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None


def test_fetchable_url_seed_uses_only_active_eligible_lineage_blocks():
    session_id = uuid.uuid4()
    current_id = uuid.uuid4()
    rows = [
        SimpleNamespace(
            id=uuid.uuid4(),
            sequence=1,
            role="user",
            status="complete",
            content="Use https://USER.example/paper",
            effective_prompt=None,
            display_blocks=[],
        ),
        SimpleNamespace(
            id=uuid.uuid4(),
            sequence=2,
            role="assistant",
            status="complete",
            content="Assistant prose https://assistant.example/denied",
            effective_prompt=None,
            display_blocks=[
                {
                    "kind": "tool",
                    "name": "Bash",
                    "status": "success",
                    "content": [
                        {
                            "type": "text",
                            "text": "Project https://catalog.example/project",
                        }
                    ],
                },
                {
                    "kind": "tool",
                    "name": "WebFetch",
                    "status": "success",
                    "content": [
                        {"type": "text", "text": "https://follow.example/denied"}
                    ],
                },
                {
                    "kind": "tool",
                    "name": "search_web",
                    "status": "success",
                    "content": [
                        {"type": "text", "text": "https://search.example/denied"}
                    ],
                },
            ],
        ),
        SimpleNamespace(
            id=uuid.uuid4(),
            sequence=3,
            role="user",
            status="superseded",
            content="https://discarded.example/denied",
            effective_prompt=None,
            display_blocks=[],
        ),
        SimpleNamespace(
            id=current_id,
            sequence=4,
            role="user",
            status="preparing",
            content="https://current.example/request",
            effective_prompt=None,
            display_blocks=[],
        ),
    ]

    class SeedDB:
        def execute(self, _query):
            return FakeResult(rows=rows)

    urls = ChatSessionService(SeedDB(), get_settings()).fetchable_url_seed(
        session_id,
        current_message_id=current_id,
        replacement_target_sequence=3,
    )
    assert urls == [
        "https://catalog.example/project",
        "https://current.example/request",
        "https://user.example/paper",
    ]


def _activation_fixture():
    session_id = uuid.uuid4()
    source_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    target = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=session_id,
        role="user",
        status="complete",
        sequence=3,
        revision=1,
    )
    old_answer = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=session_id,
        role="assistant",
        status="complete",
        sequence=4,
        revision=1,
    )
    old_later = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=session_id,
        role="user",
        status="error",
        sequence=5,
        revision=1,
    )
    prepared = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=session_id,
        role="user",
        status="preparing",
        sequence=6,
        revision=2,
        error_code=None,
        prepared_fork_sdk_session_id=None,
        prepared_fork_sdk_project_key=None,
    )
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="hf-user",
        active_turn_id=turn_id,
        sdk_session_id=source_id,
        sdk_project_key="source-project",
        transcript_status="ready",
        transcript_bytes=500,
        message_count=5,
        updated_at=None,
    )
    admission = TurnAdmission(
        session_id=session_id,
        turn_id=turn_id,
        user_message_id=prepared.id,
        selected_model="zai-org/GLM-5.2",
        model_route="zai-org/GLM-5.2:together",
        sdk_session_id=source_id,
        sdk_project_key="source-project",
        is_first_turn=False,
        is_replacement=True,
        replacement_target_id=target.id,
        replacement_target_sequence=target.sequence,
        replacement_target_revision=target.revision,
        replacement_active_suffix_ids=(target.id, old_answer.id, old_later.id),
    )
    return session, target, old_answer, old_later, prepared, admission


def test_successful_activation_commits_new_lineage_and_recounts_messages():
    session, target, old_answer, old_later, prepared, admission = _activation_fixture()
    fork_id = uuid.uuid4()
    prepared.prepared_fork_sdk_session_id = fork_id
    prepared.prepared_fork_sdk_project_key = "fork-project"

    class ActivationDB:
        def __init__(self):
            self.execute_results = iter(
                [
                    FakeResult(one=session),
                    FakeResult(rows=[target, old_answer, old_later]),
                ]
            )
            self.scalar_results = iter([321, 4])
            self.flushed = False

        def execute(self, _query):
            return next(self.execute_results)

        def get(self, _model, key):
            if key == prepared.id:
                return prepared
            if key == target.id:
                return target
            return None

        def scalar(self, _query):
            return next(self.scalar_results)

        def flush(self):
            self.flushed = True

    db = ActivationDB()
    activated = ChatSessionService(db, get_settings()).activate_edit(
        ChatOwner("hf-user", "tester"),
        admission,
        fork_id,
        "fork-project",
    )

    assert activated is True
    assert [target.status, old_answer.status, old_later.status] == [
        "superseded",
        "superseded",
        "superseded",
    ]
    assert prepared.status == "generating"
    assert prepared.error_code is None
    assert prepared.prepared_fork_sdk_session_id is None
    assert prepared.prepared_fork_sdk_project_key is None
    assert session.sdk_session_id == fork_id
    assert session.sdk_project_key == "fork-project"
    assert session.transcript_bytes == 321
    assert session.message_count == 4
    assert db.flushed is True


def test_record_prepared_fork_persists_session_and_project_key():
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    source_id = uuid.uuid4()
    fork_id = uuid.uuid4()
    prepared = SimpleNamespace(
        id=uuid.uuid4(),
        status="preparing",
        prepared_fork_sdk_session_id=None,
        prepared_fork_sdk_project_key=None,
    )
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="hf-user",
        active_turn_id=turn_id,
        sdk_session_id=source_id,
    )
    admission = SimpleNamespace(
        session_id=session_id,
        turn_id=turn_id,
        user_message_id=prepared.id,
        sdk_session_id=source_id,
    )

    class RecordingDB:
        def execute(self, _query):
            return FakeResult(one=session)

        def get(self, _model, key):
            return prepared if key == prepared.id else None

    recorded = ChatSessionService(RecordingDB(), get_settings()).record_prepared_fork(
        ChatOwner("hf-user", "tester"),
        admission,
        fork_id,
        "fork-project",
    )

    assert recorded is True
    assert prepared.prepared_fork_sdk_session_id == fork_id
    assert prepared.prepared_fork_sdk_project_key == "fork-project"


def test_activation_suffix_race_leaves_old_history_and_binding_unchanged():
    session, target, old_answer, old_later, prepared, admission = _activation_fixture()
    fork_id = uuid.uuid4()
    prepared.prepared_fork_sdk_session_id = fork_id
    prepared.prepared_fork_sdk_project_key = "fork-project"

    class RacingDB:
        def __init__(self):
            self.execute_results = iter(
                [
                    FakeResult(one=session),
                    FakeResult(rows=[target, old_answer]),
                ]
            )

        def execute(self, _query):
            return next(self.execute_results)

        def get(self, _model, key):
            return (
                prepared if key == prepared.id else target if key == target.id else None
            )

    activated = ChatSessionService(RacingDB(), get_settings()).activate_edit(
        ChatOwner("hf-user", "tester"),
        admission,
        fork_id,
        "fork-project",
    )

    assert activated is False
    assert [target.status, old_answer.status, old_later.status] == [
        "complete",
        "complete",
        "error",
    ]
    assert prepared.status == "preparing"
    assert session.sdk_session_id == admission.sdk_session_id
    assert session.sdk_project_key == "source-project"


def test_begin_turn_admits_completed_middle_message_without_superseding_it():
    settings = get_settings()
    session_id = uuid.uuid4()
    source_id = uuid.uuid4()
    boundary_id = uuid.uuid4()
    target = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=session_id,
        turn_id=uuid.uuid4(),
        role="user",
        status="complete",
        sequence=3,
        revision=4,
        sdk_resume_boundary_id=boundary_id,
        content="old prompt",
    )
    suffix_ids = (target.id, uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="hf-user",
        hf_username="tester",
        selected_model="moonshotai/Kimi-K3",
        execution_backend="local_mcp",
        transcript_status="ready",
        sdk_session_id=source_id,
        sdk_project_key="project-key",
        active_turn_id=None,
        active_turn_expires_at=None,
        transcript_bytes=100,
        projection_bytes=200,
        message_count=6,
        last_sequence=6,
        title_source="generated",
        updated_at=None,
    )

    class AdmissionDB:
        def __init__(self):
            self.results = iter(
                [
                    FakeResult(one=None),
                    FakeResult(),
                    FakeResult(),
                    FakeResult(),
                    FakeResult(one=target),
                    FakeResult(rows=suffix_ids),
                    FakeResult(rows=[]),
                ]
            )
            self.scalars = iter([0, 0, 300, 2])
            self.added = []

        def execute(self, _query):
            return next(self.results)

        def scalar(self, _query):
            return next(self.scalars)

        def add(self, value):
            self.added.append(value)

        def flush(self):
            return None

    db = AdmissionDB()
    service = ChatSessionService(db, settings)
    service._owned = lambda *_args, **_kwargs: session
    admission = service.begin_turn(
        ChatOwner("hf-user", "tester"),
        session_id=session_id,
        client_message_id="edit-client-id",
        text="edited middle prompt",
        effective_prompt="<paper_context>exact bytes</paper_context>\nedited middle prompt",
        paper_mentions=[{"route_id": "2501.00001", "title": "Paper"}],
        replace_message_id=target.id,
        prior_revision=4,
    )

    prepared = db.added[-1]
    assert target.status == "complete"
    assert prepared.status == "preparing"
    assert prepared.content == "edited middle prompt"
    assert (
        prepared.effective_prompt
        == "<paper_context>exact bytes</paper_context>\nedited middle prompt"
    )
    assert prepared.paper_mentions == [{"route_id": "2501.00001", "title": "Paper"}]
    assert prepared.turn_id != target.turn_id
    assert prepared.sequence == 7
    assert prepared.revision == 5
    assert prepared.supersedes_message_id == target.id
    assert prepared.sdk_resume_boundary_id == boundary_id
    assert prepared.model == "moonshotai/Kimi-K3"
    assert admission.replacement_active_suffix_ids == suffix_ids
    assert admission.title_should_generate is False
    assert session.message_count == 6
    assert session.active_turn_id == prepared.turn_id


def test_same_client_replay_recovers_expired_preparing_edit_and_orphan_fork():
    settings = get_settings()
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    orphan_id = uuid.uuid4()
    prepared = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=session_id,
        turn_id=turn_id,
        role="user",
        status="preparing",
        error_code=None,
        prepared_fork_sdk_session_id=orphan_id,
        prepared_fork_sdk_project_key="fork-project",
    )
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="hf-user",
        sdk_project_key="source-project",
        active_turn_id=turn_id,
        active_turn_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    class ReplayDB:
        def __init__(self):
            self.results = iter(
                [
                    FakeResult(one=prepared),
                    FakeResult(one=None),
                    FakeResult(),
                    FakeResult(),
                ]
            )
            self.executed = 0
            self.statements = []

        def execute(self, query):
            self.executed += 1
            self.statements.append(query)
            return next(self.results)

    db = ReplayDB()
    service = ChatSessionService(db, settings)
    service._owned = lambda *_args, **_kwargs: session

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            ChatOwner("hf-user", "tester"),
            session_id=session_id,
            client_message_id="same-client-id",
            text="edited prompt",
        )

    assert exc_info.value.code == "turn_requires_retry"
    assert exc_info.value.commit_changes is True
    assert prepared.status == "superseded"
    assert prepared.error_code == "edit_prepare_lease_expired"
    assert prepared.prepared_fork_sdk_session_id is None
    assert prepared.prepared_fork_sdk_project_key is None
    assert session.active_turn_id is None
    assert session.active_turn_expires_at is None
    assert db.executed == 4
    cleanup_values = [
        value
        for statement in db.statements[2:]
        for value in statement.compile().params.values()
    ]
    assert "fork-project" in cleanup_values
    assert "source-project" not in cleanup_values
    assert orphan_id in cleanup_values
