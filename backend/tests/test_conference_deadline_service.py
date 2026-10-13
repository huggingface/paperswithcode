"""Conference deadline parsing, guarded writer, sweeps and agent helpers.

No live PostgreSQL: the planner is pure, and the writer runs against SQLite.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.config import Settings
from backend.models.database import (
    CatalogMutationEvent,
    CatalogMutationIdempotency,
    Conference,
    ConferenceDeadline,
    ConferenceDeadlineSweep,
)
from backend.services import catalog_mutation_service
from backend.services import conference_deadline_agent as agent
from backend.services import conference_deadline_service as service
from backend.services import conference_deadline_sweep_service as sweeps
from backend.services.conference_deadline_service import (
    AdminEditionDeadlines,
    DeadlineState,
    DeadlineValidationError,
    EditionChange,
    EditionState,
    SeriesChangeSet,
    SeriesState,
    build_yaml_deadlines,
    canonical_timezone,
    parse_deadline_instant,
    plan_edition_change,
    select_sweep_series,
    series_manifest,
    year_labels,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint(_type, _compiler, **_kwargs):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kwargs):
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array(_type, _compiler, **_kwargs):
    return "TEXT"


NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
UTC = timezone.utc
SOURCE = "https://cvpr.thecvf.com/Conferences/2027"


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def deadline(id_, type_, when, label=None, tz="AoE"):
    return DeadlineState(
        id=id_,
        type=type_,
        label=label or type_.title(),
        deadline_at=at(when),
        timezone=tz,
    )


def cvpr_series(**overrides) -> SeriesState:
    past = EditionState(
        slug="cvpr-2026",
        year=2026,
        conference_id=1,
        short_name="CVPR",
        start_date=date(2026, 6, 3),
        end_date=date(2026, 6, 7),
        tier="a",
        deadlines=[
            deadline(10, "abstract", "2025-11-08 11:59:59"),
            deadline(11, "paper", "2025-11-15 11:59:59"),
        ],
    )
    editions = overrides.pop("editions", [past])
    return SeriesState(
        series="cvpr", title="CVPR", tier="a", tags=None, editions=editions, **overrides
    )


def neurips_series() -> SeriesState:
    upcoming = EditionState(
        slug="neurips-2027",
        year=2027,
        conference_id=2,
        short_name="NeurIPS",
        start_date=date(2027, 12, 5),
        end_date=date(2027, 12, 11),
        deadlines=[
            deadline(20, "abstract", "2027-05-10 11:59:59", "Abstract Submission"),
            deadline(21, "paper", "2027-05-17 11:59:59", "Paper Submission"),
            deadline(22, "notification", "2026-09-30 11:59:59", "Old notification"),
        ],
    )
    return SeriesState(
        series="neurips", title="NeurIPS", tier="a", tags=None, editions=[upcoming]
    )


# --- Parsing ----------------------------------------------------------------


def test_parse_deadline_instant_handles_aoe_offsets_and_iana():
    assert parse_deadline_instant("2026-11-13 23:59:59", "AoE") == at(
        "2026-11-14 11:59:59"
    )
    assert parse_deadline_instant("2026-11-13 23:59", "UTC−7") == at(
        "2026-11-14 06:59:00"
    )
    assert parse_deadline_instant("2026-01-01", "Europe/London") == at(
        "2026-01-01 00:00:00"
    )
    assert parse_deadline_instant("TBD", "AoE") is None
    assert parse_deadline_instant("garbage", "AoE") is None


def test_canonical_timezone_spells_aoe_and_rejects_ambiguous_values():
    assert canonical_timezone("UTC-12") == "AoE"
    assert canonical_timezone("aoe") == "AoE"
    assert canonical_timezone("America/Los_Angeles") == "America/Los_Angeles"
    with pytest.raises(DeadlineValidationError):
        canonical_timezone("UTC+12")
    with pytest.raises(DeadlineValidationError):
        canonical_timezone("Mars/Olympus")


def test_build_yaml_deadlines_merges_legacy_fields_and_dedupes_instants():
    block = {
        "timezone": "AoE",
        "deadline": "2026-05-15 23:59:59",
        "abstract_deadline": "2026-05-08 23:59:59",
        "deadlines": [
            {"type": "submission", "label": "Paper", "date": "2026-05-15 23:59:59"},
            {
                "type": "rebuttal_start",
                "label": "Rebuttal",
                "date": "2026-07-01 23:59:59",
            },
        ],
    }
    built = build_yaml_deadlines(block)
    assert [d["type"] for d in built] == ["submission", "rebuttal_start", "abstract"]
    assert built[0]["deadline_at"] == at("2026-05-16 11:59:59")


def test_change_set_normalizes_types_and_dates():
    change = SeriesChangeSet.model_validate(
        {
            "requires_update": True,
            "editions": [
                {
                    "year": 2027,
                    "source_urls": [SOURCE],
                    "deadlines": [
                        {
                            "type": "Camera-Ready",
                            "label": "CR",
                            "date": "2027-04-01 23:59",
                        }
                    ],
                }
            ],
        }
    )
    item = change.editions[0].deadlines[0]
    assert (item.type, item.date) == ("camera_ready", "2027-04-01 23:59:00")
    with pytest.raises(ValueError):
        SeriesChangeSet.model_validate(
            {
                "requires_update": True,
                "editions": [
                    {
                        "year": 2027,
                        "deadlines": [{"type": "paper", "label": "P", "date": "Nov 7"}],
                    }
                ],
            }
        )


# --- Labels, manifests, selection ------------------------------------------


def test_year_labels_mark_the_missing_next_edition():
    labels = year_labels(cvpr_series(), NOW.date())
    assert labels == {2026: "PAST", 2027: "MISSING_NEXT_YEAR"}
    manifest = series_manifest(cvpr_series(), NOW.date())
    assert manifest["year_labels"] == {"2026": "PAST", "2027": "MISSING_NEXT_YEAR"}
    assert manifest["editions"][0]["deadlines"][0] == {
        "type": "abstract",
        "label": "Abstract",
        "date": "2025-11-07 23:59:59",
        "timezone": "AoE",
    }


def test_biennial_series_expects_the_next_edition_two_years_later():
    iccv = SeriesState(
        series="iccv",
        title="ICCV",
        tier="a",
        tags=None,
        editions=[
            EditionState(
                slug="iccv-2023",
                year=2023,
                end_date=date(2023, 10, 6),
                deadlines=[deadline(1, "paper", "2023-03-08 23:59:59")],
            ),
            EditionState(
                slug="iccv-2025",
                year=2025,
                end_date=date(2025, 10, 23),
                deadlines=[deadline(2, "paper", "2025-03-08 23:59:59")],
            ),
        ],
    )
    assert iccv.cadence_years() == 2
    assert year_labels(iccv, NOW.date())[2027] == "MISSING_NEXT_YEAR"
    assert iccv.expected_next_deadline().year == 2027


def test_weekly_selection_puts_missing_top_tier_editions_first():
    imminent = neurips_series()
    imminent.editions[0].deadlines = [deadline(30, "paper", "2026-11-20 11:59:59")]
    far = neurips_series()
    far.series = "far"
    selected = select_sweep_series(
        [far, imminent, cvpr_series()], mode="weekly", now=NOW, limit=5
    )
    assert [s.series for s in selected] == ["cvpr", "neurips"]
    daily = select_sweep_series(
        [far, imminent, cvpr_series()], mode="daily", now=NOW, limit=5
    )
    assert [s.series for s in daily] == ["cvpr"]


# --- Guarded planner ---------------------------------------------------------


def plan(series, edition: dict):
    change = EditionChange.model_validate({"source_urls": [SOURCE], **edition})
    return plan_edition_change(series, change, fallback_sources=[], now=NOW)


def test_new_edition_is_created_with_series_metadata_and_sources():
    result = plan(
        cvpr_series(),
        {
            "year": 2027,
            "start_date": "2027-06-12",
            "end_date": "2027-06-18",
            "city": "Denver",
            "country": "USA",
            "deadlines": [
                {
                    "type": "abstract",
                    "label": "Abstract",
                    "date": "2026-11-06 23:59:59",
                    "timezone": "AoE",
                },
                {
                    "type": "paper",
                    "label": "Paper",
                    "date": "2026-11-13 23:59:59",
                    "timezone": "UTC-12",
                },
            ],
        },
    )
    assert result.create and not result.rejections
    assert result.new_edition["name"] == "CVPR 2027"
    assert result.new_edition["tier"] == "a"
    assert result.new_edition["location"] == "Denver, USA"
    assert [c.kind for c in result.changes] == [
        "create_edition",
        "add_deadline",
        "add_deadline",
    ]
    assert result.changes[2].after["timezone"] == "AoE"
    assert result.source_urls == [SOURCE]


def test_past_editions_are_immutable():
    result = plan(
        cvpr_series(),
        {
            "year": 2026,
            "deadlines": [
                {
                    "type": "paper",
                    "label": "Paper",
                    "date": "2025-11-20 23:59:59",
                    "timezone": "AoE",
                }
            ],
        },
    )
    assert result.changes == []
    assert "already taken place" in result.rejections[0]


def test_every_edition_needs_a_source_url():
    change = EditionChange.model_validate({"year": 2027, "deadlines": []})
    result = plan_edition_change(
        cvpr_series(), change, fallback_sources=["not a url"], now=NOW
    )
    assert result.rejections == ["no source URL supports this edition"]


def test_deadline_extension_updates_with_before_and_after():
    result = plan(
        neurips_series(),
        {
            "year": 2027,
            "deadlines": [
                {
                    "type": "paper",
                    "label": "Paper Submission",
                    "date": "2027-05-22 23:59:59",
                    "timezone": "AoE",
                },
                {
                    "type": "abstract",
                    "label": "Abstract Submission",
                    "date": "2027-05-09 23:59:59",
                    "timezone": "AoE",
                },
            ],
        },
    )
    assert not result.rejections
    assert [(c.kind, c.deadline_id) for c in result.changes] == [
        ("update_deadline", 21)
    ]
    change = result.changes[0]
    assert change.before["deadline_at"] == "2027-05-17T11:59:59+00:00"
    assert change.after["deadline_at"] == "2027-05-23T11:59:59+00:00"


def test_past_deadlines_and_moves_into_the_past_are_rejected():
    result = plan(
        neurips_series(),
        {
            "year": 2027,
            "deadlines": [
                {
                    "type": "notification",
                    "label": "Old notification",
                    "date": "2026-10-30 23:59:59",
                    "timezone": "AoE",
                },
                {
                    "type": "paper",
                    "label": "Paper Submission",
                    "date": "2026-10-01 23:59:59",
                    "timezone": "AoE",
                },
            ],
        },
    )
    assert result.changes == []
    assert "is immutable" in result.rejections[0]
    assert "into the past" in result.rejections[1]


def test_implausible_shifts_and_out_of_cycle_dates_are_rejected():
    result = plan(
        neurips_series(),
        {
            "year": 2027,
            "deadlines": [
                {
                    "type": "paper",
                    "label": "Paper Submission",
                    "date": "2027-11-30 23:59:59",
                    "timezone": "AoE",
                },
                {
                    "type": "camera_ready",
                    "label": "Camera ready",
                    "date": "2029-01-05 23:59:59",
                    "timezone": "AoE",
                },
            ],
        },
    )
    assert result.changes == []
    assert "implausibly large" in result.rejections[0]
    assert "outside the 2027 cycle" in result.rejections[1]


def test_omitted_deadlines_are_never_deleted_and_duplicates_skipped():
    result = plan(
        neurips_series(),
        {
            "year": 2027,
            "deadlines": [
                # Same instant as the existing paper deadline under another type.
                {
                    "type": "submission",
                    "label": "Full paper",
                    "date": "2027-05-16 23:59:59",
                    "timezone": "AoE",
                },
                {
                    "type": "rebuttal_start",
                    "label": "Rebuttal",
                    "date": "2027-08-01 23:59:59",
                    "timezone": "AoE",
                },
            ],
        },
    )
    assert [c.kind for c in result.changes] == ["add_deadline"]
    assert result.changes[0].after["type"] == "rebuttal_start"


def test_metadata_corrections_are_logged_per_field():
    result = plan(
        neurips_series(),
        {
            "year": 2027,
            "venue": "Convention Centre",
            "end_date": "2027-12-12",
            "deadlines": [],
        },
    )
    assert [(c.field, c.before, c.after) for c in result.changes] == [
        ("end_date", "2027-12-11", "2027-12-12"),
        ("venue", None, "Convention Centre"),
    ]


# --- Writer and admin edits (SQLite) -------------------------------------------


@pytest.fixture
def db(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    for model in (
        Conference,
        ConferenceDeadline,
        ConferenceDeadlineSweep,
        CatalogMutationEvent,
        CatalogMutationIdempotency,
    ):
        model.__table__.create(engine)
    monkeypatch.setattr(
        catalog_mutation_service,
        "get_settings",
        lambda: Settings(environment="production", release_id="test-release"),
    )
    with Session(engine) as session:
        session.add(
            Conference(
                id=2,
                slug="neurips-2027",
                name="NeurIPS 2027",
                short_name="NeurIPS",
                year=2027,
                end_date=date(2027, 12, 11),
            )
        )
        session.add_all(
            [
                ConferenceDeadline(
                    id=20,
                    conference_id=2,
                    deadline_type="abstract",
                    label="Abstract Submission",
                    deadline_at=at("2027-05-10 11:59:59"),
                    timezone="AoE",
                ),
                ConferenceDeadline(
                    id=21,
                    conference_id=2,
                    deadline_type="paper",
                    label="Paper Submission",
                    deadline_at=at("2027-05-17 11:59:59"),
                    timezone="AoE",
                ),
            ]
        )
        session.commit()
        yield session


def stored(db, slug):
    row = db.query(Conference).filter(Conference.slug == slug).one()
    return row, sorted(
        (d.deadline_type, d.deadline_at.replace(tzinfo=UTC)) for d in row.deadlines
    )


def test_writer_applies_plans_atomically_with_audit_events(db):
    series = neurips_series()
    series.editions[0].deadlines = series.editions[0].deadlines[:2]
    edition_plan = plan(
        series,
        {
            "year": 2027,
            "city": "Sydney",
            "deadlines": [
                {
                    "type": "paper",
                    "label": "Paper Submission",
                    "date": "2027-05-22 23:59:59",
                    "timezone": "AoE",
                },
                {
                    "type": "notification",
                    "label": "Notification",
                    "date": "2027-09-25 23:59:59",
                    "timezone": "AoE",
                },
            ],
        },
    )
    new_plan = plan(
        series,
        {
            "year": 2028,
            "deadlines": [
                {
                    "type": "paper",
                    "label": "Paper",
                    "date": "2028-05-15 23:59:59",
                    "timezone": "AoE",
                },
            ],
        },
    )
    for item in (edition_plan, new_plan):
        assert service.apply_edition_plan(db, item, request_id="test")

    row, deadlines = stored(db, "neurips-2027")
    assert (row.city, row.location) == ("Sydney", "Sydney")
    assert deadlines == [
        ("abstract", at("2027-05-10 11:59:59")),
        ("notification", at("2027-09-26 11:59:59")),
        ("paper", at("2027-05-23 11:59:59")),
    ]
    created, created_deadlines = stored(db, "neurips-2028")
    assert (created.name, created.short_name, created.year) == (
        "NeurIPS 2028",
        "NeurIPS",
        2028,
    )
    assert created_deadlines == [("paper", at("2028-05-16 11:59:59"))]

    events = (
        db.query(CatalogMutationEvent).order_by(CatalogMutationEvent.created_at).all()
    )
    assert [(e.operation, e.entity_id, e.actor_username) for e in events] == [
        ("deadline_agent_update", "neurips-2027", "conference-deadline-agent"),
        ("deadline_agent_create", "neurips-2028", "conference-deadline-agent"),
    ]
    paper_before = [
        d for d in events[0].before_snapshot["deadlines"] if d["type"] == "paper"
    ]
    assert paper_before[0]["deadline_at"].startswith("2027-05-17")
    assert events[1].before_snapshot is None


def test_writer_skips_plans_without_accepted_changes(db):
    empty = plan(neurips_series(), {"year": 2027, "deadlines": []})
    assert not service.apply_edition_plan(db, empty, request_id="test")
    assert db.query(CatalogMutationEvent).count() == 0


def test_admin_replace_edition_replaces_the_list_and_creates_editions(db):
    admin = {
        "actor": {"hf_subject": "u1", "username": "niels", "role": "admin"},
        "request_id": "r1",
    }
    body = AdminEditionDeadlines.model_validate(
        {
            "deadlines": [
                {
                    "type": "paper",
                    "label": "Paper Submission",
                    "date": "2027-05-20 23:59",
                    "timezone": "AoE",
                },
            ]
        }
    )
    after = service.admin_replace_edition(db, "neurips-2027", body, context=admin)
    assert [d["type"] for d in after["deadlines"]] == ["paper"]
    assert stored(db, "neurips-2027")[1] == [("paper", at("2027-05-21 11:59:00"))]

    with pytest.raises(DeadlineValidationError):
        service.admin_replace_edition(db, "iclr-2028", body, context=admin)
    created = AdminEditionDeadlines.model_validate(
        {**body.model_dump(), "short_name": "ICLR"}
    )
    service.admin_replace_edition(db, "iclr-2028", created, context=admin)
    assert stored(db, "iclr-2028")[0].name == "ICLR 2028"
    assert (
        db.query(CatalogMutationEvent).filter_by(operation="replace_deadlines").count()
        == 2
    )


def test_admin_endpoint_is_admin_only(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.database.connection import get_database_session
    from backend.main import create_app
    from backend.utils.auth import fresh_catalog_mutation_context

    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: iter([None])
    app.dependency_overrides[fresh_catalog_mutation_context] = lambda: {
        "actor": {"hf_subject": "c", "username": "c", "role": "contributor"},
        "request_id": "r",
    }
    response = TestClient(app).put(
        "/api/v1/conferences/cvpr-2027/deadlines", json={"deadlines": []}
    )
    assert response.status_code == 403


# --- Sweeps ----------------------------------------------------------------------


class FakeApi:
    def __init__(self, stage="COMPLETED", lines=()):
        self.stage = stage
        self.lines = list(lines)
        self.launched = []

    def run_job(self, **kwargs):
        self.launched.append(kwargs)
        return SimpleNamespace(id="job-1")

    def inspect_job(self, **_kwargs):
        return SimpleNamespace(status=SimpleNamespace(stage=self.stage))

    def fetch_job_logs(self, **_kwargs):
        return iter(self.lines)


def sweep_settings():
    return Settings(
        codex_jobs_namespace="pwc",
        codex_jobs_token="hf_x",
        conference_deadlines_anthropic_api_key="sk-test",
    )


def test_job_command_runs_the_worker_as_a_non_root_user():
    command = sweeps.job_command("0.2.115")
    assert command[:2] == ["bash", "-c"]
    assert "claude-agent-sdk==0.2.115" in command[2]
    assert "su agent -c" in command[2]


def test_missing_credentials_fail_loudly():
    with pytest.raises(sweeps.SweepConfigurationError, match="ANTHROPIC"):
        sweeps.job_credentials(
            Settings(codex_jobs_namespace="pwc", codex_jobs_token="t")
        )


def test_launch_ships_worker_and_manifest_without_db_credentials(db):
    api = FakeApi()
    runner = sweeps.ConferenceDeadlineSweeps(db, sweep_settings(), api)
    manifest = series_manifest(cvpr_series(), NOW.date())
    sweep = runner.launch("weekly", [manifest], now=NOW)
    assert (sweep.status, sweep.hf_job_id, sweep.series) == (
        "running",
        "job-1",
        ["cvpr"],
    )
    job = api.launched[0]
    assert job["secrets"] == {"ANTHROPIC_API_KEY": "sk-test"}
    assert job["labels"]["workflow"] == "conference-deadlines"
    assert "PWC_DB_PASSWORD" not in job["env"]
    payload = agent.decode_payload(job["env"]["PWC_DEADLINE_MANIFEST"])
    assert payload["num_retrieval_agents"] == 3 and payload["series"] == [manifest]
    source = agent.decode_payload_text(job["env"]["PWC_DEADLINE_AGENT_SOURCE"])
    assert "RESULT_MARKER" in source and "from backend" not in source


def test_collect_applies_valid_results_and_records_the_sweep(db, monkeypatch):
    sweep = ConferenceDeadlineSweep(
        mode="weekly",
        status="running",
        hf_job_id="job-1",
        series=["neurips", "cvpr"],
        launched_at=NOW,
    )
    db.add(sweep)
    db.commit()
    calls = []

    def fake_apply(_db, series, change_set, **kwargs):
        calls.append((series, change_set.editions[0].year, kwargs["dry_run"]))
        series_state = neurips_series()
        series_state.editions[0].deadlines = series_state.editions[0].deadlines[:2]
        return [
            plan_edition_change(
                series_state, change_set.editions[0], fallback_sources=[], now=NOW
            )
        ]

    monkeypatch.setattr(sweeps, "apply_series_change_set", fake_apply)
    change_set = {
        "requires_update": True,
        "reasoning": "CFP out",
        "source_urls": [SOURCE],
        "editions": [
            {
                "year": 2027,
                "source_urls": [SOURCE],
                "deadlines": [
                    {
                        "type": "rebuttal_start",
                        "label": "Rebuttal",
                        "date": "2027-08-01 23:59:59",
                        "timezone": "AoE",
                    }
                ],
            }
        ],
    }
    lines = [
        "noise",
        agent.encode_result_line(
            {
                "series": "neurips",
                "status": "proposed",
                "change_set": change_set,
                "total_cost_usd": 1.25,
            }
        ),
        agent.encode_result_line(
            {
                "series": "cvpr",
                "status": "no_changes",
                "total_cost_usd": 0.5,
                "reasoning": "CFP not out",
            }
        ),
        f"{agent.DONE_MARKER} 2",
    ]
    runner = sweeps.ConferenceDeadlineSweeps(db, sweep_settings(), FakeApi(lines=lines))
    [report] = runner.collect(now=NOW)
    assert calls == [("neurips", 2027, False)]
    assert report["status"] == "applied" and report["changes_applied"] == 1
    db.refresh(sweep)
    assert (sweep.status, sweep.changes_applied, float(sweep.cost_usd)) == (
        "applied",
        1,
        1.75,
    )
    assert (
        sweep.results["series"][0]["editions"][0]["changes"][0]["kind"]
        == "add_deadline"
    )


def test_partial_or_invalid_results_fail_the_sweep(db):
    sweep = ConferenceDeadlineSweep(
        mode="daily",
        status="running",
        hf_job_id="job-1",
        series=["neurips", "cvpr"],
        launched_at=NOW,
    )
    db.add(sweep)
    db.commit()
    lines = [
        agent.encode_result_line(
            {
                "series": "neurips",
                "status": "proposed",
                "change_set": {"requires_update": "maybe"},
            }
        )
    ]
    runner = sweeps.ConferenceDeadlineSweeps(
        db, sweep_settings(), FakeApi(stage="ERROR", lines=lines)
    )
    [report] = runner.collect(now=NOW)
    assert report["status"] == "failed"
    assert report["missing_series"] == ["cvpr"]
    assert report["series"][0]["status"] == "invalid"


def test_running_jobs_are_left_alone_until_terminal(db):
    db.add(
        ConferenceDeadlineSweep(
            mode="weekly",
            status="running",
            hf_job_id="job-1",
            series=["cvpr"],
            launched_at=NOW,
        )
    )
    db.commit()
    runner = sweeps.ConferenceDeadlineSweeps(
        db, sweep_settings(), FakeApi(stage="RUNNING")
    )
    assert runner.collect(now=NOW + timedelta(hours=1)) == []
    assert runner.running()[0].status == "running"


# --- Agent helpers (no SDK) ----------------------------------------------------


def test_tool_budget_nudges_on_the_last_search_then_denies():
    state = agent.ToolBudgetState(max_turns=3)
    assert state.on_post_tool_use("WebSearch") is None
    assert state.on_post_tool_use("Read") is None
    assert state.on_post_tool_use("WebFetch") == agent.BUDGET_EXHAUSTED_MESSAGE
    assert state.should_deny_pre_tool_use("mcp__exa__search")
    assert not state.should_deny_pre_tool_use("StructuredOutput")


def test_short_circuit_distinguishes_timeouts_from_no_changes():
    timed_out = agent.retrieval_short_circuit([{"status": "timeout"}, {}], 0.3)
    assert timed_out["status"] == "timeout" and timed_out["skipped_aggregation"]
    quiet = agent.retrieval_short_circuit(
        [{"requires_update": False, "reasoning": "CFP not published yet"}, {}], 0.2
    )
    assert (quiet["status"], quiet["reasoning"]) == (
        "no_changes",
        "CFP not published yet",
    )
    assert agent.any_proposed_update([{}, {"requires_update": True}])
    assert not agent.all_agree_update([{"requires_update": True}, {}])


def test_stage_limits_and_wall_clock_overrides():
    assert agent.stage_limits("retrieval", {}) == (12, 1.5)
    assert agent.stage_limits("aggregation", {"AGENT_MAX_TURNS": "5"}) == (5, 1.0)
    assert agent.agent_wall_clock_seconds("retrieval", {}) == 300.0
    assert (
        agent.agent_wall_clock_seconds(
            "retrieval", {"RETRIEVAL_WALL_CLOCK_SECONDS": "0"}
        )
        is None
    )


def test_result_lines_round_trip_and_year_labels_render():
    line = agent.encode_result_line({"series": "cvpr", "status": "no_changes"})
    assert agent.decode_result_lines(["2026-10-13T00:00:00Z " + line]) == [
        {"series": "cvpr", "status": "no_changes"}
    ]
    rendered = agent.format_year_labels(series_manifest(cvpr_series(), NOW.date()))
    assert "- 2027: MISSING_NEXT_YEAR" in rendered and "today: 2026-10-13" in rendered
    with pytest.raises(ValueError):
        agent.pipeline_result(status="pushed")


def test_change_set_schema_matches_the_validator():
    deadline_schema = agent.CHANGE_SET_SCHEMA["properties"]["editions"]["items"]
    enum = deadline_schema["properties"]["deadlines"]["items"]["properties"]["type"][
        "enum"
    ]
    assert tuple(enum) == service.AGENT_DEADLINE_TYPES
