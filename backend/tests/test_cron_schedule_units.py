"""Consistency contracts between the registry, the schedule table, and the
committed systemd units in deploy/systemd/cron/."""

from __future__ import annotations

import importlib.util
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.services.cron_health import discover_scheduled_duties
from backend.services.cron_registry import list_cron_jobs

ROOT = Path(__file__).resolve().parents[2]
UNIT_DIR = ROOT / "deploy" / "systemd" / "cron"


def _load_deploy_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "deploy" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(ROOT / "deploy"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(ROOT / "deploy"))
    return module


cron_schedules = _load_deploy_module("cron_schedules")
generate_cron_units = _load_deploy_module("generate_cron_units")
cron_throttle = _load_deploy_module("cron_throttle")


def _systemd_jobs():
    return [
        job
        for job in list_cron_jobs()
        if job.scheduler == "systemd" and job.id != "process_curation_thumbnails"
        if job.id not in {"monitor_chat_operational_alerts", "review_submissions"}
    ]


def test_generated_units_match_the_schedule_table():
    for spec in cron_schedules.TIMERS:
        service = UNIT_DIR / f"{spec.unit}.service"
        timer = UNIT_DIR / f"{spec.unit}.timer"
        assert service.is_file(), f"missing committed unit {service.name}"
        assert timer.is_file(), f"missing committed unit {timer.name}"
        assert service.read_text() == generate_cron_units.render_service(spec)
        assert timer.read_text() == generate_cron_units.render_timer(spec)
    expected = {
        f"{spec.unit}{suffix}"
        for spec in cron_schedules.TIMERS
        for suffix in (".service", ".timer")
    }
    assert {path.name for path in UNIT_DIR.iterdir()} == expected


def test_every_migrated_registry_job_owns_committed_unit_pairs():
    for job in _systemd_jobs():
        pairs = job.systemd_unit_pairs
        assert pairs, f"{job.id} has no systemd units"
        for timer_unit, service_unit in pairs:
            assert (UNIT_DIR / timer_unit).is_file(), f"{job.id}: missing {timer_unit}"
            assert (UNIT_DIR / service_unit).is_file(), (
                f"{job.id}: missing {service_unit}"
            )
            source = (UNIT_DIR / service_unit).read_text()
            match = re.search(
                r"^ExecStart=.*/pwc-cron-throttled\s+([a-z0-9_]+)", source, re.M
            )
            assert match and match.group(1) == job.id


def _calendar_matches(calendar: str, moment: datetime) -> bool:
    """Match the restricted OnCalendar grammar used by the generated timers."""

    parts = calendar.split()
    if len(parts) == 3:
        weekday, _date, clock = parts
        if moment.strftime("%a") != weekday:
            return False
    else:
        _date, clock = parts
    hour_spec, minute_spec, _second = clock.split(":")

    def field_matches(spec: str, value: int) -> bool:
        if spec == "*":
            return True
        if "/" in spec:
            start, step = spec.split("/")
            return value >= int(start) and (value - int(start)) % int(step) == 0
        return value == int(spec)

    return field_matches(hour_spec, moment.hour) and field_matches(
        minute_spec, moment.minute
    )


def _policy_matches(policy, moment: datetime) -> bool:
    previous, _upcoming = policy.slots(moment)
    return previous == moment


def test_unit_calendars_cover_every_registry_schedule_policy():
    specs_by_job: dict[str, list] = {}
    for spec in cron_schedules.TIMERS:
        specs_by_job.setdefault(spec.job, []).append(spec)

    # A Monday-through-Sunday UTC week, minute resolution.
    start = datetime(2026, 8, 24, tzinfo=timezone.utc)
    week = [start + timedelta(minutes=offset) for offset in range(7 * 24 * 60)]

    for job in _systemd_jobs():
        calendars = [
            calendar for spec in specs_by_job[job.id] for calendar in spec.on_calendar
        ]
        for policy in job.schedule_policies:
            uncovered = [
                moment
                for moment in week
                if _policy_matches(policy, moment)
                and not any(
                    _calendar_matches(calendar, moment) for calendar in calendars
                )
            ]
            assert not uncovered, (
                f"{job.id}: policy {policy} slot {uncovered[0]} is not covered "
                f"by unit calendars {calendars}"
            )


def test_discovery_includes_all_scheduled_duties():
    duties = discover_scheduled_duties()
    scheduled = {
        job.id
        for job in list_cron_jobs()
        if job.scheduler in {"github_actions", "systemd"}
    }
    assert scheduled <= duties | {"extract_urls"}
    missing = {
        job.id
        for job in list_cron_jobs()
        if job.scheduler == "systemd" and job.id not in duties
    }
    assert not missing, f"systemd duties missing from discovery: {missing}"


def test_no_cron_workflow_keeps_a_schedule_trigger():
    for workflow in (ROOT / ".github" / "workflows").glob("cron-*.yml"):
        source = workflow.read_text()
        if "pwc-cron" not in source:
            continue
        assert not re.search(r"^  schedule:\s*$", source, re.M), (
            f"{workflow.name} still has a schedule trigger"
        )


def test_throttle_bounds_concurrency_and_propagates_exit_code(tmp_path, monkeypatch):
    first = cron_throttle.acquire_slot(tmp_path, 1, 0)
    assert first is not None
    second = cron_throttle.acquire_slot(tmp_path, 1, 0)
    assert second is None
    first.close()
    third = cron_throttle.acquire_slot(tmp_path, 1, 0)
    assert third is not None
    third.close()

    monkeypatch.setenv("PWC_CRON_SLOT_DIR", str(tmp_path))
    monkeypatch.setenv("PWC_CRON_THROTTLE_SLOTS", "2")
    completed = type("Completed", (), {"returncode": 7})()
    with patch.object(cron_throttle.subprocess, "run", return_value=completed) as run:
        monkeypatch.setattr(sys, "argv", ["pwc-cron-throttled", "update_citations"])
        assert cron_throttle.main() == 7
    run.assert_called_once_with(
        ["/usr/local/sbin/pwc-cron", "update_citations"], check=False
    )


def test_throttle_requires_a_job_argument(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["pwc-cron-throttled"])
    assert cron_throttle.main() == 2


@pytest.mark.parametrize(
    "job_id,expected_after",
    [
        ("calculate_trending_scores", "pwc-cron-update-github-stars.service"),
        ("calculate_paper_trending_scores", "pwc-cron-update-hf-artifacts.service"),
        ("refresh_paper_embeddings", "pwc-cron-import-hf-daily-papers.service"),
        ("mirror_thumbnails_to_disk", "pwc-cron-preload-thumbnails-recent.service"),
        (
            "link_papers_by_task_keywords",
            "pwc-cron-link-methods-by-references.service",
        ),
    ],
)
def test_producer_chains_declare_storm_ordering(job_id, expected_after):
    unit = "pwc-cron-" + job_id.replace("_", "-")
    source = (UNIT_DIR / f"{unit}.service").read_text()
    assert expected_after in source
