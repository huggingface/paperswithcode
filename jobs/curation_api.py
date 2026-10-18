"""Job-scoped HTTP helper; intentionally contains no database configuration."""

from __future__ import annotations

import argparse
import base64
import copy
import fcntl
import gzip
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "PapersWithCode-Curation/1.0 (+https://paperswithcode.co)"
SEEN_LEADERBOARDS = "/tmp/pwc-curation-leaderboards.jsonl"


def request_json(
    path: str,
    method: str = "GET",
    payload: dict | None = None,
    timeout: int = 30,
) -> dict:
    base = os.environ["PWC_CURATION_API_URL"].rstrip("/")
    job_id = os.environ["PWC_CURATION_JOB_ID"]
    token = os.environ["PWC_CURATION_JOB_TOKEN"]
    data = json.dumps(payload).encode() if payload is not None else None
    try:
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
            timeout=timeout,
        )
    except urllib.error.HTTPError as error:
        raw_error = error.read().decode("utf-8", "replace")
        try:
            detail = json.loads(raw_error).get("detail", raw_error)
        except json.JSONDecodeError:
            detail = raw_error
        raise RuntimeError(
            f"Curation API rejected {method} {path} (HTTP {error.code}): {detail}"
        ) from error
    result = json.loads(response.read().decode())
    if path.startswith("leaderboards?"):
        remember_leaderboards(result.get("leaderboards") or [])
    return result


def _seen_leaderboards() -> dict[str, set[str]]:
    seen: dict[str, set[str]] = {}
    if not os.path.exists(SEEN_LEADERBOARDS):
        return seen
    with open(SEEN_LEADERBOARDS, encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_SH)
        for line in handle:
            for key, metrics in json.loads(line).items():
                seen.setdefault(key, set()).update(metrics)
    return seen


def remember_leaderboards(boards: list[dict]) -> None:
    """Record configured boards so apply can check evaluations against them.

    Each lookup appends one locked line, so parallel lookups cannot drop boards.
    """
    found = {
        f"{board['task']['id']}:{board['dataset']['id']}": [
            metric["name"] for metric in board["metrics"]
        ]
        for board in boards
    }
    with open(SEEN_LEADERBOARDS, "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.write(json.dumps(found) + "\n")


def request(
    path: str,
    method: str = "GET",
    payload: dict | None = None,
    timeout: int = 30,
) -> dict:
    result = request_json(path, method, payload, timeout)
    print(json.dumps(result))
    return result


def _trace_payload(proposal: dict) -> dict:
    events_path = os.environ.get("PWC_CURATION_EVENTS_PATH", "")
    raw = b""
    if events_path and os.path.exists(events_path):
        with open(events_path, "rb") as handle:
            raw = handle.read(8_000_001)
        if len(raw) > 8_000_000:
            raise ValueError("Codex event trace exceeds the pre-apply limit")
    candidates = None
    candidates_path = "/tmp/url_candidates.json"
    if os.path.exists(candidates_path):
        with open(candidates_path, encoding="utf-8") as handle:
            candidates = json.load(handle)
    return {
        "proposal": proposal,
        "events_gzip_b64": base64.b64encode(
            gzip.compress(raw, compresslevel=6)
        ).decode(),
        "prompt": os.environ.get("PWC_CURATION_PROMPT", ""),
        "url_candidates": candidates,
    }


def make_scheduled_enrichment_additive(proposal: dict, context: dict) -> dict:
    """Preserve existing enrichment links for scheduled curation jobs."""

    if os.environ.get("PWC_CURATION_TRIGGER", "admin") == "admin":
        return proposal
    if proposal.get("resolve_model_paper") is not None:
        enrich = proposal.get("enrich")
        if isinstance(enrich, dict) and not any(
            value not in (None, False, {}, []) for value in enrich.values()
        ):
            normalized = copy.deepcopy(proposal)
            normalized["enrich"] = None
            return normalized
        return proposal
    enrich = proposal.get("enrich")
    paper = context.get("paper") or {}
    if not isinstance(enrich, dict):
        return proposal

    normalized = copy.deepcopy(proposal)
    enrich = normalized["enrich"]
    for key, context_key in (("task_ids", "tasks"), ("method_ids", "methods")):
        if enrich.get(key) is not None:
            enrich[key] = list(
                dict.fromkeys(
                    [item["id"] for item in paper.get(context_key) or []] + enrich[key]
                )
            )
    for key in ("repositories", "project_pages"):
        if enrich.get(key) is not None:
            links = {
                item["url"]: {
                    "url": item["url"],
                    "is_official": item.get("is_official", True),
                }
                for item in paper.get(key) or []
            }
            for item in enrich[key]:
                links.setdefault(item["url"], item)
            enrich[key] = list(links.values())
    for key in (
        "task_removal_reasons",
        "method_removal_reasons",
        "project_page_removal_reasons",
    ):
        enrich.pop(key, None)
    return normalized


def check_benchmark_gap_fields(proposal: dict, candidates: dict | None) -> None:
    """Catch correctable field errors before consuming a server apply attempt.

    The server remains authoritative for evidence identity and catalog checks.
    Do not rewrite evidence or scores to make a proposal pass validation.
    """
    errors = []
    source_kinds = {}
    for source in (candidates or {}).get("source_documents", []):
        source_kinds.setdefault(source.get("url"), set()).add(source.get("kind"))
    for index, gap in enumerate(proposal.get("benchmark_gaps") or []):
        prefix = f"benchmark_gaps[{index}]"
        metrics = gap.get("protocol", {}).get("metrics", [])
        names = {metric.get("name") for metric in metrics}
        for metric in metrics:
            if not str(metric.get("definition") or "").strip():
                errors.append(
                    f"{prefix}: metric {metric.get('name')!r} needs a definition"
                )
        for blocked in gap.get("blocked_evaluations", []):
            scores = blocked.get("metrics") or {}
            best = blocked.get("best_metric")
            if best not in scores or best not in names:
                errors.append(
                    f"{prefix}: best_metric {best!r} must appear in both metrics and protocol.metrics"
                )
            undefined = set(scores) - names
            if undefined:
                errors.append(
                    f"{prefix}: undefined metric names {sorted(undefined)}; use split for split labels"
                )
        for evidence in gap.get("evidence", []):
            kinds = source_kinds.get(evidence.get("source_url"))
            if kinds and evidence.get("source_kind") not in kinds:
                errors.append(
                    f"{prefix}: source_kind must match manifest: {sorted(kinds)}"
                )
    if errors:
        raise ValueError(
            "Proposal preflight failed (no apply attempted):\n" + "\n".join(errors)
        )


def check_evaluation_leaderboards(proposal: dict) -> None:
    """Refuse evaluations on boards the leaderboards command never returned.

    The server rejects an evaluation without a configured task/dataset/metric
    board, and a second rejection closes the job. Catch it here so the worker
    fixes the proposal before spending its only correction.
    """
    seen = _seen_leaderboards()
    errors = []
    for index, item in enumerate(proposal.get("evaluations") or []):
        key = f"{item.get('task_id')}:{item.get('dataset_id')}"
        if key not in seen:
            errors.append(
                f"evaluations[{index}] ({item.get('model_name')}): task_id "
                f"{item.get('task_id')} + dataset_id {item.get('dataset_id')} is not "
                "a configured leaderboard returned by the leaderboards command; "
                "remove this evaluation or use the exact task_id and dataset_id "
                "of a returned board"
            )
        elif item.get("best_metric") not in seen[key]:
            errors.append(
                f"evaluations[{index}] ({item.get('model_name')}): best_metric "
                f"{item.get('best_metric')!r} is not configured for this board; "
                f"configured metrics: {sorted(seen[key])}"
            )
    if errors:
        raise ValueError(
            "Proposal preflight failed (no apply attempted):\n" + "\n".join(errors)
        )


def store_trace_with_retry(path: str, payload: dict) -> dict:
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            return request(path, "POST", payload, timeout=300)
        except Exception as error:
            last_error = error
            if attempt < 4:
                time.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def wait_for_thumbnail(timeout_seconds: int, poll_seconds: int = 5) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while True:
        result = request_json("thumbnail")
        thumbnail = result["thumbnail"]
        if thumbnail["status"] in {"not_requested", "succeeded", "failed"}:
            print(json.dumps(result))
            return result
        if time.monotonic() >= deadline:
            print(json.dumps(result))
            return result
        time.sleep(min(poll_seconds, max(0, deadline - time.monotonic())))


def check_review_reasons(proposal: dict, context: dict) -> None:
    """Mirror the server's reused-template check on overseer reasons.

    The server refuses a review whose approve, reject, or defer reasons match
    after removing each candidate's own names, digits, and punctuation.
    """
    review = proposal.get("review_benchmark_gaps")
    if not review:
        return
    names = {
        item["id"]: [item["name"], *(item.get("aliases") or [])]
        for item in (context.get("review") or {}).get("candidates", [])
    }
    templates: dict[str, list[str]] = {}
    for decision in review.get("decisions") or []:
        candidate_id = str(decision.get("candidate_id"))
        if decision.get("decision") == "merge" or candidate_id not in names:
            continue
        text = str(decision.get("reason") or "").lower()
        for name in sorted(names[candidate_id], key=len, reverse=True):
            text = text.replace(name.lower(), " ")
        template = " ".join(re.findall(r"[a-z]+", text))
        templates.setdefault(template, []).append(candidate_id)
    repeated = [ids for ids in templates.values() if len(ids) > 1]
    if repeated:
        raise ValueError(
            "Proposal preflight failed (no apply attempted): reasons of these "
            "candidate groups match once their names and digits are removed; "
            "rewrite each from its own evidence, saying what sets it apart:\n"
            + "\n".join(", ".join(ids) for ids in repeated)
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("context")
    taxonomy = sub.add_parser("taxonomy")
    taxonomy.add_argument("query")
    leaderboards = sub.add_parser("leaderboards")
    leaderboards.add_argument("query")
    catalog = sub.add_parser("catalog")
    catalog.add_argument("query")
    apply = sub.add_parser("apply")
    apply.add_argument("json_file")
    thumbnail_status = sub.add_parser("thumbnail-status")
    thumbnail_status.add_argument("--wait-seconds", type=int, default=240)
    thumbnail_status.add_argument("--poll-seconds", type=int, default=5)
    args = parser.parse_args()
    if args.command == "context":
        request("context")
    elif args.command == "taxonomy":
        request(f"taxonomy?q={urllib.parse.quote(args.query)}")
    elif args.command == "leaderboards":
        request(f"leaderboards?q={urllib.parse.quote(args.query)}")
    elif args.command == "catalog":
        request(f"catalog?q={urllib.parse.quote(args.query)}")
    elif args.command == "thumbnail-status":
        wait_for_thumbnail(args.wait_seconds, args.poll_seconds)
    else:
        with open(args.json_file, encoding="utf-8") as handle:
            proposal = json.load(handle)
        context = request_json("context")
        check_review_reasons(proposal, context)
        proposal = make_scheduled_enrichment_additive(proposal, context)
        trace = _trace_payload(proposal)
        check_benchmark_gap_fields(proposal, trace["url_candidates"])
        check_evaluation_leaderboards(proposal)
        store_trace_with_retry("trace/preapply", trace)
        request("apply", "POST", proposal, timeout=300)


if __name__ == "__main__":
    main()
