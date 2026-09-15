"""Small durable outreach ledger, independent of application releases."""

import json
import sqlite3
from pathlib import Path


class OutreachState:
    def __init__(self, path: Path, *, dry_run: bool = False):
        if dry_run:
            self.db = sqlite3.connect(":memory:")
            if path.exists():
                source = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
                source.backup(self.db)
                source.close()
        else:
            self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self.db.commit()

    def get(self, key: str) -> dict:
        row = self.db.execute(
            "SELECT value FROM state WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else {}

    def put(self, key: str, value: dict) -> None:
        self.db.execute(
            "INSERT INTO state VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, sort_keys=True)),
        )
        self.db.commit()

    def pending(self) -> list[tuple[str, dict]]:
        return [
            (key, json.loads(value))
            for key, value in self.db.execute(
                "SELECT key, value FROM state WHERE key LIKE 'repo:%'"
            )
            if json.loads(value).get("pending")
        ]

    def close(self) -> None:
        self.db.close()
