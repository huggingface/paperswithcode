import json

import httpx
import pytest
from sqlalchemy import BigInteger, create_engine, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import (
    Author,
    AuthorAlias,
    AuthorGoogleScholarProfile,
    AuthorPhoto,
    Base,
    Paper,
    PaperAuthor,
    PaperRepository,
    Repository,
    ResearchFollow,
)
from backend.services.author_claim_backfill_service import (
    AuthorClaimCleanup,
    HfPaperClient,
    fetch_hf_papers,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
def _compile_postgres_container_sqlite(_element, _compiler, **_kw):
    return "TEXT"


HAO = {"_id": "hf-hao", "user": "hao-li", "fullname": "Hao Li", "type": "user"}
OTHER = {"_id": "hf-other", "user": "other-hao", "type": "user"}


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Author.__table__,
            PaperAuthor.__table__,
            Repository.__table__,
            PaperRepository.__table__,
            AuthorAlias.__table__,
            AuthorGoogleScholarProfile.__table__,
            AuthorPhoto.__table__,
            ResearchFollow.__table__,
        ],
    )
    session = Session(engine)
    session.execute(
        text("CREATE TABLE author_google_scholar_candidates (author_id INTEGER)")
    )
    session.add_all(
        Paper(
            id=paper_id,
            arxiv_id=f"2601.0000{paper_id}",
            title=f"Paper {paper_id}",
            version="v1",
            is_latest_version=True,
        )
        for paper_id in range(1, 6)
    )
    session.add_all(
        [
            # Legacy row: every "Hao Li" paper landed on the hao-li account.
            Author(id=10, name="Hao Li", hf_username="hao-li", hf_id="hf-hao"),
            Author(id=11, name="Ann Coauthor"),
            Author(id=12, name="Bob Stranger"),
            Author(id=13, name="Cat Stranger"),
        ]
    )
    links = {1: (10, 11), 2: (10, 11), 3: (10, 12), 4: (10, 13), 5: (10, 12)}
    session.add_all(
        PaperAuthor(paper_id=paper_id, author_id=author_id, author_order=order)
        for paper_id, authors in links.items()
        for order, author_id in enumerate(authors, start=1)
    )
    session.commit()
    return session


def _cache(tmp_path, papers):
    path = tmp_path / "claims.jsonl"
    path.write_text(
        "".join(
            json.dumps({"arxiv_id": arxiv_id, "authors": authors}) + "\n"
            for arxiv_id, authors in papers.items()
        )
    )
    return path


def _claim(name, user, status="claimed_verified"):
    return {"name": name, "hidden": False, "status": status, "user": user}


def _authors_of(session, paper_id):
    return {
        (link.author_id, link.claimed)
        for link in session.query(PaperAuthor).filter_by(paper_id=paper_id)
    }


def _add_second_hao_account(session):
    # A second HF account publishing as "Hao Li" proves namesakes exist.
    session.add(Author(id=30, name="Hao Li", hf_username="hao-li-2", hf_id="hf-2"))
    session.commit()


def _cleanup(session):
    entries = []
    return AuthorClaimCleanup(session, entries.append), entries


def test_replayed_claims_mark_links_and_hand_other_claims_to_their_account(
    tmp_path,
):
    session = _session()
    cleanup, entries = _cleanup(session)
    cache = _cache(
        tmp_path,
        {
            "2601.00001": [_claim("Hao Li", HAO)],
            "2601.00004": [_claim("Hao Li", OTHER)],
            "2601.00005": [_claim("Hao Li", HAO, status="extracted_pending")],
            "2601.00003": None,
        },
    )

    cleanup.replay_claims(cache)

    assert _authors_of(session, 1) == {(10, True), (11, False)}
    other = session.query(Author).filter_by(hf_username="other-hao").one()
    assert _authors_of(session, 4) == {(other.id, True), (13, False)}
    # An unconfirmed HF guess is not a claim.
    assert (10, False) in _authors_of(session, 5)
    assert cleanup.stats.counts["claims_not_on_hf"] == 1
    assert [e["arxiv_id"] for e in entries] == ["2601.00001", "2601.00004"]


def test_split_keeps_coauthor_backed_papers_and_moves_the_rest(tmp_path):
    session = _session()
    _add_second_hao_account(session)
    cleanup, entries = _cleanup(session)
    cleanup.replay_claims(_cache(tmp_path, {"2601.00001": [_claim("Hao Li", HAO)]}))

    cleanup.split_namesakes()

    # Paper 2 shares coauthor Ann with claimed paper 1, so it stays.
    assert _authors_of(session, 2) == {(10, False), (11, False)}
    namesake = session.query(Author).filter_by(name="Hao Li", hf_username=None).one()
    for paper_id in (3, 4, 5):
        assert (namesake.id, False) in _authors_of(session, paper_id)
        assert (10, False) not in _authors_of(session, paper_id)
    order = (
        session.query(PaperAuthor.author_order)
        .filter_by(paper_id=3, author_id=namesake.id)
        .scalar()
    )
    assert order == 1
    assert cleanup.stats.counts["split_move_link"] == 3
    assert cleanup.stats.counts["split_kept_by_coauthor"] == 1
    assert {e["paper_id"] for e in entries if e["phase"] == "split"} == {3, 4, 5}


def test_split_uses_the_byline_name_of_a_row_renamed_by_its_claim(tmp_path):
    session = _session()
    _add_second_hao_account(session)
    cleanup, entries = _cleanup(session)
    # HF matched hao-li to a "Hao Li" byline; the account is really Zed Jia,
    # who claims paper 1 as "Zed Jia" and so renames the row.
    zed = {**HAO, "fullname": "Zed Jia"}
    cleanup.replay_claims(
        _cache(
            tmp_path,
            {
                "2601.00001": [_claim("Zed Jia", zed)],
                "2601.00003": [{"name": "Hao Li"}, {"name": "Bob Stranger"}],
                "2601.00004": [{"name": "Someone Else"}],
            },
        )
    )
    assert session.get(Author, 10).name == "Zed Jia"

    cleanup.split_namesakes()

    namesake = session.query(Author).filter_by(name="Hao Li", hf_username=None).one()
    assert (namesake.id, False) in _authors_of(session, 3)
    # Paper 4's byline lists neither name: the link stays and is reported.
    assert (10, False) in _authors_of(session, 4)
    # Paper 5 has no cached byline, and the row was renamed: unsure, stays.
    assert (10, False) in _authors_of(session, 5)
    assert cleanup.stats.counts["split_skipped_name_not_on_byline"] == 2


def test_split_leaves_names_with_a_single_hf_account_alone(tmp_path):
    session = _session()
    cleanup, entries = _cleanup(session)
    cleanup.replay_claims(_cache(tmp_path, {"2601.00001": [_claim("Hao Li", HAO)]}))

    cleanup.split_namesakes()

    for paper_id in (3, 4, 5):
        assert (10, False) in _authors_of(session, paper_id)
    assert cleanup.stats.counts["split_skipped_unique_name"] == 3
    assert not [e for e in entries if e["phase"] == "split"]


def test_split_leaves_rows_without_any_claim_alone():
    session = _session()
    cleanup, entries = _cleanup(session)

    cleanup.split_namesakes()

    assert (10, False) in _authors_of(session, 3)
    assert cleanup.stats.counts["split_rows_without_claims"] == 1
    assert cleanup.stats.counts["split_links_on_rows_without_claims"] == 5
    assert entries == [
        {
            "phase": "split",
            "action": "skip_no_claims",
            "author_id": 10,
            "unclaimed_links": 5,
        }
    ]


def test_doubles_keep_the_claimed_link_else_the_name_only_one():
    session = _session()
    session.add(Author(id=20, name="Hao Li"))
    session.add_all(
        [
            PaperAuthor(paper_id=1, author_id=20, author_order=1),
            PaperAuthor(paper_id=2, author_id=20, author_order=1),
            # Two coauthors named Hao Li: both stay.
            PaperAuthor(paper_id=3, author_id=20, author_order=3),
        ]
    )
    session.get(PaperAuthor, (1, 10)).claimed = True
    session.commit()
    cleanup, entries = _cleanup(session)

    cleanup.fix_doubles()

    assert _authors_of(session, 1) == {(10, True), (11, False)}
    assert _authors_of(session, 2) == {(20, False), (11, False)}
    assert _authors_of(session, 3) == {(10, False), (12, False), (20, False)}
    assert cleanup.stats.counts["doubles_removed"] == 2
    assert cleanup.stats.counts["doubles_skipped_different_positions"] == 1
    assert [e["paper_id"] for e in entries if e["action"] == "skip"] == [3]


def test_empty_name_only_authors_are_deleted_and_aliased_to_a_namesake():
    session = _session()
    session.add_all(
        [
            Author(id=30, name="hao li"),
            Author(id=31, name="Lonely Name"),
            Author(id=32, name="Followed Name"),
            Author(id=33, name="Pictured Name"),
            AuthorAlias(alias_id=99, author_id=30),
            ResearchFollow(hf_subject="u", kind="author", entity_id=32),
            AuthorPhoto(
                author_id=33,
                image_data=b"x",
                mime_type="image/jpeg",
                sha256="0" * 64,
                source_url="y",
                credit="c",
                license="z",
            ),
        ]
    )
    session.commit()
    cleanup, _ = _cleanup(session)

    cleanup.delete_empty_authors()

    assert session.get(Author, 30) is None
    assert session.get(Author, 31) is None
    assert session.get(Author, 32) is not None
    assert session.get(Author, 33) is not None
    aliases = {a.alias_id: a.author_id for a in session.query(AuthorAlias)}
    assert aliases == {30: 10, 99: 10}
    assert cleanup.stats.counts["empty_deleted"] == 2
    assert cleanup.stats.counts["empty_aliased"] == 1


def test_fetch_caches_trimmed_author_lists_and_resumes(tmp_path):
    session = _session()
    calls = []

    def handler(request):
        arxiv_id = request.url.path.rsplit("/", 1)[1]
        calls.append(arxiv_id)
        if arxiv_id == "2601.00002":
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={
                "authors": [
                    {**_claim("Hao Li", {**HAO, "extra": 1}), "_id": "x"},
                ]
            },
        )

    client = HfPaperClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        requests_per_second=1000,
        sleep=lambda _: None,
    )
    cache = tmp_path / "claims.jsonl"

    assert fetch_hf_papers(session, client, cache, limit=2) == 2
    assert fetch_hf_papers(session, client, cache) == 3

    assert calls == [f"2601.0000{i}" for i in range(1, 6)]
    lines = [json.loads(line) for line in cache.read_text().splitlines()]
    assert lines[1] == {"arxiv_id": "2601.00002", "authors": None}
    assert lines[0]["authors"] == [_claim("Hao Li", HAO)]


def _link(session, paper_id, author_id, order=9, claimed=False):
    session.add(
        PaperAuthor(
            paper_id=paper_id, author_id=author_id, author_order=order, claimed=claimed
        )
    )


def test_merge_moves_a_name_only_paper_sharing_an_official_repo_with_a_curated_row():
    session = _session()
    session.add_all(
        [
            # A curator set the HF username by hand: no HF id, no claims.
            Author(id=40, name="Vik Paruchuri", hf_username="vikp"),
            Author(id=41, name="Vik Paruchuri"),
            Repository(id=1, url="https://github.com/datalab-to/surya"),
        ]
    )
    _link(session, 1, 40)
    _link(session, 2, 41, order=2)
    session.add_all(
        [
            PaperRepository(paper_id=1, repository_id=1, is_official=True),
            PaperRepository(paper_id=2, repository_id=1, is_official=True),
        ]
    )
    session.commit()
    cleanup, entries = _cleanup(session)

    cleanup.merge_namesakes()
    cleanup.delete_empty_authors()

    assert (40, False) in _authors_of(session, 2)
    assert session.get(PaperAuthor, (2, 40)).author_order == 2
    assert session.get(Author, 41) is None
    assert session.get(AuthorAlias, 41).author_id == 40
    assert [e["evidence"] for e in entries if e["phase"] == "merge"] == [
        ["official_repository"]
    ]


def _account_with_namesake(session):
    session.add_all(
        [
            Author(id=50, name="Zed Verified", hf_username="zed", hf_id="hf-zed"),
            Author(id=51, name="Mia Account", hf_username="mia", hf_id="hf-mia"),
            Author(id=52, name="Mia Account"),
        ]
    )
    # Paper 3 is Mia's claimed anchor, written with Zed (claimed), Bob and Ann.
    _link(session, 3, 51, claimed=True)
    _link(session, 3, 50, claimed=True)
    _link(session, 3, 11)


def test_merge_needs_a_coauthor_whose_identity_is_certain_on_both_papers():
    session = _session()
    _account_with_namesake(session)
    _link(session, 4, 52)
    _link(session, 4, 50, claimed=True)
    _link(session, 5, 52)
    _link(session, 5, 50)  # Zed by name only on paper 5: could be a namesake.
    session.commit()
    cleanup, _ = _cleanup(session)

    cleanup.merge_namesakes()

    assert (51, False) in _authors_of(session, 4)
    assert (52, False) in _authors_of(session, 5)
    assert cleanup.stats.counts["merge_by_verified_coauthor"] == 1


@pytest.mark.parametrize("cat_accounts", [0, 2])
def test_merge_counts_distinctive_name_only_coauthors(cat_accounts):
    session = _session()
    _account_with_namesake(session)
    # Mia's anchor (paper 3) lists Hao Li (an HF row, never counted), Bob (12)
    # and Cat (13); paper 4 lists all three, paper 5 only Hao Li and Bob.
    _link(session, 3, 13)
    _link(session, 4, 52)
    _link(session, 4, 12)
    _link(session, 5, 52)
    # Accounts named "Cat Stranger" mean the Cat row may lump namesakes.
    session.add_all(
        Author(id=70 + i, name="Cat Stranger", hf_username=f"cat{i}", hf_id=f"c{i}")
        for i in range(cat_accounts)
    )
    session.commit()
    cleanup, entries = _cleanup(session)

    cleanup.merge_namesakes()

    merged = [(e["paper_id"], e["shared_coauthors"]) for e in entries]
    assert merged == ([(4, 2)] if cat_accounts == 0 else [])
    assert (52, False) in _authors_of(session, 5)


def test_merge_skips_names_shared_by_two_accounts():
    session = _session()
    _account_with_namesake(session)
    session.add(Author(id=53, name="Mia Account", hf_username="mia2", hf_id="hf-2"))
    _link(session, 4, 52)
    _link(session, 4, 50, claimed=True)
    session.commit()
    cleanup, _ = _cleanup(session)

    cleanup.merge_namesakes()

    assert (52, False) in _authors_of(session, 4)
    assert cleanup.stats.counts["merge_candidates"] == 0
