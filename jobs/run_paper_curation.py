"""Entrypoint for a remote, scoped Papers With Code Codex Job."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


API_URL = os.environ["PWC_CURATION_API_URL"].rstrip("/")
JOB_ID = os.environ["PWC_CURATION_JOB_ID"]
TOKEN = os.environ["PWC_CURATION_JOB_TOKEN"]
KIND = os.environ["PWC_CURATION_KIND"]
REVISION = os.environ["PWC_GIT_SHA"]
WORKTREE = Path("/tmp/paperswithcode")
ASKPASS = Path("/tmp/pwc-git-askpass.sh")
USER_AGENT = "PapersWithCode-Curation/1.0 (+https://paperswithcode.co)"


def callback(path: str, payload: dict) -> None:
    request = urllib.request.Request(
        f"{API_URL}/admin/codex-curation/jobs/{JOB_ID}/{path}",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30):
        pass


def main() -> int:
    try:
        ASKPASS.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            "  *Username*) printf '%s\\n' 'x-access-token' ;;\n"
            "  *Password*) printf '%s\\n' \"$GITHUB_TOKEN\" ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        ASKPASS.chmod(0o700)
        clone_env = {
            **os.environ,
            "GIT_ASKPASS": str(ASKPASS),
            "GIT_TERMINAL_PROMPT": "0",
        }
        subprocess.run(
            [
                "git",
                "clone",
                "https://github.com/huggingface/paperswithcode.git",
                str(WORKTREE),
            ],
            check=True,
            env=clone_env,
        )
        subprocess.run(["git", "checkout", REVISION], cwd=WORKTREE, check=True)
        subprocess.run(
            ["codex", "login", "--with-api-key"],
            input=f"{os.environ['OPENAI_API_KEY']}\n",
            text=True,
            check=True,
        )
        final_path = Path("/tmp/codex-final.txt")
        skill = ".agents/skills/remote-paper-curation/SKILL.md"
        kind_requirement = (
            "For add-evals, call `python jobs/curation_api.py leaderboards "
            '"<benchmark>"` for every benchmark found in the source before '
            "submitting the payload. The taxonomy command returns only tasks and methods. "
            "Never use it to decide whether a benchmark or leaderboard exists. "
            if KIND == "add-evals"
            else ""
        )
        prompt = (
            f"Run the remote paper-curation skill at {skill}. Job kind: {KIND}. "
            f"{kind_requirement}"
            "Use the job-scoped helper in jobs/curation_api.py for every VPS read and write; "
            "do not access PostgreSQL, backend/keys.env, or modify repository files. "
            "Apply the scoped mutation before finishing, then give a concise audit report."
        )
        completed = subprocess.run(
            [
                "codex",
                "exec",
                "--ephemeral",
                "--json",
                "--sandbox",
                "danger-full-access",
                "--cd",
                str(WORKTREE),
                "--output-last-message",
                str(final_path),
                prompt,
            ],
            check=False,
        )
        report = (
            final_path.read_text(encoding="utf-8").strip()
            if final_path.exists()
            else ""
        )
        if completed.returncode:
            callback(
                "complete",
                {
                    "report": report,
                    "error": f"Codex exited with status {completed.returncode}.",
                },
            )
            return completed.returncode
        callback("complete", {"report": report})
        return 0
    except Exception as exc:
        try:
            callback(
                "complete",
                {
                    "report": "",
                    "error": f"Remote runner failed ({type(exc).__name__}).",
                },
            )
        except urllib.error.URLError:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
