"""
Deploy the React/Vite frontend to a Hugging Face Static Space.

This builds `frontend/` with `VITE_API_URL` pointing at the production backend,
`VITE_USE_HASH_ROUTER=1`, and `VITE_DISABLE_AUTH=1` (so the Space mirror hides
bookmark / sign-in / CRON-dashboard affordances that depend on cross-origin
cookies), then pushes the resulting `dist/` folder to the target Space repo.

Usage:

    uv run --env-file backend/keys.env python .github/workflows/scripts/deploy_hf_space.py \\
        --space your-namespace/paperswithcode-mirror

    # First time only: creates the Space repo with sdk=static.
    uv run --env-file backend/keys.env python .github/workflows/scripts/deploy_hf_space.py \\
        --space your-namespace/paperswithcode-mirror --create

The Space then serves a static SPA that calls the live API at
`https://paperswithcode.co`. The backend must allow the Space origin in its
CORS config -- see `extra_allowed_origins` / `extra_allowed_origin_regex` in
`backend/config.py`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

from huggingface_hub import HfApi


REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = REPO_ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"

DEFAULT_API_URL = "https://paperswithcode.co"


def _readme_for_space(space_id: str, api_url: str) -> str:
    """Produce the README.md that Hugging Face Static Spaces reads.

    `sdk: static` + `app_file: index.html` make HF serve the prebuilt SPA as
    a static site. We pre-build locally so the `VITE_*` envs are baked into
    the bundle (Vite resolves `import.meta.env.*` at build time).
    """

    title = space_id.split("/", 1)[-1].replace("-", " ").title() or "Papers With Code"
    return dedent(
        f"""\
        ---
        title: {title}
        emoji: \U0001f4da
        colorFrom: indigo
        colorTo: purple
        sdk: static
        app_file: index.html
        pinned: false
        short_description: Mirror of paperswithcode.co served as a Hugging Face Space.
        ---

        # Papers With Code (Hugging Face Space mirror)

        Static mirror of [paperswithcode.co](https://paperswithcode.co/) deployed
        as a Hugging Face Space. The React/Vite frontend is prebuilt locally
        with `VITE_API_URL={api_url}` so the SPA fetches data from the
        production API while being hosted entirely on the Hub.

        Auth-only affordances (sign-in, saved papers, CRON dashboard) are
        hidden in this build because the HF OAuth session cookie cannot be
        shared across the Space origin and the API origin.

        Regenerate with:

        ```bash
        uv run --env-file backend/keys.env python .github/workflows/scripts/deploy_hf_space.py \\
            --space <owner>/<space>
        ```
        """
    )


def _ensure_clean(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def build_frontend(api_url: str, disable_auth: bool) -> None:
    """Run `npm run build` with Space-specific Vite env injected."""

    env = os.environ.copy()
    env["VITE_API_URL"] = api_url
    env["VITE_USE_HASH_ROUTER"] = "1"
    env["VITE_DISABLE_AUTH"] = "1" if disable_auth else ""

    if not (FRONTEND_DIR / "node_modules").exists():
        print("[deploy] installing npm dependencies (one-time)...", flush=True)
        subprocess.run(
            ["npm", "install"],
            cwd=FRONTEND_DIR,
            env=env,
            check=True,
        )

    _ensure_clean(DIST_DIR)
    print(
        f"[deploy] building frontend "
        f"(VITE_API_URL={api_url!r}, "
        f"VITE_USE_HASH_ROUTER={env['VITE_USE_HASH_ROUTER']!r}, "
        f"VITE_DISABLE_AUTH={env['VITE_DISABLE_AUTH']!r})...",
        flush=True,
    )
    subprocess.run(
        ["npm", "run", "build"],
        cwd=FRONTEND_DIR,
        env=env,
        check=True,
    )

    if not (DIST_DIR / "index.html").exists():
        sys.exit("[deploy] build did not produce dist/index.html; aborting")


def write_space_readme(space_id: str, api_url: str) -> None:
    readme_path = DIST_DIR / "README.md"
    readme_path.write_text(_readme_for_space(space_id, api_url), encoding="utf-8")


def ensure_space(api: HfApi, space_id: str, create: bool) -> None:
    try:
        api.repo_info(repo_id=space_id, repo_type="space")
        return
    except Exception:
        if not create:
            sys.exit(
                f"[deploy] Space {space_id!r} not found. Re-run with --create "
                "to create it (sdk=static)."
            )

    print(f"[deploy] creating Space {space_id} (sdk=static)...", flush=True)
    api.create_repo(
        repo_id=space_id,
        repo_type="space",
        space_sdk="static",
        exist_ok=True,
    )


def upload_dist(api: HfApi, space_id: str) -> None:
    print(f"[deploy] uploading {DIST_DIR} -> {space_id}", flush=True)
    api.upload_folder(
        repo_id=space_id,
        repo_type="space",
        folder_path=str(DIST_DIR),
        commit_message="Sync paperswithcode.co frontend",
        # Drop stale hashed asset files from previous deploys.
        delete_patterns=["*"],
    )


def restore_canonical_dist() -> None:
    """Rebuild `frontend/dist` as the canonical paperswithcode.co bundle.

    The VPS that hosts this repo also serves `https://paperswithcode.co`
    from `frontend/dist` via nginx. A Space build bakes in `VITE_API_URL`
    with Space-specific env. After uploading the Space build, rebuild without
    those env vars so the live site keeps clean URLs and same-origin API calls.
    """

    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"VITE_API_URL", "VITE_USE_HASH_ROUTER", "VITE_DISABLE_AUTH"}
    }

    _ensure_clean(DIST_DIR)
    print("[deploy] restoring canonical frontend/dist (no Space env)...", flush=True)
    subprocess.run(
        ["npm", "run", "build"],
        cwd=FRONTEND_DIR,
        env=env,
        check=True,
    )

    if not (DIST_DIR / "index.html").exists():
        sys.exit("[deploy] canonical rebuild did not produce dist/index.html")

    nginx = shutil.which("nginx")
    if nginx is None:
        return
    if subprocess.run([nginx, "-t"], capture_output=True).returncode != 0:
        print("[deploy] nginx -t failed; skipping reload", flush=True)
        return
    subprocess.run([nginx, "-s", "reload"], check=False)
    print("[deploy] nginx reloaded with canonical dist", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--space",
        required=True,
        help="Target Space repo id, e.g. your-namespace/paperswithcode-mirror",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"Backend API origin baked into the build (default: {DEFAULT_API_URL})",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create the Space if it does not already exist.",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Skip the local `npm run build` step and upload whatever is "
        "already in frontend/dist (useful for fast retries).",
    )
    parser.add_argument(
        "--keep-auth",
        action="store_true",
        help="Keep the HF sign-in / bookmark / CRON UI visible. Off by default "
        "because the OAuth cookie cannot follow visitors across origins.",
    )
    parser.add_argument(
        "--skip-restore",
        action="store_true",
        help="Skip rebuilding frontend/dist back to the canonical "
        "paperswithcode.co bundle after the Space upload. Only use this off "
        "the production VPS, where nginx isn't serving this folder.",
    )
    args = parser.parse_args()

    if not args.no_build:
        build_frontend(api_url=args.api_url, disable_auth=not args.keep_auth)

    if not (DIST_DIR / "index.html").exists():
        sys.exit("[deploy] frontend/dist/index.html missing -- run without --no-build")

    write_space_readme(args.space, args.api_url)

    token = os.environ.get("HF_TOKEN") or os.environ.get("PWC_HF_TOKEN")
    api = HfApi(token=token) if token else HfApi()

    try:
        ensure_space(api, args.space, create=args.create)
        upload_dist(api, args.space)
        print(
            f"[deploy] done -> https://huggingface.co/spaces/{args.space}",
            flush=True,
        )
    finally:
        if not args.skip_restore:
            restore_canonical_dist()


if __name__ == "__main__":
    main()
