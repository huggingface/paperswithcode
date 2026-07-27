from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pwc_cli.cli import build_parser, main  # noqa: E402
from pwc_cli.transport import Client, Response  # noqa: E402

INSTALLER_SPEC = importlib.util.spec_from_file_location(
    "pwc_cli_installer", ROOT / "install.py"
)
assert INSTALLER_SPEC and INSTALLER_SPEC.loader
installer = importlib.util.module_from_spec(INSTALLER_SPEC)
INSTALLER_SPEC.loader.exec_module(installer)


def test_complete_parser_omits_mutation_and_auth_commands():
    help_text = build_parser().format_help()
    assert "{search,paper,benchmark,version}" in help_text
    for command in ("auth", "add-external", "cron", "embedding", "github-issue"):
        assert command not in help_text
    assert build_parser().parse_args(["paper", "lineage", "list", "2501.1"]).paper


def test_installer_downloads_from_this_repository_release_origin():
    source = (ROOT / "install.py").read_text()
    assert "github.com/huggingface/pwc-cli/releases/download" in source
    assert "github.com/paperswithcode/paperswithcode.co" not in source


def test_installer_version_pin_is_optional_and_explicit_pin_skips_lookup(monkeypatch):
    assert installer.parse_args([]).version is None
    monkeypatch.setattr(
        installer, "_open", lambda _url: (_ for _ in ()).throw(AssertionError())
    )
    assert installer.resolve_version("1.2.3", "unused") == "1.2.3"


def test_installer_resolves_valid_latest_release_tag(monkeypatch):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    monkeypatch.setattr(
        installer,
        "_open",
        lambda _url: Response(b'{"tag_name": "pwc-cli-1.2.3"}'),
    )
    assert installer.resolve_version(None, "https://example.test/latest") == "1.2.3"


def test_installer_release_lookup_network_error_is_one_line_exit_3(monkeypatch, capsys):
    monkeypatch.setattr(
        installer.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            urllib.error.URLError("offline\nnow")
        ),
    )
    assert installer.main([]) == 3
    assert capsys.readouterr().err == "pwc installer: network error: offline now\n"


def test_installer_artifact_and_checksum_network_errors_exit_3(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(installer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(installer.platform, "machine", lambda: "x86_64")

    monkeypatch.setattr(
        installer,
        "_download",
        lambda *_args: (_ for _ in ()).throw(installer.NetworkError("artifact")),
    )
    assert installer.main(["--version", "1.2.3", "--prefix", str(tmp_path)]) == 3
    assert capsys.readouterr().err == "pwc installer: network error: artifact\n"

    monkeypatch.setattr(
        installer, "_download", lambda _url, destination: destination.write_bytes(b"x")
    )
    monkeypatch.setattr(
        installer,
        "_read_checksum",
        lambda *_args: (_ for _ in ()).throw(installer.NetworkError("checksum")),
    )
    assert installer.main(["--version", "1.2.3", "--prefix", str(tmp_path)]) == 3
    assert capsys.readouterr().err == "pwc installer: network error: checksum\n"


def test_installer_reports_path_and_persistent_instruction(tmp_path, capsys):
    bin_directory = tmp_path / ".local" / "bin"
    installer.report_path(bin_directory, f"/usr/bin:{bin_directory}")
    captured = capsys.readouterr()
    assert captured.out == f"{bin_directory} is on PATH\n"
    assert captured.err == ""

    installer.report_path(bin_directory, "/usr/bin")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"warning: {bin_directory} is not on PATH\n"
        f'Add this to ~/.profile: export PATH={bin_directory}:"$PATH"\n'
    )


def test_installer_default_path_instruction_uses_expandable_home(capsys):
    installer.report_path(Path.home() / ".local" / "bin", "/usr/bin")
    assert capsys.readouterr().err == (
        "warning: ~/.local/bin is not on PATH\n"
        'Add this to ~/.profile: export PATH="$HOME/.local/bin:$PATH"\n'
    )


def test_installer_replaces_binary_atomically(tmp_path):
    artifact = tmp_path / "artifact"
    artifact.write_bytes(b"new executable")
    destination = tmp_path / "bin" / "pwc"
    destination.parent.mkdir()
    destination.write_bytes(b"old executable")

    installer._install_atomically(artifact, destination)

    assert destination.read_bytes() == b"new executable"
    assert destination.stat().st_mode & 0o111
    assert list(destination.parent.iterdir()) == [destination]


def test_benchmark_limit_alias_preserves_page_size_destination():
    parser = build_parser()
    assert parser.parse_args(["benchmark", "list", "--limit", "7"]).page_size == 7
    assert parser.parse_args(["benchmark", "list", "--page-size", "8"]).page_size == 8


def test_benchmark_detail_parser_matches_requested_command_shape():
    args = build_parser().parse_args(
        ["benchmark", "--name", "SWE-Bench Pro", "--limit", "5"]
    )

    assert args.name == "SWE-Bench Pro"
    assert args.limit == 5


def test_task_benchmark_list_uses_frontend_trending_order(monkeypatch):
    calls = []
    payload = {
        "task_id": "18",
        "task_slug": "ocr",
        "recent_days": 90,
        "results": [
            {
                "id": "2",
                "name": "Recent OCR",
                "recent_paper_count": 4,
                "all_time_paper_count": 5,
                "trend_score": 1.3333,
                "best_model_name": "Reader 2",
            },
            {
                "id": "1",
                "name": "Classic OCR",
                "recent_paper_count": 1,
                "all_time_paper_count": 20,
                "trend_score": 0.3333,
                "best_model_name": "Reader 1",
            },
        ],
    }

    class Client:
        def __init__(self):
            pass

        def get(self, path, params):
            calls.append((path, params))
            return Response(json.dumps(payload).encode(), {})

    monkeypatch.setattr("pwc_cli.cli.Client", Client)
    output = io.StringIO()
    with redirect_stdout(output):
        assert main(["benchmark", "list", "--task", "OCR"]) == 0

    assert calls[0][0] == "tasks/OCR/trending-benchmarks"
    assert calls[0][1]["min_recent_papers"] == 0
    assert output.getvalue().splitlines()[1:3] == [
        "2\tRecent OCR\t4\t1.3333\tReader 2",
        "1\tClassic OCR\t1\t0.3333\tReader 1",
    ]


def test_benchmark_detail_renders_merged_markdown_leaderboard(monkeypatch):
    calls = []
    benchmark_payload = {
        "count": 1,
        "results": [
            {
                "id": "42",
                "name": "SWE-Bench Pro",
                "slug": "swe-bench-pro",
                "description": "A coding-agent benchmark.",
            }
        ],
    }
    evaluations_payload = {
        "count": 2,
        "results": [
            {
                "id": "1",
                "paper_id": "9",
                "task_id": "3",
                "dataset_id": "42",
                "model_name": "Agent | One",
                "metrics": {"Resolved": 55.5},
                "best_metric": "Resolved",
                "best_rank": 1,
                "paper_title": "An Agent Paper",
                "paper_arxiv_id": "2601.12345",
                "paper_published_date": "2026-01-20",
                "task_name": "Coding Agents",
                "is_open": False,
            },
            {
                "id": "2",
                "paper_id": "9",
                "task_id": "3",
                "dataset_id": "42",
                "model_name": "Agent | One",
                "metrics": {"Pass@1": 50},
                "best_metric": "Pass@1",
                "best_rank": 2,
                "paper_title": "An Agent Paper",
                "paper_arxiv_id": "2601.12345",
                "paper_published_date": "2026-01-20",
                "task_name": "Coding Agents",
                "is_open": False,
            },
        ],
    }

    class Client:
        def __init__(self):
            pass

        def get(self, path, params):
            calls.append((path, params))
            payload = benchmark_payload if path == "datasets/" else evaluations_payload
            return Response(json.dumps(payload).encode(), {})

    monkeypatch.setattr("pwc_cli.cli.Client", Client)
    output = io.StringIO()
    with redirect_stdout(output):
        assert main(["benchmark", "--name", "SWE-Bench Pro"]) == 0

    rendered = output.getvalue()
    assert "# SWE-Bench Pro" in rendered
    assert "Agent \\| One" in rendered
    assert "Resolved: 55.5, Pass@1: 50" in rendered
    assert "[An Agent Paper](https://paperswithcode.co/paper/2601.12345)" in rendered
    assert "2026-01-20" in rendered
    assert calls[1] == (
        "datasets/42/evaluations/",
        {
            "page": 1,
            "page_size": 100,
            "ordering": "best_rank",
            "is_open": None,
        },
    )


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
    paths = []

    class Client:
        def __init__(self):
            pass

        def get(self, path, params=None):
            paths.append((path, params))
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
    assert paths == [
        ("research/papers/2501.01234/read", None),
        ("research/papers/2501.01234/read", None),
    ]


def test_transport_is_anonymous_by_default(monkeypatch):
    requests = []

    class HTTPResponse(io.BytesIO):
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def fake_urlopen(request, *, timeout):
        requests.append(request)
        assert timeout == 30
        return HTTPResponse(b"# Public paper\n")

    monkeypatch.delenv("PWC_API_URL", raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    response = Client("https://example.test/api/v1").get(
        "research/papers/2501.01234/read"
    )

    assert response.body == b"# Public paper\n"
    assert requests[0].full_url.endswith("/api/v1/research/papers/2501.01234/read")
    assert requests[0].get_header("Authorization") is None
