from __future__ import annotations

import asyncio
from io import BytesIO
from zipfile import ZipFile

import pytest


def test_qualification_report_is_content_free_and_marks_unexercised_gates() -> None:
    from backend.scripts.qualify_latex_paper_staging import Check, report

    private_prompt = "private manuscript text must not leave the runner"
    payload = report(
        [
            Check(name="first_compile", passed=True, elapsed_ms=12),
            Check(
                name="repair_three_attempt_bound",
                passed=False,
                elapsed_ms=0,
                executed=False,
            ),
        ]
    )

    assert payload == {
        "checks": [
            {
                "name": "first_compile",
                "passed": True,
                "executed": True,
                "elapsed_ms": 12,
            },
            {
                "name": "repair_three_attempt_bound",
                "passed": False,
                "executed": False,
                "elapsed_ms": 0,
            },
        ],
        "passed": False,
    }
    assert private_prompt not in str(payload)


def test_validate_settings_fails_closed_for_the_wrong_staging_flag_state() -> None:
    from backend.config import Settings
    from backend.scripts.qualify_latex_paper_staging import validate_settings

    disabled = Settings(environment="staging")
    validate_settings(disabled, expect_enabled=False)

    with pytest.raises(ValueError, match="paper feature flags"):
        validate_settings(disabled, expect_enabled=True)

    enabled = disabled.model_copy(
        update={
            "chat_artifacts_enabled": True,
            "chat_latex_paper_enabled": True,
            "chat_latex_compiler_jobs_enabled": True,
        }
    )
    validate_settings(enabled, expect_enabled=True)

    with pytest.raises(ValueError, match="must be off"):
        validate_settings(enabled, expect_enabled=False)

    for drifted_flag in (
        "chat_posterly_enabled",
        "chat_artifact_shared_preview_enabled",
    ):
        drifted = enabled.model_copy(update={drifted_flag: True})
        with pytest.raises(ValueError, match="private paper qualification"):
            validate_settings(drifted, expect_enabled=True)


def test_qualification_owner_must_use_the_protected_pi_prefix() -> None:
    from backend.scripts.qualify_latex_paper_staging import validate_qualification_owner

    validate_qualification_owner("operator:pi-qualification:paper-test")
    with pytest.raises(ValueError, match="protected Pi"):
        validate_qualification_owner("operator:admin")
    with pytest.raises(ValueError, match="protected Pi"):
        validate_qualification_owner("operator:pi-qualification:" + "x" * 129)


def test_explicit_luna_selection_never_accepts_an_undiscovered_or_non_luna_model() -> (
    None
):
    from backend.scripts.qualify_latex_paper_staging import validate_selected_model

    discovered = {
        "items": [
            {"id": "gpt-5.6-luna@openai"},
            {"id": "other-model"},
        ],
        "default_model": "gpt-5.6-luna@openai",
    }

    validate_selected_model(discovered, "gpt-5.6-luna@openai")
    with pytest.raises(ValueError, match="explicit Luna"):
        validate_selected_model(discovered, "other-model")
    with pytest.raises(ValueError, match="discovered"):
        validate_selected_model(discovered, "gpt-5.7-luna@openai")
    discovered["default_model"] = "other-model"
    with pytest.raises(ValueError, match="default Luna"):
        validate_selected_model(discovered, "gpt-5.6-luna@openai")


def test_terminal_turn_summary_discards_answer_and_manuscript_payloads() -> None:
    from backend.scripts.qualify_latex_paper_staging import summarize_event

    summary = summarize_event(
        {
            "type": "paper_artifact",
            "operation": "draft",
            "activated": True,
            "descriptor": {
                "artifact_id": "00000000-0000-0000-0000-000000000001",
                "title": "private manuscript title",
                "source_head": {"version_id": "version-id"},
            },
            "answer": "private manuscript answer",
        }
    )

    assert summary == {
        "kind": "paper_artifact",
        "paper_artifact": True,
        "paper_operation": "draft",
        "paper_activated": True,
        "artifact_id": "00000000-0000-0000-0000-000000000001",
    }
    assert "private manuscript" not in str(summary)


def test_telemetry_canary_is_safe_for_private_authoring_and_never_in_report() -> None:
    from backend.scripts.qualify_latex_paper_staging import (
        Check,
        edited_project_files,
        private_authoring_prompt,
        report,
        validate_telemetry_canary,
    )

    canary = "pwc-canary-8d9af6a8-1e5b-47b1"
    validate_telemetry_canary(canary)
    prompt = private_authoring_prompt("/write-paper Draft a private paper.", canary)
    files = edited_project_files(
        [{"path": "paper.tex", "content": "\\documentclass{article}"}],
        root_document="paper.tex",
        telemetry_canary=canary,
    )

    assert canary in prompt
    assert files is not None
    assert canary in files[0]["content"]
    assert canary not in str(report([Check("activation", True, 1)]))
    with pytest.raises(ValueError, match="opaque"):
        validate_telemetry_canary("contains a newline\n")


def test_owner_source_zip_canary_check_is_bounded_and_content_free() -> None:
    from backend.scripts.qualify_latex_paper_staging import owner_source_zip_contains

    canary = "pwc-canary-8d9af6a8-1e5b-47b1"
    archive = BytesIO()
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("paper.tex", f"% {canary}\n")

    class Response:
        status_code = 200
        headers = {"content-type": "application/zip"}
        content = archive.getvalue()

    class Client:
        async def get(self, path):
            assert path.endswith("/export/source.zip")
            return Response()

    assert asyncio.run(
        owner_source_zip_contains(
            Client(),
            artifact_id="artifact",
            version_id="version",
            canary=canary,
        )
    )


def test_static_unexercised_gates_keep_the_overall_run_failed() -> None:
    from backend.scripts.qualify_latex_paper_staging import overall_passed

    assert overall_passed([CheckLike("activation", True, True)])
    assert not overall_passed(
        [
            CheckLike("activation", True, True),
            CheckLike("archive_after_30_days", False, False),
        ]
    )
    assert not overall_passed([])


class CheckLike:
    def __init__(self, name: str, passed: bool, executed: bool) -> None:
        self.name = name
        self.passed = passed
        self.executed = executed


def test_unexercised_acceptance_gates_are_explicit_and_never_count_as_passed() -> None:
    from backend.scripts.qualify_latex_paper_staging import unexercised_gates

    checks = unexercised_gates(expect_enabled=True)

    assert {check.name for check in checks} == {
        "telemetry_content_free",
        "kill_switch_rollback",
    }
    assert all(not check.executed and not check.passed for check in checks)


def test_disabled_mode_only_marks_kill_switch_passed_after_a_real_observation() -> None:
    from backend.scripts.qualify_latex_paper_staging import (
        overall_passed,
        unexercised_gates,
    )

    unrun = {check.name: check for check in unexercised_gates(expect_enabled=False)}
    passed = {
        check.name: check
        for check in unexercised_gates(
            expect_enabled=False,
            kill_switch_passed=True,
        )
    }
    failed = {
        check.name: check
        for check in unexercised_gates(
            expect_enabled=False,
            kill_switch_passed=False,
        )
    }

    assert unrun["kill_switch_rollback"].executed is False
    assert unrun["kill_switch_rollback"].passed is False
    assert passed["kill_switch_rollback"].executed is True
    assert passed["kill_switch_rollback"].passed is True
    assert failed["kill_switch_rollback"].executed is True
    assert failed["kill_switch_rollback"].passed is False
    assert passed["telemetry_content_free"].executed is False
    assert not overall_passed(passed.values())


def test_stream_observation_drops_answer_deltas_before_returning() -> None:
    from backend.scripts.qualify_latex_paper_staging import stream_turn

    class Response:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def aiter_lines(self):
            for item in (
                'data: {"type":"answer_delta","text":"private manuscript"}',
                'data: {"type":"paper_artifact","operation":"create","activated":true,"descriptor":{"artifact_id":"00000000-0000-0000-0000-000000000001","title":"private title"}}',
                'data: {"type":"paper_artifact","operation":"draft","activated":false,"descriptor":{"artifact_id":"00000000-0000-0000-0000-000000000001","title":"private title"}}',
                'data: {"type":"done","finish_reason":"success","citations":[{"kind":"catalog_paper"}]}',
            ):
                yield item

    class Client:
        def stream(self, *_args, **_kwargs):
            return Response()

    observation = asyncio.run(
        stream_turn(Client(), session_id="session", prompt="private manuscript")
    )

    assert observation.successful is True
    assert observation.paper_activated is True
    assert observation.paper_operation == "draft"
    assert observation.paper_operations == ("create", "draft")
    assert observation.citations_structural is True
    assert "private manuscript" not in str(observation)


def test_stream_requires_a_success_terminal_reason() -> None:
    from backend.scripts.qualify_latex_paper_staging import stream_turn

    class Response:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def aiter_lines(self):
            yield 'data: {"type":"done","finish_reason":"tool_limit","citations":[]}'

    class Client:
        def stream(self, *_args, **_kwargs):
            return Response()

    observation = asyncio.run(
        stream_turn(Client(), session_id="session", prompt="test")
    )

    assert observation.terminal is True
    assert observation.successful is False


def test_parser_requires_an_explicit_confirmation_and_luna_selection() -> None:
    from backend.scripts.qualify_latex_paper_staging import parser

    args = parser().parse_args(
        [
            "--admin-subject",
            "admin",
            "--admin-username",
            "operator",
            "--qualification-owner",
            "operator:pi-qualification:paper-test",
            "--confirm",
            "QUALIFY_STAGING_LATEX_PAPER",
        ]
    )

    assert args.model == "gpt-5.6-luna@openai"
    assert args.expect == "enabled"
    assert args.preserve_for_kill_switch is False
    assert args.verify_historical is False
    assert args.telemetry_canary is None


def test_parser_supports_the_two_explicit_kill_switch_phases() -> None:
    from backend.scripts.qualify_latex_paper_staging import parser

    common = [
        "--admin-subject",
        "admin",
        "--admin-username",
        "operator",
        "--qualification-owner",
        "operator:pi-qualification:paper-test",
        "--confirm",
        "QUALIFY_STAGING_LATEX_PAPER",
    ]

    canary = "pwc-canary-8d9af6a8-1e5b-47b1"
    preserved = parser().parse_args(
        [*common, "--preserve-for-kill-switch", "--telemetry-canary", canary]
    )
    historical = parser().parse_args(
        [*common, "--expect", "disabled", "--verify-historical"]
    )

    assert preserved.preserve_for_kill_switch is True
    assert preserved.telemetry_canary == canary
    assert historical.verify_historical is True


def test_kill_switch_phase_flags_are_mutually_safe() -> None:
    from backend.scripts.qualify_latex_paper_staging import validate_phase

    validate_phase(
        expect_enabled=True,
        preserve_for_kill_switch=True,
        verify_historical=False,
    )
    validate_phase(
        expect_enabled=False,
        preserve_for_kill_switch=False,
        verify_historical=True,
    )
    with pytest.raises(ValueError, match="enabled"):
        validate_phase(
            expect_enabled=False,
            preserve_for_kill_switch=True,
            verify_historical=False,
        )
    with pytest.raises(ValueError, match="disabled"):
        validate_phase(
            expect_enabled=True,
            preserve_for_kill_switch=False,
            verify_historical=True,
        )
    with pytest.raises(ValueError, match="mutually exclusive"):
        validate_phase(
            expect_enabled=True,
            preserve_for_kill_switch=True,
            verify_historical=True,
        )


def test_failed_compile_fixture_preserves_the_discovered_root_document_name() -> None:
    from backend.scripts.qualify_latex_paper_staging import malformed_project

    files = malformed_project("paper.tex")

    assert files[0]["path"] == "paper.tex"
    assert "undefinedcontrolsequence" in files[0]["content"]


def test_disabled_qualification_deletes_its_operator_session_in_finally(
    monkeypatch,
) -> None:
    from backend.config import Settings
    from backend.scripts import qualify_latex_paper_staging as qualification

    class Response:
        def __init__(self, status_code: int, payload=None) -> None:
            self.status_code = status_code
            self._payload = payload
            self.headers = {}

        def json(self):
            return self._payload

    class StreamResponse(Response):
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def aiter_lines(self):
            yield 'data: {"type":"done","finish_reason":"success","citations":[]}'

    class Client:
        deleted: list[str] = []

        async def get(self, path):
            if path == "/health":
                return Response(200)
            if path == "/api/v1/chat/models":
                return Response(
                    200,
                    {
                        "items": [{"id": "gpt-5.6-luna@openai"}],
                        "default_model": "gpt-5.6-luna@openai",
                    },
                )
            if path.endswith("/session-1"):
                return Response(404)
            raise AssertionError(path)

        async def post(self, path, **_kwargs):
            assert path == "/api/v1/chat/admin/sessions"
            return Response(
                201, {"id": "session-1", "selected_model": "gpt-5.6-luna@openai"}
            )

        async def delete(self, path):
            self.deleted.append(path)
            return Response(204)

        def stream(self, *_args, **_kwargs):
            return StreamResponse(200)

    class Context:
        client = Client()

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(qualification, "staging_client", lambda **_kwargs: Context())
    monkeypatch.setattr(qualification, "_encode_legacy_session", lambda _user: "token")

    checks = asyncio.run(
        qualification.run_qualification(
            Settings(environment="staging"),
            admin_subject="admin",
            admin_username="operator",
            qualification_owner="operator:pi-qualification:paper-test",
            model="gpt-5.6-luna@openai",
            expect_enabled=False,
        )
    )

    assert Context.client.deleted == ["/api/v1/chat/sessions/session-1"]
    assert checks[-1].name == "delete_disposable_sessions"
    assert checks[-1].passed is True


def test_unhealthy_staging_fails_closed_before_creating_a_session(monkeypatch) -> None:
    from backend.config import Settings
    from backend.scripts import qualify_latex_paper_staging as qualification

    class Response:
        status_code = 503

    class Client:
        async def get(self, path):
            assert path == "/health"
            return Response()

        async def delete(self, _path):
            raise AssertionError("no session should require deletion")

    class Context:
        async def __aenter__(self):
            return Client()

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(qualification, "staging_client", lambda **_kwargs: Context())
    monkeypatch.setattr(qualification, "_encode_legacy_session", lambda _user: "token")

    checks = asyncio.run(
        qualification.run_qualification(
            Settings(environment="staging"),
            admin_subject="admin",
            admin_username="operator",
            qualification_owner="operator:pi-qualification:paper-test",
            model="gpt-5.6-luna@openai",
            expect_enabled=False,
        )
    )

    by_name = {check.name: check for check in checks}
    assert by_name["active_staging_health"].passed is False
    assert "selected_luna_model" not in by_name
    assert "explicit_luna_session" not in by_name


def test_historical_disabled_phase_never_creates_a_new_session_and_deletes_the_preserved_one(
    monkeypatch,
) -> None:
    from backend.config import Settings
    from backend.scripts import qualify_latex_paper_staging as qualification

    artifact_id = "00000000-0000-0000-0000-000000000001"

    class Response:
        def __init__(self, status_code: int, payload=None, headers=None) -> None:
            self.status_code = status_code
            self._payload = payload
            self.headers = headers or {}

        def json(self):
            return self._payload

    class StreamResponse(Response):
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def aiter_lines(self):
            yield 'data: {"type":"done","finish_reason":"success","citations":[]}'

    class Client:
        deleted: list[str] = []

        async def get(self, path):
            if path == "/health":
                return Response(200)
            if path == "/api/v1/chat/models":
                return Response(
                    200,
                    {
                        "items": [{"id": "gpt-5.6-luna@openai"}],
                        "default_model": "gpt-5.6-luna@openai",
                    },
                )
            if path == "/api/v1/chat/sessions?limit=50":
                return Response(
                    200, {"items": [{"id": "session-1"}], "next_cursor": None}
                )
            if path == "/api/v1/chat/sessions/session-1":
                if self.deleted:
                    return Response(404)
                return Response(
                    200,
                    {
                        "selected_model": "gpt-5.6-luna@openai",
                        "latex_paper": {"artifact_id": artifact_id},
                    },
                )
            if path == f"/api/v1/chat/artifacts/{artifact_id}":
                return Response(
                    200,
                    {
                        "artifact_id": artifact_id,
                        "source_head": {"version_id": "source-1"},
                    },
                )
            if path.endswith("/export/source.zip"):
                return Response(200, headers={"content-type": "application/zip"})
            raise AssertionError(path)

        async def post(self, path, **_kwargs):
            raise AssertionError(
                f"historical phase must not create or mutate via {path}"
            )

        async def delete(self, path):
            self.deleted.append(path)
            return Response(204)

        def stream(self, *_args, **_kwargs):
            return StreamResponse(200)

    class Context:
        client = Client()

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(qualification, "staging_client", lambda **_kwargs: Context())
    monkeypatch.setattr(qualification, "_encode_legacy_session", lambda _user: "token")

    checks = asyncio.run(
        qualification.run_qualification(
            Settings(environment="staging"),
            admin_subject="admin",
            admin_username="operator",
            qualification_owner="operator:pi-qualification:paper-test",
            model="gpt-5.6-luna@openai",
            expect_enabled=False,
            verify_historical=True,
        )
    )

    by_name = {check.name: check for check in checks}
    assert Context.client.deleted == ["/api/v1/chat/sessions/session-1"]
    assert by_name["historical_private_descriptor_source_export"].passed is True
    assert by_name["disabled_historical_write_paper_nonactivation"].passed is True
    assert by_name["kill_switch_rollback"].passed is True


def test_archive_keeps_the_private_paper_readable_to_its_dedicated_owner() -> None:
    from backend.scripts.qualify_latex_paper_staging import (
        archive_preserves_private_paper,
    )

    artifact_id = "00000000-0000-0000-0000-000000000001"

    class Response:
        def __init__(self, status_code: int, payload) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    class Client:
        async def post(self, path, **_kwargs):
            assert path == "/api/v1/chat/sessions/archive-oldest"
            return Response(200, {"archived_count": 1})

        async def get(self, path):
            if path == "/api/v1/chat/sessions/session-1":
                return Response(200, {"latex_paper": {"artifact_id": artifact_id}})
            if path == f"/api/v1/chat/artifacts/{artifact_id}":
                return Response(200, {"artifact_id": artifact_id})
            raise AssertionError(path)

    assert asyncio.run(
        archive_preserves_private_paper(
            Client(), session_id="session-1", artifact_id=artifact_id
        )
    )


def test_historical_kill_switch_phase_reads_only_one_preserved_owner_artifact() -> None:
    from backend.scripts.qualify_latex_paper_staging import (
        historical_private_artifact_readable,
    )

    artifact_id = "00000000-0000-0000-0000-000000000001"

    class Response:
        def __init__(self, status_code: int, payload=None, headers=None) -> None:
            self.status_code = status_code
            self._payload = payload
            self.headers = headers or {}

        def json(self):
            return self._payload

    class Client:
        async def get(self, path):
            if path == "/api/v1/chat/sessions?limit=50":
                return Response(
                    200, {"items": [{"id": "session-1"}], "next_cursor": None}
                )
            if path == "/api/v1/chat/sessions/session-1":
                return Response(
                    200,
                    {
                        "selected_model": "gpt-5.6-luna@openai",
                        "latex_paper": {"artifact_id": artifact_id},
                    },
                )
            if path == f"/api/v1/chat/artifacts/{artifact_id}":
                return Response(
                    200,
                    {
                        "artifact_id": artifact_id,
                        "source_head": {"version_id": "source-1"},
                    },
                )
            if path == (
                f"/api/v1/chat/artifacts/{artifact_id}/versions/source-1/export/source.zip"
            ):
                return Response(200, headers={"content-type": "application/zip"})
            raise AssertionError(path)

    session_id, readable = asyncio.run(
        historical_private_artifact_readable(Client(), model="gpt-5.6-luna@openai")
    )

    assert session_id == "session-1"
    assert readable is True


def test_preserve_phase_refuses_more_than_one_owner_session() -> None:
    from backend.scripts.qualify_latex_paper_staging import preserved_owner_artifact

    artifact_id = "00000000-0000-0000-0000-000000000001"

    class Response:
        def __init__(self, status_code: int, payload=None) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    class Client:
        async def get(self, path):
            if path == "/api/v1/chat/sessions?limit=50":
                return Response(
                    200,
                    {
                        "items": [{"id": "session-1"}, {"id": "unexpected"}],
                        "next_cursor": None,
                    },
                )
            raise AssertionError(path)

    assert not asyncio.run(
        preserved_owner_artifact(
            Client(),
            session_id="session-1",
            artifact_id=artifact_id,
            model="gpt-5.6-luna@openai",
        )
    )


def test_bounded_repair_requires_three_receipts_and_an_exhausted_unchanged_head() -> (
    None
):
    from backend.scripts.qualify_latex_paper_staging import (
        PaperState,
        TurnObservation,
        bounded_repair_passes,
    )

    turn = TurnObservation(
        terminal=True,
        successful=True,
        had_error=False,
        paper_artifact_id="artifact",
        paper_activated=False,
        paper_operation="repair",
        paper_operations=("repair", "repair", "repair"),
        citations_structural=False,
    )
    exhausted = PaperState(
        source_version_id="failed-source",
        source_status="failed",
        source_actor_type="human",
        preview_version_id="last-good-preview",
        repair_attempts_remaining=0,
        repair_exhausted=True,
    )

    assert bounded_repair_passes(
        turn,
        exhausted,
        failed_source_id="failed-source",
        preserved_preview_id="last-good-preview",
    )
    assert not bounded_repair_passes(
        TurnObservation(
            **{
                **turn.__dict__,
                "paper_operations": ("repair", "repair"),
            }
        ),
        exhausted,
        failed_source_id="failed-source",
        preserved_preview_id="last-good-preview",
    )
