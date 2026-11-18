import json
import re
from pathlib import Path

import pytest

from backend.services import spa_shell_service
from backend.services.spa_shell_service import route_preload_links

REPO = Path(__file__).resolve().parents[2]

MANIFEST = {
    "index.html": {
        "file": "assets/index-E.js",
        "isEntry": True,
        "imports": ["_vendor-V.js"],
        "dynamicImports": ["src/views/PaperDetailView.tsx"],
    },
    "_vendor-V.js": {"file": "assets/vendor-V.js"},
    "_shared-S.js": {
        "file": "assets/shared-S.js",
        "imports": ["_vendor-V.js"],
        "css": ["assets/shared-S.css"],
    },
    "src/views/PaperDetailView.tsx": {
        "file": "assets/PaperDetailView-P.js",
        "isDynamicEntry": True,
        "imports": ["_shared-S.js", "_vendor-V.js"],
        "dynamicImports": ["src/components/MathMarkdownText.tsx"],
        "css": ["assets/PaperDetailView-P.css"],
    },
}


@pytest.fixture
def shell_dir(tmp_path, monkeypatch):
    (tmp_path / ".vite").mkdir()
    (tmp_path / ".vite" / "manifest.json").write_text(json.dumps(MANIFEST))
    monkeypatch.setattr(
        spa_shell_service, "_cached_index_path", tmp_path / "index.html"
    )
    monkeypatch.setattr(spa_shell_service, "_cached_manifest_key", None)
    return tmp_path


def test_preloads_view_chunk_imports_and_css_but_not_entry_chunks(shell_dir):
    links = route_preload_links("/paper/2607.24653").splitlines()
    assert links == [
        '<link rel="modulepreload" crossorigin href="/assets/PaperDetailView-P.js">',
        '<link rel="modulepreload" crossorigin href="/assets/shared-S.js">',
        '<link rel="preload" as="style" crossorigin href="/assets/PaperDetailView-P.css">',
        '<link rel="preload" as="style" crossorigin href="/assets/shared-S.css">',
    ]


def test_old_style_arxiv_ids_with_slashes_match(shell_dir):
    assert "PaperDetailView-P.js" in route_preload_links("/paper/hep-th/9901001")


def test_unknown_routes_and_missing_manifest_get_nothing(shell_dir):
    assert route_preload_links("/settings") == ""
    (shell_dir / ".vite" / "manifest.json").unlink()
    assert route_preload_links("/paper/1") == ""


def test_every_mapped_view_is_a_lazy_route_in_app():
    app = (REPO / "frontend" / "src" / "App.tsx").read_text()
    lazy = set(
        re.findall(r'React\.lazy\(\(\) => import\("@/(views/[A-Za-z]+)"\)\)', app)
    )
    for _pattern, source in spa_shell_service._ROUTE_VIEWS:
        assert source.removeprefix("src/").removesuffix(".tsx") in lazy, source
        assert (REPO / "frontend" / source).exists(), source
