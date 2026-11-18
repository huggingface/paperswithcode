import base64
import hashlib
import json
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.config import Settings
from backend.routers import csp_reports
from backend.services import csp_report_service
from backend.services.csp_report_service import (
    append_csp_reports,
    csp_report_log_path,
    parse_csp_reports,
)
from backend.utils.csrf import cookie_request_passes_csrf

REPO = Path(__file__).resolve().parents[2]


def test_parses_reporting_api_batches_without_queries():
    records = parse_csp_reports(
        [
            {
                "type": "csp-violation",
                "url": "https://paperswithcode.co/search?q=secret",
                "body": {
                    "documentURL": "https://paperswithcode.co/search?q=secret#x",
                    "blockedURL": "https://cdn.example/x.js?token=abc",
                    "effectiveDirective": "script-src-elem",
                    "sourceFile": "https://paperswithcode.co/assets/a.js",
                    "lineNumber": 7,
                    "sample": "",
                    "disposition": "report",
                },
            },
            {"type": "deprecation", "body": {"id": "x"}},
        ]
    )
    assert records == [
        {
            "page": "https://paperswithcode.co/search",
            "blocked": "https://cdn.example/x.js",
            "directive": "script-src-elem",
            "source": "https://paperswithcode.co/assets/a.js",
            "line": 7,
            "sample": "",
            "disposition": "report",
        }
    ]


def test_parses_legacy_report_uri_bodies():
    records = parse_csp_reports(
        {
            "csp-report": {
                "document-uri": "https://paperswithcode.co/paper/1?ref=x",
                "blocked-uri": "inline",
                "violated-directive": "script-src",
                "script-sample": "alert(1)",
                "line-number": "not-a-number",
            }
        }
    )
    assert records[0]["page"] == "https://paperswithcode.co/paper/1"
    assert records[0]["blocked"] == "inline"
    assert records[0]["directive"] == "script-src"
    assert records[0]["sample"] == "alert(1)"
    assert records[0]["line"] is None
    assert parse_csp_reports({"unexpected": True}) == []
    assert parse_csp_reports("text") == []


def test_append_respects_size_cap(tmp_path, monkeypatch):
    log = tmp_path / "csp.jsonl"
    record = {"page": "https://paperswithcode.co/", "directive": "script-src"}
    append_csp_reports([record], log)
    assert json.loads(log.read_text())["directive"] == "script-src"

    monkeypatch.setattr(csp_report_service, "MAX_LOG_BYTES", log.stat().st_size)
    append_csp_reports([record], log)
    assert len(log.read_text().splitlines()) == 1


def test_log_path_defaults_to_environment_log_dir():
    deployed = Settings(environment="production", release_id="abc")
    assert csp_report_log_path(deployed) == Path(
        "/var/log/paperswithcode/production/csp-reports.jsonl"
    )
    assert csp_report_log_path(Settings(environment="development")) is None


def test_endpoint_logs_reports(tmp_path, monkeypatch):
    log = tmp_path / "csp.jsonl"
    monkeypatch.setattr(
        csp_reports,
        "get_settings",
        lambda: Settings(environment="development", csp_report_log=str(log)),
    )
    app = FastAPI()
    app.include_router(csp_reports.router, prefix="/api/v1")
    client = TestClient(app)

    body = {
        "csp-report": {
            "document-uri": "https://paperswithcode.co/",
            "violated-directive": "object-src",
        }
    }
    response = client.post(
        "/api/v1/csp-reports",
        content=json.dumps(body),
        headers={"Content-Type": "application/csp-report"},
    )
    assert response.status_code == 204
    assert json.loads(log.read_text())["directive"] == "object-src"

    assert client.post("/api/v1/csp-reports", content=b"{").status_code == 400
    too_big = b"[" + b" " * csp_report_service.MAX_BODY_BYTES + b"]"
    assert client.post("/api/v1/csp-reports", content=too_big).status_code == 413


def test_reports_with_cookies_skip_csrf_origin_check():
    settings = Settings(environment="production", session_cookie_name="pwc_session")
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/csp-reports",
            "headers": [(b"cookie", b"pwc_session=value")],
        }
    )
    assert cookie_request_passes_csrf(request, settings)


def test_nginx_csp_hashes_match_index_html_inline_scripts():
    html = (REPO / "frontend" / "index.html").read_text()
    hashes = {
        "'sha256-"
        + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
        + "'"
        for body in re.findall(r"<script>(.*?)</script>", html, re.S)
    }
    assert len(hashes) == 2
    for name in ("paperswithcode.co.conf", "staging.paperswithcode.co.conf"):
        conf = (REPO / "deploy" / "nginx" / name).read_text()
        policies = re.findall(r'Content-Security-Policy-Report-Only "([^"]*)"', conf)
        assert len(policies) == 3
        assert len(set(policies)) == 1
        script_src = policies[0].split(";")[0].split()
        assert hashes == {token for token in script_src if token.startswith("'sha256-")}
