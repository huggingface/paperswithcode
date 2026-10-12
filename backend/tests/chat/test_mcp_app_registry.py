from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from backend.chat_sandbox_worker.mcp_app_registry import (
    EMPTY_EGRESS_POLICY_DIGEST,
    MANIFEST_PATH,
    WORKER_MCP_PROVIDERS,
    enabled_worker_mcp_providers,
    egress_policy_digest,
    sandbox_outbound_domains,
    validate_provider_entry,
)
from backend.config import Settings

REPOSITORY = Path(__file__).resolve().parents[3]


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "chat_gateway_url": "https://gateway.example.test/api/internal/chat-gateway",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_checked_in_manifest_matches_python_and_typescript_allowlists():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    providers = WORKER_MCP_PROVIDERS
    assert [entry.id for entry in providers] == ["excalidraw"]
    excalidraw = providers[0]
    assert excalidraw.endpoint == "https://mcp.excalidraw.com/mcp"
    assert excalidraw.hostname == "mcp.excalidraw.com"
    assert excalidraw.model_tools == ("read_me", "create_view")
    assert excalidraw.app_html_sha256 == (
        "441650e7bc844a43511b906281d11589e8d24a34a83d657c1d7a56f907c21a63"
    )
    assert manifest["providers"][0]["endpoint"] == excalidraw.endpoint
    worker = (
        REPOSITORY / "backend/chat_sandbox_worker/pi_worker/src/mcp_app_registry.ts"
    ).read_text(encoding="utf-8")
    frontend = (
        REPOSITORY / "frontend/src/components/chat/mcpAppRegistry.ts"
    ).read_text(encoding="utf-8")
    for source in (worker, frontend):
        assert 'EXCALIDRAW_ENDPOINT = "https://mcp.excalidraw.com/mcp"' in source
        assert 'EXCALIDRAW_HOSTNAME = "mcp.excalidraw.com"' in source
        assert re.search(
            r'EXCALIDRAW_MODEL_TOOLS = \["read_me", "create_view"\]', source
        )
    assert 'EXCALIDRAW_HOST_PATH = "/api/v1/chat/mcp-apps/excalidraw"' in frontend
    assert (
        'EXCALIDRAW_HOST_HTML_PATH = "/api/v1/chat/mcp-apps/excalidraw/html"'
        in frontend
    )
    assert "new URL(EXCALIDRAW_ENDPOINT)" not in frontend


def test_disabled_excalidraw_preserves_gateway_only_egress():
    settings = _settings(chat_excalidraw_enabled=False)
    assert sandbox_outbound_domains(settings) == ["gateway.example.test"]
    assert enabled_worker_mcp_providers(settings) == ()
    assert egress_policy_digest(settings) == EMPTY_EGRESS_POLICY_DIGEST
    assert EMPTY_EGRESS_POLICY_DIGEST == hashlib.sha256(b"[]").hexdigest()


def test_enabled_excalidraw_adds_only_reviewed_hostname():
    settings = _settings(chat_excalidraw_enabled=True, chat_mcp_apps_host_enabled=True)
    assert sandbox_outbound_domains(settings) == [
        "gateway.example.test",
        "mcp.excalidraw.com",
    ]
    assert [provider.id for provider in enabled_worker_mcp_providers(settings)] == [
        "excalidraw"
    ]
    enabled = egress_policy_digest(settings)
    assert enabled != EMPTY_EGRESS_POLICY_DIGEST
    assert enabled == egress_policy_digest(settings)


def test_either_excalidraw_kill_switch_removes_worker_egress():
    settings = _settings(chat_excalidraw_enabled=True, chat_mcp_apps_host_enabled=False)
    assert sandbox_outbound_domains(settings) == ["gateway.example.test"]
    assert enabled_worker_mcp_providers(settings) == ()


def test_invalid_registry_endpoints_fail_validation():
    base = {
        "id": "example",
        "endpoint": "https://mcp.example.test/mcp",
        "hostname": "mcp.example.test",
        "worker_flag": "chat_excalidraw_enabled",
        "model_tools": ["read_me"],
        "app_tools": ["save_checkpoint"],
        "resource_uri": "ui://example/app.html",
        "app_html_sha256": "a" * 64,
    }
    with pytest.raises(ValueError, match="HTTPS"):
        validate_provider_entry({**base, "endpoint": "http://mcp.example.test/mcp"})
    with pytest.raises(ValueError, match="credentials"):
        validate_provider_entry(
            {**base, "endpoint": "https://user:pass@mcp.example.test/mcp"}
        )
    with pytest.raises(ValueError, match="query or fragment"):
        validate_provider_entry(
            {**base, "endpoint": "https://mcp.example.test/mcp?x=1"}
        )
    with pytest.raises(ValueError, match="IP literal"):
        validate_provider_entry(
            {
                **base,
                "endpoint": "https://127.0.0.1/mcp",
                "hostname": "127.0.0.1",
            }
        )
    with pytest.raises(ValueError, match="exact host"):
        validate_provider_entry({**base, "hostname": "*.example.test"})
    with pytest.raises(ValueError, match="must match egress hostname"):
        validate_provider_entry({**base, "hostname": "other.example.test"})
    with pytest.raises(ValueError, match="App HTML SHA-256"):
        validate_provider_entry({**base, "app_html_sha256": "not-a-digest"})


def test_user_controlled_values_never_enter_domain_list():
    settings = _settings(chat_excalidraw_enabled=True, chat_mcp_apps_host_enabled=True)
    domains = sandbox_outbound_domains(settings)
    assert "evil.example" not in domains
    assert set(domains) == {"gateway.example.test", "mcp.excalidraw.com"}


def test_qualify_excalidraw_probe_requires_deployed_environment_and_reviewed_egress():
    from backend.scripts.qualify_chat_excalidraw_mcp import validate_settings

    with pytest.raises(RuntimeError, match="deployed environment"):
        validate_settings(
            _settings(
                environment="development",
                chat_excalidraw_enabled=True,
                chat_mcp_apps_host_enabled=True,
            )
        )
    with pytest.raises(RuntimeError, match="Enable PWC_CHAT_EXCALIDRAW_ENABLED"):
        validate_settings(
            _settings(environment="staging", chat_excalidraw_enabled=False)
        )
    validate_settings(
        _settings(
            environment="staging",
            chat_excalidraw_enabled=True,
            chat_mcp_apps_host_enabled=True,
        )
    )
    validate_settings(
        _settings(
            environment="production",
            chat_excalidraw_enabled=True,
            chat_mcp_apps_host_enabled=True,
        )
    )


def test_qualify_excalidraw_uses_selected_release_identity(tmp_path, monkeypatch):
    from backend.scripts import qualify_chat_excalidraw_mcp as qualify

    release = tmp_path / "release"
    release.mkdir()
    monkeypatch.setattr(
        qualify,
        "validate_manifest",
        lambda path, environment: {
            "release_id": "abc-production",
            "chat_runtime": {
                "modal_image_version": "im-reviewed",
                "worker_contract_version": "94",
            },
        },
    )
    merged = qualify.merge_release_identity(
        _settings(
            environment="production",
            chat_modal_image_version="im-stale",
            chat_worker_contract_version="old",
        ),
        release,
    )
    assert merged.release_id == "abc-production"
    assert merged.chat_modal_image_version == "im-reviewed"
    assert merged.chat_worker_contract_version == "94"
