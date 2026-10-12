from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Base,
    Method as DBMethod,
    Paper as DBPaper,
    PaperMethod,
)
from backend.services.method_service import MethodService
from backend.services.paper_service import PaperService
from backend.database.methods_setup.check_method_source_links import (
    apply_source_link_plan,
    build_source_link_plan,
    parse_trusted_source_url,
)


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


def test_paper_response_keeps_source_paper_id_on_methods_without_url_fallback():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with SessionLocal() as db:
        paper = DBPaper(
            id=1,
            title="Source Paper",
            abstract="Introduces one method and uses another.",
            arxiv_id="2212.04356",
            version="v1",
            is_latest_version=True,
            date_published=date(2022, 12, 8),
        )
        introduced_method = DBMethod(
            id=1,
            name="Whisper",
            slug="whisper",
            source_paper_id=1,
            source_url="/paper/2212.04356",
        )
        used_method = DBMethod(
            id=2,
            name="Transformer",
            slug="transformer",
        )
        source_url_only_method = DBMethod(
            id=3,
            name="Legacy URL Match",
            slug="legacy-url-match",
            source_url="/paper/2212.04356",
        )
        db.add_all([paper, introduced_method, used_method, source_url_only_method])
        db.add_all(
            [
                PaperMethod(paper_id=1, method_id=1),
                PaperMethod(paper_id=1, method_id=2),
            ]
        )
        db.commit()

        response = PaperService(db).get_paper_by_arxiv_id("2212.04356")

    assert [method.name for method in response.methods or []] == [
        "Transformer",
        "Whisper",
    ]
    introduced_methods = [
        method
        for method in response.methods or []
        if method.source_paper_id == response.id
    ]
    assert [method.name for method in introduced_methods] == ["Whisper"]


def test_method_response_normalizes_internal_source_url_to_relative_paper_route():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with SessionLocal() as db:
        db.add(
            DBPaper(
                id=1,
                title="Robust Speech Recognition via Large-Scale Weak Supervision",
                abstract="Whisper source paper.",
                arxiv_id="2212.04356",
                version="v1",
                is_latest_version=True,
                date_published=date(2022, 12, 8),
            )
        )
        db.add(
            DBMethod(
                id=1,
                name="Whisper",
                slug="whisper",
                source_paper_id=1,
                source_url="http://167.235.148.241:8080/paper/wrong-host-link",
                source_title="Robust Speech Recognition via Large-Scale Weak Supervision",
            )
        )
        db.add(
            DBMethod(
                id=2,
                name="External",
                slug="external",
                source_url="https://openai.com/index/whisper/",
                source_title="OpenAI Whisper",
            )
        )
        db.add(PaperMethod(paper_id=1, method_id=1))
        db.commit()

        whisper = MethodService(db).get_method_by_name("whisper")
        external = MethodService(db).get_method_by_name("external")
        method_page = MethodService(db).get_methods()

    assert whisper.source_url == "/paper/2212.04356"
    assert external.source_url == "https://openai.com/index/whisper/"
    assert {method.slug: method.source_url for method in method_page.results} == {
        "external": "https://openai.com/index/whisper/",
        "whisper": "/paper/2212.04356",
    }
    assert {method.slug: method.paper_count for method in method_page.results} == {
        "external": 0,
        "whisper": 1,
    }


def test_parse_trusted_source_url_accepts_site_and_arxiv_routes_only():
    assert parse_trusted_source_url("/paper/2212.04356v2").arxiv_id == "2212.04356"
    assert parse_trusted_source_url("/paper/2212.04356v2").version == "v2"
    assert (
        parse_trusted_source_url("https://arxiv.org/pdf/cs.CL/0101001.pdf").arxiv_id
        == "cs.CL/0101001"
    )
    assert parse_trusted_source_url("https://example.com/article/2212.04356") is None


def test_backfill_populates_source_paper_and_paper_methods_for_trusted_urls():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with SessionLocal() as db:
        db.add_all(
            [
                DBPaper(
                    id=1,
                    title="Old Version",
                    abstract="v1",
                    arxiv_id="2212.04356",
                    version="v1",
                    is_latest_version=False,
                    date_published=date(2022, 12, 8),
                ),
                DBPaper(
                    id=2,
                    title="Latest Version",
                    abstract="v2",
                    arxiv_id="2212.04356",
                    version="v2",
                    is_latest_version=True,
                    date_published=date(2022, 12, 9),
                ),
                DBPaper(
                    id=3,
                    title="Legacy ArXiv",
                    abstract="legacy",
                    arxiv_id="cs.CL/0101001",
                    version="v1",
                    is_latest_version=True,
                    date_published=date(2001, 1, 1),
                ),
            ]
        )
        db.add_all(
            [
                DBMethod(
                    id=1,
                    name="Unversioned",
                    slug="unversioned",
                    source_url="https://paperswithcode.co/paper/2212.04356",
                ),
                DBMethod(
                    id=2,
                    name="Versioned",
                    slug="versioned",
                    source_url="https://arxiv.org/abs/2212.04356v1",
                ),
                DBMethod(
                    id=3,
                    name="Legacy",
                    slug="legacy",
                    source_url="https://arxiv.org/pdf/cs.CL/0101001.pdf",
                ),
                DBMethod(
                    id=4,
                    name="External",
                    slug="external",
                    source_url="https://example.com/article/2212.04356",
                ),
            ]
        )
        db.commit()

        plan = build_source_link_plan(db)
        assert len(plan.source_paper_updates) == 3
        assert len(plan.paper_method_inserts) == 3

        apply_source_link_plan(db, plan)

        assert db.get(DBMethod, 1).source_paper_id == 2
        assert db.get(DBMethod, 2).source_paper_id == 1
        assert db.get(DBMethod, 3).source_paper_id == 3
        assert db.get(DBMethod, 4).source_paper_id is None
        assert {
            (paper_method.paper_id, paper_method.method_id)
            for paper_method in db.query(PaperMethod).all()
        } == {(2, 1), (1, 2), (3, 3)}
