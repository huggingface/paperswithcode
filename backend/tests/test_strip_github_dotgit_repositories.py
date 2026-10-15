from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.database.migrations.strip_github_dotgit_repositories import (
    strip_dotgit_repositories,
)

SCHEMA = """
CREATE TABLE repositories (
    id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL, owner TEXT, name TEXT,
    num_stars INTEGER DEFAULT 0, num_stars_updated_at TIMESTAMP
);
CREATE TABLE paper_repositories (
    paper_id INTEGER, repository_id INTEGER, is_official BOOLEAN,
    PRIMARY KEY (paper_id, repository_id)
);
CREATE TABLE repository_star_history (
    id INTEGER PRIMARY KEY, repository_id INTEGER, num_stars INTEGER,
    snapshot_at TIMESTAMP, UNIQUE (repository_id, snapshot_at)
);
CREATE TABLE frameworks (id INTEGER PRIMARY KEY, repository_id INTEGER);
CREATE TABLE task_recommended_frameworks (
    task_id INTEGER, repository_id INTEGER, PRIMARY KEY (task_id, repository_id)
);
INSERT INTO repositories VALUES
    (1, 'https://github.com/wuzimeng/comp.git', 'wuzimeng', 'comp.git', 0, '2026-10-15'),
    (2, 'https://github.com/wuzimeng/comp', 'wuzimeng', 'comp', 2, '2026-10-15'),
    (3, 'https://github.com/YU-deep/MACT.git', 'YU-deep', 'MACT.git', 0, '2026-10-15'),
    (4, 'https://github.com/other/repo', 'other', 'repo', 7, '2026-10-15');
INSERT INTO paper_repositories VALUES (10, 1, 1), (10, 2, 0), (11, 1, 1), (12, 3, 1);
INSERT INTO repository_star_history VALUES
    (1, 1, 0, '2026-10-14'), (2, 2, 2, '2026-10-14'),
    (3, 3, 0, '2026-10-14'), (4, 3, 5, '2026-10-13');
INSERT INTO frameworks VALUES (1, 1);
INSERT INTO task_recommended_frameworks VALUES (20, 1), (20, 2), (21, 1);
"""


def _session() -> Session:
    session = Session(create_engine("sqlite:///:memory:"))
    for statement in SCHEMA.split(";"):
        if statement.strip():
            session.execute(text(statement))
    session.commit()
    return session


def _rows(session, sql):
    return [tuple(row) for row in session.execute(text(sql))]


def test_dry_run_reports_plan_without_writing():
    session = _session()

    stats = strip_dotgit_repositories(session)

    assert stats == {"rows": 2, "merged": 1, "renamed": 1, "skipped": 0}
    assert _rows(session, "SELECT COUNT(*) FROM repositories") == [(4,)]


def test_apply_merges_into_existing_row_and_renames_the_rest():
    session = _session()

    strip_dotgit_repositories(session, apply=True)

    assert _rows(
        session,
        "SELECT id, url, owner, name, num_stars, num_stars_updated_at "
        "FROM repositories ORDER BY id",
    ) == [
        (2, "https://github.com/wuzimeng/comp", "wuzimeng", "comp", 2, "2026-10-15"),
        (3, "https://github.com/yu-deep/mact", "yu-deep", "mact", 0, None),
        (4, "https://github.com/other/repo", "other", "repo", 7, "2026-10-15"),
    ]
    assert _rows(
        session,
        "SELECT paper_id, repository_id, is_official FROM paper_repositories "
        "ORDER BY paper_id",
    ) == [(10, 2, 1), (11, 2, 1), (12, 3, 1)]
    assert _rows(
        session,
        "SELECT repository_id, num_stars FROM repository_star_history ORDER BY id",
    ) == [(2, 2), (3, 5)]
    assert _rows(session, "SELECT repository_id FROM frameworks") == [(2,)]
    assert _rows(
        session,
        "SELECT task_id, repository_id FROM task_recommended_frameworks "
        "ORDER BY task_id",
    ) == [(20, 2), (21, 2)]
