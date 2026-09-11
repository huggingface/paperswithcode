#!/usr/bin/env python3
"""Root-side closed broker for autonomous source-repair Git operations."""

from __future__ import annotations

import base64
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path, PurePosixPath


REPOSITORY = Path("/srv/paperswithcode/repository.git")
CANDIDATES = Path("/var/lib/paperswithcode/autonomous-candidates")
BROKER_STATE = Path("/var/lib/paperswithcode/autonomous-source-broker")
GIT = "/usr/bin/git"
PSQL = "/usr/bin/psql"
RUNUSER = "/usr/sbin/runuser"
DATABASE = "paperswithcode_hf"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SAFE_JOB = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")
_FORBIDDEN_PREFIXES = (
    "backend/database/migrations/",
    "deploy/nginx",
    "deploy/systemd",
    "deploy/install_host_layout.py",
    "deploy/keys",
)


class BridgeError(RuntimeError):
    pass


def _safe_path(value: str) -> bool:
    path = PurePosixPath(value)
    name = path.name.lower()
    return bool(
        value
        and "\\" not in value
        and not path.is_absolute()
        and ".." not in path.parts
        and str(path) == value
        and not value.startswith(_FORBIDDEN_PREFIXES)
        and name not in {".env", "keys.env"}
        and not name.endswith((".env", ".key", ".pem"))
        and not any(term in name for term in ("credential", "secret"))
    )


def _git(repository: Path, *arguments: str, capture: bool = False):
    return subprocess.run(
        [
            GIT,
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "commit.gpgsign=false",
            "-c",
            f"safe.directory={repository}",
            *arguments,
        ],
        cwd=repository,
        check=True,
        capture_output=capture,
        text=True,
        env={"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
    )


def _metadata_path(candidate_id: uuid.UUID, state_root: Path) -> Path:
    return state_root / f"{candidate_id}.json"


def _candidate_path(candidate_id: uuid.UUID, candidates_root: Path) -> Path:
    return candidates_root / f"candidate-{candidate_id.hex}"


def _load_candidate(
    candidate_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    candidates_root: Path,
    state_root: Path,
) -> tuple[Path, str]:
    try:
        value = json.loads(
            _metadata_path(candidate_id, state_root).read_text(encoding="utf-8")
        )
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        raise BridgeError("unknown autonomous source candidate") from None
    candidate = _candidate_path(candidate_id, candidates_root)
    if (
        not isinstance(value, dict)
        or set(value) != {"base_sha", "candidate_id", "run_id", "worktree"}
        or value["candidate_id"] != str(candidate_id)
        or value["run_id"] != str(run_id)
        or value["worktree"] != str(candidate)
        or not isinstance(value["base_sha"], str)
        or _SHA.fullmatch(value["base_sha"]) is None
        or not candidate.is_dir()
    ):
        raise BridgeError("invalid autonomous source candidate")
    return candidate, value["base_sha"]


def prepare_candidate(
    candidate_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    repository: Path = REPOSITORY,
    candidates_root: Path = CANDIDATES,
    state_root: Path = BROKER_STATE,
    owner: str = "pwc-cron",
) -> str:
    candidates_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_root.chmod(0o700)
    worktree = _candidate_path(candidate_id, candidates_root)
    metadata = _metadata_path(candidate_id, state_root)
    if worktree.exists() or metadata.exists():
        raise BridgeError("autonomous source candidate already exists")
    for existing in state_root.glob("*.json"):
        try:
            value = json.loads(existing.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("run_id") == str(run_id):
            raise BridgeError("autonomous run already owns a source candidate")
    _git(repository, "fetch", "--prune", "origin", "main")
    base_sha = _git(
        repository, "rev-parse", "refs/heads/main", capture=True
    ).stdout.strip()
    if _SHA.fullmatch(base_sha) is None:
        raise BridgeError("origin/main returned an invalid SHA")
    _git(repository, "worktree", "add", "--detach", str(worktree), base_sha)
    try:
        if owner:
            account = pwd.getpwnam(owner)
            for root, directories, files in os.walk(worktree):
                os.lchown(root, account.pw_uid, account.pw_gid)
                for name in (*directories, *files):
                    os.lchown(Path(root) / name, account.pw_uid, account.pw_gid)
            git_pointer = worktree / ".git"
            os.chown(git_pointer, 0, 0)
            git_pointer.chmod(0o444)
        temporary = metadata.with_suffix(".new")
        temporary.write_text(
            json.dumps(
                {
                    "base_sha": base_sha,
                    "candidate_id": str(candidate_id),
                    "run_id": str(run_id),
                    "worktree": str(worktree),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        os.replace(temporary, metadata)
    except Exception:
        _git(repository, "worktree", "remove", "--force", str(worktree))
        raise
    return base_sha


def inspect_candidate(
    candidate_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    repository: Path = REPOSITORY,
    candidates_root: Path = CANDIDATES,
    state_root: Path = BROKER_STATE,
) -> dict[str, object]:
    worktree, base_sha = _load_candidate(
        candidate_id,
        run_id,
        candidates_root=candidates_root,
        state_root=state_root,
    )
    head = _git(worktree, "rev-parse", "HEAD", capture=True).stdout.strip()
    tracked = _git(
        worktree, "diff", "--name-only", "HEAD", capture=True
    ).stdout.splitlines()
    untracked = _git(
        worktree,
        "ls-files",
        "--others",
        "--exclude-standard",
        capture=True,
    ).stdout.splitlines()
    changed = tuple(sorted(set((*tracked, *untracked))))
    if head != base_sha or any(not _safe_path(path) for path in changed):
        raise BridgeError(
            "autonomous source candidate escaped its history or path scope"
        )
    patch = _git(worktree, "diff", "--binary", "HEAD", capture=True).stdout.encode()
    tracked_paths = set(_git(worktree, "ls-files", capture=True).stdout.splitlines())
    for path in changed:
        target = worktree / path
        if path not in tracked_paths:
            if target.is_symlink() or not target.is_file():
                raise BridgeError("untracked autonomous candidate path is unsafe")
            patch += b"\0" + path.encode() + b"\0" + target.read_bytes()
    if len(patch) > 2_000_000:
        raise BridgeError("autonomous source candidate patch exceeds the limit")
    return {
        "base_sha": base_sha,
        "changed_paths": list(changed),
        "head_sha": head,
        "patch": base64.b64encode(patch).decode(),
        "patch_digest": sha256(patch).hexdigest(),
    }


def publish_candidate(
    candidate_id: uuid.UUID,
    run_id: uuid.UUID,
    job_name: str,
    expected_patch_digest: str,
    *,
    repository: Path = REPOSITORY,
    candidates_root: Path = CANDIDATES,
    state_root: Path = BROKER_STATE,
) -> str:
    if (
        _SAFE_JOB.fullmatch(job_name) is None
        or _DIGEST.fullmatch(expected_patch_digest) is None
    ):
        raise BridgeError("invalid autonomous source publication scope")
    inspected = inspect_candidate(
        candidate_id,
        run_id,
        repository=repository,
        candidates_root=candidates_root,
        state_root=state_root,
    )
    changed = tuple(inspected["changed_paths"])
    if not changed or inspected["patch_digest"] != expected_patch_digest:
        raise BridgeError("reviewed autonomous patch no longer matches")
    worktree = _candidate_path(candidate_id, candidates_root)
    _git(repository, "fetch", "--prune", "origin", "main")
    origin_sha = _git(
        repository, "rev-parse", "refs/heads/main", capture=True
    ).stdout.strip()
    if origin_sha != inspected["base_sha"]:
        raise BridgeError("origin/main advanced after candidate preparation")
    _git(worktree, "add", "--", *changed)
    _git(
        worktree,
        "-c",
        "user.name=Papers With Code Autonomy",
        "-c",
        "user.email=autonomy@paperswithcode.co",
        "commit",
        "-m",
        f"fix(cron): autonomous repair {run_id}",
    )
    published_sha = _git(worktree, "rev-parse", "HEAD", capture=True).stdout.strip()
    parent = _git(worktree, "rev-parse", "HEAD^", capture=True).stdout.strip()
    if parent != origin_sha or _SHA.fullmatch(published_sha) is None:
        raise BridgeError("autonomous source commit parent changed")
    _git(worktree, "-c", "remote.origin.mirror=false", "push", "origin", "HEAD:main")
    remote = _git(
        repository,
        "ls-remote",
        "--exit-code",
        "origin",
        "refs/heads/main",
        capture=True,
    ).stdout.partition("\t")[0]
    if remote != published_sha:
        raise BridgeError("origin/main did not retain the autonomous source SHA")
    return published_sha


def cleanup_candidate(
    candidate_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    repository: Path = REPOSITORY,
    candidates_root: Path = CANDIDATES,
    state_root: Path = BROKER_STATE,
) -> None:
    worktree, _base_sha = _load_candidate(
        candidate_id,
        run_id,
        candidates_root=candidates_root,
        state_root=state_root,
    )
    _git(repository, "worktree", "remove", "--force", str(worktree))
    _metadata_path(candidate_id, state_root).unlink()


def authorize(
    run_id: uuid.UUID,
    *,
    require_review: bool,
    patch_digest: str = "",
    job_name: str = "",
) -> None:
    review = ""
    if require_review:
        review = f"""
       AND EXISTS (
           SELECT 1 FROM public.autonomous_action AS reviewed
            WHERE reviewed.run_id = run.id
              AND reviewed.operator = 'cron_health'
              AND reviewed.capability = 'repair_declared_cron_source'
              AND reviewed.reason_code = 'review_approved'
              AND reviewed.resource_identifier = '{job_name}'
              AND reviewed.before_digest = '{patch_digest}'
       )
"""
    query = f"""
SELECT run.id
  FROM public.autonomous_run AS run
 WHERE run.id = '{run_id}'::uuid
   AND run.operator = 'cron_health' AND run.dry_run = false
   AND EXISTS (
       SELECT 1 FROM public.autonomous_operator_state
        WHERE operator = 'global' AND manual_mode = false
   )
   AND EXISTS (
       SELECT 1 FROM public.autonomous_operator_state
        WHERE operator = 'cron_health' AND enabled = true
   )
   AND EXISTS (
       SELECT 1 FROM public.autonomous_repair_lease
        WHERE singleton_key = 'source_repair'
          AND owner_run_id = run.id
          AND owner_operator = 'cron_health'
          AND expires_at > clock_timestamp()
   )
{review}
LIMIT 1;
"""
    outcome = subprocess.run(
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
    if outcome.stdout.strip() != str(run_id):
        raise BridgeError("no live source-repair authorization matched the request")


def authorize_abandoned(
    candidate_id: uuid.UUID, run_id: uuid.UUID, *, state_root: Path = BROKER_STATE
) -> None:
    metadata = _metadata_path(candidate_id, state_root)
    try:
        age = datetime.now(UTC) - datetime.fromtimestamp(
            metadata.stat().st_mtime, tz=UTC
        )
    except FileNotFoundError:
        raise BridgeError("unknown autonomous source candidate") from None
    if age < timedelta(hours=2):
        raise BridgeError("autonomous source candidate is not abandoned")
    query = f"""
SELECT NOT EXISTS (
    SELECT 1 FROM public.autonomous_repair_lease
     WHERE singleton_key = 'source_repair'
       AND owner_run_id = '{run_id}'::uuid
       AND expires_at > clock_timestamp()
);
"""
    outcome = subprocess.run(
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
    if outcome.stdout.strip() != "t":
        raise BridgeError("autonomous source candidate still owns a live lease")


def parse_request(arguments: list[str]) -> tuple[str, uuid.UUID, uuid.UUID, list[str]]:
    if len(arguments) < 3:
        raise BridgeError("autonomous source request has an invalid shape")
    action, candidate_value, run_value, *extra = arguments
    if action not in {
        "prepare",
        "inspect",
        "publish",
        "cleanup",
        "cleanup-abandoned",
    }:
        raise BridgeError("unknown autonomous source action")
    try:
        candidate_id = uuid.UUID(candidate_value)
        run_id = uuid.UUID(run_value)
    except ValueError:
        raise BridgeError("autonomous source request requires exact IDs") from None
    expected = 2 if action == "publish" else 0
    if len(extra) != expected:
        raise BridgeError("autonomous source request has an invalid shape")
    if action == "publish" and (
        _SAFE_JOB.fullmatch(extra[0]) is None or _DIGEST.fullmatch(extra[1]) is None
    ):
        raise BridgeError("invalid autonomous source publication scope")
    return action, candidate_id, run_id, extra


def main(arguments: list[str] | None = None) -> int:
    if os.geteuid() != 0:
        raise BridgeError("autonomous source bridge requires root")
    action, candidate_id, run_id, extra = parse_request(
        list(sys.argv[1:] if arguments is None else arguments)
    )
    if action == "cleanup-abandoned":
        authorize_abandoned(candidate_id, run_id)
    else:
        authorize(
            run_id,
            require_review=action == "publish",
            patch_digest=extra[1] if action == "publish" else "",
            job_name=extra[0] if action == "publish" else "",
        )
    if action == "prepare":
        print(prepare_candidate(candidate_id, run_id))
    elif action == "inspect":
        print(json.dumps(inspect_candidate(candidate_id, run_id), sort_keys=True))
    elif action == "publish":
        print(publish_candidate(candidate_id, run_id, extra[0], extra[1]))
    else:
        cleanup_candidate(candidate_id, run_id)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BridgeError, OSError, shutil.Error, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error
