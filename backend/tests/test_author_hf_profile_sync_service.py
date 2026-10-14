from datetime import UTC, datetime

import httpx
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import Author, Base, Paper, PaperAuthor
from backend.services.author_hf_profile_sync_service import (
    AuthorHfProfileSyncService,
    iter_hf_papers,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
def _compile_postgres_container_sqlite(_element, _compiler, **_kw):
    return "TEXT"


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[Paper.__table__, Author.__table__, PaperAuthor.__table__],
    )
    session = Session(engine)
    session.add(
        Paper(
            id=1,
            arxiv_id="2610.11959",
            title="MiMo-V2.6",
            version="v1",
            is_latest_version=True,
        )
    )
    session.add_all(
        [
            Author(id=10, name="Ziyue Hua"),
            Author(id=11, name="Zihao Yue"),
            Author(
                id=12,
                name="Weikun Wang",
                hf_username="kunwww",
                hf_id="hf-kunwww",
                hf_avatar_url="/avatars/old.svg",
                hf_status="claimed_verified",
            ),
            Author(id=13, name="Yang Liu", hf_username="someone", hf_id="hf-someone"),
            Author(id=14, name="Unrelated Author"),
        ]
    )
    session.add_all(
        PaperAuthor(paper_id=1, author_id=author_id, author_order=order)
        for order, author_id in enumerate((10, 11, 12, 13), start=1)
    )
    session.commit()
    return session


def _claim(name: str, username: str, hf_id: str, avatar: str = "/avatars/a.svg"):
    return {
        "name": name,
        "status": "claimed_verified",
        "hidden": False,
        "user": {
            "_id": hf_id,
            "user": username,
            "avatarUrl": avatar,
            "isPro": True,
            "type": "user",
        },
    }


def _hf_paper(*authors):
    return {
        "id": "2610.11959",
        "publishedAt": "2026-10-08T00:00:00.000Z",
        "authors": [{"name": "Ziyue Hua", "hidden": False}, *authors],
    }


def test_claim_links_the_named_author_on_that_paper():
    session = _session()
    service = AuthorHfProfileSyncService(session)

    service.sync_paper(
        _hf_paper(_claim("Zihao  Yue", "yuezih", "hf-yuezih", "https://cdn/y.jpeg"))
    )

    author = session.get(Author, 11)
    assert author.hf_username == "yuezih"
    assert author.hf_id == "hf-yuezih"
    assert author.hf_avatar_url == "https://cdn/y.jpeg"
    assert author.hf_status == "claimed_verified"
    assert author.hf_is_pro is True
    assert session.get(Author, 10).hf_username is None
    assert service.stats.linked == 1


def test_linked_account_refreshes_its_profile_without_moving():
    session = _session()
    service = AuthorHfProfileSyncService(session)

    service.sync_paper(
        _hf_paper(_claim("W. Wang", "kunwww", "hf-kunwww", "/avatars/new.svg"))
    )
    service.sync_paper(
        _hf_paper(_claim("W. Wang", "kunwww", "hf-kunwww", "/avatars/new.svg"))
    )

    assert session.get(Author, 12).hf_avatar_url == "/avatars/new.svg"
    assert service.stats.refreshed == 1
    assert service.stats.unchanged == 1
    assert service.stats.linked == 0


def test_renamed_account_keeps_its_author():
    session = _session()
    service = AuthorHfProfileSyncService(session)

    service.sync_paper(_hf_paper(_claim("Weikun Wang", "kunwang", "hf-kunwww")))

    assert session.get(Author, 12).hf_username == "kunwang"
    assert service.stats.refreshed == 1


def test_namesake_unmatched_and_unknown_papers_are_left_alone():
    session = _session()
    service = AuthorHfProfileSyncService(session)

    service.sync_paper(
        _hf_paper(
            _claim("Yang Liu", "other-yang", "hf-other-yang"),
            _claim("Unrelated Author", "unrelated", "hf-unrelated"),
        )
    )
    service.sync_paper(
        {
            "id": "2610.99999",
            "publishedAt": "2026-10-08T00:00:00.000Z",
            "authors": [_claim("Zihao Yue", "yuezih", "hf-yuezih")],
        }
    )

    assert session.get(Author, 13).hf_username == "someone"
    assert session.get(Author, 14).hf_username is None
    assert session.get(Author, 11).hf_username is None
    assert service.stats.conflicts == 1
    assert service.stats.unmatched == 1
    assert service.stats.papers_matched == 1


def test_iter_hf_papers_follows_cursor_until_the_cutoff():
    pages = {
        "https://huggingface.co/api/papers?limit=100": (
            [{"id": "a", "publishedAt": "2026-10-13T00:00:00.000Z"}],
            {
                "link": '<https://huggingface.co/api/papers?limit=100&cursor=x>; rel="next"'
            },
        ),
        "https://huggingface.co/api/papers?limit=100&cursor=x": (
            [
                {"id": "b", "publishedAt": "2026-10-10T00:00:00.000Z"},
                {"id": "c", "publishedAt": "2026-09-01T00:00:00.000Z"},
            ],
            {
                "link": '<https://huggingface.co/api/papers?limit=100&cursor=y>; rel="next"'
            },
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body, headers = pages[str(request.url)]
        return httpx.Response(200, json=body, headers=headers)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        papers = list(
            iter_hf_papers(client, datetime(2026, 10, 1, tzinfo=UTC), pause_seconds=0)
        )

    assert [paper["id"] for paper in papers] == ["a", "b"]
