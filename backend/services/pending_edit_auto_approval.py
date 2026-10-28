"""Decide whether a signed-in user's paper-page edit is applied immediately.

Auto-approved edits are reviewed afterwards on ``/submissions`` and reverted
through the catalog audit rollback. This policy only holds back the edits that
are cheap to abuse: links to unfamiliar sites, evaluations on unconfigured
benchmarks, mass removals, accounts past their daily paper budget, and new
organizations without a real Hugging Face organization behind them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.database import PendingPaperEdit, ProjectPage
from backend.services.hf_organization_service import HFOrganizationClient
from backend.services.pending_edit_mutations import PendingEditMutationService
from backend.services.x_thread_service import parse_x_post_id

AUTO_REVIEWER = "auto-approve"
AUTO_EDIT_TYPES = frozenset(
    {
        "tasks",
        "methods",
        "organizations",
        "repositories",
        "project_pages",
        "source_url",
        "hf_artifacts",
        "x_threads",
        "evaluations",
        "new_organization",
    }
)
TRUSTED_HOST_SUFFIXES = (
    "github.com",
    "github.io",
    "gitlab.com",
    "huggingface.co",
    "hf.co",
    "hf.space",
    "arxiv.org",
    "x.com",
    "twitter.com",
)
ACADEMIC_HOST = re.compile(r"\.(edu|ac\.[a-z]{2})$")
KNOWN_HOST_MIN_PAGES = 3
KNOWN_HOST_CANDIDATES = 500
URL_EDIT_TYPES = frozenset({"repositories", "project_pages", "source_url"})
ID_FIELDS = {
    "tasks": ("tasks", "task_ids"),
    "methods": ("methods", "method_ids"),
    "organizations": ("organizations", "organization_ids"),
}

Payload = dict[str, Any]


@dataclass(frozen=True)
class AutoApprovalDecision:
    apply: bool
    # Why the edit was held; None when it simply is not eligible or is applied.
    held_reason: str | None = None

    @property
    def note(self) -> str | None:
        return f"Held for review: {self.held_reason}" if self.held_reason else None


def member_values(edit_type: str, payload: Payload) -> set[str]:
    """Membership of a snapshot or proposed payload, for set comparison."""
    if edit_type in ID_FIELDS:
        snapshot_key, payload_key = ID_FIELDS[edit_type]
        if payload_key in payload:
            return {str(value) for value in payload[payload_key]}
        return {str(item["id"]) for item in payload.get(snapshot_key, [])}
    if edit_type in {"repositories", "project_pages"}:
        return {row["url"].strip() for row in payload.get(edit_type, [])}
    if edit_type == "source_url":
        return {payload["source_url"].strip()} if payload.get("source_url") else set()
    if edit_type == "x_threads":
        return {
            str(parse_x_post_id(item if isinstance(item, str) else item["url"]))
            for item in payload.get("x_threads", [])
        }
    if edit_type == "hf_artifacts":
        return {
            f"{key}:{value}"
            for key in ("hf_models", "hf_datasets", "hf_spaces")
            for value in payload.get(key) or []
        }
    return set()


def removed_values(edit_type: str, current: Payload, proposed: Payload) -> set[str]:
    """Existing values an edit would drop or replace."""
    if edit_type == "evaluations":
        return {
            f"evaluation:{operation['evaluation_id']}"
            for operation in proposed.get("operations", [])
            if operation["op"] == "delete"
        }
    return member_values(edit_type, current) - member_values(edit_type, proposed)


def _hosts(edit_type: str, current: Payload, proposed: Payload) -> set[str]:
    if edit_type in URL_EDIT_TYPES:
        urls = member_values(edit_type, proposed) - member_values(edit_type, current)
    elif edit_type == "evaluations":
        urls = {
            data[field]
            for operation in proposed.get("operations", [])
            for data in [operation.get("data") or {}]
            for field in ("source_url", "external_source_url")
            if data.get(field)
        }
    else:
        return set()
    return {(urlparse(url).hostname or "").lower().removeprefix("www.") for url in urls}


class AutoApprovalPolicy:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def decide(
        self,
        *,
        hf_subject: str,
        paper_id: int | None,
        edit_type: str,
        current: Payload,
        proposed: Payload,
        now: datetime | None = None,
    ) -> AutoApprovalDecision:
        if (
            not self.settings.paper_edit_auto_approve_enabled
            or paper_id is None
            or edit_type not in AUTO_EDIT_TYPES
        ):
            return AutoApprovalDecision(apply=False)
        now = now or datetime.now(timezone.utc)
        reason = (
            self._unverified_link(edit_type, current, proposed)
            or self._unverified_organization(edit_type, proposed)
            or self._unconfigured_evaluation(edit_type, proposed)
            or self._mass_removal(
                hf_subject, paper_id, edit_type, current, proposed, now
            )
            or self._daily_cap(hf_subject, paper_id, now)
        )
        return AutoApprovalDecision(apply=reason is None, held_reason=reason)

    def _unverified_link(
        self, edit_type: str, current: Payload, proposed: Payload
    ) -> str | None:
        for host in sorted(_hosts(edit_type, current, proposed)):
            if not self._host_is_trusted(host):
                return f"link to unfamiliar site {host or 'with no host'}"
        return None

    def _unverified_organization(self, edit_type: str, proposed: Payload) -> str | None:
        if edit_type != "new_organization":
            return None
        hf_slug = proposed.get("hf_slug")
        if not hf_slug:
            return "new organization has no Hugging Face organization"
        client = HFOrganizationClient(attempts=2)
        try:
            profile = client.fetch_profile(hf_slug)
        finally:
            client.close()
        if profile is None:
            return f"Hugging Face organization {hf_slug} not found"
        return None

    def _host_is_trusted(self, host: str) -> bool:
        if not host:
            return False
        extra = {
            item.strip().lower()
            for item in self.settings.paper_edit_auto_approve_extra_domains.split(",")
            if item.strip()
        }
        if (
            any(host == s or host.endswith(f".{s}") for s in TRUSTED_HOST_SUFFIXES)
            or host in extra
            or ACADEMIC_HOST.search(host)
        ):
            return True
        # LIKE only narrows the candidates; the hostname of each is compared
        # exactly, so a host mentioned in a path or query string earns no trust.
        escaped = host.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        urls = (
            self.db.query(ProjectPage.url)
            .filter(ProjectPage.url.ilike(f"%//%{escaped}%", escape="\\"))
            .limit(KNOWN_HOST_CANDIDATES)
            .all()
        )
        known = sum(
            (urlparse(url).hostname or "").lower().removeprefix("www.") == host
            for (url,) in urls
        )
        return known >= KNOWN_HOST_MIN_PAGES

    def _unconfigured_evaluation(self, edit_type: str, proposed: Payload) -> str | None:
        if edit_type != "evaluations":
            return None
        missing = PendingEditMutationService(self.db).unresolved_evaluation_resources(
            proposed
        )
        if missing:
            return f"evaluation uses unconfigured {', '.join(sorted(set(missing)))}"
        return None

    def _auto_rows(self, hf_subject: str, since: datetime) -> list[PendingPaperEdit]:
        return (
            self.db.query(PendingPaperEdit)
            .filter(
                PendingPaperEdit.hf_subject == hf_subject,
                PendingPaperEdit.status == "approved",
                PendingPaperEdit.reviewed_by_kind == "auto",
                PendingPaperEdit.reviewed_at >= since,
            )
            .all()
        )

    def _mass_removal(
        self,
        hf_subject: str,
        paper_id: int,
        edit_type: str,
        current: Payload,
        proposed: Payload,
        now: datetime,
    ) -> str | None:
        removed = removed_values(edit_type, current, proposed)
        if not removed:
            return None
        rows = self._auto_rows(hf_subject, now - timedelta(hours=24))
        # Taking back one's own earlier additions is a correction, not a removal.
        own = set()
        for row in rows:
            if row.paper_id == paper_id and row.edit_type == edit_type:
                own |= member_values(edit_type, row.applied_payload or {}) - (
                    member_values(edit_type, row.current_payload or {})
                )
        if not removed - own:
            return None
        papers = {paper_id}
        for row in rows:
            if row.paper_id is not None and removed_values(
                row.edit_type, row.current_payload or {}, row.applied_payload or {}
            ):
                papers.add(row.paper_id)
        if len(papers) > self.settings.paper_edit_auto_approve_removal_papers:
            return f"removals on more than {self.settings.paper_edit_auto_approve_removal_papers} papers in 24 hours"
        return None

    def _daily_cap(self, hf_subject: str, paper_id: int, now: datetime) -> str | None:
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        papers = {row.paper_id for row in self._auto_rows(hf_subject, midnight)}
        if (
            paper_id not in papers
            and len(papers) >= self.settings.paper_edit_auto_approve_daily_papers
        ):
            return (
                f"over {self.settings.paper_edit_auto_approve_daily_papers} "
                "auto-applied papers today"
            )
        return None
