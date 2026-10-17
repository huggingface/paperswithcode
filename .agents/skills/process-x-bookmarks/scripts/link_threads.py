"""Link reviewed X threads to papers through the audited admin curation API.

Input is a JSON list of {"paper": "<arXiv id or database id>", "urls": [...]}.
Existing threads are kept; new URLs are appended (the API caps a paper at 10).

Usage (from the repository root):
  uv run --env-file backend/keys.env python \
      .agents/skills/process-x-bookmarks/scripts/link_threads.py \
      <scratchpad>/x_thread_links.json [--dry-run]
"""

import json
import os
import sys
import urllib.error
import urllib.request
import uuid

BASE = "https://paperswithcode.co/api/v1"
HEADERS = {
    "User-Agent": "curl/8.5.0",
    "X-Admin-Token": os.environ["PWC_ADMIN_API_TOKEN"],
}


def call(path, method="GET", body=None, extra=None):
    request = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={**HEADERS, "Content-Type": "application/json", **(extra or {})},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def post_id(url):
    return url.split("?")[0].rstrip("/").split("/")[-1]


dry_run = "--dry-run" in sys.argv
for row in json.load(open(sys.argv[1])):
    try:
        paper = call(f"/papers/{row['paper']}?include_resources=true")
        existing = [thread["url"] for thread in paper.get("x_threads") or []]
        known = {post_id(url) for url in existing}
        new = [url for url in row["urls"] if post_id(url) not in known]
        if dry_run or not new:
            print("SKIP" if not new else "WOULD", row["paper"], paper["id"], new)
            continue
        updated = call(
            f"/papers/{paper['id']}/x-threads",
            "PUT",
            {"x_threads": existing + new},
            {"Idempotency-Key": str(uuid.uuid4())},
        )
        print("OK", row["paper"], paper["id"], len(updated["x_threads"]))
    except urllib.error.HTTPError as error:
        print("FAIL", row["paper"], error.code, error.read()[:200])
