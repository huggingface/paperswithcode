"""Bounded reconciliation and duplicate-safe GitHub evaluation outreach."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import re
import time

from backend.services.github_eval_outreach_body import render_repository_body
from backend.services.github_eval_outreach_state import OutreachState
from backend.services.github_issue_body_service import ISSUE_TITLE
from backend.services.github_issue_publish_service import (
    GithubApiError,
    NIELSROGGE_LOGIN,
    _is_excluded_repository,
)

DAY = 86400


def matches_paper(body: str, paper) -> bool:
    aliases = {str(paper.id), re.sub(r"v\d+$", "", paper.route)}
    return any(
        re.search(
            r"https?://paperswithcode\.co/paper/"
            + re.escape(alias)
            + r"(?:v\d+)?(?=$|[^\w.])",
            body,
        )
        for alias in aliases
    )


def issues(api, repository: str, *, state: str = "all", creator: str | None = None):
    page = 1
    while True:
        arguments = [
            f"repos/{repository}/issues",
            "--method",
            "GET",
            "-f",
            f"state={state}",
            "-f",
            "per_page=100",
            "-f",
            f"page={page}",
        ]
        if creator:
            arguments += ["-f", f"creator={creator}"]
        batch = api(arguments)
        yield from (issue for issue in batch if "pull_request" not in issue)
        if len(batch) < 100:
            return
        page += 1


# GitHub allows 30 authenticated search requests per minute; pacing every
# search call at this interval keeps a repository pass under that cap.
SEARCH_PACE_SECONDS = 2


def site_issues(api, repository: str, *, sleep=time.sleep):
    """Yield issues in ``repository`` whose body links a Papers with Code paper.

    Repository-wide ``/issues`` listings reject page-based pagination on large
    repositories (HTTP 422), so coverage detection uses the search API, which
    returns only the handful of issues that mention the site.
    """
    page = 1
    while True:
        sleep(SEARCH_PACE_SECONDS)
        batch = api(
            [
                "search/issues",
                "--method",
                "GET",
                "-f",
                f"q=repo:{repository} is:issue in:body paperswithcode.co/paper/",
                "-f",
                "per_page=100",
                "-f",
                f"page={page}",
            ]
        )
        items = batch.get("items", [])
        yield from (issue for issue in items if "pull_request" not in issue)
        if len(items) < 100 or page >= 10:
            return
        page += 1


class OutreachRunner:
    def __init__(
        self,
        state: OutreachState,
        api,
        catalog,
        draft,
        *,
        dry_run=False,
        limit=500,
        max_create=30,
        sleep=time.sleep,
        now=time.time,
    ):
        self.state, self.api, self.catalog, self.draft = state, api, catalog, draft
        self.dry_run, self.limit, self.max_create = dry_run, limit, max_create
        self.sleep, self.now = sleep, now
        self.counts = Counter()
        self.events = []

    def record(self, status, repository, **details):
        self.counts[status] += 1
        self.events.append({"status": status, "repository": repository, **details})

    def reconcile_pending(self, key, record):
        pending = record["pending"]
        repository = pending["repository"]
        if pending.get("number"):
            found = self.api([f"repos/{repository}/issues/{pending['number']}"])
        else:
            found = next(
                (
                    issue
                    for issue in issues(self.api, repository, creator="NielsRogge")
                    if issue.get("title") == ISSUE_TITLE
                    and issue.get("body") == pending["body"]
                ),
                None,
            )
        if (
            not found
            or found.get("title") != ISSUE_TITLE
            or found.get("body") != pending["body"]
            or found.get("user", {}).get("login", "").lower() != NIELSROGGE_LOGIN
        ):
            self.record(
                "needs_review",
                repository,
                reason="Uncertain post; automatic repost is disabled",
            )
            return
        record["covered"] = sorted(
            set(record.get("covered", [])) | set(pending["papers"])
        )
        record["issues"] = [*record.get("issues", []), found["html_url"]]
        record.pop("pending")
        self.state.put(key, record)
        self.record("verified", repository, issue_url=found["html_url"])

    def resolve_aliases(self, cohort):
        """Finish bounded identity discovery before grouping, including redirected URLs."""
        unresolved = 0
        checked = 0
        for alias in sorted(cohort):
            key = f"alias:{alias}"
            cached = self.state.get(key)
            if cached.get("expires", 0) > self.now():
                continue
            if checked == min(self.limit * 10, 500):
                unresolved += 1
                continue
            checked += 1
            try:
                metadata = self.api([f"repos/{alias}"])
            except GithubApiError as error:
                if not error.repository_unavailable:
                    raise
                metadata = {}
                self.record("unavailable", alias, reason=str(error))
            self.state.put(
                key,
                {
                    "id": metadata.get("id"),
                    "name": metadata.get("full_name"),
                    "expires": self.now() + 7 * DAY,
                },
            )
        self.counts["aliases_checked"] = checked
        self.counts["aliases_remaining"] = unresolved
        return unresolved == 0

    def groups(self, cohort):
        groups = defaultdict(dict)
        names = {}
        for alias, papers in cohort.items():
            cached = self.state.get(f"alias:{alias}")
            if cached.get("id") and not _is_excluded_repository(cached["name"]):
                key = f"repo:{cached['id']}"
                groups[key].update(papers)
                names[key] = cached["name"]
        return groups, names

    def process(self, key, repository, papers):
        record = self.state.get(key)
        if record.get("pending"):
            return
        uncovered = [
            paper
            for paper in papers.values()
            if paper.id not in record.get("covered", [])
        ]
        if not uncovered or record.get("next_check", 0) > self.now():
            return
        # Wait for all linked evaluated papers to settle before composing a shared issue.
        if not all(paper.ready for paper in uncovered):
            record.update(checked_at=self.now(), next_check=self.now() + 3600)
            self.state.put(key, record)
            self.record("curating", repository)
            return
        record["checked_at"] = self.now()
        record["next_check"] = self.now() + DAY
        self.state.put(key, record)
        metadata = self.api([f"repos/{repository}"])
        if f"repo:{metadata['id']}" != key:
            self.record(
                "needs_review", repository, reason="Repository identity changed"
            )
            return
        repository = metadata["full_name"]
        if (
            _is_excluded_repository(repository)
            or metadata.get("archived")
            or metadata.get("disabled")
            or not metadata.get("has_issues")
        ):
            self.record("ineligible", repository)
            return
        if next(issues(self.api, repository, state="open", creator="NielsRogge"), None):
            self.record("open_issue", repository)
            return
        covered = set(record.get("covered", []))
        for issue in site_issues(self.api, repository, sleep=self.sleep):
            covered.update(
                paper.id
                for paper in uncovered
                if matches_paper(issue.get("body") or "", paper)
            )
        record["covered"] = sorted(covered)
        self.state.put(key, record)
        uncovered = [paper for paper in uncovered if paper.id not in covered]
        if not uncovered:
            self.record("already_contacted", repository)
            return
        # Re-read committed catalog state just before rendering/posting. New work waits
        # for another pass; removed official links or evaluations cannot use stale drafts.
        fresh, _ = self.groups(self.catalog())
        current = fresh.get(key, {})
        if set(current) != set(papers) or not all(
            current[paper.id].ready for paper in uncovered
        ):
            self.record("catalog_changed", repository)
            return
        drafts = [
            self.draft(paper.id)
            for paper in sorted(uncovered, key=lambda item: item.id)
        ]
        body = render_repository_body(drafts)
        if self.dry_run:
            self.record(
                "would_create",
                repository,
                body=body,
                papers=[paper.id for paper in uncovered],
            )
            return
        # Recheck the author gate immediately before the write, after potentially slow drafts.
        if next(issues(self.api, repository, state="open", creator="NielsRogge"), None):
            self.record("open_issue", repository)
            return
        pending = {
            "repository": repository,
            "papers": [paper.id for paper in uncovered],
            "body": body,
            "at": self.now(),
        }
        record["pending"] = pending
        self.state.put(
            key, record
        )  # commit before POST, including before any process death
        self.counts["attempted"] += 1
        try:
            issue = self.api(
                [
                    f"repos/{repository}/issues",
                    "--method",
                    "POST",
                    "--raw-field",
                    f"title={ISSUE_TITLE}",
                    "--raw-field",
                    f"body={body}",
                ]
            )
        except GithubApiError as error:
            if error.status == 422 or (
                error.status == 403 and not error.is_rate_limited
            ):
                record.pop(
                    "pending"
                )  # definitive validation/permission rejection, no issue created
                record["next_check"] = self.now() + 30 * DAY
                record["rejection"] = str(error)
                self.state.put(key, record)
                self.record("rejected", repository, reason=str(error))
                return
            raise  # uncertain outcomes retain the pre-POST checkpoint; no blind retries
        finally:
            self.sleep(10)
        pending["number"] = issue["number"]
        self.state.put(key, record)
        self.reconcile_pending(key, record)

    def run(self):
        if self.state.get("rate_limit").get("not_before", 0) > self.now():
            return {
                "at": datetime.now(timezone.utc).isoformat(),
                "dry_run": self.dry_run,
                "counts": {"rate_limited": 1},
                "events": [],
            }
        if self.api(["user"])["login"].lower() != NIELSROGGE_LOGIN:
            raise ValueError(
                "Evaluation outreach requires the NielsRogge GitHub account"
            )
        for key, record in self.state.pending()[: self.limit]:
            try:
                self.reconcile_pending(key, record)
            except GithubApiError as error:
                if not error.repository_unavailable:
                    raise
                self.record(
                    "needs_review", record["pending"]["repository"], reason=str(error)
                )
        cohort = self.catalog()
        self.counts["catalog_repositories"] = len(cohort)
        if self.resolve_aliases(cohort):
            groups, names = self.groups(cohort)
            # Prefer newly settled evaluations over routine rechecks of old repos.
            # Reserve the first check for the oldest eligible repo to prevent starvation.
            eligible = []
            for key, papers in groups.items():
                record = self.state.get(key)
                uncovered = [
                    p for p in papers.values() if p.id not in record.get("covered", [])
                ]
                if (
                    not uncovered
                    or record.get("pending")
                    or record.get("next_check", 0) > self.now()
                ):
                    continue
                if not all(p.ready for p in uncovered):
                    self.counts["curating"] += 1
                    continue
                eligible.append(key)
            self.counts["repositories_due"] = len(eligible)

            def priority(key):
                record = self.state.get(key)
                newest = max(
                    p.evaluated_at
                    for p in groups[key].values()
                    if p.id not in record.get("covered", [])
                )
                checked_at = record.get("checked_at", 0)
                return (-newest, checked_at, key)

            keys = sorted(eligible, key=priority)
            if keys:
                oldest = min(
                    keys, key=lambda key: self.state.get(key).get("checked_at", 0)
                )
                keys.remove(oldest)
                keys.insert(0, oldest)
            checked = 0
            for key in keys:
                if checked >= self.limit or self.counts["attempted"] >= self.max_create:
                    break
                checked += 1
                try:
                    self.process(key, names[key], groups[key])
                except GithubApiError as error:
                    if not error.repository_unavailable:
                        raise
                    # This repository can be inaccessible without blocking other work.
                    self.record("unavailable", names[key], reason=str(error))
            self.counts["repositories_checked"] = checked
        result = {
            "at": datetime.now(timezone.utc).isoformat(),
            "dry_run": self.dry_run,
            "counts": dict(self.counts),
            "events": self.events,
        }
        self.state.put("last_run", result)
        return result
