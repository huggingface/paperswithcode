"""Run content-free aggregate and optional synthetic production chat probes."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta

from backend.config import get_settings
from backend.services.autonomous_cron_probe import FindingState
from backend.services.chat_reliability_probe import probe_chat_aggregates
from backend.services.chat_synthetic_probe import run_synthetic_chat


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Also run the paid dedicated-account lifecycle probe",
    )
    args = parser.parse_args()
    settings = get_settings()
    if settings.environment != "production":
        parser.error("chat reliability probes are production-only")
    now = datetime.now(UTC)
    findings = probe_chat_aggregates(timedelta(minutes=15), settings=settings, now=now)
    payload: dict[str, object] = {
        "environment": settings.environment,
        "release_id": settings.release_id,
        "observed_at": now.isoformat(),
        "findings": [finding.as_dict() for finding in findings],
    }
    states = {finding.state for finding in findings}
    if args.synthetic:
        synthetic = asyncio.run(run_synthetic_chat(settings.environment, now=now))
        payload["synthetic"] = synthetic.as_dict()
        states.add(synthetic.state)
    print(json.dumps(payload, sort_keys=True))
    return 0 if states <= {FindingState.HEALTHY} else 1


if __name__ == "__main__":
    raise SystemExit(main())
