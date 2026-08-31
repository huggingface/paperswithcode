"""Run the sanitized labeled research-scope qualification set."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

from backend.config import get_settings
from backend.services.chat_scope_guardrail_service import (
    ScopeGuardrailService,
    ScopeMessage,
)

DEFAULT_DATASET = (
    Path(__file__).parents[1] / "tests/fixtures/chat_scope_qualification.jsonl"
)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, round((len(ordered) - 1) * percentile))
    return ordered[index]


async def qualify(path: Path) -> dict[str, object]:
    settings = get_settings()
    if not settings.chat_scope_guardrail_enabled:
        raise RuntimeError("PWC_CHAT_SCOPE_GUARDRAIL_ENABLED must be true")
    service = ScopeGuardrailService(settings)
    results: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        example = json.loads(line)
        started = time.perf_counter()
        decision = await service.classify(
            [ScopeMessage(**message) for message in example["messages"]]
        )
        latency_ms = (time.perf_counter() - started) * 1000
        results.append(
            {
                "id": example["id"],
                "label": example["label"],
                "decision": decision.decision,
                "provider": decision.provider,
                "attempts": decision.attempts,
                "fail_open": decision.fail_open,
                "latency_ms": round(latency_ms, 1),
                "timeout": any(
                    attempt.outcome == "TimeoutError"
                    for attempt in decision.attempt_records
                ),
                "attempt_records": [
                    {
                        "provider": attempt.provider,
                        "latency_ms": attempt.latency_ms,
                        "outcome": attempt.outcome,
                    }
                    for attempt in decision.attempt_records
                ],
            }
        )
    latencies = [float(result["latency_ms"]) for result in results]
    primary_latencies = [
        float(attempt["latency_ms"])
        for result in results
        for attempt in result["attempt_records"]
        if attempt["provider"] == "huggingface-baseten"
    ]
    fallback_latencies = [
        float(attempt["latency_ms"])
        for result in results
        for attempt in result["attempt_records"]
        if attempt["provider"] == "openai"
    ]
    total = len(results)
    return {
        "examples": total,
        "false_allow": sum(
            result["label"] == "block" and result["decision"] == "allow"
            for result in results
        ),
        "false_block": sum(
            result["label"] == "allow" and result["decision"] == "block"
            for result in results
        ),
        "p50_latency_ms": round(statistics.median(latencies), 1),
        "p95_latency_ms": round(_percentile(latencies, 0.95), 1),
        "glm_p50_latency_ms": round(statistics.median(primary_latencies), 1),
        "glm_p95_latency_ms": round(_percentile(primary_latencies, 0.95), 1),
        "fallback_p50_latency_ms": (
            round(statistics.median(fallback_latencies), 1)
            if fallback_latencies
            else None
        ),
        "fallback_p95_latency_ms": (
            round(_percentile(fallback_latencies, 0.95), 1)
            if fallback_latencies
            else None
        ),
        "timeout_rate": sum(bool(result["timeout"]) for result in results) / total,
        "retry_rate": sum(int(result["attempts"]) > 1 for result in results) / total,
        "fail_open_rate": sum(bool(result["fail_open"]) for result in results) / total,
        "provider_counts": {
            provider: sum(result["provider"] == provider for result in results)
            for provider in sorted({str(result["provider"]) for result in results})
        },
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(qualify(args.dataset)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
