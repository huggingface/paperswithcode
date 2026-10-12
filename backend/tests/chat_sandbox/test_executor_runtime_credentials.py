from types import SimpleNamespace
import os

import pytest

from backend.services.chat_executor_runtime import ChatExecutorRuntime


@pytest.mark.parametrize(
    "mode,uid,gid,in_directory,allowed",
    [
        (0o400, 0, 0, False, True),
        (0o600, 0, 0, False, True),
        (0o440, 0, 0, True, True),
        (0o440, 0, 0, False, False),
        (0o440, 1000, 0, True, False),
        (0o440, 0, 1000, True, False),
        (0o640, 0, 0, True, False),
        (0o444, 0, 0, True, False),
    ],
)
def test_admission_key_accepts_only_protected_systemd_group_read(
    tmp_path, monkeypatch, mode, uid, gid, in_directory, allowed
):
    path = tmp_path / "admission"
    path.write_bytes(b"x" * 32)
    path.chmod(mode)
    real_fstat = os.fstat

    def metadata(fd):
        actual = real_fstat(fd)
        return SimpleNamespace(
            st_mode=actual.st_mode, st_size=actual.st_size, st_uid=uid, st_gid=gid
        )

    monkeypatch.setattr(os, "fstat", metadata)
    monkeypatch.setenv(
        "CREDENTIALS_DIRECTORY", str(tmp_path if in_directory else tmp_path / "other")
    )
    runtime = ChatExecutorRuntime(
        SimpleNamespace(chat_executor_admission_signing_key_file=str(path)),
        session_factory=lambda: None,
    )
    if allowed:
        assert runtime._private_key().private_bytes_raw() == b"x" * 32
    else:
        with pytest.raises(PermissionError):
            runtime._private_key()
