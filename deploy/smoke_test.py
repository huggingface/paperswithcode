#!/usr/bin/env python3
"""Read-only release and HTTP smoke checks used by deploys and monitoring."""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

try:
    from deploy.release import profile_features
except ModuleNotFoundError:
    from release import profile_features  # type: ignore[no-redef]

ASSET_RE = re.compile(
    r"""(?:src|href)=["'](?P<url>/assets/[^"'?#]+\.(?P<kind>js|css))(?:[?#][^"']*)?["']"""
)


def request(url: str, *, allow_redirects: bool = True) -> tuple[int, dict, bytes]:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = (
        urllib.request.build_opener()
        if allow_redirects
        else urllib.request.build_opener(NoRedirect())
    )
    try:
        with opener.open(
            urllib.request.Request(url, headers={"User-Agent": "pwc-smoke/1"}),
            timeout=20,
        ) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def validate_local_bundle(
    release_dir: Path, expected_features: dict[str, bool] | bool
) -> list[str]:
    failures: list[str] = []
    dist = release_dir / "frontend-dist"
    try:
        features = json.loads((dist / "features.json").read_text())
        if isinstance(expected_features, bool):
            manifest = json.loads((release_dir / "release.json").read_text())
            expected_features = manifest.get(
                "frontend_features", {"chat": expected_features}
            )
        if features != expected_features:
            failures.append(f"unexpected frontend features: {features!r}")
        html = (dist / "index.html").read_text()
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read frontend bundle: {exc}"]
    if "/src/main.tsx" in html:
        failures.append("frontend references /src/main.tsx")
    assets = list(ASSET_RE.finditer(html))
    if not any(match.group("kind") == "js" for match in assets):
        failures.append("no JavaScript asset found")
    for match in assets:
        path = dist / match.group("url").removeprefix("/")
        if not path.is_file():
            failures.append(f"missing asset: {match.group('url')}")
        expected_mime = (
            "text/css" if match.group("kind") == "css" else "text/javascript"
        )
        guessed = mimetypes.guess_type(path.name)[0]
        if guessed not in {expected_mime, "application/javascript"}:
            failures.append(f"unexpected local MIME for {path.name}: {guessed}")
    return failures


def run_http_smoke(
    environment: str,
    base_url: str,
    *,
    expected_release: str | None = None,
    monitor_subset: bool = False,
    candidate: bool = False,
) -> list[str]:
    failures: list[str] = []
    status, _, body = request(urljoin(base_url, "/health"))
    if status != 200:
        failures.append(f"/health returned {status}")
    else:
        try:
            health = json.loads(body)
            if expected_release and health.get("release_id") != expected_release:
                failures.append("/health release ID mismatch")
        except json.JSONDecodeError:
            failures.append("/health did not return JSON")

    if environment == "staging":
        if candidate:
            status, _, _ = request(urljoin(base_url, "/api/v1/chat/sessions"))
            if status not in {401, 403}:
                failures.append(f"staging chat auth boundary returned {status}")
            return failures
        status, _, _ = request(urljoin(base_url, "/"), allow_redirects=False)
        if status not in {302, 401, 403}:
            failures.append(f"staging / was not admin-gated: {status}")
        return failures

    if candidate:
        status, _, body = request(
            urljoin(base_url, "/api/v1/papers/?page=1&page_size=1")
        )
        if status != 200:
            failures.append(f"paper API returned {status}")
        else:
            try:
                json.loads(body)
            except json.JSONDecodeError:
                failures.append("paper API did not return JSON")
        status, _, _ = request(urljoin(base_url, "/api/v1/chat/sessions"))
        if status not in {404, 405}:
            failures.append(f"production chat API is reachable: {status}")
        return failures

    for path in ("/", "/paper/2605.13517"):
        status, headers, body = request(urljoin(base_url, path))
        if status != 200:
            failures.append(f"{path} returned {status}")
            continue
        html = body.decode("utf-8", "replace")
        if "/src/main.tsx" in html:
            failures.append(f"{path} references /src/main.tsx")
        if path.startswith("/paper/"):
            assets = list(ASSET_RE.finditer(html))
            if not assets:
                failures.append("paper page has no built assets")
            for match in assets:
                asset_status, asset_headers, _ = request(
                    urljoin(base_url, match.group("url"))
                )
                content_type = asset_headers.get("Content-Type", "").split(";")[0]
                allowed = (
                    {"text/css"}
                    if match.group("kind") == "css"
                    else {"text/javascript", "application/javascript"}
                )
                if asset_status != 200 or content_type not in allowed:
                    failures.append(
                        f"{match.group('url')} returned {asset_status} {content_type}"
                    )
    if monitor_subset:
        return failures
    status, _, body = request(urljoin(base_url, "/api/v1/papers/?page=1&page_size=1"))
    if status != 200:
        failures.append(f"paper API returned {status}")
    else:
        try:
            json.loads(body)
        except json.JSONDecodeError:
            failures.append("paper API did not return JSON")
    status, _, _ = request(urljoin(base_url, "/api/v1/chat/sessions"))
    if status not in {404, 405}:
        failures.append(f"production chat API is reachable: {status}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--environment", choices=("production", "staging"), required=True
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-release")
    parser.add_argument("--release-dir", type=Path)
    parser.add_argument("--monitor-subset", action="store_true")
    parser.add_argument("--candidate", action="store_true")
    args = parser.parse_args()
    failures = []
    if args.release_dir:
        failures.extend(
            validate_local_bundle(args.release_dir, profile_features(args.environment))
        )
    failures.extend(
        run_http_smoke(
            args.environment,
            args.base_url,
            expected_release=args.expected_release,
            monitor_subset=args.monitor_subset,
            candidate=args.candidate,
        )
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"{args.environment} smoke checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
