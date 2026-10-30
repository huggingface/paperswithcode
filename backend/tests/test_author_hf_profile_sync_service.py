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


def _claim(
    name: str,
    username: str,
    hf_id: str,
    avatar: str = "/avatars/a.svg",
    fullname: str | None = None,
):
    return {
        "name": name,
        "status": "claimed_verified",
        "hidden": False,
        "user": {
            "_id": hf_id,
            "user": username,
            "fullname": fullname,
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


def _links(session, paper_id=1):
    return {
        (link.author_id, link.author_order, link.claimed)
        for link in session.query(PaperAuthor).filter_by(paper_id=paper_id)
    }


def _account_author(session, username):
    return session.query(Author).filter_by(hf_username=username).one()


def test_claim_moves_the_paper_to_the_accounts_own_author():
    session = _session()
    service = AuthorHfProfileSyncService(session)

    service.sync_paper(
        _hf_paper(_claim("Zihao  Yue", "yuezih", "hf-yuezih", "https://cdn/y.jpeg"))
    )

    author = _account_author(session, "yuezih")
    assert author.id != 11
    assert author.name == "Zihao Yue"
    assert author.hf_id == "hf-yuezih"
    assert author.hf_avatar_url == "https://cdn/y.jpeg"
    assert author.hf_status == "claimed_verified"
    assert author.hf_is_pro is True
    # The name-matched author keeps its other papers and gets no account.
    assert session.get(Author, 11).hf_username is None
    assert _links(session) == {
        (10, 1, False),
        (author.id, 2, True),
        (12, 3, False),
        (13, 4, False),
    }
    assert service.stats.linked == 1
    assert service.stats.claimed == 1


def test_linked_account_refreshes_its_profile_and_claims_the_paper():
    session = _session()
    service = AuthorHfProfileSyncService(session)

    service.sync_paper(
        _hf_paper(_claim("W. Wang", "kunwww", "hf-kunwww", "/avatars/new.svg"))
    )
    service.sync_paper(
        _hf_paper(_claim("W. Wang", "kunwww", "hf-kunwww", "/avatars/new.svg"))
    )

    assert session.get(Author, 12).hf_avatar_url == "/avatars/new.svg"
    assert (12, 3, True) in _links(session)
    assert service.stats.refreshed == 1
    assert service.stats.unchanged == 1
    assert service.stats.claimed == 1
    assert service.stats.linked == 0


def test_account_claiming_a_paper_listed_under_a_namesake_takes_it_over():
    session = _session()
    service = AuthorHfProfileSyncService(session)

    # An account that already has an author claims the "Ziyue Hua" slot of a
    # paper it is not linked to yet: the name-matched author 10 loses it.
    session.delete(session.get(PaperAuthor, (1, 12)))
    session.commit()
    service.sync_paper(_hf_paper(_claim("Ziyue Hua", "kunwww", "hf-kunwww")))

    assert _links(session) == {(12, 1, True), (11, 2, False), (13, 4, False)}
    assert service.stats.linked == 0
    assert service.stats.claimed == 1


def test_claim_drops_the_name_matched_duplicate_of_a_linked_account():
    session = _session()
    # The account's author is stored as "W. Wang"; the paper also lists a
    # name-only "Weikun Wang", which is the same person.
    session.get(Author, 12).name = "W. Wang"
    session.get(Author, 14).name = "Weikun Wang"
    session.add(PaperAuthor(paper_id=1, author_id=14, author_order=5))
    session.commit()
    service = AuthorHfProfileSyncService(session)

    service.sync_paper(_hf_paper(_claim("Weikun Wang", "kunwww", "hf-kunwww")))

    links = _links(session)
    assert (12, 3, True) in links
    assert not any(author_id == 14 for author_id, _, _ in links)
    assert service.stats.claimed == 1


def test_unclaimed_namesake_link_moves_but_a_claimed_one_conflicts():
    session = _session()
    service = AuthorHfProfileSyncService(session)

    # Author 13 ("someone") was matched to "Yang Liu" by name only.
    service.sync_paper(_hf_paper(_claim("Yang Liu", "other-yang", "hf-other-yang")))
    other = _account_author(session, "other-yang")
    assert (other.id, 4, True) in _links(session)
    assert session.get(Author, 13).hf_username == "someone"

    # A second account claiming the same, now claimed, slot is a conflict.
    service.sync_paper(_hf_paper(_claim("Yang Liu", "third-yang", "hf-third-yang")))
    assert session.query(Author).filter_by(hf_username="third-yang").count() == 0
    assert service.stats.conflicts == 1


def test_unmatched_unknown_and_unconfirmed_claims_are_left_alone():
    session = _session()
    service = AuthorHfProfileSyncService(session)
    pending = _claim("Zihao Yue", "yuezih", "hf-yuezih")
    pending["status"] = "extracted_pending"

    service.sync_paper(
        _hf_paper(_claim("Unrelated Author", "unrelated", "hf-unrelated"), pending)
    )
    service.sync_paper(
        {
            "id": "2610.99999",
            "publishedAt": "2026-10-08T00:00:00.000Z",
            "authors": [_claim("Zihao Yue", "yuezih", "hf-yuezih")],
        }
    )

    assert (
        session.query(Author)
        .filter(Author.hf_username.in_(["unrelated", "yuezih"]))
        .count()
        == 0
    )
    assert session.get(Author, 14).hf_username is None
    assert service.stats.unmatched == 1
    assert service.stats.claims_seen == 1
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


def test_reused_username_never_rebinds_an_author():
    session = _session()
    service = AuthorHfProfileSyncService(session)

    service.sync_paper(_hf_paper(_claim("Weikun Wang", "kunwww", "hf-new-owner")))

    author = session.get(Author, 12)
    assert (author.hf_username, author.hf_id) == ("kunwww", "hf-kunwww")
    assert service.stats.conflicts == 1


def test_stored_names_are_normalized_and_ambiguous_names_skipped():
    session = _session()
    session.add_all(
        [
            Author(id=20, name="Ziyue  Hua (MiMo)"),
            Author(id=21, name="Zihao Yue (Xiaomi)"),
        ]
    )
    session.add_all(
        [
            PaperAuthor(paper_id=1, author_id=20, author_order=5),
            PaperAuthor(paper_id=1, author_id=21, author_order=6),
        ]
    )
    session.delete(session.get(PaperAuthor, (1, 11)))
    session.commit()
    service = AuthorHfProfileSyncService(session)

    service.sync_paper(
        _hf_paper(
            _claim("Zihao Yue", "yuezih", "hf-yuezih"),
            _claim("Ziyue Hua", "ziyue", "hf-ziyue"),
        )
    )

    author = _account_author(session, "yuezih")
    assert author.name == "Zihao Yue"
    assert (author.id, 6, True) in _links(session)
    assert session.get(Author, 21).hf_username is None
    assert session.get(Author, 10).hf_username is None
    assert session.get(Author, 20).hf_username is None
    assert service.stats.linked == 1
    assert service.stats.unmatched == 1


def test_account_takes_its_full_name_from_a_byline_it_claimed():
    session = _session()
    session.add(
        Paper(
            id=2,
            arxiv_id="2610.00002",
            title="New",
            version="v1",
            is_latest_version=True,
        )
    )
    session.add(Author(id=15, name="Weikun Knaebel"))
    session.add(PaperAuthor(paper_id=2, author_id=15, author_order=1))
    session.commit()
    service = AuthorHfProfileSyncService(session)

    # A former name on the byline leaves the row's name alone.
    service.sync_paper(
        _hf_paper(
            _claim("Weikun Wang", "kunwww", "hf-kunwww", fullname="Weikun Knaebel")
        )
    )
    assert session.get(Author, 12).name == "Weikun Wang"

    service.sync_paper(
        {
            "id": "2610.00002",
            "authors": [
                _claim(
                    "WEIKUN  KNAEBEL", "kunwww", "hf-kunwww", fullname="Weikun Knaebel"
                )
            ],
        }
    )

    assert session.get(Author, 12).name == "Weikun Knaebel"
    assert _links(session, 2) == {(12, 1, True)}
    assert (12, 3, True) in _links(session)
    assert service.stats.renamed == 1

    # Another capitalization of the same name does not flip the row back.
    service.sync_paper(
        _hf_paper(
            _claim("Weikun Knaebel", "kunwww", "hf-kunwww", fullname="Weikun Knaebel")
        )
    )
    assert session.get(Author, 12).name == "Weikun Knaebel"
    assert service.stats.renamed == 1


def test_a_nickname_full_name_never_renames_the_author():
    session = _session()
    service = AuthorHfProfileSyncService(session)

    service.sync_paper(
        _hf_paper(_claim("Weikun Wang", "kunwww", "hf-kunwww", fullname="kun"))
    )

    assert session.get(Author, 12).name == "Weikun Wang"
    assert service.stats.renamed == 0
