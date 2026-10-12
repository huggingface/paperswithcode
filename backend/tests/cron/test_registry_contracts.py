"""Effective contracts captured before removing the registry migration overlays."""

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from backend.services.cron_registry import (
    SchedulePolicy,
    get_cron_job,
    list_cron_jobs,
    validate_cron_jobs,
)


def test_every_effective_scheduler_and_output_contract_is_preserved():
    expected = json.loads(
        (
            Path(__file__).parent / "fixtures" / "cron_effective_contracts.json"
        ).read_text()
    )
    actual = [
        {key: asdict(job)[key] for key in expected[0]} for job in list_cron_jobs()
    ]
    assert json.loads(json.dumps(actual)) == expected


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"scheduler": "unknown"}, "unknown scheduler"),
        ({"schedule_policies": ()}, "require schedule policies"),
        ({"schedule_grace_minutes": -1}, "grace must be nonnegative"),
        ({"output_evaluator": None}, "evaluator must be explicit"),
        ({"output_evaluator": " "}, "evaluator must be explicit"),
        ({"systemd_timer": None}, "require a timer/service pair"),
        ({"systemd_service": None}, "require a timer/service pair"),
        (
            {"systemd_extra_units": (("broken", "test.service"),)},
            "invalid timer/service",
        ),
        ({"schedule_policies": (SchedulePolicy("weekly"),)}, "invalid schedule policy"),
        ({"schedule_policies": (SchedulePolicy.fixed(0),)}, "invalid schedule policy"),
        (
            {"schedule_policies": (SchedulePolicy.daily(24, 0),)},
            "invalid schedule policy",
        ),
        (
            {"schedule_policies": (SchedulePolicy.weekly(7, 0, 0),)},
            "invalid schedule policy",
        ),
    ],
)
def test_incomplete_policies_fail_at_registry_validation(changes, message):
    job = replace(get_cron_job("update_citations"), **changes)
    with pytest.raises(ValueError, match=message):
        validate_cron_jobs((job,))


def test_duplicate_ids_are_rejected():
    job = get_cron_job("update_citations")
    with pytest.raises(ValueError, match="duplicate CRON job ID"):
        validate_cron_jobs((job, job))


def test_manual_and_github_schedules_with_generic_evaluators_are_valid():
    manual = get_cron_job("extract_urls")
    assert manual.scheduler == "manual"
    assert manual.output_evaluator == "generic"
    assert not manual.schedule_policies
    github = replace(
        manual,
        id="github-example",
        scheduler="github_actions",
        workflow_file="example.yml",
        schedule_policies=(SchedulePolicy.daily(1, 30),),
    )
    validate_cron_jobs((manual, github))
    assert github.evidence_contract.semantic_source == "unavailable"
    with pytest.raises(ValueError, match="require a workflow"):
        validate_cron_jobs((replace(github, workflow_file=None),))
    with pytest.raises(ValueError, match="cannot own systemd units"):
        validate_cron_jobs((replace(manual, systemd_timer="unexpected.timer"),))
