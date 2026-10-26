from __future__ import annotations

import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import deploy.cli as deploy_cli
import deploy.external_pi_runtime as runtime_module
from deploy.external_pi_runtime import (
    RETAIN_ALL_RUNTIMES,
    cleanup_external_pi_runtimes,
    external_pi_runtime_id,
    external_pi_runtime_manifest,
    prepare_external_pi_runtime,
    run_bounded_command,
)
from deploy.release import atomic_symlink


PROMPT_INPUTS = (
    "backend/__init__.py",
    "backend/chat_execution_policy.py",
    "backend/chat_sandbox_worker/__init__.py",
    "backend/chat_sandbox_worker/render_pi_prompt_asset.py",
    "backend/chat_sandbox_worker/prompt.py",
    "backend/chat_sandbox_worker/PAPER_AUTHORING_PROMPT.md",
    "backend/chat_sandbox_worker/PAPER_AUTHORING.md",
    "backend/chat_sandbox_worker/PWC_CLI_SKILL.md",
    "backend/chat_sandbox_worker/PWC_MCP_SKILL.md",
    "backend/chat_sandbox_worker/HF_CLI_SKILL.md",
    "backend/chat_sandbox_worker/S2_CLI_SKILL.md",
    "backend/chat_sandbox_worker/TASK_CATALOG.md",
    "backend/chat_sandbox_worker/METHOD_CATALOG.md",
)


def release_fixture(root: Path, name: str = "release-a") -> Path:
    release = root / name
    worker = release / "backend/chat_sandbox_worker/pi_worker"
    (worker / "src").mkdir(parents=True)
    (worker / "package.json").write_text(
        json.dumps({"engines": {"node": "22.19.0"}}), encoding="utf-8"
    )
    (worker / "package-lock.json").write_text("locked\n", encoding="utf-8")
    (worker / "tsconfig.json").write_text("{}\n", encoding="utf-8")
    (worker / "src/external_http_main.ts").write_text(
        "export const worker = true;\n", encoding="utf-8"
    )
    (worker / "test").mkdir()
    (worker / "test/external_http_main.test.ts").write_text(
        "export const testWorker = true;\n", encoding="utf-8"
    )
    for relative in PROMPT_INPUTS:
        path = release / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{relative}\n", encoding="utf-8")
    (release / "release.json").write_text(
        json.dumps(
            {
                "release_id": name,
                "chat_runtime": {
                    "pi_node_version": runtime_module.PI_NODE_VERSION,
                    "pi_node_sha256": runtime_module.PI_NODE_SHA256,
                },
            }
        ),
        encoding="utf-8",
    )
    return release


@pytest.fixture
def pinned_node_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    archive = tmp_path / "node.tar.xz"
    prefix = "node-v22.19.0-linux-x64"
    with tarfile.open(archive, "w:xz") as bundle:
        for relative, content, mode in (
            ("bin/node", b"pinned node executable\n", 0o755),
            ("lib/node_modules/npm/bin/npm-cli.js", b"npm cli\n", 0o644),
        ):
            info = tarfile.TarInfo(f"{prefix}/{relative}")
            info.size = len(content)
            info.mode = mode
            bundle.addfile(info, io.BytesIO(content))
    monkeypatch.setattr(
        runtime_module,
        "PI_NODE_SHA256",
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    return archive


class PackageRunner:
    def __init__(self, *, fail_build: bool = False) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.call_details: list[tuple[tuple[str, ...], dict]] = []
        self.fail_build = fail_build

    def __call__(self, command, **kwargs):
        normalized = tuple(str(value) for value in command)
        self.calls.append(normalized)
        self.call_details.append((normalized, kwargs))
        if command[-1] == "--version":
            return SimpleNamespace(stdout="v22.19.0\n")
        cwd = Path(kwargs.get("cwd", "."))
        if "ci" in command:
            dependency = cwd / "node_modules/example/index.js"
            dependency.parent.mkdir(parents=True)
            dependency.write_text("export default 1;\n", encoding="utf-8")
        elif command[-2:] == ["run", "build"]:
            if self.fail_build:
                raise RuntimeError("build failed")
            output = cwd / "dist/src/external_http_main.js"
            output.parent.mkdir(parents=True)
            output.write_text("export const worker = true;\n", encoding="utf-8")
        elif "prune" in command:
            # npm rewrites the lockfile; the build user must be able to.
            assert (cwd / "package-lock.json").stat().st_mode & 0o200
        else:
            Path(command[-1]).write_text("canonical prompt\n", encoding="utf-8")
        return SimpleNamespace(stdout="")


def test_external_pi_identity_is_stable_and_changes_with_every_input(tmp_path: Path):
    release = release_fixture(tmp_path)
    expected = external_pi_runtime_id(release)

    assert external_pi_runtime_id(release) == expected
    for relative in (
        "backend/chat_sandbox_worker/pi_worker/package.json",
        "backend/chat_sandbox_worker/pi_worker/package-lock.json",
        "backend/chat_sandbox_worker/pi_worker/tsconfig.json",
        "backend/chat_sandbox_worker/pi_worker/src/external_http_main.ts",
        "backend/chat_sandbox_worker/pi_worker/test/external_http_main.test.ts",
        "backend/chat_sandbox_worker/PWC_CLI_SKILL.md",
        "backend/chat_sandbox_worker/PWC_MCP_SKILL.md",
    ):
        path = release / relative
        original = path.read_text(encoding="utf-8")
        path.write_text(original + "changed\n", encoding="utf-8")
        assert external_pi_runtime_id(release) != expected
        path.write_text(original, encoding="utf-8")


def test_failed_build_is_atomic_and_leaves_no_runtime(
    tmp_path: Path, pinned_node_archive: Path
):
    release = release_fixture(tmp_path)
    runtimes = tmp_path / "runtimes"
    current = tmp_path / "current"
    current.symlink_to(release)

    with pytest.raises(RuntimeError, match="build failed"):
        prepare_external_pi_runtime(
            release,
            runtimes,
            runner=PackageRunner(fail_build=True),
            node_archive=pinned_node_archive,
            python_binary=tmp_path / "python",
        )

    assert not (runtimes / external_pi_runtime_id(release)).exists()
    assert not list(runtimes.glob(".*.new-*"))
    assert current.resolve() == release


def test_runtime_construction_rejects_insufficient_capacity_before_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        runtime_module.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=runtime_module.MIN_FREE_BYTES - 1),
    )
    runner = PackageRunner()

    with pytest.raises(ValueError, match="insufficient free space"):
        prepare_external_pi_runtime(
            release_fixture(tmp_path), tmp_path / "runtimes", runner=runner
        )

    assert runner.calls == []


@pytest.mark.parametrize("growth", ["bytes", "directories"])
def test_live_build_bound_terminates_the_complete_growing_process_group(
    tmp_path: Path, growth: str
):
    root = tmp_path / "runtime"
    root.mkdir()
    child_code = (
        "import pathlib,sys,time\n"
        "root=pathlib.Path(sys.argv[1])\n"
        "growth=sys.argv[2]\n"
        "i=0\n"
        "while True:\n"
        " p=root/f'entry-{i}'\n"
        " p.mkdir() if growth == 'directories' else p.write_bytes(b'x'*4096)\n"
        " i+=1\n"
        " time.sleep(0.002)\n"
    )
    parent_code = (
        "import pathlib,subprocess,sys,time\n"
        "child=subprocess.Popen([sys.executable,'-c',sys.argv[3],sys.argv[1],sys.argv[2]])\n"
        "pathlib.Path(sys.argv[1],'child.pid').write_text(str(child.pid))\n"
        "time.sleep(30)\n"
    )

    with pytest.raises(ValueError, match="live construction bound"):
        run_bounded_command(
            [sys.executable, "-c", parent_code, str(root), growth, child_code],
            root=root,
            max_bytes=8 * 1024,
            max_inodes=12,
            timeout=5,
            poll_seconds=0.005,
        )

    child_pid = int((root / "child.pid").read_text(encoding="utf-8"))
    for _ in range(20):
        if not Path(f"/proc/{child_pid}").exists():
            break
        time.sleep(0.01)
    child_status = Path(f"/proc/{child_pid}/stat")
    assert not child_status.exists() or child_status.read_text().split()[2] == "Z"
    count = sum(1 for _ in root.rglob("*"))
    time.sleep(0.03)
    assert sum(1 for _ in root.rglob("*")) == count


def test_live_bound_tracks_descendants_after_the_direct_parent_exits(tmp_path: Path):
    root = tmp_path / "runtime"
    root.mkdir()
    child_code = (
        "import pathlib,sys,time\n"
        "root=pathlib.Path(sys.argv[1])\n"
        "time.sleep(.05)\n"
        "i=0\n"
        "while True:\n"
        " (root/f'growth-{i}').write_bytes(b'x'*4096)\n"
        " i+=1\n"
        " time.sleep(.002)\n"
    )
    parent_code = (
        "import pathlib,subprocess,sys\n"
        "child=subprocess.Popen([sys.executable,'-c',sys.argv[2],sys.argv[1]])\n"
        "pathlib.Path(sys.argv[1],'child.pid').write_text(str(child.pid))\n"
    )

    run_bounded_command(
        [sys.executable, "-c", parent_code, str(root), child_code],
        root=root,
        max_bytes=16 * 1024,
        max_inodes=30,
        timeout=5,
        poll_seconds=0.005,
    )

    child_pid = int((root / "child.pid").read_text(encoding="utf-8"))
    time.sleep(0.1)
    assert not Path(f"/proc/{child_pid}").exists()
    assert not list(root.glob("growth-*"))


def test_bounded_command_contains_a_regrouped_child_after_parent_exit(tmp_path: Path):
    root = tmp_path / "runtime"
    root.mkdir()
    child_code = (
        "import os,pathlib,sys,time\n"
        "os.setpgrp()\n"
        "root=pathlib.Path(sys.argv[1])\n"
        "time.sleep(.1)\n"
        "i=0\n"
        "while True:\n"
        " (root/f'escaped-{i}').write_bytes(b'x'*4096)\n"
        " i+=1\n"
        " time.sleep(.002)\n"
    )
    parent_code = (
        "import pathlib,subprocess,sys\n"
        "child=subprocess.Popen([sys.executable,'-c',sys.argv[2],sys.argv[1]])\n"
        "pathlib.Path(sys.argv[1],'child.pid').write_text(str(child.pid))\n"
    )
    child_pid = None
    try:
        run_bounded_command(
            [sys.executable, "-c", parent_code, str(root), child_code],
            root=root,
            max_bytes=16 * 1024,
            max_inodes=30,
            timeout=2,
            poll_seconds=0.005,
        )
        child_pid = int((root / "child.pid").read_text(encoding="utf-8"))
        time.sleep(0.2)

        assert not Path(f"/proc/{child_pid}").exists()
        assert not list(root.glob("escaped-*"))
    finally:
        if child_pid is not None and Path(f"/proc/{child_pid}").exists():
            os.kill(child_pid, signal.SIGKILL)


def test_bounded_command_contains_a_double_forked_session(tmp_path: Path):
    root = tmp_path / "runtime"
    root.mkdir()
    daemon_code = (
        "import os,pathlib,sys,time\n"
        "if os.fork(): raise SystemExit\n"
        "os.setsid()\n"
        "if os.fork(): raise SystemExit\n"
        "root=pathlib.Path(sys.argv[1])\n"
        "(root/'daemon.pid').write_text(str(os.getpid()))\n"
        "time.sleep(.1)\n"
        "i=0\n"
        "while True:\n"
        " (root/f'daemon-growth-{i}').write_bytes(b'x'*4096)\n"
        " i+=1\n"
        " time.sleep(.002)\n"
    )
    parent_code = (
        "import pathlib,subprocess,sys,time\n"
        "root=pathlib.Path(sys.argv[1])\n"
        "subprocess.Popen([sys.executable,'-c',sys.argv[2],sys.argv[1]])\n"
        "while not (root/'daemon.pid').exists(): time.sleep(.005)\n"
    )

    run_bounded_command(
        [sys.executable, "-c", parent_code, str(root), daemon_code],
        root=root,
        max_bytes=16 * 1024,
        max_inodes=30,
        timeout=2,
        poll_seconds=0.005,
    )
    daemon_pid = int((root / "daemon.pid").read_text(encoding="utf-8"))
    time.sleep(0.2)

    assert not Path(f"/proc/{daemon_pid}").exists()
    assert not list(root.glob("daemon-growth-*"))


def test_bounded_command_timeout_reaps_a_regrouped_child(tmp_path: Path):
    root = tmp_path / "runtime"
    root.mkdir()
    child_code = "import os,time\nos.setpgrp()\ntime.sleep(30)\n"
    parent_code = (
        "import pathlib,subprocess,sys,time\n"
        "child=subprocess.Popen([sys.executable,'-c',sys.argv[2]])\n"
        "pathlib.Path(sys.argv[1],'child.pid').write_text(str(child.pid))\n"
        "time.sleep(30)\n"
    )

    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded_command(
            [sys.executable, "-c", parent_code, str(root), child_code],
            root=root,
            timeout=0.1,
            poll_seconds=0.005,
        )

    child_pid = int((root / "child.pid").read_text(encoding="utf-8"))
    assert not Path(f"/proc/{child_pid}").exists()


def test_bounded_command_restores_the_process_subreaper_state(tmp_path: Path):
    original = runtime_module._get_child_subreaper()
    try:
        run_bounded_command(
            [sys.executable, "-c", "pass"],
            root=tmp_path,
            timeout=2,
        )
        assert runtime_module._get_child_subreaper() is original

        runtime_module._set_child_subreaper(True)
        run_bounded_command(
            [sys.executable, "-c", "pass"],
            root=tmp_path,
            timeout=2,
        )
        assert runtime_module._get_child_subreaper() is True
    finally:
        runtime_module._set_child_subreaper(original)


def test_bounded_command_does_not_kill_an_unrelated_preexisting_child_lineage(
    tmp_path: Path,
):
    root = tmp_path / "runtime"
    root.mkdir()
    trigger = tmp_path / "fork-now"
    grandchild_pid_path = tmp_path / "unrelated-grandchild.pid"
    unrelated_code = (
        "import os,pathlib,sys,time\n"
        "trigger=pathlib.Path(sys.argv[1])\n"
        "pid_path=pathlib.Path(sys.argv[2])\n"
        "while not trigger.exists(): time.sleep(.005)\n"
        "pid=os.fork()\n"
        "if pid:\n"
        " pid_path.write_text(str(pid))\n"
        " raise SystemExit\n"
        "time.sleep(30)\n"
    )
    bounded_code = (
        "import pathlib,sys,time\n"
        "trigger=pathlib.Path(sys.argv[1])\n"
        "pid_path=pathlib.Path(sys.argv[2])\n"
        "trigger.touch()\n"
        "while not pid_path.exists(): time.sleep(.005)\n"
        "time.sleep(.1)\n"
    )
    unrelated = subprocess.Popen(
        [sys.executable, "-c", unrelated_code, str(trigger), str(grandchild_pid_path)]
    )
    grandchild_pid = None
    try:
        run_bounded_command(
            [
                sys.executable,
                "-c",
                bounded_code,
                str(trigger),
                str(grandchild_pid_path),
            ],
            root=root,
            timeout=2,
            poll_seconds=0.005,
        )
        assert unrelated.wait(timeout=1) == 0
        grandchild_pid = int(grandchild_pid_path.read_text(encoding="utf-8"))

        assert Path(f"/proc/{grandchild_pid}").exists()
    finally:
        if unrelated.poll() is None:
            unrelated.kill()
            unrelated.wait()
        if grandchild_pid is not None and Path(f"/proc/{grandchild_pid}").exists():
            os.kill(grandchild_pid, signal.SIGKILL)


def test_live_npm_growth_breach_removes_the_temporary_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    archive = tmp_path / "growing-node.tar.xz"
    prefix = "node-v22.19.0-linux-x64"
    node_script = (
        b"#!/usr/bin/python3\n"
        b"import pathlib,subprocess,sys\n"
        b"if '--version' in sys.argv:\n print('v22.19.0'); raise SystemExit\n"
        b"code=\"import pathlib,sys,time\\nroot=pathlib.Path(sys.argv[1])/'node_modules'\\n"
        b"root.mkdir(exist_ok=True)\\ntime.sleep(.05)\\ni=0\\nwhile True:\\n "
        b"(root/f'growth-{i}').write_bytes(b'x'*4096); i+=1; time.sleep(.002)\"\n"
        b"subprocess.Popen([sys.executable,'-c',code,str(pathlib.Path.cwd())])\n"
    )
    with tarfile.open(archive, "w:xz") as bundle:
        for relative, content, mode in (
            ("bin/node", node_script, 0o755),
            ("lib/node_modules/npm/bin/npm-cli.js", b"npm cli\n", 0o644),
        ):
            info = tarfile.TarInfo(f"{prefix}/{relative}")
            info.size = len(content)
            info.mode = mode
            bundle.addfile(info, io.BytesIO(content))
    monkeypatch.setattr(
        runtime_module,
        "PI_NODE_SHA256",
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(runtime_module, "MAX_RUNTIME_BYTES", 32 * 1024)
    release = release_fixture(tmp_path)
    runtimes = tmp_path / "runtimes"

    with pytest.raises(ValueError, match="live construction bound"):
        prepare_external_pi_runtime(release, runtimes, node_archive=archive)

    assert not (runtimes / external_pi_runtime_id(release)).exists()
    assert not list(runtimes.glob(".*.new-*"))


def test_runtime_is_strictly_validated_and_reused(
    tmp_path: Path, pinned_node_archive: Path
):
    release = release_fixture(tmp_path)
    # Deployed releases are read-only.
    worker = release / "backend/chat_sandbox_worker/pi_worker"
    for name in ("package.json", "package-lock.json", "tsconfig.json"):
        (worker / name).chmod(0o444)
    runtimes = tmp_path / "runtimes"
    runner = PackageRunner()
    runtime, created = prepare_external_pi_runtime(
        release,
        runtimes,
        runner=runner,
        node_archive=pinned_node_archive,
        python_binary=tmp_path / "python",
    )

    assert created is True
    manifest = external_pi_runtime_manifest(runtime)
    assert manifest["contract"] == "external-pi-v1"
    assert manifest["entry_point"] == "app/dist/src/external_http_main.js"
    assert manifest["node"]["version"] == "22.19.0"
    assert manifest["source_release"] == "release-a"
    assert runtime.stat().st_mode & 0o222 == 0
    assert all(
        "--ignore-scripts" in call
        for call in runner.calls
        if "ci" in call or "prune" in call
    )
    build_environment = next(
        kwargs for command, kwargs in runner.call_details if "ci" in command
    )["env"]
    assert "NODE_OPTIONS" not in build_environment
    assert set(build_environment) == {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "npm_config_cache",
        "npm_config_userconfig",
        "npm_config_globalconfig",
        "npm_config_update_notifier",
    }

    reused, created = prepare_external_pi_runtime(
        release,
        runtimes,
        runner=runner,
        node_archive=tmp_path / "unused-node-archive",
        python_binary=tmp_path / "unused-python",
    )
    assert reused == runtime
    assert created is False
    assert sum(call[-1] == "--version" for call in runner.calls) == 1


def test_runtime_rejects_a_node_archive_outside_the_pinned_contract(
    tmp_path: Path, pinned_node_archive: Path
):
    pinned_node_archive.write_bytes(pinned_node_archive.read_bytes() + b"changed")

    with pytest.raises(ValueError, match="archive digest"):
        prepare_external_pi_runtime(
            release_fixture(tmp_path),
            tmp_path / "runtimes",
            runner=PackageRunner(),
            node_archive=pinned_node_archive,
            python_binary=tmp_path / "python",
        )


@pytest.mark.parametrize("mutation", ["digest", "mutable", "extra", "missing"])
def test_runtime_validation_rejects_changed_executable_inputs(
    tmp_path: Path, pinned_node_archive: Path, mutation: str
):
    release = release_fixture(tmp_path)
    runtime, _ = prepare_external_pi_runtime(
        release,
        tmp_path / "runtimes",
        runner=PackageRunner(),
        node_archive=pinned_node_archive,
        python_binary=tmp_path / "python",
    )
    entry = runtime / "app/dist/src/external_http_main.js"
    runtime.chmod(0o755)
    entry.parent.chmod(0o755)
    if mutation == "digest":
        entry.chmod(0o644)
        entry.write_text("changed\n", encoding="utf-8")
        entry.chmod(0o444)
    elif mutation == "mutable":
        entry.chmod(0o644)
    elif mutation == "extra":
        extra = entry.parent / "extra.js"
        extra.write_text("extra\n", encoding="utf-8")
        extra.chmod(0o444)
    else:
        entry.unlink()
    entry.parent.chmod(0o555)
    runtime.chmod(0o555)

    with pytest.raises(ValueError):
        external_pi_runtime_manifest(runtime)


def test_cleanup_removes_only_unprotected_external_pi_runtimes(tmp_path: Path):
    runtimes = tmp_path / "external-pi"
    for name in ("active", "previous", "prepared", "stale"):
        (runtimes / name).mkdir(parents=True)
    (runtimes / ".incomplete").mkdir()

    removed = cleanup_external_pi_runtimes(runtimes, {"active", "previous", "prepared"})

    assert removed == ["stale"]
    assert {path.name for path in runtimes.iterdir()} == {
        "active",
        "previous",
        "prepared",
        ".incomplete",
    }


def test_cleanup_protection_includes_current_previous_and_prepared_releases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environments = tmp_path / "environments"
    releases = {
        name: release_fixture(tmp_path, name)
        for name in ("active", "previous", "prepared")
    }
    root = environments / "staging"
    (root / "slots/blue").mkdir(parents=True)
    (root / "slots/green").mkdir()
    atomic_symlink(releases["active"], root / "current")
    atomic_symlink(releases["previous"], root / "previous")
    atomic_symlink(releases["prepared"], root / "slots/green/release")
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS", ("staging",))
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environments)
    expected = {external_pi_runtime_id(release) for release in releases.values()}
    monkeypatch.setattr(runtime_module, "PI_NODE_VERSION", "23.0.0")
    monkeypatch.setattr(runtime_module, "PI_NODE_SHA256", "f" * 64)

    assert deploy_cli.protected_external_pi_runtime_ids() == {
        *expected,
        RETAIN_ALL_RUNTIMES,
    }


def test_cleanup_uses_packaged_runtime_descriptors_across_identity_schema_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environments = tmp_path / "environments"
    releases = {
        name: release_fixture(tmp_path, name)
        for name in ("active", "previous", "prepared")
    }
    recorded = {name: f"{index:064x}" for index, name in enumerate(releases, start=1)}
    for name, release in releases.items():
        manifest_path = release / "release.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["external_pi_runtime"] = {
            "identity_schema": 1,
            "runtime_id": recorded[name],
            "contract": "external-pi-v1",
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    root = environments / "staging"
    (root / "slots/blue").mkdir(parents=True)
    (root / "slots/green").mkdir()
    atomic_symlink(releases["active"], root / "current")
    atomic_symlink(releases["previous"], root / "previous")
    atomic_symlink(releases["prepared"], root / "slots/green/release")
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS", ("staging",))
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environments)
    monkeypatch.setattr(runtime_module, "CONTRACT", "external-pi-v2")
    monkeypatch.setattr(
        runtime_module,
        "PROMPT_INPUTS",
        (*runtime_module.PROMPT_INPUTS, Path("new-required-prompt-input")),
    )

    assert deploy_cli.protected_external_pi_runtime_ids() == set(recorded.values())


def test_descriptorless_production_releases_do_not_disable_staging_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environments = tmp_path / "environments"
    staging = release_fixture(tmp_path, "staging-active")
    staging_manifest_path = staging / "release.json"
    staging_manifest = json.loads(staging_manifest_path.read_text(encoding="utf-8"))
    staging_manifest["external_pi_runtime"] = {
        "identity_schema": 1,
        "runtime_id": "a" * 64,
        "contract": "external-pi-v1",
    }
    staging_manifest_path.write_text(json.dumps(staging_manifest), encoding="utf-8")
    production = release_fixture(tmp_path, "production-active")
    for environment, release in (("staging", staging), ("production", production)):
        root = environments / environment
        (root / "slots/blue").mkdir(parents=True)
        (root / "slots/green").mkdir()
        atomic_symlink(release, root / "current")
        atomic_symlink(release, root / "slots/blue/release")
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS", ("production", "staging"))
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environments)

    assert deploy_cli.protected_external_pi_runtime_ids() == {"a" * 64}


def test_cleanup_protects_packaged_production_external_pi_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environments = tmp_path / "environments"
    recorded = {
        "staging": "a" * 64,
        "production": "b" * 64,
    }
    for environment, runtime_id in recorded.items():
        release = release_fixture(tmp_path, f"{environment}-active")
        manifest_path = release / "release.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["external_pi_runtime"] = {
            "identity_schema": 1,
            "runtime_id": runtime_id,
            "contract": "external-pi-v1",
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        root = environments / environment
        (root / "slots/blue").mkdir(parents=True)
        (root / "slots/green").mkdir()
        atomic_symlink(release, root / "current")
        atomic_symlink(release, root / "slots/blue/release")
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS", ("production", "staging"))
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environments)

    assert deploy_cli.protected_external_pi_runtime_ids() == set(recorded.values())


def test_packaged_descriptor_reuses_historical_runtime_after_schema_change(
    tmp_path: Path,
    pinned_node_archive: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    release = release_fixture(tmp_path)
    runtimes = tmp_path / "runtimes"
    runtime, _ = prepare_external_pi_runtime(
        release,
        runtimes,
        runner=PackageRunner(),
        node_archive=pinned_node_archive,
        python_binary=tmp_path / "python",
    )
    manifest_path = release / "release.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["external_pi_runtime"] = {
        "identity_schema": 1,
        "runtime_id": runtime.name,
        "contract": "external-pi-v1",
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(runtime_module, "CONTRACT", "external-pi-v2")
    monkeypatch.setattr(
        runtime_module,
        "PROMPT_INPUTS",
        (*runtime_module.PROMPT_INPUTS, Path("new-required-prompt-input")),
    )

    reused, created = prepare_external_pi_runtime(
        release, runtimes, node_archive=tmp_path / "unused-node-archive"
    )

    assert reused == runtime
    assert created is False
