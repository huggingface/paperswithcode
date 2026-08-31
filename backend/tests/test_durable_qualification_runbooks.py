from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]


def _bash_block(path: Path, after: str) -> str:
    text = path.read_text(encoding="utf-8")
    section = text.split(after, 1)[1]
    return section.split("```bash\n", 1)[1].split("\n```", 1)[0]


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _qualification_fixture(tmp_path: Path, *, install_runtime: bool = True):
    app = tmp_path / "srv/paperswithcode"
    release_root = app / "releases"
    sha = "a" * 40
    release = release_root / f"{sha[:12]}-staging"
    release.mkdir(parents=True)
    lock = b"independent-lock-fixture\n"
    (release / "uv.lock").write_bytes(lock)
    (release / "release.json").write_text(
        json.dumps(
            {
                "git_sha": sha,
                "release_id": f"{sha[:12]}-staging",
                "chat_runtime": {"worker_contract_version": "102"},
            }
        ),
        encoding="utf-8",
    )
    current = app / "environments/staging/current"
    current.parent.mkdir(parents=True)
    current.symlink_to(release)
    runtime = app / "runtimes" / hashlib.sha256(lock).hexdigest()
    log = tmp_path / "qualification.log"
    if install_runtime:
        runtime_python = runtime / "bin/python"
        runtime_python.parent.mkdir(parents=True)
        _write_executable(
            runtime_python,
            "#!/bin/sh\n"
            "printf '%s|%s|%s|%s|%s\\n' \"$PWC_RELEASE_ID\" "
            '"$PWC_CHAT_WORKER_CONTRACT_VERSION" "$PWD" "$0" "$*" '
            '>> "$COMMAND_LOG"\n',
        )

    env_file = tmp_path / "etc/paperswithcode/staging.env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text(
        "PWC_RELEASE_ID=stale-release\n"
        "PWC_CHAT_WORKER_CONTRACT_VERSION=3\n"
        "PWC_LOADTEST_ENV_MARKER=loaded\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "sudo", '#!/bin/sh\nexec "$@"\n')
    _write_executable(
        fake_bin / "systemd-run",
        "#!/bin/bash\n"
        "set -eu\n"
        "while [ $# -gt 0 ]; do\n"
        '  case "$1" in\n'
        "    --uid=*) uid=${1#*=} ;;\n"
        "    --gid=*) gid=${1#*=} ;;\n"
        "    --working-directory=*) working=${1#*=} ;;\n"
        "    --property=EnvironmentFile=*) env_file=${1#*=EnvironmentFile=} ;;\n"
        "    --) separator=yes; shift; break ;;\n"
        "    /*) break ;;\n"
        "  esac\n"
        "  shift\n"
        "done\n"
        'printf \'%s|%s|%s|%s|%s|%s\\n\' "$uid" "$gid" "$working" '
        '"$env_file" "$separator" "$*" >> "$SYSTEMD_LOG"\n'
        'cd -- "$working"\n'
        'set -a\n. "$env_file"\nset +a\nexec "$@"\n',
    )
    _write_executable(
        fake_bin / "pwc-deploy",
        "#!/bin/sh\n"
        '[ -z "${CONTROL_LOG:-}" ] || printf \'deploy|%s\\n\' "$*" >> "$CONTROL_LOG"\n',
    )
    configure = release / "deploy/configure_host_env.py"
    configure.parent.mkdir()
    configure.write_text(
        "import os, sys\n"
        "if log := os.environ.get('CONTROL_LOG'):\n"
        "    with open(log, 'a', encoding='utf-8') as output:\n"
        "        output.write('configure|' + ' '.join(sys.argv[1:]) + '\\n')\n",
        encoding="utf-8",
    )
    return app, release, env_file, fake_bin, log, sha


def _adapt_qualification_block(block: str, app: Path, env_file: Path):
    block = block.replace("/srv/paperswithcode", str(app))
    block = block.replace("/etc/paperswithcode/staging.env", str(env_file))
    block = block.replace(f"{app}/.venv/bin/python", sys.executable)
    block = block.replace("<durable-bridge-activation-time>", "2026-08-27T00:00:00Z")
    return block


def test_durable_qualification_uses_one_installed_runtime_after_environment_file(
    tmp_path: Path,
):
    """Catch release mutation or stale staging identity reaching qualification."""
    app, release, env_file, fake_bin, log, sha = _qualification_fixture(tmp_path)
    block = _bash_block(
        ROOT / "docs/deployment.md",
        "Resolve and validate the active immutable staging release",
    )
    command = _adapt_qualification_block(block, app, env_file)
    before = sorted(path.relative_to(release) for path in release.rglob("*"))
    systemd_log = tmp_path / "systemd.log"
    control_log = tmp_path / "control.log"
    result = subprocess.run(
        ["bash", "-eu", "-o", "pipefail", "-c", command],
        check=False,
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "COMMAND_LOG": str(log),
            "SYSTEMD_LOG": str(systemd_log),
            "CONTROL_LOG": str(control_log),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    runtime_python = (
        app
        / "runtimes"
        / hashlib.sha256((release / "uv.lock").read_bytes()).hexdigest()
        / "bin/python"
    )
    expected_identity = f"{sha[:12]}-staging|102|{release}|{runtime_python}|"
    assert len(calls) == 4
    assert all(call.startswith(expected_identity) for call in calls)
    assert calls[0].endswith("--audit-disabled-only")
    assert calls[1].endswith("--qualify-enabled-only")
    assert "backend.scripts.qualify_chat_durable_dispatch" in calls[0]
    assert "backend.scripts.qualify_chat_durable_dispatch" in calls[1]
    assert calls[2].endswith(
        "-m backend.scripts.qualify_chat_soak "
        f"--release-dir {release} --confirm QUALIFY_STAGING_CHAT_SOAK"
    )
    assert calls[3].endswith(
        "-m backend.scripts.audit_chat_soak --started-at 2026-08-27T00:00:00Z "
        f"--release-dir {release} --confirm AUDIT_STAGING_CHAT_SOAK"
    )
    transient_calls = systemd_log.read_text(encoding="utf-8").splitlines()
    assert len(transient_calls) == 4
    transient_prefix = f"pwc-staging|pwc-staging|{release}|{env_file}|yes|"
    assert all(call.startswith(transient_prefix) for call in transient_calls)
    assert all(
        f"/usr/bin/env PWC_RELEASE_ID={sha[:12]}-staging "
        f"PWC_CHAT_WORKER_CONTRACT_VERSION=102 {runtime_python} -m " in call
        for call in transient_calls
    )
    assert control_log.read_text(encoding="utf-8").splitlines() == [
        (
            f"configure|--legacy-env {env_file} "
            "--staging-chat-durable-dispatch-enable-only"
        ),
        f"deploy|staging {sha} --refresh-environment",
    ]
    assert sorted(path.relative_to(release) for path in release.rglob("*")) == before
    assert not (release / ".venv").exists()


def test_durable_qualification_refuses_a_missing_or_wrong_installed_runtime(
    tmp_path: Path,
):
    """Catch accidental fallback to a shared or release-local Python runtime."""
    app, release, env_file, fake_bin, log, _sha = _qualification_fixture(
        tmp_path, install_runtime=False
    )
    wrong_python = app / "runtimes" / ("b" * 64) / "bin/python"
    wrong_python.parent.mkdir(parents=True)
    _write_executable(
        wrong_python,
        "#!/bin/sh\nprintf 'wrong runtime executed\\n' >> \"$COMMAND_LOG\"\n",
    )
    block = _bash_block(
        ROOT / "docs/deployment.md",
        "Resolve and validate the active immutable staging release",
    )
    command = _adapt_qualification_block(block, app, env_file)
    result = subprocess.run(
        ["bash", "-eu", "-o", "pipefail", "-c", command],
        check=False,
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "COMMAND_LOG": str(log),
            "SYSTEMD_LOG": str(tmp_path / "systemd.log"),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not log.exists()
    assert not (release / ".venv").exists()


def test_bridge_smoke_uses_isolated_uv_with_exact_manifest_identity(tmp_path: Path):
    """Catch production targeting, dependency writes, or stale load-test identity."""
    app, release, env_file, fake_bin, log, sha = _qualification_fixture(tmp_path)
    _write_executable(
        fake_bin / "uv",
        "#!/bin/bash\n"
        "set -eu\n"
        "caller_release=${PWC_RELEASE_ID-}\n"
        "caller_worker=${PWC_CHAT_WORKER_CONTRACT_VERSION-}\n"
        'args=("$@")\n'
        "while [ $# -gt 0 ]; do\n"
        '  if [ "$1" = --env-file ]; then env_file=$2; break; fi\n'
        "  shift\n"
        "done\n"
        'set -a\n. "$env_file"\nset +a\n'
        '[ -z "$caller_release" ] || PWC_RELEASE_ID=$caller_release\n'
        '[ -z "$caller_worker" ] || '
        "PWC_CHAT_WORKER_CONTRACT_VERSION=$caller_worker\n"
        "printf '%s|%s|%s|%s\\n' \"$PWC_RELEASE_ID\" "
        '"$PWC_CHAT_WORKER_CONTRACT_VERSION" "$PWC_LOADTEST_ENV_MARKER" '
        '"${args[*]}" >> "$COMMAND_LOG"\n',
    )
    block = _bash_block(
        ROOT / "backend/loadtests/README.md",
        "## Invocation",
    )
    block = block.replace("/srv/paperswithcode", str(app))
    block = block.replace("/etc/paperswithcode/staging.env", str(env_file))
    block = block.replace(f"{app}/.venv/bin/python", sys.executable)
    result = subprocess.run(
        ["bash", "-eu", "-o", "pipefail", "-c", block],
        check=False,
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "COMMAND_LOG": str(log),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    call = log.read_text(encoding="utf-8").strip()
    assert call.startswith(f"{sha[:12]}-staging|102|loaded|")
    assert "--isolated --env-file" in call
    assert "--with locust>=2.40,<3" in call
    assert "--users 2 --spawn-rate 2.0" in call
    assert "--processes" not in call
    assert "https://paperswithcode.co" not in call
    assert not (release / ".venv").exists()


def test_durable_rollback_is_self_contained_in_a_fresh_shell(tmp_path: Path):
    """Catch a failed rollback that leaves the staging bridge enabled."""
    app, release, env_file, fake_bin, _log, sha = _qualification_fixture(tmp_path)
    control_log = tmp_path / "control.log"
    block = _bash_block(ROOT / "docs/deployment.md", "Any non-zero exit")
    block = block.replace("/srv/paperswithcode", str(app))
    block = block.replace("/etc/paperswithcode/staging.env", str(env_file))
    block = block.replace(f"{app}/.venv/bin/python", sys.executable)
    before = sorted(path.relative_to(release) for path in release.rglob("*"))
    result = subprocess.run(
        ["bash", "-eu", "-o", "pipefail", "-c", block],
        check=False,
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "CONTROL_LOG": str(control_log),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    calls = control_log.read_text(encoding="utf-8").splitlines()
    assert calls == [
        (
            f"configure|--legacy-env {env_file} "
            "--staging-chat-durable-dispatch-disable-only"
        ),
        f"deploy|staging {sha} --refresh-environment",
    ]
    assert sorted(path.relative_to(release) for path in release.rglob("*")) == before
    assert not (release / ".venv").exists()


def test_bridge_smoke_refuses_a_manifest_release_name_mismatch(tmp_path: Path):
    """Catch load against a release whose directory and manifest identities differ."""
    app, release, env_file, fake_bin, log, _sha = _qualification_fixture(tmp_path)
    manifest = json.loads((release / "release.json").read_text(encoding="utf-8"))
    manifest["release_id"] = "b" * 12 + "-staging"
    (release / "release.json").write_text(json.dumps(manifest), encoding="utf-8")
    uv_marker = tmp_path / "uv-invoked"
    _write_executable(
        fake_bin / "uv",
        '#!/bin/sh\nprintf invoked > "$UV_MARKER"\nexit 99\n',
    )
    block = _bash_block(
        ROOT / "backend/loadtests/README.md",
        "## Invocation",
    )
    block = block.replace("/srv/paperswithcode", str(app))
    block = block.replace("/etc/paperswithcode/staging.env", str(env_file))
    block = block.replace(f"{app}/.venv/bin/python", sys.executable)
    result = subprocess.run(
        ["bash", "-eu", "-o", "pipefail", "-c", block],
        check=False,
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "UV_MARKER": str(uv_marker),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not log.exists()
    assert not uv_marker.exists()
