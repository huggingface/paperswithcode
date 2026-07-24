#!/usr/bin/env python3
"""Static cross-environment safety checks for checked-in nginx templates."""

from __future__ import annotations

import argparse
from pathlib import Path


def validate(production: str, staging: str) -> list[str]:
    failures: list[str] = []
    if "pwc_staging_backend" in production or "127.0.0.1:8001" in production:
        failures.append("production references staging backend")
    if "pwc_production_backend" in staging or "127.0.0.1:8000" in staging:
        failures.append("staging references production backend")
    if "/environments/production/current/frontend-dist" not in production:
        failures.append("production root is not its current release")
    if "/environments/staging/current/frontend-dist" not in staging:
        failures.append("staging root is not its current release")
    if "8081" in staging or "proxy_set_header Upgrade" in staging:
        failures.append("staging exposes Vite/HMR")
    if "location = /_admin_check" not in staging or "internal;" not in staging:
        failures.append("staging admin-check is not internal")
    gateway_host = "server_name chat-gateway-staging.paperswithcode.co;"
    if gateway_host not in staging:
        failures.append("staging chat gateway hostname is missing")
    for endpoint in ("catalog", "session-store", "v1/messages"):
        location = f"location = /api/internal/chat-gateway/{endpoint}"
        if location not in staging:
            failures.append(f"staging chat gateway {endpoint} route is missing")
    if "client_max_body_size 512k;" not in staging:
        failures.append("staging chat gateway body limit is missing")
    if staging.count("location / {") != 1 or production.count("location / {") != 1:
        failures.append("ambiguous catch-all location")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent / "nginx"
    )
    args = parser.parse_args()
    failures = validate(
        (args.root / "paperswithcode.co.conf").read_text(),
        (args.root / "staging.paperswithcode.co.conf").read_text(),
    )
    for failure in failures:
        print(f"FAIL: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
