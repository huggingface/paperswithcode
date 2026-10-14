import asyncio
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from backend.cli import build_parser
from backend.services import paper_thumbnail_service
from backend.services.paper_thumbnail_service import (
    describe_thumbnail,
    regenerate_paper_thumbnail,
)


def save_thumbnail(path: Path, size: tuple[int, int]) -> None:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, size[0] - 10, size[1] - 20), fill="black")
    image.save(path, "JPEG")


class FakeDb:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class FakeArxivThumbnailService:
    def __init__(self, previous: Path, generated: Path):
        self.previous = previous
        self.generated = generated
        self.calls = []

    def get_local_thumbnail_path(self, _filename):
        return self.previous

    async def generate_thumbnail(self, arxiv_id, version, force):
        self.calls.append((arxiv_id, version, force))
        return self.generated


class FakeExternalThumbnailService:
    def __init__(self, generated: Path):
        self.generated = generated
        self.calls = []

    def get_local_custom_thumbnail_path(self, _filename):
        return None

    async def generate_external_thumbnail(
        self, paper_id, source_url, force, title=None, pdf_url=None
    ):
        self.calls.append((paper_id, source_url, force, title, pdf_url))
        return self.generated


def test_describe_thumbnail_reports_dimensions_and_content(tmp_path: Path):
    path = tmp_path / "thumbnail.jpg"
    save_thumbnail(path, (400, 550))

    stats = describe_thumbnail(path)

    assert stats is not None
    assert (stats.width, stats.height) == (400, 550)
    assert stats.valid
    assert stats.bottom_margin_px is not None
    assert stats.bottom_margin_px <= 40


def test_regenerate_arxiv_thumbnail_reports_old_and_new_dimensions(
    tmp_path: Path, monkeypatch
):
    previous = tmp_path / "old.jpg"
    generated = tmp_path / "new.jpg"
    save_thumbnail(previous, (400, 282))
    save_thumbnail(generated, (400, 550))
    paper = SimpleNamespace(
        id=10,
        arxiv_id="2512.20856",
        source="arxiv",
        source_url=None,
        version="v2",
        thumbnail_url="/api/thumbnails/2512_20856_v2.jpg?fit=fit5",
    )
    monkeypatch.setattr(
        paper_thumbnail_service,
        "resolve_paper",
        lambda _db, _reference: (paper, paper.arxiv_id),
    )
    service = FakeArxivThumbnailService(previous, generated)
    db = FakeDb()

    result = asyncio.run(regenerate_paper_thumbnail(db, "2512.20856", service=service))

    assert result.previous is not None
    assert (result.previous.width, result.previous.height) == (400, 282)
    assert (result.generated.width, result.generated.height) == (400, 550)
    assert result.success
    assert paper.thumbnail_url.startswith("/api/thumbnails/2512_20856_v2.jpg?fit=")
    assert "&v=" in paper.thumbnail_url
    assert db.commits == 1
    assert service.calls == [("2512.20856", "v2", True)]


def test_regenerate_external_thumbnail_persists_public_url(tmp_path: Path, monkeypatch):
    generated = tmp_path / "external.jpg"
    save_thumbnail(generated, (400, 550))
    paper = SimpleNamespace(
        id=42,
        arxiv_id=None,
        source="external",
        source_url="https://example.com/report.pdf",
        title="External report",
        conference_url_pdf=None,
        version="v1",
        thumbnail_url=None,
    )
    monkeypatch.setattr(
        paper_thumbnail_service,
        "resolve_paper",
        lambda _db, _reference: (paper, str(paper.id)),
    )
    db = FakeDb()
    service = FakeExternalThumbnailService(generated)

    result = asyncio.run(regenerate_paper_thumbnail(db, "42", service=service))

    assert result.success
    assert result.thumbnail_url.startswith("/api/thumbnails/custom/external_42.jpg")
    assert paper.thumbnail_url == result.thumbnail_url
    assert db.commits == 1
    assert service.calls == [
        (42, "https://example.com/report.pdf", True, "External report", None)
    ]


def test_pwc_thumbnail_cli_parses_simple_and_structured_forms():
    simple = build_parser().parse_args(["thumbnail", "2512.20856"])
    structured = build_parser().parse_args(
        [
            "thumbnail",
            "https://paperswithcode.co/paper/2512.20856",
            "--no-force",
            "--json",
        ]
    )

    assert simple.paper == "2512.20856"
    assert not simple.no_force
    assert structured.no_force
    assert structured.json
