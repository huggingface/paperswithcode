import logging
import sqlite3
import sys
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).parents[3] / ".github" / "workflows"
if str(WORKFLOWS_DIR) not in sys.path:
    sys.path.append(str(WORKFLOWS_DIR))

from scripts.utils.hf_paper_importer import HuggingFacePaperImporterMixin  # noqa: E402


class _Importer(HuggingFacePaperImporterMixin):
    """The importer's author handling on SQLite, with psycopg-style queries."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.new_authors_count = 0
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE authors (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, hf_username TEXT,
                hf_id TEXT, hf_avatar_url TEXT, hf_status TEXT,
                hf_is_pro BOOLEAN DEFAULT 0, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE paper_authors (
                paper_id INTEGER, author_id INTEGER, author_order INTEGER,
                claimed BOOLEAN NOT NULL DEFAULT 0,
                PRIMARY KEY (paper_id, author_id)
            );
            """
        )

    def execute_query(self, query, params=()):
        cursor = self.db.execute(query.replace("%s", "?"), params)
        return [dict(row) for row in cursor.fetchall()]

    def links(self):
        return self.execute_query(
            "SELECT a.name, a.hf_username, pa.author_order, pa.claimed"
            " FROM paper_authors pa JOIN authors a ON a.id = pa.author_id"
            " ORDER BY pa.author_order"
        )


def _claim(name, username, hf_id, status="claimed_verified"):
    return {
        "name": name,
        "status": status,
        "hidden": False,
        "user": {"_id": hf_id, "user": username, "type": "user"},
    }


def test_claims_get_the_accounts_author_and_names_get_name_only_authors():
    importer = _Importer()
    importer.execute_query(
        "INSERT INTO authors (id, name, hf_username, hf_id)"
        " VALUES (1, 'Yuxuan Wang', 'billy', 'hf-billy')"
    )

    importer.process_authors(
        7,
        [
            {"name": "Yuxuan Wang"},
            _claim("Ada Lovelace", "ada", "hf-ada"),
            _claim("Grace Hopper", "grace", "hf-grace", status="extracted_pending"),
        ],
    )

    assert [
        (row["name"], row["hf_username"], row["author_order"], bool(row["claimed"]))
        for row in importer.links()
    ] == [
        ("Yuxuan Wang", None, 1, False),
        ("Ada Lovelace", "ada", 2, True),
        ("Grace Hopper", None, 3, False),
    ]


def test_reused_username_is_not_claimed_for_the_old_account():
    importer = _Importer()
    importer.execute_query(
        "INSERT INTO authors (id, name, hf_username, hf_id)"
        " VALUES (1, 'Weikun Wang', 'kunwww', 'hf-old-owner')"
    )

    importer.process_authors(7, [_claim("Someone Else", "kunwww", "hf-new-owner")])

    assert [
        (row["name"], row["hf_username"], bool(row["claimed"]))
        for row in importer.links()
    ] == [("Someone Else", None, False)]
