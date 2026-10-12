"""Link extraction and link-replacement fixes for `pwc paper add-external`/`update`."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

from backend import cli, cli_papers
from backend.genai_steps.extract_external_resource_metadata import (
    ExternalResourceMetadata,
    extract_external_resource_metadata,
)
from backend.services import paper_association_service
from backend.services.external_resource_service import ExternalResourceService
from backend.services.hf_artifact_service import unlink_replaced_hf_artifact_links
from backend.services.paper_association_service import PaperAssociationService
from backend.utils.url_fetch import extract_github_urls, extract_hf_repo_urls


def _page(*hrefs: str) -> str:
    return "".join(f'<a href="{href}">link</a>' for href in hrefs)


def test_github_extraction_keeps_names_ending_in_git_letters():
    html = _page(
        "https://github.com/4rtemi5/ssog",
        "https://github.com/acme/tool.git",
        "https://github.com/acme/digit/tree/main/src",
    )

    assert extract_github_urls(html) == [
        "https://github.com/4rtemi5/ssog",
        "https://github.com/acme/tool",
        "https://github.com/acme/digit",
    ]


def test_github_extraction_skips_site_pages():
    html = _page(
        "https://github.com/orgs/acme/repositories",
        "https://github.com/sponsors/someone",
        "https://github.com/acme",
    )

    assert extract_github_urls(html) == []


def test_hf_extraction_keeps_full_dataset_and_space_ids():
    html = _page(
        "https://huggingface.co/datasets/allenai/olmo-mix?row=3",
        "https://huggingface.co/spaces/LiquidAI/demo/tree/main",
        "https://huggingface.co/LiquidAI/d1-3B/blob/main/README.md",
    )

    assert extract_hf_repo_urls(html) == [
        "https://huggingface.co/datasets/allenai/olmo-mix",
        "https://huggingface.co/spaces/LiquidAI/demo",
        "https://huggingface.co/LiquidAI/d1-3B",
    ]


def test_hf_extraction_skips_bare_owner_pages():
    html = _page(
        "https://huggingface.co/datasets/allenai",
        "https://huggingface.co/datasets/datalab-to/",
        "https://huggingface.co/spaces/LiquidAI",
        "https://huggingface.co/spaces/multimodalart",
        "https://huggingface.co/LiquidAI",
        "https://huggingface.co/organizations/LiquidAI/share",
        "https://huggingface.co/collections/LiquidAI/lfm",
    )
    # Raw text URLs too, not only anchors.
    html += " see https://huggingface.co/datasets/allenai for more"

    assert extract_hf_repo_urls(html) == []


def test_hf_extraction_drops_case_variant_duplicates():
    html = _page(
        "https://huggingface.co/LiquidAI/d1-3B",
        "https://huggingface.co/LiquidAI/d1-3b",
    )

    assert extract_hf_repo_urls(html) == ["https://huggingface.co/LiquidAI/d1-3B"]


class _FakeGenerator:
    def __init__(self, response: ExternalResourceMetadata):
        self.response = response

    async def generate(self, _messages, schema):
        return self.response, "fake-model"


def _extract(html: str, metadata: ExternalResourceMetadata):
    return asyncio.run(
        extract_external_resource_metadata(
            url="https://example.com/post",
            page_text="Release post",
            raw_html=html,
            generator=_FakeGenerator(metadata),
        )
    )


def test_metadata_keeps_only_repositories_the_page_presents_as_its_own():
    html = _page(
        "https://github.com/tzafon/lightcone",
        "https://github.com/PrimeIntellect-ai/prime-rl",
    )
    metadata = ExternalResourceMetadata(
        github_repository_urls=["https://github.com/Tzafon/Lightcone/"]
    )

    result = _extract(html, metadata)

    assert result.github_repository_urls == ["https://github.com/tzafon/lightcone"]


def test_metadata_does_not_fall_back_to_dependency_repositories():
    html = _page(
        "https://github.com/Lifelong-Robot-Learning/LIBERO",
        "https://github.com/robocurve/inspect-robots",
    )

    result = _extract(html, ExternalResourceMetadata())

    assert result.github_repository_urls == []


def test_metadata_drops_hallucinated_links_and_keeps_page_hf_spelling():
    html = _page("https://huggingface.co/LiquidAI/d1-3B")
    metadata = ExternalResourceMetadata(
        github_repository_urls=["https://github.com/acme/not-on-page"],
        hf_artifact_urls=["https://huggingface.co/LiquidAI/d1-3b"],
    )

    result = _extract(html, metadata)

    assert result.github_repository_urls == []
    assert result.hf_artifact_urls == ["https://huggingface.co/LiquidAI/d1-3B"]


class _Query:
    def __init__(self, paper):
        self.paper = paper

    def filter(self, *args):
        return self

    def first(self):
        return self.paper


def test_external_ingestion_skips_case_variant_hf_duplicates(monkeypatch):
    paper = SimpleNamespace(
        id=123164,
        hf_models=["https://huggingface.co/LiquidAI/d1-3B"],
        hf_datasets=None,
        hf_spaces=None,
        hf_artifacts_scanned_at=None,
    )
    db = Mock()
    db.query.return_value = _Query(paper)
    monkeypatch.setattr(
        "backend.services.external_resource_service.sync_explicit_hf_artifact_links",
        Mock(),
    )

    result = ExternalResourceService(db)._set_hf_artifacts(
        paper.id, ["https://huggingface.co/LiquidAI/d1-3b"]
    )

    assert result["models_added"] == 0
    assert result["existing"] == 1
    assert paper.hf_models == ["https://huggingface.co/LiquidAI/d1-3B"]


def test_unlink_replaced_hf_artifact_links_deletes_only_dropped_artifacts():
    session = Mock()
    session.execute.return_value = Mock(rowcount=1)

    removed = unlink_replaced_hf_artifact_links(
        session,
        123162,
        previous=(
            ["https://huggingface.co/LiquidAI/d1-3B"],
            ["https://huggingface.co/datasets/allenai/olmo-mix"],
            ["https://huggingface.co/spaces/LiquidAI/demo"],
        ),
        current=(["https://huggingface.co/LiquidAI/d1-3B"], None, None),
    )

    assert removed == 2
    deleted = [call.args[1] for call in session.execute.call_args_list]
    assert deleted == [
        {"paper_id": 123162, "kind": "dataset", "repo_id": "allenai/olmo-mix"},
        {"paper_id": 123162, "kind": "space", "repo_id": "LiquidAI/demo"},
    ]
    assert "DELETE FROM paper_hf_artifacts" in str(
        session.execute.call_args_list[0].args[0]
    )


def test_update_hf_artifacts_unlinks_previous_explicit_artifacts(monkeypatch):
    paper = SimpleNamespace(
        id=123162,
        hf_models=["https://huggingface.co/LiquidAI/d1-3B"],
        hf_datasets=["https://huggingface.co/datasets/allenai/olmo-mix"],
        hf_spaces=None,
        hf_artifacts_scanned_at=None,
    )
    db = Mock()
    db.query.return_value = _Query(paper)
    unlink = Mock()
    monkeypatch.setattr(
        paper_association_service, "unlink_replaced_hf_artifact_links", unlink
    )
    monkeypatch.setattr(
        paper_association_service, "sync_explicit_hf_artifact_links", Mock()
    )

    PaperAssociationService(db, Mock()).update_hf_artifacts(
        paper.id, ["https://huggingface.co/LiquidAI/d1-3B"], [], []
    )

    unlink.assert_called_once_with(
        db,
        123162,
        previous=(
            ["https://huggingface.co/LiquidAI/d1-3B"],
            ["https://huggingface.co/datasets/allenai/olmo-mix"],
            None,
        ),
        current=(["https://huggingface.co/LiquidAI/d1-3B"], [], []),
    )
    assert paper.hf_datasets is None


def test_cli_update_repositories_keeps_lone_unofficial_repository(monkeypatch):
    calls = []

    class FakeSessionContext:
        def __enter__(self):
            return "database-session"

        def __exit__(self, *_args):
            return None

    class FakeAssociationService:
        def __init__(self, _db, _hydrate):
            pass

        def update_repositories(self, paper_id, resources, **kwargs):
            calls.append((paper_id, resources, kwargs))

    monkeypatch.setattr(
        cli_papers, "db_manager", SimpleNamespace(session_local=FakeSessionContext)
    )
    monkeypatch.setattr(
        cli_papers,
        "resolve_paper",
        lambda _db, _ref: (SimpleNamespace(id=123161), "123161"),
    )
    monkeypatch.setattr(
        cli_papers, "PaperService", lambda _db: SimpleNamespace(get_paper_by_id=None)
    )
    monkeypatch.setattr(cli_papers, "PaperAssociationService", FakeAssociationService)
    args = cli.build_parser().parse_args(
        [
            "paper",
            "update",
            "123161",
            "repositories",
            "--unofficial",
            "https://github.com/PrimeIntellect-ai/prime-rl",
        ]
    )

    assert args.handler(args) == 0
    assert calls == [
        (
            123161,
            [
                {
                    "url": "https://github.com/PrimeIntellect-ai/prime-rl",
                    "is_official": False,
                }
            ],
            {"promote_lone_repository": False},
        )
    ]
