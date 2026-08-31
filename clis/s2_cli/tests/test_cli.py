from __future__ import annotations

import io
import json
import sys
import urllib.error
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from s2_cli.cli import build_parser, main  # noqa: E402
from s2_cli.resolve import normalize_paper_id  # noqa: E402
from s2_cli.transport import Client, Response, TransportError  # noqa: E402


def _headers(retry_after: str | None = None) -> EmailMessage:
    headers = EmailMessage()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return headers


def _http_error(
    url: str, status: int, body: bytes, retry_after: str | None = None
) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url, status, "error", _headers(retry_after), io.BytesIO(body)
    )


class FakeClient:
    def __init__(self, payloads: dict[str, dict], api_key: str = "test-key"):
        self.payloads = payloads
        self.calls: list[tuple[str, dict | None]] = []
        self.api_key = api_key

    def get(self, path, params=None):
        self.calls.append((path, params))
        if path not in self.payloads:
            raise AssertionError(f"unexpected path {path}")
        return Response(json.dumps(self.payloads[path]).encode(), {}, 200)


def test_parser_commands():
    help_text = build_parser().format_help()
    assert "{search,refs,citations,version}" in help_text
    args = build_parser().parse_args(
        ["refs", "Attention is All You Need", "--limit", "5"]
    )
    assert args.paper == "Attention is All You Need"
    assert args.limit == 5


def test_normalize_paper_ids():
    assert normalize_paper_id("1706.03762") == "ARXIV:1706.03762"
    assert normalize_paper_id("arXiv:1706.03762v5") == "ARXIV:1706.03762"
    assert normalize_paper_id("https://arxiv.org/abs/1706.03762") == "ARXIV:1706.03762"
    assert normalize_paper_id("10.18653/v1/N18-3011") == "DOI:10.18653/v1/N18-3011"
    assert (
        normalize_paper_id("204e3073870fae3d05bcbc2f6a8e263d9b72e776")
        == "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
    )
    assert normalize_paper_id("Attention is All You Need") is None
    assert (
        normalize_paper_id("https://www.semanticscholar.org/paper/foo/" + "a" * 40)
        == "a" * 40
    )


def test_missing_api_key_exits_2(monkeypatch, capsys):
    monkeypatch.delenv("PWC_SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("S2_API_KEY", raising=False)
    assert main(["search", "transformers"]) == 2
    captured = capsys.readouterr()
    assert "missing API key" in captured.err


def test_client_uses_configured_api_url(monkeypatch):
    monkeypatch.setenv("S2_API_URL", "http://127.0.0.1:8765/semantic-scholar/")
    client = Client(api_key="test-key", delay=0)
    assert client.base_url == "http://127.0.0.1:8765/semantic-scholar"


def test_invalid_limit_exits_2(capsys):
    with pytest.raises(SystemExit) as raised:
        main(["search", "transformers", "--limit", "0"])
    assert raised.value.code == 2
    assert "--limit must be 1-100" in capsys.readouterr().err


def test_citations_hard_cap_exits_2(monkeypatch, capsys):
    monkeypatch.setenv("S2_API_KEY", "test-key")
    monkeypatch.setenv("S2_REQUEST_DELAY", "0")
    monkeypatch.setattr("s2_cli.cli.Client", lambda: FakeClient({}))
    assert main(["citations", "1706.03762", "--offset", "9990", "--limit", "20"]) == 2
    assert "--offset + --limit must be <=" in capsys.readouterr().err


def test_search_tsv_and_more(monkeypatch, capsys):
    monkeypatch.setenv("S2_API_KEY", "test-key")
    client = FakeClient(
        {
            "paper/search": {
                "total": 40,
                "offset": 0,
                "next": 20,
                "data": [
                    {
                        "paperId": "abc",
                        "title": "Dehazing",
                        "year": 2025,
                        "citationCount": 12,
                        "externalIds": {"ArXiv": "2501.00001"},
                    }
                ],
            }
        }
    )
    monkeypatch.setattr("s2_cli.cli.Client", lambda: client)
    assert main(["search", "image dehazing", "--year", "2025-2026"]) == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "paperId\tyear\tcites\tarxiv\ttitle",
        "abc\t2025\t12\t2501.00001\tDehazing",
    ]
    assert "# more: rerun with --offset 20" in captured.err
    assert client.calls == [
        (
            "paper/search",
            {
                "query": "image dehazing",
                "limit": 20,
                "offset": 0,
                "year": "2025-2026",
                "fields": ("title,year,citationCount,externalIds,url,authors,abstract"),
            },
        )
    ]


def test_search_json(monkeypatch, capsys):
    monkeypatch.setenv("S2_API_KEY", "test-key")
    payload = {"total": 1, "data": [{"paperId": "abc", "title": "Dehazing"}]}
    client = FakeClient({"paper/search": payload})
    monkeypatch.setattr("s2_cli.cli.Client", lambda: client)
    assert main(["search", "dehazing", "--json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["schema_version"] == "v1"
    assert body["data"] == payload


def test_search_jsonl_emits_unnested_papers(monkeypatch, capsys):
    monkeypatch.setenv("S2_API_KEY", "test-key")
    papers = [
        {"paperId": "a", "title": "First", "citationCount": 2},
        {"paperId": "b", "title": "Second", "citationCount": 3},
    ]
    monkeypatch.setattr(
        "s2_cli.cli.Client", lambda: FakeClient({"paper/search": {"data": papers}})
    )
    assert main(["search", "test", "--jsonl"]) == 0
    assert [json.loads(line) for line in capsys.readouterr().out.splitlines()] == papers


def test_refs_title_match_then_flatten(monkeypatch, capsys):
    monkeypatch.setenv("S2_API_KEY", "test-key")
    client = FakeClient(
        {
            "paper/search/match": {
                "data": [
                    {
                        "paperId": "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
                        "title": "Attention Is All You Need",
                        "matchScore": 0.97,
                        "externalIds": {"ArXiv": "1706.03762"},
                    }
                ]
            },
            "paper/204e3073870fae3d05bcbc2f6a8e263d9b72e776/references": {
                "offset": 0,
                "next": 20,
                "data": [
                    {
                        "citedPaper": {
                            "paperId": "ref-1",
                            "title": "LSTM",
                            "year": 1997,
                            "citationCount": 9000,
                            "externalIds": {},
                        }
                    },
                    {"citedPaper": None},
                ],
            },
        }
    )
    monkeypatch.setattr("s2_cli.cli.Client", lambda: client)
    assert main(["refs", "Attention is All You Need"]) == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "paperId\tyear\tcites\tarxiv\ttitle",
        "ref-1\t1997\t9000\t\tLSTM",
    ]
    assert captured.err.splitlines() == [
        "# paper:\tAttention Is All You Need\t"
        "204e3073870fae3d05bcbc2f6a8e263d9b72e776\t1706.03762\t0.97",
        "# more: rerun with --offset 20",
    ]
    assert client.calls[0][0] == "paper/search/match"
    assert client.calls[1][0].endswith("/references")


def test_citations_arxiv_skips_title_match(monkeypatch, capsys):
    monkeypatch.setenv("S2_API_KEY", "test-key")
    client = FakeClient(
        {
            "paper/ARXIV:1706.03762/citations": {
                "offset": 0,
                "data": [
                    {
                        "citingPaper": {
                            "paperId": "bert",
                            "title": "BERT",
                            "year": 2018,
                            "citationCount": 80000,
                            "externalIds": {"ArXiv": "1810.04805v2"},
                        }
                    }
                ],
            }
        }
    )
    monkeypatch.setattr("s2_cli.cli.Client", lambda: client)
    assert main(["citations", "1706.03762", "--limit", "5"]) == 0
    captured = capsys.readouterr()
    assert "bert\t2018\t80000\t1810.04805\tBERT" in captured.out
    assert captured.err.splitlines() == ["# paper:\tARXIV:1706.03762"]
    assert [path for path, _params in client.calls] == [
        "paper/ARXIV:1706.03762/citations"
    ]


def test_citations_jsonl_flattens_edges(monkeypatch, capsys):
    monkeypatch.setenv("S2_API_KEY", "test-key")
    paper = {"paperId": "bert", "title": "BERT", "citationCount": 80000}
    client = FakeClient(
        {"paper/ARXIV:1706.03762/citations": {"data": [{"citingPaper": paper}]}}
    )
    monkeypatch.setattr("s2_cli.cli.Client", lambda: client)
    assert main(["citations", "1706.03762", "--jsonl"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == paper
    assert "# paper:\tARXIV:1706.03762" in captured.err


def test_citations_sort_and_top_are_explicitly_page_scoped(monkeypatch, capsys):
    monkeypatch.setenv("S2_API_KEY", "test-key")
    papers = [
        {"paperId": "low", "title": "Low", "citationCount": 2},
        {"paperId": "high", "title": "High", "citationCount": 100},
        {"paperId": "unknown", "title": "Unknown", "citationCount": None},
    ]
    client = FakeClient(
        {
            "paper/ARXIV:1706.03762/citations": {
                "offset": 40,
                "next": 43,
                "data": [{"citingPaper": paper} for paper in papers],
            }
        }
    )
    monkeypatch.setattr("s2_cli.cli.Client", lambda: client)
    assert (
        main(
            [
                "citations",
                "1706.03762",
                "--limit",
                "3",
                "--offset",
                "40",
                "--sort-by",
                "citation-count",
                "--top",
                "2",
                "--jsonl",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert [json.loads(line)["paperId"] for line in captured.out.splitlines()] == [
        "high",
        "low",
    ]
    assert "3 results returned at offset 40" in captured.err
    assert "not a global citation ranking" in captured.err
    assert "# more: rerun with --offset 43" in captured.err


@pytest.mark.parametrize(
    "arguments,message",
    [
        (["--top", "5"], "--top requires --sort-by citation-count"),
        (
            ["--sort-by", "citation-count", "--json"],
            "--sort-by cannot be combined with raw --json",
        ),
        (
            ["--limit", "5", "--sort-by", "citation-count", "--top", "6"],
            "--top cannot exceed --limit",
        ),
    ],
)
def test_invalid_output_flag_combinations_exit_2(arguments, message, capsys):
    with pytest.raises(SystemExit) as raised:
        main(["citations", "1706.03762", *arguments])
    assert raised.value.code == 2
    assert message in capsys.readouterr().err


def test_refs_json_includes_resolved_paper(monkeypatch, capsys):
    monkeypatch.setenv("S2_API_KEY", "test-key")
    payload = {"data": [{"citedPaper": {"paperId": "ref-1", "title": "LSTM"}}]}
    client = FakeClient({"paper/ARXIV:1706.03762/references": payload})
    monkeypatch.setattr("s2_cli.cli.Client", lambda: client)
    assert main(["refs", "ARXIV:1706.03762", "--json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["schema_version"] == "v1"
    assert body["paper"] == {"id": "ARXIV:1706.03762"}
    assert body["data"] == payload


def test_title_match_404_exits_4(monkeypatch, capsys):
    from s2_cli.transport import NotFoundError

    class MissingClient(FakeClient):
        def get(self, path, params=None):
            raise NotFoundError("API request failed (404): Title match not found")

    monkeypatch.setenv("S2_API_KEY", "test-key")
    monkeypatch.setattr("s2_cli.cli.Client", lambda: MissingClient({}))
    assert main(["refs", "totalGarbageNonsense"]) == 4
    assert "Title match not found: totalGarbageNonsense" in capsys.readouterr().err


def test_version_does_not_need_a_key(monkeypatch, capsys):
    monkeypatch.delenv("PWC_SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("S2_API_KEY", raising=False)
    assert main(["version"]) == 0
    assert capsys.readouterr().out.startswith("s2 0.2.0")


def test_429_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("S2_API_KEY", "test-key")
    monkeypatch.setenv("S2_REQUEST_DELAY", "0")
    sleeps: list[float] = []
    attempts = {"n": 0}

    class DummyResponse:
        headers = {}
        status = 200

        def read(self, _size):
            return b'{"data":[]}'

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(request, timeout=30):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(request.full_url, 429, b"slow down", retry_after="0")
        return DummyResponse()

    client = Client(api_key="test-key", delay=0)
    client._sleep = sleeps.append
    monkeypatch.setattr("s2_cli.transport.urllib.request.urlopen", fake_urlopen)
    payload = client.get("paper/search", {"query": "x"}).json()
    assert payload == {"data": []}
    assert attempts["n"] == 2
    assert sleeps == [0.0]


def test_429_exhausted_raises_transport_error(monkeypatch):
    monkeypatch.setenv("S2_REQUEST_DELAY", "0")

    def fake_urlopen(request, timeout=30):
        raise _http_error(request.full_url, 429, b"slow down", retry_after="0")

    client = Client(api_key="test-key", delay=0, max_retries=2)
    client._sleep = lambda _seconds: None
    monkeypatch.setattr("s2_cli.transport.urllib.request.urlopen", fake_urlopen)
    try:
        client.get("paper/search")
    except TransportError as error:
        assert "429" in str(error)
    else:
        raise AssertionError("expected TransportError")


def test_search_encodes_query(monkeypatch):
    monkeypatch.setenv("S2_API_KEY", "test-key")
    seen = {}

    class DummyResponse:
        headers = {}
        status = 200

        def read(self, _size):
            return b'{"data":[]}'

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(request, timeout=30):
        seen["url"] = request.full_url
        seen["key"] = request.headers.get("X-api-key") or request.headers.get(
            "x-api-key"
        )
        return DummyResponse()

    client = Client(api_key="secret", delay=0)
    monkeypatch.setattr("s2_cli.transport.urllib.request.urlopen", fake_urlopen)
    client.get("paper/search", {"query": "a b", "limit": 20})
    parsed = urlparse(seen["url"])
    assert parse_qs(parsed.query)["query"] == ["a b"]
    assert seen["key"] == "secret"
