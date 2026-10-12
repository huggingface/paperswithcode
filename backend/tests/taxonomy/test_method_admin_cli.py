from datetime import date

from sqlalchemy import BigInteger, create_engine, event, func, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import cli
from backend.models.database import Area, Base, Method, Paper, PaperMethod
from backend.services.method_admin_service import add_or_update_method


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(BigInteger, "sqlite")
def _compile_big_integer_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


def test_method_add_cli_parses_source_paper_and_description_file(tmp_path):
    description = tmp_path / "description.md"
    description.write_text("A contrastive learning method.")

    args = cli.build_parser().parse_args(
        [
            "method",
            "add",
            "simclr",
            "--name",
            "SimCLR",
            "--full-name",
            "Simple Framework for Contrastive Learning (SimCLR)",
            "--description-file",
            str(description),
            "--keywords",
            "SimCLR, contrastive learning",
            "--area",
            "Vision",
            "--introduced-year",
            "2020",
            "--source-paper",
            "2002.05709",
            "--source-title",
            "A Simple Framework for Contrastive Learning of Visual Representations",
            "--json",
        ]
    )

    assert args.handler is cli.add_method
    assert args.slug == "simclr"
    assert args.source_paper == "2002.05709"
    assert args.description_file == description
    assert args.introduced_year == 2020
    assert args.json


def test_add_or_update_method_is_idempotent_and_links_source_paper():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(
        engine,
        "connect",
        lambda connection, _record: connection.create_function(
            "jsonb_typeof", 1, lambda _value: "array"
        ),
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as db:
        db.add(Area(name="Vision"))
        db.add(
            Paper(
                title="A Simple Framework for Contrastive Learning",
                abstract="Source paper.",
                arxiv_id="2002.05709",
                version="v3",
                is_latest_version=True,
                date_published=date(2020, 2, 13),
            )
        )
        db.commit()

        inputs = {
            "slug": "simclr",
            "name": "SimCLR",
            "full_name": "Simple Contrastive Learning (SimCLR)",
            "description": "A contrastive learning framework.",
            "keywords": "SimCLR, contrastive learning",
            "area_name": "Vision",
            "introduced_year": 2020,
            "source_paper": "2002.05709",
            "source_title": "A Simple Framework for Contrastive Learning",
        }
        created = add_or_update_method(db, **inputs)
        updated = add_or_update_method(db, **inputs)

        method = db.execute(select(Method).where(Method.slug == "simclr")).scalar_one()
        link_count = db.scalar(
            select(func.count())
            .select_from(PaperMethod)
            .where(PaperMethod.method_id == method.id)
        )

    assert created.status == "created"
    assert created.source_link_status == "created"
    assert updated.status == "updated"
    assert updated.source_link_status == "existing"
    assert method.source_url is None
    assert link_count == 1
