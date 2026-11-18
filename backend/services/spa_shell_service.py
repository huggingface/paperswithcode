"""Load and safely customize the active Vite SPA shell."""

from __future__ import annotations

import html
import json
import logging
import re
from pathlib import Path
from typing import Optional

from backend.config import get_settings

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_INDEX_PATH = (
    _PROJECT_ROOT.parent / "pwc-releases" / "current" / "frontend-dist" / "index.html"
)
_DIST_INDEX_PATH = _PROJECT_ROOT / "frontend" / "dist" / "index.html"
_SRC_INDEX_PATH = _PROJECT_ROOT / "frontend" / "index.html"

_cached_index_html: Optional[str] = None
_cached_index_mtime: Optional[float] = None
_cached_index_path: Optional[Path] = None


def load_index_html() -> Optional[str]:
    """Load the deployed shell, with release/build/source fallbacks in development."""
    global _cached_index_html, _cached_index_mtime, _cached_index_path

    settings = get_settings()
    paths = (
        (settings.frontend_dist_path / "index.html",)
        if settings.is_deployed
        else (_RELEASE_INDEX_PATH, _DIST_INDEX_PATH, _SRC_INDEX_PATH)
    )
    for path in paths:
        if not path.exists():
            continue
        try:
            mtime = path.stat().st_mtime
            if (
                _cached_index_html is not None
                and _cached_index_mtime == mtime
                and _cached_index_path == path
            ):
                return _cached_index_html
            html = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to read SPA index from %s: %s", path, exc)
            continue
        _cached_index_html = html
        _cached_index_mtime = mtime
        _cached_index_path = path
        return html
    return None


# Server-rendered routes and the lazily loaded view module each one renders
# (React.lazy in frontend/src/App.tsx). Unknown paths simply get no preloads.
_ROUTE_VIEWS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), source)
    for pattern, source in (
        (r"^/$", "src/views/FeedView.tsx"),
        (r"^/paper/.+$", "src/views/PaperDetailView.tsx"),
        (r"^/tasks$", "src/views/TagsIndexView.tsx"),
        (r"^/tasks/[^/]+$", "src/views/TagBrowseView.tsx"),
        (r"^/methods$", "src/views/MethodsIndexView.tsx"),
        (r"^/methods/[^/]+$", "src/views/MethodDetailView.tsx"),
        (r"^/benchmark/[^/]+$", "src/views/BenchmarkDetailView.tsx"),
        (r"^/conferences$", "src/views/ConferencesIndexView.tsx"),
        (r"^/conferences/[^/]+$", "src/views/ConferenceDetailView.tsx"),
        (r"^/conferences/[^/]+/[^/]+$", "src/views/ConferenceTaskView.tsx"),
        (r"^/organizations$", "src/views/OrganizationsIndexView.tsx"),
        (
            r"^/(orgs|organizations)/[^/]+(/[^/]+)?$",
            "src/views/OrganizationDetailView.tsx",
        ),
        (r"^/authors/[^/]+$", "src/views/AuthorDetailView.tsx"),
        (r"^/frameworks$", "src/views/FrameworksIndexView.tsx"),
        (r"^/trends$", "src/views/TrendsView.tsx"),
        (r"^/ai-deadlines$", "src/views/AiDeadlinesView.tsx"),
        (r"^/astra-for-robotics$", "src/views/AstraForRoboticsView.tsx"),
    )
)

_cached_manifest: Optional[dict] = None
_cached_manifest_key: Optional[tuple[Path, float]] = None


def _load_vite_manifest() -> Optional[dict]:
    """The build manifest next to the shell that load_index_html() served."""
    global _cached_manifest, _cached_manifest_key
    if _cached_index_path is None:
        return None
    path = _cached_index_path.parent / ".vite" / "manifest.json"
    try:
        key = (path, path.stat().st_mtime)
        if _cached_manifest_key != key:
            _cached_manifest = json.loads(path.read_text(encoding="utf-8"))
            _cached_manifest_key = key
    except (OSError, ValueError):
        return None
    return _cached_manifest


def _static_import_closure(manifest: dict, key: str) -> list[str]:
    ordered: list[str] = []
    pending = [key]
    while pending:
        current = pending.pop(0)
        if current in ordered or current not in manifest:
            continue
        ordered.append(current)
        pending.extend(manifest[current].get("imports", ()))
    return ordered


def route_preload_links(path: str) -> str:
    """Preload a route's lazy view chunk, its imports and CSS from the HTML.

    Otherwise the browser only discovers them after downloading and running the
    entry script. Chunks the entry already imports are skipped.
    """
    source = next((src for pattern, src in _ROUTE_VIEWS if pattern.match(path)), None)
    manifest = _load_vite_manifest() if source else None
    if not manifest or source not in manifest:
        return ""
    loaded = set(_static_import_closure(manifest, "index.html"))
    links: list[str] = []
    styles: list[str] = []
    for key in _static_import_closure(manifest, source):
        if key in loaded:
            continue
        chunk = manifest[key]
        links.append(
            f'<link rel="modulepreload" crossorigin href="/{html.escape(chunk["file"])}">'
        )
        styles.extend(chunk.get("css", ()))
    links.extend(
        f'<link rel="preload" as="style" crossorigin href="/{html.escape(css)}">'
        for css in dict.fromkeys(styles)
    )
    return "\n".join(links)


def inject_head(shell: str, head_html: str) -> str:
    marker = "</head>"
    if marker not in shell:
        raise ValueError("SPA shell is missing </head>")
    return shell.replace(marker, f"{head_html}\n{marker}", 1)


def replace_document_head(shell: str, head_html: str) -> str:
    """Remove generic document metadata before adding page-specific metadata."""
    patterns = (
        r"<title\b[^>]*>.*?</title>",
        r'<meta\b[^>]*\bname=["\']description["\'][^>]*>',
        r'<meta\b[^>]*\bname=["\']robots["\'][^>]*>',
        r'<link\b[^>]*\brel=["\']canonical["\'][^>]*>',
    )
    for pattern in patterns:
        shell = re.sub(pattern, "", shell, count=1, flags=re.IGNORECASE | re.DOTALL)
    return inject_head(shell, head_html)


def inject_root_document(shell: str, document_html: str) -> str:
    for marker in ('<div id="root"></div>', '<div id="root"></div>\n'):
        if marker in shell:
            return shell.replace(marker, f'<div id="root">{document_html}</div>', 1)
    raise ValueError("SPA shell is missing an empty #root mount")


def reset_cache() -> None:
    """Test helper for shell path/content changes."""
    global _cached_index_html, _cached_index_mtime, _cached_index_path
    _cached_index_html = None
    _cached_index_mtime = None
    _cached_index_path = None
