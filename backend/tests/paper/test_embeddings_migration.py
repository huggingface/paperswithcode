"""Optional isolated PostgreSQL+pgvector integration checks.

Set ``TEST_PGVECTOR_DATABASE_URL`` to a disposable database. The test refuses
the configured application database and never creates/drops production data.
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.config import get_settings


@pytest.fixture(scope="module")
def pgvector_engine():
    url = os.getenv("TEST_PGVECTOR_DATABASE_URL")
    if not url:
        pytest.skip("TEST_PGVECTOR_DATABASE_URL is not configured")
    if make_url(url).database == get_settings().db_name:
        pytest.fail("Refusing to run pgvector migration test against the app database")
    engine = create_engine(url)
    with engine.begin() as connection:
        available = connection.execute(
            text("SELECT 1 FROM pg_available_extensions WHERE name='vector'")
        ).scalar_one_or_none()
        if not available:
            pytest.skip("Disposable PostgreSQL does not provide pgvector")
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS papers (id bigserial PRIMARY KEY)"
        )
        migration = (
            Path(__file__).parents[2] / "database/migrations/add_paper_embeddings.sql"
        ).read_text(encoding="utf-8")
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute(migration)
            cursor.execute(migration)
    yield engine
    engine.dispose()


def test_generation_partition_dimension_and_cosine_index(pgvector_engine):
    with pgvector_engine.begin() as connection:
        generation_id = connection.execute(
            text(
                """INSERT INTO paper_embedding_generations
                   (model_name, model_revision, dimensions, input_format_version,
                    query_instruction_version, bucket_run_uri, status)
                   VALUES ('test/model', 'revision', 32, 'title-abstract-v1',
                           'query-v1', 'file:///tmp/test', 'loading') RETURNING id"""
            )
        ).scalar_one()
        connection.execute(
            text("SELECT create_paper_embedding_partition(:id, 32)"),
            {"id": generation_id},
        )
        connection.exec_driver_sql(
            f"""CREATE INDEX idx_paper_embeddings_g{generation_id}_hnsw_cosine
                ON paper_embeddings_g{generation_id}
                USING hnsw ((embedding::halfvec(32)) halfvec_cosine_ops)"""
        )
        paper_id = -int(generation_id)
        connection.execute(
            text("INSERT INTO papers (id) VALUES (:id)"), {"id": paper_id}
        )
        connection.execute(
            text(
                """INSERT INTO paper_embeddings
                   (generation_id, paper_id, content_hash, embedding)
                   VALUES (:generation_id, :paper_id, :hash,
                     ('[' || '1,' || repeat('0,', 30) || '0]')::halfvec)"""
            ),
            {"generation_id": generation_id, "paper_id": paper_id, "hash": "a" * 64},
        )
        distance = connection.execute(
            text(
                """SELECT embedding::halfvec(32) <=>
                     ('[' || '0.9,0.1,' || repeat('0,', 29) || '0]')::halfvec(32)
                   FROM paper_embeddings WHERE generation_id=:id"""
            ),
            {"id": generation_id},
        ).scalar_one()
        assert 0 <= distance < 0.02
        index_valid = connection.execute(
            text(
                """SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
                   WHERE c.relname=:name"""
            ),
            {"name": f"idx_paper_embeddings_g{generation_id}_hnsw_cosine"},
        ).scalar_one()
        assert index_valid
