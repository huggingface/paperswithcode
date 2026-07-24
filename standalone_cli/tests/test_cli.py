from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pwc_cli.cli import build_parser, main  # noqa: E402
from pwc_cli.transport import Response  # noqa: E402


def test_complete_parser_omits_mutation_and_auth_commands():
    help_text = build_parser().format_help()
    assert "{search,paper,benchmark,version}" in help_text
    for command in ("auth", "add-external", "cron", "embedding", "github-issue"):
        assert command not in help_text
    assert build_parser().parse_args(["paper", "lineage", "list", "2501.1"]).paper


def test_installer_downloads_from_this_repository_release_origin():
    installer = (ROOT / "install.py").read_text()
    assert "github.com/huggingface/pwc-cli/releases/download" in installer
    assert "github.com/paperswithcode/paperswithcode.co" not in installer


def test_top_level_version_is_offline_and_stable():
    output = io.StringIO()
    with redirect_stdout(output):
        try:
            build_parser().parse_args(["--version"])
        except SystemExit as error:
            assert error.code == 0
    assert output.getvalue() == "pwc 0.1.1\tapi v1\n"


def test_search_default_output_is_compact_deterministic_tsv(monkeypatch):
    payload = {
        "count": 1,
        "results": [
            {
                "arxiv_id": "2501.01234",
                "title": "Line one\nline two",
                "published": "2025-01-03",
                "citation_count": 42,
            }
        ],
    }

    class Client:
        def __init__(self):
            pass

        def get(self, _path, _params):
            return Response(json.dumps(payload).encode(), {})

    monkeypatch.setattr("pwc_cli.cli.Client", Client)
    output = io.StringIO()
    with redirect_stdout(output):
        assert main(["search", "vision"]) == 0
    assert output.getvalue() == (
        "id\ttitle\tyear\tcitations\n2501.01234\tLine one\\nline two\t2025\t42\n"
    )


def test_json_schema_and_errors_use_stable_streams(monkeypatch):
    class Client:
        def __init__(self):
            pass

        def get(self, _path, _params):
            return Response(b'{"count":0,"results":[]}', {})

    monkeypatch.setattr("pwc_cli.cli.Client", Client)
    output = io.StringIO()
    errors = io.StringIO()
    with redirect_stdout(output), redirect_stderr(errors):
        assert main(["search", "none", "--json"]) == 0
    assert json.loads(output.getvalue())["schema_version"] == "v1"
    assert errors.getvalue() == ""


def test_paper_read_supports_markdown_and_versioned_json(monkeypatch):
    class Client:
        def __init__(self):
            pass

        def get(self, _path, _params=None):
            return Response(b"# Paper\n\nBody", {})

    monkeypatch.setattr("pwc_cli.cli.Client", Client)
    output = io.StringIO()
    with redirect_stdout(output):
        assert main(["paper", "read", "2501.01234"]) == 0
    assert output.getvalue() == "# Paper\n\nBody\n"

    output = io.StringIO()
    with redirect_stdout(output):
        assert main(["paper", "read", "2501.01234", "--json"]) == 0
    payload = json.loads(output.getvalue())
    assert payload == {
        "schema_version": "v1",
        "data": {"paper": "2501.01234", "markdown": "# Paper\n\nBody"},
    }
