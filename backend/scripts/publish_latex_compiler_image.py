"""Build the staging LaTeX compiler image on Modal and print its immutable ID.

An explicit operator release action, never run by the web service. The printed
``im-...`` ID is installed as ``PWC_CHAT_LATEX_COMPILER_MODAL_IMAGE_ID`` through
``configure_host_env.py --staging-latex-paper-install-only``.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import modal

from latex_compiler_contract import (
    STAGING_COMPILER_MODAL_ENVIRONMENT,
    validate_qualified_compiler_image,
)

REPOSITORY = Path(__file__).resolve().parents[2]
MODAL_APP_NAME = "pwc-latex-compiler"


def _build_context(root: Path) -> None:
    """Lay out exactly the files the compiler Dockerfile copies."""
    compiler = REPOSITORY / "latex_compiler_space"
    shutil.copy2(compiler / "Dockerfile", root / "Dockerfile")
    shutil.copy2(compiler / "requirements.txt", root / "requirements.txt")
    for package in ("latex_compiler_contract", "latex_compiler_space"):
        shutil.copytree(
            REPOSITORY / package,
            root / package,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pwc-latex-compiler-") as temporary:
        context = Path(temporary)
        _build_context(context)
        # Modal needs its own interpreter to manage the container; the compiler
        # keeps running on the image's Debian Python at /usr/bin/python3.
        image = modal.Image.from_dockerfile(
            context / "Dockerfile", context_dir=context, add_python="3.12"
        )
        app = modal.App.lookup(
            MODAL_APP_NAME,
            create_if_missing=True,
            environment_name=STAGING_COMPILER_MODAL_ENVIRONMENT,
        )
        with modal.enable_output():
            image.build(app)
    print(validate_qualified_compiler_image(image.object_id or ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
