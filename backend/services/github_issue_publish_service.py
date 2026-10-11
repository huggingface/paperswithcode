"""Deterministic, duplicate-safe publication of evaluation outreach issues."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

from backend.services.github_issue_body_service import (
    GithubIssueDraft,
    normalize_repository_url,
)


@dataclass(frozen=True)
class GithubIssuePublishResult:
    status: str
    repository: str
    issue_url: str
    issue_number: int
    state: str
    title_verified: bool
    body_verified: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


GithubApi = Callable[[list[str], dict[str, str]], Any]
NIELSROGGE_LOGIN = "nielsrogge"
# GitHub issue search does not match URL paths or arXiv ids in bodies, so
# outreach issues are found by the site name they all carry.
SITE_ISSUE_QUERY = 'is:issue "Papers with Code"'
EXCLUDED_REPOSITORY_OWNERS = frozenset(
    {"huggingface", "tensorflow", "pytorch", "openai", "anthropic", "anthropics"}
)
EXCLUDED_REPOSITORY_NAMES = frozenset(
    {"vllm", "sglang", "llama.cpp", "tensorflow", "pytorch"}
)
EXCLUDED_REPOSITORIES = frozenset({"google-research/google-research", "pwc-1/paper-9"})


def _is_excluded_repository(repository: str) -> bool:
    owner, _, name = repository.lower().partition("/")
    return (
        owner in EXCLUDED_REPOSITORY_OWNERS
        or name in EXCLUDED_REPOSITORY_NAMES
        or repository.lower() in EXCLUDED_REPOSITORIES
    )


def select_official_repository(
    candidates: tuple[str, ...], requested_repository: str | None
) -> str:
    if not candidates:
        raise ValueError("Paper has no official GitHub repository")
    if requested_repository:
        requested = normalize_repository_url(
            requested_repository
            if "://" in requested_repository
            else f"https://github.com/{requested_repository}"
        )
        match = next(
            (
                candidate
                for candidate in candidates
                if candidate.lower() == requested.lower()
            ),
            None,
        )
        if not match:
            raise ValueError(
                "Requested repository is not marked official for the paper"
            )
        selected = match
    else:
        if len(candidates) > 1:
            joined = ", ".join(candidates)
            raise ValueError(
                f"Paper has multiple official repositories; use --repository: {joined}"
            )
        selected = candidates[0]
    if _is_excluded_repository(selected):
        raise ValueError(f"Repository {selected} is excluded from outreach")
    return selected


def github_environment(token_environment_variable: str) -> dict[str, str]:
    env = os.environ.copy()
    token = env.get(token_environment_variable)
    if not token:
        raise ValueError(
            f"GitHub token environment variable is unset: {token_environment_variable}"
        )
    env["GH_TOKEN"] = token
    return env


class GithubApiError(ValueError):
    def __init__(
        self,
        message: str,
        status: int | None = None,
        retry_at: float = 0,
        *,
        is_rate_limited: bool = False,
    ):
        super().__init__(message)
        self.status = status
        self.retry_at = retry_at
        self.is_rate_limited = status == 429 or is_rate_limited

    @property
    def repository_unavailable(self) -> bool:
        return self.status in {403, 404, 410, 451} and not self.is_rate_limited


def gh_json(arguments: list[str], env: dict[str, str]) -> Any:
    process = subprocess.run(
        ["gh", "api", "--include", *arguments],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    headers, _, body = process.stdout.partition("\n\n")
    if not headers.startswith("HTTP/"):
        body, headers = process.stdout, ""
    if process.returncode:
        retry_after = re.search(r"(?im)^retry-after: (\d+)", headers)
        reset = re.search(r"(?im)^x-ratelimit-reset: (\d+)", headers)
        retry_at = max(
            time.time() + int(retry_after[1]) if retry_after else 0,
            int(reset[1]) if reset else 0,
        )
        message = process.stderr.strip().splitlines()
        status = re.search(r"HTTP (\d{3})", process.stderr)
        detail = body.strip()[:2000]
        status_code = int(status[1]) if status else None
        remaining = re.search(r"(?im)^x-ratelimit-remaining: (\d+)", headers)
        rate_message = (process.stderr + body).lower()
        is_rate_limited = status_code == 429 or (
            status_code == 403
            and (
                retry_after is not None
                or (remaining is not None and remaining[1] == "0")
                or "rate limit" in rate_message
                or "secondary-rate-limit" in rate_message
                or "abuse detection" in rate_message
            )
        )
        raise GithubApiError(
            ": ".join(
                filter(
                    None,
                    [message[-1] if message else "GitHub API request failed", detail],
                )
            ),
            status_code,
            retry_at if is_rate_limited else 0,
            is_rate_limited=is_rate_limited,
        )
    return json.loads(body)


def _matching_issue(
    draft: GithubIssueDraft,
    repository: str,
    env: dict[str, str],
    api: GithubApi,
) -> dict[str, Any] | None:
    paper_url = f"https://paperswithcode.co/paper/{draft.paper_id}"
    recent = api(
        [
            f"repos/{repository}/issues",
            "-f",
            "state=all",
            "-f",
            "per_page=100",
            "-f",
            "sort=created",
            "-f",
            "direction=desc",
            "--method",
            "GET",
        ],
        env,
    )
    direct_match = next(
        (
            issue
            for issue in recent
            if "pull_request" not in issue and paper_url in (issue.get("body") or "")
        ),
        None,
    )
    if direct_match:
        return direct_match

    search = api(
        [
            "search/issues",
            "-f",
            f"q=repo:{repository} {SITE_ISSUE_QUERY}",
            "-f",
            "per_page=100",
            "--method",
            "GET",
        ],
        env,
    )
    return next(
        (
            issue
            for issue in search.get("items", [])
            if paper_url in (issue.get("body") or "")
        ),
        None,
    )


def _has_open_nielsrogge_issue(
    repository: str,
    env: dict[str, str],
    api: GithubApi,
) -> bool:
    open_issues = api(
        [
            f"repos/{repository}/issues",
            "-f",
            "state=open",
            "-f",
            "creator=NielsRogge",
            "-f",
            "per_page=100",
            "-f",
            "sort=created",
            "-f",
            "direction=desc",
            "--method",
            "GET",
        ],
        env,
    )
    return any(
        "pull_request" not in issue
        and (issue.get("user", {}).get("login") or "").lower() == NIELSROGGE_LOGIN
        for issue in open_issues
    )


def publish_github_issue(
    draft: GithubIssueDraft,
    *,
    token_environment_variable: str,
    requested_repository: str | None = None,
    api: GithubApi = gh_json,
) -> GithubIssuePublishResult:
    repository = select_official_repository(
        draft.official_repositories,
        requested_repository,
    )
    env = github_environment(token_environment_variable)
    metadata = api([f"repos/{repository}"], env)
    if metadata["archived"]:
        raise ValueError("Official repository is archived")
    if not metadata["has_issues"]:
        raise ValueError("Official repository has issues disabled")
    repository = metadata["full_name"]
    if _is_excluded_repository(repository):
        raise ValueError(f"Repository {repository} is excluded from outreach")

    if _has_open_nielsrogge_issue(repository, env, api):
        raise ValueError(
            f"Repository {repository} already has an open issue authored by "
            f"{NIELSROGGE_LOGIN}"
        )

    existing = _matching_issue(draft, repository, env, api)
    status = "existing"
    issue = existing
    if not issue:
        status = "created"
        issue = api(
            [
                f"repos/{repository}/issues",
                "--method",
                "POST",
                "--raw-field",
                f"title={draft.issue_title}",
                "--raw-field",
                f"body={draft.body}",
            ],
            env,
        )

    verified = api(
        [f"repos/{repository}/issues/{issue['number']}"],
        env,
    )
    return GithubIssuePublishResult(
        status=status,
        repository=repository,
        issue_url=verified["html_url"],
        issue_number=verified["number"],
        state=verified["state"],
        title_verified=verified["title"] == draft.issue_title,
        body_verified=(
            draft.body == verified.get("body")
            if status == "created"
            else f"https://paperswithcode.co/paper/{draft.paper_id}"
            in (verified.get("body") or "")
        ),
    )
