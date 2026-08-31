"""Exact-SHA deployment and fail-closed rollback for autonomous repairs."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256

from backend.services.autonomous_capabilities import Capability, ResourceKind
from backend.services.autonomous_operations_repository import Operator, RunContext


_SHA = re.compile(r"^[0-9a-f]{40}$")


class ReleaseVerificationError(RuntimeError):
    def __init__(self, message: str, *, rollback_performed: bool = False) -> None:
        super().__init__(message)
        self.rollback_performed = rollback_performed


class AutonomousReleaseService:
    def __init__(
        self,
        *,
        repository,
        command_runner: Callable[[list[str]], None] | None = None,
        deployed_sha: Callable[[str], str] | None = None,
        smoke_verifier: Callable[[str, str], bool],
        deploy_executable: str = "/usr/local/sbin/pwc-autonomous-release",
        rollback_executable: str = "/usr/local/sbin/pwc-autonomous-release",
        status_executable: str = "/usr/local/sbin/pwc-autonomous-release",
        inspection_runner: Callable[[list[str]], str] | None = None,
        changed_paths: Callable[[str, str], tuple[str, ...]] | None = None,
    ) -> None:
        if any(
            not value.startswith("/")
            for value in (deploy_executable, rollback_executable, status_executable)
        ):
            raise ValueError("Release lifecycle executables must be absolute")
        self.command_runner = command_runner or self._run
        self.repository = repository
        self.deployed_sha = deployed_sha or (
            lambda environment: self._deployed_sha(status_executable, environment)
        )
        self.smoke_verifier = smoke_verifier
        self.deploy_executable = deploy_executable
        self.rollback_executable = rollback_executable
        self.inspection_runner = inspection_runner or self._inspect
        self.changed_paths = changed_paths or self._changed_paths

    def deploy_exact_sha(
        self, db, context: RunContext, environment: str, sha: str
    ) -> None:
        self._validate(environment, sha)
        self._require_authorized(db, context, sha)
        previous_sha = self.deployed_sha(environment)
        if environment == "production" and any(
            self._chat_path(path) for path in self.changed_paths(previous_sha, sha)
        ):
            raise ReleaseVerificationError(
                "production candidate contains staging-only chat changes"
            )
        self._audit(db, context, "deploy_started", environment, previous_sha, sha)
        self._require_authorized(db, context, sha)
        command = [
            self.deploy_executable,
            "deploy",
            environment,
            sha,
            str(context.run_id),
        ]
        if environment == "production":
            command.extend(("--confirm", "DEPLOY_PRODUCTION"))
        try:
            self.command_runner(command)
        except (OSError, subprocess.CalledProcessError) as error:
            rolled_back = False
            if self.deployed_sha(environment) == sha:
                self.rollback(db, context, environment, sha)
                rolled_back = True
            self._audit(db, context, "deploy_failed", environment, previous_sha, sha)
            raise ReleaseVerificationError(
                f"{environment} exact-SHA deployment command failed",
                rollback_performed=rolled_back,
            ) from error
        active_sha = self.deployed_sha(environment)
        if active_sha != sha:
            self._audit(
                db, context, "unexpected_active_sha", environment, sha, active_sha
            )
            raise ReleaseVerificationError(f"{environment} activated an unexpected SHA")
        if not self.smoke_verifier(environment, sha):
            self.rollback(db, context, environment, sha)
            if self.deployed_sha(environment) != previous_sha:
                raise ReleaseVerificationError(
                    f"{environment} rollback did not restore the previous SHA"
                )
            raise ReleaseVerificationError(
                f"{environment} failed exact-SHA release verification",
                rollback_performed=True,
            )
        self._audit(db, context, "deployment_verified", environment, previous_sha, sha)

    def rollback(
        self, db, context: RunContext, environment: str, failed_sha: str
    ) -> None:
        self._validate(environment, failed_sha)
        if context.operator != Operator.CRON_HEALTH:
            raise ReleaseVerificationError(
                "Chat rollback requires the separately qualified baseline"
            )
        if not self.repository.owns_repair_lease(db, context=context):
            raise ReleaseVerificationError("source-repair lease is no longer owned")
        if not self.repository.has_published_repair(
            db,
            context=context,
            sha_digest=sha256(failed_sha.encode()).hexdigest(),
        ):
            raise ReleaseVerificationError("failed SHA was not published by this run")
        if self.deployed_sha(environment) != failed_sha:
            raise ReleaseVerificationError("failed SHA is no longer active")
        self._audit(
            db, context, "rollback_started", environment, failed_sha, failed_sha
        )
        self._require_authorized(db, context, failed_sha)
        command = [
            self.rollback_executable,
            "rollback",
            environment,
            failed_sha,
            str(context.run_id),
        ]
        if environment == "production":
            command.extend(("--confirm", "ROLLBACK_PRODUCTION"))
        self.command_runner(command)
        restored_sha = self.deployed_sha(environment)
        if restored_sha == failed_sha:
            raise ReleaseVerificationError("rollback did not replace the failed SHA")
        self._audit(db, context, "rolled_back", environment, failed_sha, restored_sha)

    @staticmethod
    def _validate(environment: str, sha: str) -> None:
        if environment not in {"production", "staging"} or _SHA.fullmatch(sha) is None:
            raise ValueError("Exact release environment and SHA are required")

    @staticmethod
    def _run(command: list[str]) -> None:
        subprocess.run(command, check=True, text=True)

    @staticmethod
    def _inspect(command: list[str]) -> str:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env={"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
        ).stdout

    @staticmethod
    def _deployed_sha(status_executable: str, environment: str) -> str:
        outcome = subprocess.run(
            [status_executable, "status"], check=True, capture_output=True, text=True
        )
        value = json.loads(outcome.stdout)
        try:
            sha = value["environments"][environment]["current"]["git_sha"]
        except (KeyError, TypeError):
            raise ReleaseVerificationError(
                "deployment status omitted the active SHA"
            ) from None
        if not isinstance(sha, str) or _SHA.fullmatch(sha) is None:
            raise ReleaseVerificationError("deployment status contained an invalid SHA")
        return sha

    def _require_authorized(self, db, context: RunContext, sha: str) -> None:
        if context.operator != Operator.CRON_HEALTH:
            raise ReleaseVerificationError(
                "Chat release requires the separately qualified baseline"
            )
        self.repository.assert_mutation_allowed(db, context)
        if not self.repository.owns_repair_lease(db, context=context):
            raise ReleaseVerificationError("source-repair lease is no longer owned")
        if not self.repository.has_published_repair(
            db,
            context=context,
            sha_digest=sha256(sha.encode()).hexdigest(),
        ):
            raise ReleaseVerificationError("SHA was not published by this run")

    def _audit(
        self,
        db,
        context: RunContext,
        reason_code: str,
        environment: str,
        before_sha: str,
        after_sha: str,
    ) -> None:
        self.repository.append_action(
            db,
            context=context,
            capability=Capability.REPAIR_DECLARED_CRON_SOURCE.value,
            reason_code=reason_code,
            resource_kind=ResourceKind.SOURCE_REPAIR.value,
            resource_identifier=f"{environment}:{after_sha}",
            before_digest=sha256(before_sha.encode()).hexdigest(),
            after_digest=sha256(after_sha.encode()).hexdigest(),
            now=datetime.now(UTC),
        )
        db.commit()

    def _changed_paths(self, before_sha: str, after_sha: str) -> tuple[str, ...]:
        output = self.inspection_runner(
            [self.deploy_executable, "diff", before_sha, after_sha]
        )
        return tuple(output.splitlines())

    @staticmethod
    def _chat_path(path: str) -> bool:
        lowered = path.lower()
        return "chat" in lowered or "external_pi" in lowered or "external-pi" in lowered
