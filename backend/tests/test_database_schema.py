from sqlalchemy import create_mock_engine
from sqlalchemy.dialects import postgresql

from backend.models.database import Base, PaperCurationJob, PaperCurationWorkflow


def test_paper_curation_cycle_can_be_dropped_on_postgresql():
    """Cyclic curation foreign keys must be removable by the CI schema teardown."""
    statements = []
    engine = create_mock_engine(
        "postgresql://",
        lambda sql, *_multiparams, **_params: statements.append(
            str(sql.compile(dialect=postgresql.dialect()))
        ),
    )

    Base.metadata.drop_all(
        engine,
        tables=[PaperCurationJob.__table__, PaperCurationWorkflow.__table__],
        checkfirst=False,
    )

    dropped_constraints = {
        statement.rsplit(" ", 1)[-1]
        for statement in statements
        if "DROP CONSTRAINT" in statement
    }
    assert dropped_constraints == {
        "fk_paper_curation_jobs_parent_workflow",
        "fk_paper_curation_workflows_enrich_satisfied_by_job",
        "fk_paper_curation_workflows_evals_satisfied_by_job",
    }


def test_server_defaults_avoid_postgresql_only_casts():
    """SQLite-backed tests create these tables, so defaults must stay portable."""
    casts = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.server_default is not None
        and "::" in str(getattr(column.server_default, "arg", ""))
    ]

    assert casts == []
