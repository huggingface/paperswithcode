from types import SimpleNamespace

import pytest

from backend.scripts.qualify_chat_pool import (
    PoolQualification,
    PoolSample,
    arrival_offsets_ms,
    new_chat_payload,
    parser,
    qualification_passes,
    summarize,
)


def test_pool_qualification_summary_is_sanitized_and_reports_active_cost():
    samples = [
        PoolSample(
            request_id="00000000-0000-0000-0000-000000000001",
            acquisition_outcome="pool_hit",
            pool_lookup_ms=20,
            sdk_dispatch_ms=80,
            first_delta_ms=300,
            total_ms=500,
            estimated_active_cost_usd=0.00001,
            continuous_pool_interval=True,
            cleanup_confirmed=True,
            terminal_status="complete",
            error_code=None,
        ),
        PoolSample(
            request_id="00000000-0000-0000-0000-000000000002",
            acquisition_outcome="pool_hit",
            pool_lookup_ms=30,
            sdk_dispatch_ms=90,
            first_delta_ms=350,
            total_ms=550,
            estimated_active_cost_usd=0.00002,
            continuous_pool_interval=True,
            cleanup_confirmed=True,
            terminal_status="complete",
            error_code=None,
        ),
    ]

    result = summarize(samples)

    assert result["complete"] == 2
    assert result["pool_hits"] == 2
    assert result["continuous_pool_intervals"] == 2
    assert result["cleanup_confirmed"] == 2
    assert result["sdk_dispatch_ms"]["p95"] == 90
    assert result["estimated_active_cost_usd"] == {
        "total": 0.00003,
        "per_completed_turn": 0.000015,
    }


def test_pool_qualification_requires_an_immutable_release_directory():
    arguments = parser().parse_args(
        [
            "--samples",
            "1",
            "--candidate-cpu",
            "0.125",
            "--candidate-memory-mib",
            "512",
            "--admin-subject",
            "admin-subject",
            "--admin-username",
            "admin",
            "--qualification-owner",
            "operator:pi-qualification:pool-test",
            "--selected-model",
            "deepseek-ai/DeepSeek-V4-Flash-0731",
            "--release-dir",
            "/srv/paperswithcode/environments/staging/current",
            "--confirm",
            "QUALIFY_STAGING_CHAT_POOL",
        ]
    )

    assert arguments.release_dir.name == "current"


def test_pool_qualification_rejects_non_pi_new_session_runtime():
    settings = SimpleNamespace(
        environment="staging",
        chat_persistent_worker_enabled=True,
        chat_blank_pool_enabled=True,
        chat_default_agent_harness="claude",
        chat_new_session_pi_percentage=0,
        chat_sandbox_cpu=0.5,
        chat_sandbox_memory_mib=512,
        chat_model_routes={
            "deepseek-ai/DeepSeek-V4-Flash-0731": ("deepseek/deepseek-v4-flash-0731")
        },
        chat_pi_prewarm_model="deepseek/deepseek-v4-flash-0731",
    )
    qualification = PoolQualification(
        settings=settings,
        billing_settings=settings,
        samples=200,
        blank_timeout=90,
        arrival_concurrency=2,
        interarrival_ms=750,
        admin_subject="admin",
        admin_username="operator",
        qualification_owner="operator:pi-qualification:test",
        selected_model="deepseek-ai/DeepSeek-V4-Flash-0731",
        arrival_profile="fixed",
    )

    with pytest.raises(ValueError, match="all new staging sessions to use Pi"):
        qualification.validate(cpu=0.5, memory_mib=512)


def test_pool_qualification_submits_a_real_new_chat():
    payload = new_chat_payload(
        selected_model="deepseek-ai/DeepSeek-V4-Flash-0731",
        reasoning_effort="low",
    )

    assert "session_id" not in payload
    assert payload["initial_model"] == "deepseek-ai/DeepSeek-V4-Flash-0731"
    assert payload["reasoning_effort"] == "low"


def test_production_arrival_profile_preserves_bounded_bursts():
    offsets = arrival_offsets_ms(
        samples=200,
        interarrival_ms=750,
        profile="production-7d-v1",
    )
    gaps = [right - left for left, right in zip(offsets, offsets[1:])]

    assert len(offsets) == 200
    assert sum(gap <= 15_000 for gap in gaps) == 9
    assert min(gaps) == 10_000
    assert max(gaps) == 30_000
    assert (
        max(
            sum(start <= value <= start + 15_000 for value in offsets)
            for start in offsets
        )
        == 2
    )
    assert (
        max(
            sum(start <= value <= start + 30_000 for value in offsets)
            for start in offsets
        )
        == 3
    )


def test_pool_gate_allows_explicit_cold_misses_below_five_percent():
    summary = {
        "complete": 200,
        "hit_rate": 0.955,
        "pool_hits": 191,
        "continuous_pool_intervals": 191,
        "cleanup_confirmed": 200,
        "assignment_to_dispatch_ms": {"count": 191, "p50": 800, "p90": 1200},
    }

    assert qualification_passes(
        samples=200,
        summary=summary,
        blank_starts=191,
        marked=200,
    )
    summary["continuous_pool_intervals"] = 190
    assert not qualification_passes(
        samples=200,
        summary=summary,
        blank_starts=191,
        marked=200,
    )
