"""The Modal compiler image build context and in-sandbox helpers."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from backend.scripts import publish_latex_compiler_image
from latex_compiler_contract import (
    EnvelopeError,
    validate_staging_compiler_identity,
)
from latex_compiler_space import app as compiler_app
from latex_compiler_space import workspace_runner

REPOSITORY = Path(__file__).resolve().parents[3]


def test_build_context_holds_every_file_the_dockerfile_copies(tmp_path: Path):
    publish_latex_compiler_image._build_context(tmp_path)

    dockerfile = (tmp_path / "Dockerfile").read_text()
    sources = re.findall(r"^COPY (\S+) ", dockerfile, re.MULTILINE)
    assert sources
    for source in sources:
        assert (tmp_path / source).exists(), source
    assert (tmp_path / "latex_compiler_space" / "local_client.py").is_file()
    assert not list(tmp_path.rglob("__pycache__"))


def test_compiler_path_reaches_the_tex_live_binaries(tmp_path: Path):
    # The pinned texlive-debian base installs latexmk under /opt/texlive/bin.
    dockerfile = (REPOSITORY / "latex_compiler_space" / "Dockerfile").read_text()
    assert "xu-cheng/texlive-debian@sha256:" in dockerfile
    (tmp_path / "app").mkdir()
    (tmp_path / "runner").mkdir()
    for environment in (
        compiler_app._compiler_environment(tmp_path / "app"),
        workspace_runner._compiler_environment(tmp_path / "runner"),
    ):
        assert environment["PATH"].split(":")[0] == "/opt/texlive/bin"


def test_staging_identity_requires_a_modal_image_in_the_latex_environment():
    image = "im-StagingLatexCompiler01"

    assert validate_staging_compiler_identity(image, "pwc-latex-staging") == image
    for bad_image, environment in (
        ("registry.hf.space/x@sha256:" + "a" * 64, "pwc-latex-staging"),
        (image, "pwc-chat-staging"),
    ):
        with pytest.raises(EnvelopeError):
            validate_staging_compiler_identity(bad_image, environment)


def test_loopback_client_reports_an_unreachable_compiler_as_status_zero():
    completed = subprocess.run(
        [sys.executable, "-m", "latex_compiler_space.local_client", "GET", "/health"],
        cwd=REPOSITORY,
        capture_output=True,
        check=True,
        timeout=30,
    )

    assert json.loads(completed.stdout) == {"status": 0, "body": ""}


def test_loopback_client_rejects_unknown_methods_and_paths():
    for arguments in (["PUT", "/v1/jobs"], ["GET", "http://example.com/"]):
        completed = subprocess.run(
            [sys.executable, "-m", "latex_compiler_space.local_client", *arguments],
            cwd=REPOSITORY,
            capture_output=True,
            timeout=30,
        )
        assert completed.returncode == 2
        assert completed.stdout == b""
