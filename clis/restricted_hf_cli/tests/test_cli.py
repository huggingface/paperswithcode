from __future__ import annotations

import io
import json

import pytest

from restricted_hf_cli import cli, transport


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def query(operation, arguments):
        calls.append((operation, arguments))
        return {
            "schema_version": 1,
            "operation": operation,
            "data": {"ok": True},
            "truncation": {"truncated": False, "reason": None},
        }

    monkeypatch.setattr(cli, "query", query)
    return calls


@pytest.mark.parametrize(
    ("argv", "operation"),
    [
        (["collections", "info", "owner/name"], "collection_info"),
        (["collections", "list", "--limit", "3"], "collection_list"),
        (["datasets", "card", "owner/name"], "dataset_card"),
        (["datasets", "info", "owner/name"], "dataset_info"),
        (["datasets", "list"], "dataset_list"),
        (["models", "card", "owner/name"], "model_card"),
        (["models", "info", "owner/name"], "model_info"),
        (["models", "list"], "model_list"),
        (["spaces", "card", "owner/name"], "space_card"),
        (["spaces", "info", "owner/name"], "space_info"),
        (["spaces", "list"], "space_list"),
    ],
)
def test_supported_commands_emit_exact_operations(argv, operation, captured, capsys):
    assert cli.main(argv) == 0
    assert captured[-1][0] == operation
    assert "operation:" in capsys.readouterr().out


def test_list_modes_and_selectors_are_strict(captured):
    assert cli.main(["models", "list", "owner/name", "--recursive", "--tree"]) == 0
    assert captured[-1] == (
        "model_list",
        {"repo_id": "owner/name", "tree": True, "recursive": True},
    )
    assert cli.main(["models", "list", "--author", "moonshotai", "--limit", "30"]) == 0
    assert captured[-1] == (
        "model_list",
        {"author": "moonshotai", "limit": 30},
    )
    for argv in (
        ["models", "list", "owner/name", "--search", "bad"],
        ["models", "list", "--recursive"],
        ["models", "card", "owner/name", "--metadata", "--text"],
        ["models", "card", "https://huggingface.co/owner/name"],
        ["models", "info", "owner/name", "--expand", "futureField"],
        ["models", "list", "--limit", "51"],
        ["models", "list", "--format", "json"],
        ["auth", "login"],
        ["upload", "owner/name", "file"],
    ):
        with pytest.raises(SystemExit) as error:
            cli.main(argv)
        assert error.value.code == 2


def test_default_and_explicit_agent_format_match(captured, capsys):
    assert cli.main(["datasets", "info", "owner/name"]) == 0
    first = capsys.readouterr().out
    assert cli.main(["datasets", "info", "owner/name", "--format", "agent"]) == 0
    assert capsys.readouterr().out == first


def test_version_is_local(captured, capsys):
    assert cli.main(["version"]) == 0
    assert not captured
    assert "PwC read-only subset" in capsys.readouterr().out


def test_transport_rejects_non_loopback(monkeypatch):
    monkeypatch.setenv("PWC_HF_API_URL", "https://huggingface.co/api/models")
    with pytest.raises(transport.TransportError, match="gateway is invalid"):
        transport.query("model_info", {"repo_id": "owner/name"})


@pytest.mark.parametrize(
    ("raw", "content_type", "message"),
    [
        (b"x" * (transport.MAX_RESPONSE_BYTES + 1), "application/json", "too large"),
        (b"not-json", "application/json", "malformed JSON"),
        (b"{}", "text/html", "invalid content"),
        (b'{"schema_version":99}', "application/json", "contract mismatch"),
    ],
)
def test_transport_rejects_untrusted_gateway_responses(
    monkeypatch, raw, content_type, message
):
    class Headers:
        def get_content_type(self):
            return content_type

    class Response(io.BytesIO):
        headers = Headers()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    class Opener:
        def open(self, *_args, **_kwargs):
            return Response(raw)

    monkeypatch.delenv("PWC_HF_API_URL", raising=False)
    monkeypatch.setattr(
        transport.urllib.request, "build_opener", lambda *_args: Opener()
    )
    with pytest.raises(transport.TransportError, match=message):
        transport.query("model_info", {"repo_id": "owner/name"})


def test_renderer_preserves_utf8_and_explicit_truncation(captured, capsys):
    assert cli.main(["spaces", "card", "owner/demo"]) == 0
    output = capsys.readouterr().out
    assert json.loads(output.split("data:\n", 1)[1].split("\ntruncation:", 1)[0]) == {
        "ok": True
    }
    assert '"truncated": false' in output
