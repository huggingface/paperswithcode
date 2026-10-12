from pathlib import Path
from types import SimpleNamespace

import backend.scripts.staging_qualification_http as qualification_http
from backend.scripts.qualify_chat_soak import CONFIRMATION, _matches_release, parser


def test_soak_qualifier_parser_has_bounded_explicit_controls(tmp_path):
    release = tmp_path / "release"
    args = parser().parse_args(
        [
            "--followup-sessions",
            "13",
            "--followups-per-session",
            "4",
            "--clean-cancellations",
            "20",
            "--forced-cancellations",
            "10",
            "--release-dir",
            str(release),
            "--confirm",
            CONFIRMATION,
        ]
    )

    assert args.followup_sessions == 13
    assert args.followups_per_session == 4
    assert args.clean_cancellations == 20
    assert args.forced_cancellations == 10
    assert args.release_dir == release


def test_soak_qualifier_rejects_cross_release_rows():
    settings = SimpleNamespace(
        release_id="current-staging",
        chat_worker_contract_version="30",
    )
    current = SimpleNamespace(
        app_release_id="current-staging",
        worker_contract_version="30",
    )
    previous = SimpleNamespace(
        app_release_id="previous-staging",
        worker_contract_version="30",
    )

    assert _matches_release([current], settings) is True
    assert _matches_release([current, previous], settings) is False


def test_staging_qualification_client_uses_active_slot_socket(tmp_path, monkeypatch):
    socket_path = tmp_path / "active.sock"
    socket_path.touch()
    monkeypatch.setenv("PWC_STAGING_ACTIVE_SOCKET", str(socket_path))
    seen = {}

    class Transport:
        def __init__(self, *, uds):
            seen["uds"] = uds

    class Client:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(qualification_http.httpx, "AsyncHTTPTransport", Transport)
    monkeypatch.setattr(qualification_http.httpx, "AsyncClient", Client)

    qualification_http.client(timeout=30, cookies={"session": "token"})

    assert seen["uds"] == str(socket_path)
    assert seen["base_url"] == "http://staging-active"
    assert seen["timeout"] == 30
    assert seen["cookies"] == {"session": "token"}
    assert seen["headers"] == {"Origin": "https://staging.paperswithcode.co"}


def test_qualification_scripts_do_not_reference_retired_fixed_port():
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    for name in (
        "qualify_chat_soak.py",
        "qualify_chat_pool.py",
        "qualify_chat_cutover.py",
    ):
        assert "127.0.0.1:8001" not in (scripts / name).read_text()


def test_pi_qualification_uses_persisted_scenario_taxonomy():
    source = (
        Path(__file__).resolve().parents[2] / "scripts" / "qualify_chat_pi.py"
    ).read_text()

    for retired_label in (
        '"paired_quality"',
        '"admin_new_chat"',
        '"admin_followup"',
        '"edit_retry"',
    ):
        assert retired_label not in source
    assert '"reliability"' in source
    assert '"forced_failure"' in source
    assert "prior_compute_exists is not None" in source
