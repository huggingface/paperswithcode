"""Isolated, lease-fenced source repair candidates for autonomous operators."""

from __future__ import annotations

import hashlib
import base64
import json
import os
import shutil
import subprocess
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

from backend.services.autonomous_capabilities import Capability, ResourceKind
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    Operator,
    RunContext,
)


_SHARED_CRON_REPAIR_SOURCES: frozenset[str] = frozenset()


class CandidatePolicyError(PermissionError):
    pass


class ReviewRejected(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RepairProposal:
    capability: Capability
    declared_job: str

    def __post_init__(self) -> None:
        if (
            self.capability
            not in {
                Capability.REPAIR_DECLARED_CRON_SOURCE,
                Capability.REPAIR_CHAT_SOURCE,
            }
            or not self.declared_job
            or len(self.declared_job) > 100
            or any(
                character not in "abcdefghijklmnopqrstuvwxyz0123456789_-"
                for character in self.declared_job
            )
        ):
            raise ValueError("Invalid autonomous repair proposal")


@dataclass(frozen=True, slots=True)
class RepairTarget:
    source_paths: tuple[str, ...]
    test_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        paths = (*self.source_paths, *self.test_paths)
        if (
            not self.source_paths
            or not self.test_paths
            or len(paths) > 50
            or len(set(paths)) != len(paths)
            or any(not _safe_relative_path(value) for value in paths)
            or any(
                (
                    not value.startswith(".github/workflows/scripts/")
                    or not value.endswith((".py", ".sh"))
                )
                and (
                    not value.startswith("backend/scripts/")
                    or not value.endswith(".py")
                )
                and (
                    not value.startswith("url_extraction_agent/")
                    or not value.endswith(".py")
                )
                and value not in _SHARED_CRON_REPAIR_SOURCES
                for value in self.source_paths
            )
            or any(not value.startswith("backend/tests/") for value in self.test_paths)
        ):
            raise ValueError("Invalid server repair target")


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    command: tuple[str, ...]
    output_digest: str


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    reviewer_alias: str
    approved: bool
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class RepairCandidate:
    candidate_id: uuid.UUID
    context: RunContext
    proposal: RepairProposal
    lease_id: uuid.UUID
    base_sha: str
    worktree: Path


@dataclass(frozen=True, slots=True)
class ReviewBundle:
    candidate_id: uuid.UUID
    base_sha: str
    changed_paths: tuple[str, ...]
    patch_digest: str
    patch: str
    check_outcomes: tuple[CheckOutcome, ...]


def _safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(
        value
        and "\\" not in value
        and not path.is_absolute()
        and ".." not in path.parts
        and str(path) == value
    )


def _digest(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


class AutonomousSourceRepairService:
    _FORBIDDEN_PREFIXES = (
        "backend/database/migrations/",
        "deploy/nginx",
        "deploy/systemd",
        "deploy/install_host_layout.py",
        "deploy/keys",
    )

    def __init__(
        self,
        *,
        repository: AutonomousOperationsRepository | object,
        source_repository: Path,
        candidates_root: Path,
        repair_targets: Mapping[str, RepairTarget],
        min_free_bytes: int = 2 * 1024**3,
        check_runner: Callable[[tuple[str, ...], Path], CheckOutcome] | None = None,
        environ: dict[str, str] | None = None,
        git_executable: str = "/usr/bin/git",
        git_bridge_executable: str | None = None,
    ) -> None:
        if not Path(git_executable).is_absolute():
            raise ValueError("Autonomous Git executable must be absolute")
        self.repository = repository
        self.source_repository = source_repository.resolve()
        self.candidates_root = candidates_root.resolve()
        if (
            self.source_repository == self.candidates_root
            or self.source_repository in self.candidates_root.parents
            or self.candidates_root in self.source_repository.parents
        ):
            raise ValueError("Candidate storage must be isolated from release source")
        self.min_free_bytes = min_free_bytes
        self.repair_targets = dict(repair_targets)
        if not self.repair_targets or any(
            not isinstance(target, RepairTarget)
            for target in self.repair_targets.values()
        ):
            raise ValueError("Server repair targets are required")
        self.environ = dict(os.environ if environ is None else environ)
        self.git_executable = git_executable
        configured_bridge = git_bridge_executable or self.environ.get(
            "PWC_AUTONOMOUS_SOURCE_BRIDGE"
        )
        if configured_bridge is None and self.source_repository == Path(
            "/srv/paperswithcode/repository.git"
        ):
            configured_bridge = "/usr/local/sbin/pwc-autonomous-source"
        if configured_bridge is not None and not Path(configured_bridge).is_absolute():
            raise ValueError("Autonomous source bridge must be absolute")
        self.git_bridge_executable = configured_bridge
        self.check_runner = check_runner or self._run_check
        self._candidates: dict[uuid.UUID, RepairCandidate] = {}

    def prepare_candidate(
        self, db, context: RunContext, proposal: RepairProposal
    ) -> RepairCandidate:
        self._validate_operator_scope(context, proposal)
        lease = self.repository.acquire_repair_lease(
            db, context=context, ttl=timedelta(hours=2)
        )
        self.candidates_root.mkdir(parents=True, exist_ok=True)
        candidate_id = uuid.uuid4()
        worktree = self.candidates_root / f"candidate-{candidate_id.hex}"
        metadata_path = self._metadata_path(candidate_id)
        try:
            if shutil.disk_usage(self.candidates_root).free < self.min_free_bytes:
                raise CandidatePolicyError("Insufficient disk for isolated repair")
            if self.git_bridge_executable:
                base_sha = self._bridge(
                    "prepare", candidate_id, context.run_id, capture=True
                ).stdout.strip()
            else:
                self._git("fetch", "origin", "main", cwd=self.source_repository)
                base_sha = self._git(
                    "rev-parse", "origin/main", cwd=self.source_repository, capture=True
                ).stdout.strip()
            candidate = RepairCandidate(
                candidate_id, context, proposal, lease.lease_id, base_sha, worktree
            )
            metadata_path.write_text(
                json.dumps(
                    {
                        "base_sha": candidate.base_sha,
                        "candidate_id": str(candidate.candidate_id),
                        "created_at": datetime.now(UTC).isoformat(),
                        "dry_run": context.dry_run,
                        "lease_id": str(candidate.lease_id),
                        "manifest_revision": context.manifest_revision,
                        "operator": context.operator.value,
                        "run_id": str(context.run_id),
                        "worktree": str(candidate.worktree),
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            if not self.git_bridge_executable:
                self._git(
                    "worktree",
                    "add",
                    "--detach",
                    str(worktree),
                    base_sha,
                    cwd=self.source_repository,
                )
            if self._changed_paths(candidate):
                raise CandidatePolicyError("Candidate worktree is not clean")
            target = self.repair_targets[proposal.declared_job]
            if any(
                not (worktree / path).is_file()
                for path in (*target.source_paths, *target.test_paths)
            ):
                raise CandidatePolicyError(
                    "Declared repair target is absent from origin/main"
                )
        except (CandidatePolicyError, OSError, subprocess.CalledProcessError):
            if worktree.exists():
                if self.git_bridge_executable:
                    self._bridge("cleanup", candidate_id, context.run_id)
                else:
                    self._git(
                        "worktree",
                        "remove",
                        "--force",
                        str(worktree),
                        cwd=self.source_repository,
                    )
            metadata_path.unlink(missing_ok=True)
            self.repository.release_repair_lease(
                db, lease_id=lease.lease_id, owner_run_id=context.run_id
            )
            raise
        self._candidates[candidate.candidate_id] = candidate
        return candidate

    def review_candidate(
        self,
        db,
        candidate: RepairCandidate,
        *,
        reviewer_alias: str,
        reviewer: Callable[[str, ReviewBundle], ReviewDecision],
    ) -> ReviewBundle:
        self._require_registered(candidate)
        self._require_lease(db, candidate)
        self._require_candidate_base(candidate)
        changed = self._changed_paths(candidate)
        if not changed:
            raise CandidatePolicyError("Candidate has no source changes")
        target = self.repair_targets[candidate.proposal.declared_job]
        declared = set((*target.source_paths, *target.test_paths))
        if not set(changed).intersection(target.source_paths) or any(
            path not in declared or self._forbidden(path) for path in changed
        ):
            raise CandidatePolicyError(
                "Candidate changed an undeclared or forbidden path"
            )
        if any(
            (candidate.worktree / path).is_symlink()
            or candidate.worktree.resolve()
            not in (candidate.worktree / path).resolve().parents
            for path in changed
            if (candidate.worktree / path).exists()
        ):
            raise CandidatePolicyError("Candidate contains an unsafe path")
        commands = [("lint", *changed), ("pytest", *target.test_paths)]
        validated_patch_digest = hashlib.sha256(
            self._patch_bytes(candidate, changed)
        ).hexdigest()
        try:
            completed = []
            for command in commands:
                completed.append(self.check_runner(command, candidate.worktree))
                current_changed = self._changed_paths(candidate)
                if (
                    current_changed != changed
                    or hashlib.sha256(
                        self._patch_bytes(candidate, current_changed)
                    ).hexdigest()
                    != validated_patch_digest
                ):
                    raise CandidatePolicyError("Candidate changed during validation")
            outcomes = tuple(completed)
        except (CandidatePolicyError, OSError, subprocess.SubprocessError) as error:
            self._audit(
                db,
                candidate,
                "validation_failed",
                hashlib.sha256(candidate.base_sha.encode()).hexdigest(),
                hashlib.sha256(type(error).__name__.encode()).hexdigest(),
            )
            raise
        if any(
            outcome.command != command or not _digest(outcome.output_digest)
            for command, outcome in zip(commands, outcomes, strict=True)
        ):
            raise CandidatePolicyError("Autonomous check outcome is invalid")
        patch = self._patch_bytes(candidate, changed)
        if len(patch) > 2_000_000:
            raise CandidatePolicyError("Candidate patch exceeds the review limit")
        bundle = ReviewBundle(
            candidate.candidate_id,
            candidate.base_sha,
            changed,
            hashlib.sha256(patch).hexdigest(),
            patch.decode("utf-8", errors="replace"),
            outcomes,
        )
        validation_digest = hashlib.sha256(
            "\x1f".join(outcome.output_digest for outcome in outcomes).encode()
        ).hexdigest()
        self._audit(
            db,
            candidate,
            "validation_passed",
            hashlib.sha256(candidate.base_sha.encode()).hexdigest(),
            validation_digest,
        )
        if reviewer_alias != "diagnosis":
            raise CandidatePolicyError("Reviewer alias is not allowed for CRON repair")
        decision = reviewer(reviewer_alias, bundle)
        if (
            not isinstance(decision, ReviewDecision)
            or decision.reviewer_alias != reviewer_alias
            or not _digest(decision.evidence_digest)
        ):
            raise CandidatePolicyError("Autonomous review decision is invalid")
        self._audit(
            db,
            candidate,
            "review_approved" if decision.approved else "review_rejected",
            bundle.patch_digest,
            decision.evidence_digest,
        )
        if not decision.approved:
            raise ReviewRejected("Autonomous source-repair review was not approved")
        return bundle

    def publish_candidate(
        self, db, candidate: RepairCandidate, bundle: ReviewBundle
    ) -> str:
        self._require_registered(candidate)
        self._require_lease(db, candidate)
        self._require_candidate_base(candidate)
        self.repository.assert_mutation_allowed(db, candidate.context)
        changed = self._changed_paths(candidate)
        if (
            bundle.candidate_id != candidate.candidate_id
            or bundle.changed_paths != changed
            or bundle.patch_digest
            != hashlib.sha256(self._patch_bytes(candidate, changed)).hexdigest()
        ):
            raise CandidatePolicyError("Candidate changed after review")
        self._audit(
            db,
            candidate,
            "publish_started",
            hashlib.sha256(candidate.base_sha.encode()).hexdigest(),
            bundle.patch_digest,
        )
        self.repository.assert_mutation_allowed(db, candidate.context)
        self._require_lease(db, candidate)
        if self.git_bridge_executable:
            published_sha = self._bridge(
                "publish",
                candidate.candidate_id,
                candidate.context.run_id,
                candidate.proposal.declared_job,
                bundle.patch_digest,
                capture=True,
            ).stdout.strip()
        else:
            self._git("fetch", "origin", "main", cwd=candidate.worktree)
            origin_sha = self._git(
                "rev-parse", "origin/main", cwd=candidate.worktree, capture=True
            ).stdout.strip()
            if origin_sha != candidate.base_sha:
                raise CandidatePolicyError(
                    "origin/main advanced after candidate preparation"
                )
            self._git("add", "--", *changed, cwd=candidate.worktree)
            self._git(
                "-c",
                "user.name=Papers With Code Autonomy",
                "-c",
                "user.email=autonomy@paperswithcode.co",
                "commit",
                "-m",
                f"fix(cron): autonomous repair {candidate.context.run_id}",
                cwd=candidate.worktree,
            )
            parent_sha = self._git(
                "rev-parse", "HEAD^", cwd=candidate.worktree, capture=True
            ).stdout.strip()
            if origin_sha != candidate.base_sha or parent_sha != origin_sha:
                raise CandidatePolicyError(
                    "origin/main advanced after candidate preparation"
                )
            self._git("push", "origin", "HEAD:main", cwd=candidate.worktree)
            published_sha = self._git(
                "rev-parse", "HEAD", cwd=candidate.worktree, capture=True
            ).stdout.strip()
            remote_sha = self._git(
                "ls-remote",
                "--exit-code",
                "origin",
                "refs/heads/main",
                cwd=candidate.worktree,
                capture=True,
            ).stdout.partition("\t")[0]
            if remote_sha != published_sha:
                raise CandidatePolicyError(
                    "origin/main did not retain the published SHA"
                )
        self._audit(
            db,
            candidate,
            "published",
            bundle.patch_digest,
            hashlib.sha256(published_sha.encode()).hexdigest(),
        )
        return published_sha

    def cleanup_candidate(self, db, candidate: RepairCandidate) -> None:
        self._require_registered(candidate)
        if self.git_bridge_executable:
            self._bridge("cleanup", candidate.candidate_id, candidate.context.run_id)
        else:
            self._git(
                "worktree",
                "remove",
                "--force",
                str(candidate.worktree),
                cwd=self.source_repository,
            )
        self.repository.release_repair_lease(
            db,
            lease_id=candidate.lease_id,
            owner_run_id=candidate.context.run_id,
        )
        self._metadata_path(candidate.candidate_id).unlink(missing_ok=True)
        del self._candidates[candidate.candidate_id]

    def cleanup_abandoned(
        self, db, *, now: datetime, minimum_age: timedelta = timedelta(hours=2)
    ) -> int:
        if now.tzinfo is None or minimum_age < timedelta(minutes=1):
            raise ValueError("Invalid abandoned-candidate cleanup window")
        cleaned = 0
        for metadata_path in sorted(self.candidates_root.glob("*.json")):
            try:
                value = json.loads(metadata_path.read_text(encoding="utf-8"))
                context = RunContext(
                    uuid.UUID(value["run_id"]),
                    Operator(value["operator"]),
                    value["dry_run"],
                    value["manifest_revision"],
                )
                candidate_id = uuid.UUID(value["candidate_id"])
                lease_id = uuid.UUID(value["lease_id"])
                created_at = datetime.fromisoformat(value["created_at"])
                worktree = Path(value["worktree"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if (
                candidate_id in self._candidates
                or created_at.tzinfo is None
                or now - created_at < minimum_age
                or worktree.parent.resolve() != self.candidates_root
                or not worktree.name.startswith("candidate-")
                or self.repository.owns_repair_lease(db, context=context)
            ):
                continue
            if worktree.exists():
                if self.git_bridge_executable:
                    self._bridge("cleanup-abandoned", candidate_id, context.run_id)
                else:
                    self._git(
                        "worktree",
                        "remove",
                        "--force",
                        str(worktree),
                        cwd=self.source_repository,
                    )
            self.repository.release_repair_lease(
                db, lease_id=lease_id, owner_run_id=context.run_id
            )
            metadata_path.unlink()
            cleaned += 1
        return cleaned

    def _validate_operator_scope(
        self, context: RunContext, proposal: RepairProposal
    ) -> None:
        if (
            context.operator != Operator.CRON_HEALTH
            or proposal.capability != Capability.REPAIR_DECLARED_CRON_SOURCE
        ):
            raise CandidatePolicyError(
                "Chat source repair requires the separately qualified baseline"
            )
        if proposal.declared_job not in self.repair_targets:
            raise CandidatePolicyError("Declared CRON job is not repairable")

    def _require_registered(self, candidate: RepairCandidate) -> None:
        if self._candidates.get(candidate.candidate_id) != candidate:
            raise CandidatePolicyError("Unknown autonomous repair candidate")

    def _metadata_path(self, candidate_id: uuid.UUID) -> Path:
        return self.candidates_root / f"{candidate_id}.json"

    def _require_lease(self, db, candidate: RepairCandidate) -> None:
        if not self.repository.owns_repair_lease(db, context=candidate.context):
            raise CandidatePolicyError("Autonomous repair lease is no longer owned")

    def _require_candidate_base(self, candidate: RepairCandidate) -> None:
        if self.git_bridge_executable:
            head = self._bridge_inspect(candidate)["head_sha"]
        else:
            head = self._git(
                "rev-parse", "HEAD", cwd=candidate.worktree, capture=True
            ).stdout.strip()
        if head != candidate.base_sha:
            raise CandidatePolicyError("Candidate history changed outside the pipeline")

    def _audit(
        self,
        db,
        candidate: RepairCandidate,
        reason_code: str,
        before_digest: str,
        after_digest: str,
    ) -> None:
        self.repository.append_action(
            db,
            context=candidate.context,
            capability=candidate.proposal.capability.value,
            reason_code=reason_code,
            resource_kind=ResourceKind.SOURCE_REPAIR.value,
            resource_identifier=candidate.proposal.declared_job,
            before_digest=before_digest,
            after_digest=after_digest,
            now=datetime.now(UTC),
        )
        db.commit()

    def _changed_paths(self, candidate: RepairCandidate) -> tuple[str, ...]:
        if self.git_bridge_executable:
            return tuple(self._bridge_inspect(candidate)["changed_paths"])
        tracked = self._git(
            "diff", "--name-only", "HEAD", cwd=candidate.worktree, capture=True
        ).stdout.splitlines()
        untracked = self._git(
            "ls-files",
            "--others",
            "--exclude-standard",
            cwd=candidate.worktree,
            capture=True,
        ).stdout.splitlines()
        paths = tuple(sorted(set((*tracked, *untracked))))
        if any(not _safe_relative_path(path) for path in paths):
            raise CandidatePolicyError("Candidate path is invalid")
        return paths

    def _patch_bytes(
        self, candidate: RepairCandidate, changed: tuple[str, ...]
    ) -> bytes:
        if self.git_bridge_executable:
            inspected = self._bridge_inspect(candidate)
            if tuple(inspected["changed_paths"]) != changed:
                raise CandidatePolicyError("Candidate changed during bridge inspection")
            try:
                return base64.b64decode(inspected["patch"], validate=True)
            except (TypeError, ValueError):
                raise CandidatePolicyError("Source bridge returned an invalid patch")
        patch = self._git(
            "diff", "--binary", "HEAD", cwd=candidate.worktree, capture=True
        ).stdout.encode()
        tracked = set(
            self._git(
                "ls-files", cwd=candidate.worktree, capture=True
            ).stdout.splitlines()
        )
        for path in changed:
            target = candidate.worktree / path
            if path not in tracked:
                if target.is_symlink() or not target.is_file():
                    raise CandidatePolicyError("Untracked candidate path is not a file")
                patch += b"\0" + path.encode() + b"\0" + target.read_bytes()
        return patch

    def _forbidden(self, path: str) -> bool:
        target = self.source_repository / path
        name = target.name.lower()
        return (
            path.startswith(self._FORBIDDEN_PREFIXES)
            or name in {".env", "keys.env"}
            or name.endswith((".env", ".key", ".pem"))
            or any(term in name for term in ("credential", "secret"))
        )

    def _git(self, *args: str, cwd: Path, capture: bool = False):
        return subprocess.run(
            [
                self.git_executable,
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=cwd,
            check=True,
            capture_output=capture,
            text=True,
        )

    def _bridge(self, *args, capture: bool = False):
        if self.git_bridge_executable is None:
            raise CandidatePolicyError("Autonomous source bridge is not configured")
        return subprocess.run(
            [self.git_bridge_executable, *(str(value) for value in args)],
            check=True,
            capture_output=capture,
            text=True,
            timeout=1800,
            env={"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
        )

    def _bridge_inspect(self, candidate: RepairCandidate) -> dict:
        outcome = self._bridge(
            "inspect",
            candidate.candidate_id,
            candidate.context.run_id,
            capture=True,
        )
        try:
            value = json.loads(outcome.stdout)
        except json.JSONDecodeError:
            raise CandidatePolicyError(
                "Source bridge returned invalid evidence"
            ) from None
        if (
            not isinstance(value, dict)
            or set(value)
            != {"base_sha", "changed_paths", "head_sha", "patch", "patch_digest"}
            or value["base_sha"] != candidate.base_sha
            or not isinstance(value["changed_paths"], list)
            or any(not _safe_relative_path(path) for path in value["changed_paths"])
            or not isinstance(value["head_sha"], str)
            or not isinstance(value["patch"], str)
            or not _digest(value["patch_digest"])
        ):
            raise CandidatePolicyError("Source bridge returned invalid evidence")
        return value

    def _run_check(self, command: tuple[str, ...], cwd: Path) -> CheckOutcome:
        if (
            not command
            or command[0] not in {"lint", "pytest"}
            or len(command) < 2
            or any(not _safe_relative_path(value) for value in command[1:])
        ):
            raise CandidatePolicyError("Autonomous check command is invalid")
        executable = self.environ.get(
            "PWC_AUTONOMOUS_CHECK_RUNNER", "/usr/local/sbin/pwc-autonomous-check"
        )
        if not Path(executable).is_absolute():
            raise CandidatePolicyError("Autonomous check runner is not configured")
        outcome = subprocess.run(
            [executable, "--worktree", str(cwd), "--", *command],
            check=True,
            text=True,
            capture_output=True,
            timeout=1800,
            env={"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
        )
        output = (outcome.stdout + outcome.stderr).encode()
        if len(output) > 64_000:
            raise CandidatePolicyError("Autonomous check output exceeded its limit")
        return CheckOutcome(command, hashlib.sha256(output).hexdigest())
