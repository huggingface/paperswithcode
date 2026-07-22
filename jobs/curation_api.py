"""Job-scoped HTTP helper; intentionally contains no database configuration."""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request

USER_AGENT = "PapersWithCode-Curation/1.0 (+https://paperswithcode.co)"


def request(path: str, method: str = "GET", payload: dict | None = None) -> None:
    base = os.environ["PWC_CURATION_API_URL"].rstrip("/")
    job_id = os.environ["PWC_CURATION_JOB_ID"]
    token = os.environ["PWC_CURATION_JOB_TOKEN"]
    data = json.dumps(payload).encode() if payload is not None else None
    response = urllib.request.urlopen(
        urllib.request.Request(
            f"{base}/admin/codex-curation/jobs/{job_id}/{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            method=method,
        ),
        timeout=30,
    )
    print(response.read().decode())


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("context")
    taxonomy = sub.add_parser("taxonomy")
    taxonomy.add_argument("query")
    leaderboards = sub.add_parser("leaderboards")
    leaderboards.add_argument("query")
    apply = sub.add_parser("apply")
    apply.add_argument("json_file")
    args = parser.parse_args()
    if args.command == "context":
        request("context")
    elif args.command == "taxonomy":
        request(f"taxonomy?q={urllib.parse.quote(args.query)}")
    elif args.command == "leaderboards":
        request(f"leaderboards?q={urllib.parse.quote(args.query)}")
    else:
        with open(args.json_file, encoding="utf-8") as handle:
            request("apply", "POST", json.load(handle))


if __name__ == "__main__":
    main()
