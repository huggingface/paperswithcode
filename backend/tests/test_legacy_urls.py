from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.scripts import import_legacy_pwc_slugs as importer
from backend.services.legacy_url_service import LegacyUrlService


@pytest.fixture
def client():
    app = create_app()

    def database():
        yield object()

    app.dependency_overrides[get_database_session] = database
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    ("path", "method", "location"),
    [
        ("/sota/image-classification-on-imagenet", "sota_path", "/benchmark/imagenet"),
        ("/dataset/coco", "dataset_path", "/benchmark/coco"),
        ("/method/transformer", "method_path", "/methods/transformer"),
    ],
)
def test_legacy_routes_redirect_permanently(
    client, monkeypatch, path, method, location
):
    monkeypatch.setattr(LegacyUrlService, method, lambda self, slug: location)

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"] == location
    assert client.head(path, follow_redirects=False).status_code == 301


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/sota/unknown-on-nothing", "sota_path"),
        ("/dataset/unknown", "dataset_path"),
        ("/method/unknown", "method_path"),
    ],
)
def test_unresolved_legacy_routes_return_noindex_404(client, monkeypatch, path, method):
    monkeypatch.setattr(LegacyUrlService, method, lambda self, slug: None)

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 404
    assert 'name="robots" content="noindex"' in response.text


def test_importer_reads_each_legacy_dump(tmp_path):
    def dump(name, rows):
        (tmp_path / name).write_text(json.dumps(rows))

    dump(
        "papers-with-abstracts.json",
        [
            {
                "paper_url": "https://paperswithcode.com/paper/attention",
                "arxiv_id": "1706.03762",
            },
            {
                "paper_url": "https://paperswithcode.com/paper/no-arxiv",
                "arxiv_id": None,
            },
        ],
    )
    dump(
        "jul-28-methods.json",
        [
            {
                "url": "https://paperswithcode.com/method/transformer",
                "name": "Transformer",
            }
        ],
    )
    dump(
        "jul-28-datasets.json",
        [{"url": "https://paperswithcode.com/dataset/coco", "name": "COCO"}],
    )
    dump(
        "evaluation-tables.json",
        [
            {
                "task": "Object Detection",
                "datasets": [],
                "subtasks": [
                    {
                        "task": "Real-Time Object Detection",
                        "subtasks": [],
                        "datasets": [
                            {
                                "dataset": "COCO",
                                "dataset_links": [
                                    {
                                        "url": "https://paperswithcode.com/sota/real-time-object-detection-on-coco"
                                    },
                                    {"url": "https://cocodataset.org"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    )

    rows = list(importer.iter_rows(tmp_path, ["method", "dataset", "sota", "paper"]))

    assert rows == [
        ("method", "transformer", "Transformer"),
        ("dataset", "coco", "COCO"),
        ("sota", "real-time-object-detection-on-coco", "COCO"),
        ("paper", "attention", "1706.03762"),
    ]


def test_dataset_name_key_ignores_case_and_punctuation():
    from backend.services.legacy_url_service import _name_key

    assert _name_key("SQuAD2.0") == _name_key("SQuAD 2.0") == "squad20"
    assert _name_key("Mini-Imagenet") == _name_key("MiniImageNet")


def test_legacy_method_moved_to_task_redirects_to_the_task(client):
    response = client.get("/method/continual-learning", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"] == "/tasks/continual-learning"
