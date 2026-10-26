"""The radar entrypoint logs queued signals after its session has closed."""

from types import SimpleNamespace

from backend.scripts import scan_model_releases as script


class _Session:
    def __init__(self):
        self.closed = False

    def commit(self):
        pass


class _Signal:
    """Mimic an ORM row whose attributes cannot load once the session closed."""

    def __init__(self, session, **fields):
        self._session = session
        self._fields = fields

    def __getattr__(self, name):
        if self._session.closed:
            raise RuntimeError("Instance is not bound to a Session")
        return self._fields[name]


def test_queued_signals_are_logged_after_the_session_closes(monkeypatch, caplog):
    db = _Session()

    def session_generator():
        yield db
        db.closed = True

    report = SimpleNamespace(
        to_dict=lambda: {}, unindexed=[], errors=[], sources_checked=1
    )
    signal = _Signal(
        db, lab="Moonshot", model_name="Kimi K3.1", lead_url="https://example.com"
    )
    dispatched = []
    monkeypatch.setattr(script, "get_database_session", session_generator)
    monkeypatch.setattr(script, "scan_model_releases", lambda *a, **k: report)
    monkeypatch.setattr(script, "get_settings", lambda: object())
    monkeypatch.setattr(script, "record_release_signals", lambda *a: None)
    monkeypatch.setattr(script, "queue_release_signals", lambda *a, **k: [signal])
    monkeypatch.setattr(
        script.codex_paper_job_service,
        "dispatch_next",
        lambda *a: dispatched.append(True),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["scan_model_releases", "--skip-artificial-analysis", "--skip-web-search"],
    )

    with caplog.at_level("INFO", logger="scan_model_releases"):
        assert script.main() == 0

    assert dispatched == [True]
    assert (
        'model_release_radar_queued {"lab": "Moonshot", "model": "Kimi K3.1", '
        '"url": "https://example.com"}' in caplog.text
    )
