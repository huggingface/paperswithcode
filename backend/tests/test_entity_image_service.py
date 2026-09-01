from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from PIL import Image

from backend import cli
from backend.services.entity_image_service import add_entity_image
from backend.utils.entity_image_import import IMAGE_SEED_ROOT


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (4, 3), "blue").save(output, format="PNG")
    return output.getvalue()


def _session_with_row(row: SimpleNamespace) -> MagicMock:
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = row
    return session


@pytest.mark.parametrize("entity", ["task", "method", "conference"])
def test_add_entity_image_downloads_seeds_and_updates_row(
    entity: str, tmp_path: Path
) -> None:
    image_bytes = _png_bytes()
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=image_bytes, request=request)
        )
    )
    row = SimpleNamespace(
        image_data=None,
        image_mime_type=None,
        image_credit=None,
        updated_at=None,
    )
    session = _session_with_row(row)

    result = add_entity_image(
        session,
        entity,
        "example-slug",
        "https://images.example/hero",
        "https://source.example/page",
        client=client,
        seed_root=tmp_path,
    )

    plural = {"task": "tasks", "method": "methods", "conference": "conferences"}[entity]
    assert result.seed_path == str(tmp_path / plural / "example-slug.png")
    assert (tmp_path / plural / "example-slug.png").read_bytes() == image_bytes
    assert row.image_data == image_bytes
    assert row.image_mime_type == "image/png"
    assert row.image_credit == "https://source.example/page"
    assert row.updated_at is not None


def test_default_seed_root_is_not_repository_relative() -> None:
    assert (
        IMAGE_SEED_ROOT
        == Path(tempfile.gettempdir()) / "paperswithcode_entity_image_seeds"
    )
    assert IMAGE_SEED_ROOT != Path("data") / "entity_image_seeds"


def test_add_entity_image_rejects_non_image(tmp_path: Path) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="not an image", request=request)
        )
    )

    with pytest.raises(ValueError, match="not a valid supported image"):
        add_entity_image(
            _session_with_row(SimpleNamespace()),
            "task",
            "example-slug",
            "https://images.example/not-image",
            "https://source.example/page",
            client=client,
            seed_root=tmp_path,
        )


def test_image_add_cli_arguments() -> None:
    args = cli.build_parser().parse_args(
        [
            "image",
            "add",
            "method",
            "transformer",
            "https://images.example/transformer.png",
            "--source",
            "https://source.example/paper",
            "--json",
        ]
    )

    assert args.handler is cli.add_image
    assert args.entity == "method"
    assert args.slug == "transformer"
    assert args.image_url == "https://images.example/transformer.png"
    assert args.source == "https://source.example/paper"
    assert args.json is True
