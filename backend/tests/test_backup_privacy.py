"""Exercise backup privacy gates without database or network access."""

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/backup_postgres_to_hf_bucket.sh"


@pytest.mark.parametrize(
    "metadata",
    [
        '{"private": false}',
        "{}",
        '{"private": "true"}',
        '{"private": 1}',
        "null",
        "[]",
        "not json",
    ],
)
def test_unverified_bucket_never_dumps_or_uploads(tmp_path, metadata):
    result, calls, _ = run_backup(tmp_path, [metadata])
    assert result.returncode != 0
    assert "privacy could not be verified" in result.stderr
    assert calls == ["info"]


def run_backup(
    tmp_path,
    responses,
    fail_info=False,
    fail_dump=False,
    keep="3",
    existing=(),
    remote=None,
    available=10**12,
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    backup_dir = tmp_path / "backups"
    for name, size in existing:
        backup_dir.mkdir(exist_ok=True)
        (backup_dir / name).write_bytes(b"x" * size)
        (backup_dir / f"{name}.sha256").write_text("checksum")
    calls = tmp_path / "calls"
    state = tmp_path / "state"
    stub = """#!/usr/bin/env python3
import json, os, pathlib, sys
calls = pathlib.Path(os.environ['TEST_CALLS'])
state = pathlib.Path(os.environ['TEST_STATE'])
args = sys.argv[1:]
name = pathlib.Path(sys.argv[0]).name
if name == 'pg_dump':
    with calls.open('a') as f: f.write('dump\\n')
    dump_path = pathlib.Path(args[args.index('-f') + 1])
    assert dump_path.parent == pathlib.Path(os.environ['PWC_POSTGRES_BACKUP_DIR'])
    assert dump_path.name.endswith('.partial')
    seen = sorted(p.name for p in dump_path.parent.glob('*.dump'))
    pathlib.Path(os.environ['TEST_SEEN']).write_text(json.dumps(seen))
    dump_path.write_bytes(b'fake private dump')
    sys.exit(1 if os.environ['TEST_FAIL_DUMP'] == '1' else 0)
elif args[:2] == ['buckets', 'info']:
    with calls.open('a') as f: f.write('info\\n')
    n = int(state.read_text()) if state.exists() else 0
    responses = json.loads(os.environ['TEST_RESPONSES'])
    print(responses[min(n, len(responses)-1)])
    state.write_text(str(n+1))
    sys.exit(1 if os.environ['TEST_FAIL_INFO'] == '1' else 0)
elif args[:2] == ['buckets', 'cp']:
    with calls.open('a') as f: f.write('upload\\n')
elif args[:2] == ['buckets', 'list']:
    remote = json.loads(os.environ['TEST_REMOTE'])
    if remote is None:
        remote = [p.name for p in pathlib.Path(os.environ['PWC_POSTGRES_BACKUP_DIR']).iterdir()]
    for name in remote:
        print('postgres/' + name)
elif name == 'df':
    print('Avail')
    print(os.environ['TEST_AVAILABLE'])
else:
    sys.exit(2)
"""
    for name in ("hf", "pg_dump", "df"):
        p = bin_dir / name
        p.write_text(stub)
        p.chmod(0o700)
    env = os.environ | {
        "PATH": f"{bin_dir}:" + os.environ["PATH"],
        "HF_BIN": str(bin_dir / "hf"),
        "PWC_BACKUP_ENV_FILE": "",
        "PWC_BACKUP_CREDENTIAL_ENV_FILE": "",
        "PWC_POSTGRES_BACKUP_DIR": str(backup_dir),
        "PWC_POSTGRES_BACKUP_BUCKET": "test/private",
        "PWC_DB_NAME": "privacy_test_" + tmp_path.name,
        "PWC_POSTGRES_BACKUP_DB_USER": "test",
        "PWC_POSTGRES_BACKUP_DB_PASSWORD": "test",
        "PWC_POSTGRES_BACKUP_HF_TOKEN": "test",
        "PWC_POSTGRES_BACKUP_LOCAL_KEEP_COUNT": keep,
        "PWC_POSTGRES_BACKUP_REMOTE_KEEP_COUNT": "30",
        "TEST_CALLS": str(calls),
        "TEST_STATE": str(state),
        "TEST_RESPONSES": json.dumps(responses),
        "TEST_FAIL_INFO": "1" if fail_info else "0",
        "TEST_FAIL_DUMP": "1" if fail_dump else "0",
        "TEST_REMOTE": json.dumps(remote),
        "TEST_AVAILABLE": str(available),
        "TEST_SEEN": str(tmp_path / "seen"),
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
    )
    return result, calls.read_text().splitlines(), backup_dir


def test_metadata_command_failure_is_closed_even_with_private_response(tmp_path):
    result, calls, _ = run_backup(tmp_path, ['{"private": true}'], fail_info=True)
    assert result.returncode != 0
    assert calls == ["info"]


def test_visibility_change_before_upload_preserves_local_backup(tmp_path):
    result, calls, backups = run_backup(
        tmp_path, ['{"private": true}', '{"private": false}']
    )
    assert result.returncode != 0
    assert calls == ["info", "dump", "info"]
    assert len(list(backups.glob("*.dump"))) == 1


def test_private_backup_uploads_and_has_restricted_permissions(tmp_path):
    result, calls, backups = run_backup(tmp_path, ['{"private": true}'])
    assert result.returncode == 0, result.stderr
    assert calls == ["info", "dump", "info", "upload", "upload", "info"]
    assert len(list(backups.iterdir())) == 2
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in backups.iterdir())


def test_visibility_change_after_upload_fails_before_pruning(tmp_path):
    result, calls, backups = run_backup(
        tmp_path,
        [
            '{"private": true}',
            '{"private": true}',
            '{"private": false}',
        ],
    )
    assert result.returncode != 0
    assert calls == ["info", "dump", "info", "upload", "upload", "info"]
    assert len(list(backups.iterdir())) == 2


def test_failed_dump_is_removed_without_upload(tmp_path):
    result, calls, backups = run_backup(tmp_path, ['{"private": true}'], fail_dump=True)
    assert result.returncode != 0
    assert calls == ["info", "dump"]
    assert list(backups.iterdir()) == []


def _old_dump(tmp_path, day):
    return f"privacy_test_{tmp_path.name}_202610{day}_031501.dump"


def test_uploaded_old_dump_is_pruned_before_the_new_dump(tmp_path):
    old = _old_dump(tmp_path, "22")
    result, calls, backups = run_backup(
        tmp_path, ['{"private": true}'], keep="1", existing=[(old, 100)]
    )
    assert result.returncode == 0, result.stderr
    # pg_dump ran with the uploaded old dump already gone.
    assert json.loads((tmp_path / "seen").read_text()) == []
    assert old not in {p.name for p in backups.iterdir()}
    assert len(list(backups.glob("*.dump"))) == 1


def test_old_dump_missing_from_the_bucket_is_kept(tmp_path):
    old = _old_dump(tmp_path, "22")
    result, _, _ = run_backup(
        tmp_path, ['{"private": true}'], keep="1", existing=[(old, 100)], remote=[]
    )
    # The upload of the new dump then fails verification, but the old local
    # dump, never uploaded, is still there when pg_dump runs.
    assert result.returncode != 0
    assert json.loads((tmp_path / "seen").read_text()) == [old]


def test_dump_refuses_to_start_without_room_for_another_dump(tmp_path):
    old = _old_dump(tmp_path, "22")
    result, calls, backups = run_backup(
        tmp_path,
        ['{"private": true}'],
        keep="1",
        existing=[(old, 1000)],
        available=1050,
    )
    assert result.returncode != 0
    assert "Not enough free disk for a dump" in result.stderr
    assert "dump" not in calls
