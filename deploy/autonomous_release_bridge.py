#!/usr/bin/env python3
"""Root-side, closed command broker for autonomous exact-SHA releases."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from hashlib import sha256
from pathlib import Path


REPOSITORY = Path("/srv/paperswithcode/repository.git")
DEPLOY = "/usr/local/sbin/pwc-deploy"
ROLLBACK = "/usr/local/sbin/pwc-rollback"
STATUS = "/usr/local/sbin/pwc-status"
GIT = "/usr/bin/git"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_SCHEMA = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
PSQL = "/usr/bin/psql"
RUNUSER = "/usr/sbin/runuser"
DATABASE = "paperswithcode_hf"


class BridgeError(RuntimeError):
    pass


def _sha(value: str) -> bool:
    return _SHA.fullmatch(value) is not None


def parse_request(arguments: list[str]) -> tuple[str, ...] | None:
    if arguments == ["status"]:
        return (STATUS,)
    if len(arguments) == 3 and arguments[0] == "diff":
        if all(_sha(value) for value in arguments[1:]):
            return None
        raise BridgeError("diff requires two exact SHAs")
    if len(arguments) not in {4, 6}:
        raise BridgeError("release request has an invalid shape")
    action, environment, sha, run_id, *confirmation = arguments
    try:
        uuid.UUID(run_id)
    except ValueError:
        raise BridgeError("release requires an exact run ID") from None
    if environment not in {"staging", "production"} or not _sha(sha):
        raise BridgeError("release requires an exact environment and SHA")
    expected_confirmation = {
        ("deploy", "production"): ["--confirm", "DEPLOY_PRODUCTION"],
        ("rollback", "production"): ["--confirm", "ROLLBACK_PRODUCTION"],
    }.get((action, environment), [])
    if confirmation != expected_confirmation:
        raise BridgeError("release confirmation does not match the closed request")
    if action == "deploy":
        return (DEPLOY, environment, sha, *confirmation)
    if action == "rollback":
        return (ROLLBACK, environment, "--failed-sha", sha, *confirmation)
    raise BridgeError("unknown autonomous release action")


def consume_authorization(
    action: str,
    environment: str,
    sha: str,
    run_id: str,
    *,
    runner=subprocess.run,
    schema: str = "public",
) -> None:
    reason_code = {"deploy": "deploy_started", "rollback": "rollback_started"}.get(
        action
    )
    if reason_code is None:
        raise BridgeError("release action cannot consume an authorization")
    if environment not in {"staging", "production"} or not _sha(sha):
        raise BridgeError("release authorization scope is invalid")
    if _SCHEMA.fullmatch(schema) is None:
        raise BridgeError("release authorization schema is invalid")
    try:
        normalized_run_id = str(uuid.UUID(run_id))
    except ValueError:
        raise BridgeError("release authorization run ID is invalid") from None
    digest = sha256(sha.encode()).hexdigest()
    resource_identifier = f"{environment}:{sha}"
    query = f"""
WITH eligible AS (
    SELECT action.id
      FROM {schema}.autonomous_action AS action
      JOIN {schema}.autonomous_run AS run ON run.id = action.run_id
     WHERE action.run_id = '{normalized_run_id}'::uuid
       AND run.operator = 'cron_health' AND run.dry_run = false
       AND action.operator = 'cron_health'
       AND action.capability = 'repair_declared_cron_source'
       AND action.reason_code = '{reason_code}'
       AND action.resource_kind = 'source_repair'
       AND action.resource_identifier = '{resource_identifier}'
       AND action.after_digest = '{digest}'
       AND action.created_at >= clock_timestamp() - interval '5 minutes'
       AND EXISTS (
           SELECT 1 FROM {schema}.autonomous_operator_state
            WHERE operator = 'global' AND manual_mode = false
       )
       AND EXISTS (
           SELECT 1 FROM {schema}.autonomous_operator_state
            WHERE operator = 'cron_health' AND enabled = true
       )
       AND EXISTS (
           SELECT 1 FROM {schema}.autonomous_repair_lease
            WHERE singleton_key = 'source_repair'
              AND owner_run_id = action.run_id
              AND owner_operator = 'cron_health'
              AND expires_at > clock_timestamp()
       )
       AND EXISTS (
           SELECT 1 FROM {schema}.autonomous_action AS published
            WHERE published.run_id = action.run_id
              AND published.operator = 'cron_health'
              AND published.capability = 'repair_declared_cron_source'
              AND published.reason_code = 'published'
              AND published.resource_kind = 'source_repair'
              AND published.after_digest = '{digest}'
              AND published.created_at <= action.created_at
       )
       AND NOT EXISTS (
           SELECT 1 FROM {schema}.autonomous_release_consumption AS consumed
            WHERE consumed.authorization_action_id = action.id
       )
     ORDER BY action.created_at DESC
     LIMIT 1
     FOR UPDATE OF action
), consumed AS (
    INSERT INTO {schema}.autonomous_release_consumption (
        authorization_action_id, run_id, action, environment, sha
    )
    SELECT id, '{normalized_run_id}'::uuid, '{action}', '{environment}', '{sha}'
      FROM eligible
    ON CONFLICT DO NOTHING
    RETURNING authorization_action_id
)
SELECT authorization_action_id FROM consumed;
"""
    outcome = runner(
        [
            RUNUSER,
            "-u",
            "postgres",
            "--",
            PSQL,
            "--dbname",
            DATABASE,
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            "--set",
            "ON_ERROR_STOP=1",
            "--command",
            query,
        ],
        check=True,
        capture_output=True,
        text=True,
        env={"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
    )
    try:
        uuid.UUID(outcome.stdout.strip())
    except ValueError:
        raise BridgeError(
            "no live single-use release authorization matched the request"
        ) from None


def changed_paths(before_sha: str, after_sha: str) -> tuple[str, ...]:
    environment = {"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"}
    subprocess.run(
        [GIT, "--git-dir", str(REPOSITORY), "fetch", "--prune", "origin"],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
    )
    remote_main = subprocess.run(
        [GIT, "--git-dir", str(REPOSITORY), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    ).stdout.strip()
    if subprocess.run(
        [
            GIT,
            "--git-dir",
            str(REPOSITORY),
            "merge-base",
            "--is-ancestor",
            after_sha,
            remote_main,
        ],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
    ).returncode:
        raise BridgeError("candidate SHA is not on current origin/main")
    outcome = subprocess.run(
        [
            GIT,
            "--git-dir",
            str(REPOSITORY),
            "diff",
            "--name-only",
            before_sha,
            after_sha,
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    paths = tuple(outcome.stdout.splitlines())
    if any(not path or "\n" in path or "\r" in path for path in paths):
        raise BridgeError("release diff contained an invalid path")
    return paths


def main(arguments: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if arguments is None else arguments)
    if os.geteuid() != 0:
        raise BridgeError("autonomous release bridge requires root")
    command = parse_request(values)
    if command is None:
        for path in changed_paths(values[1], values[2]):
            print(path)
        return 0
    if values == ["status"]:
        os.execv(command[0], list(command))
        raise AssertionError("unreachable")
    consume_authorization(values[0], values[1], values[2], values[3])
    os.execv(command[0], list(command))
    raise AssertionError("unreachable")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BridgeError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error
