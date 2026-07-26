#!/usr/bin/env python3
"""Create least-privilege staging and backup roles, then isolate staging state."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key] = value.strip().strip("'\"")
    return result


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def psql(database: str, sql: str) -> None:
    subprocess.run(
        [
            "runuser",
            "--user",
            "postgres",
            "--",
            "psql",
            "--no-psqlrc",
            "--set",
            "ON_ERROR_STOP=1",
            "--dbname",
            database,
        ],
        input=sql,
        text=True,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--staging-env",
        type=Path,
        default=Path("/etc/paperswithcode/staging.env"),
    )
    parser.add_argument(
        "--cron-env",
        type=Path,
        default=Path("/etc/paperswithcode/production-cron.env"),
    )
    parser.add_argument("--roles-only", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo")
    staging = read_env(args.staging_env)
    cron = read_env(args.cron_env)
    database = staging["PWC_DB_NAME"]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database):
        parser.error("invalid database name")

    role_sql = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        CREATE ROLE pwc_staging LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_backup') THEN
        CREATE ROLE pwc_backup LOGIN;
    END IF;
END $$;
ALTER ROLE pwc_staging PASSWORD {sql_literal(staging["PWC_DB_PASSWORD"])};
ALTER ROLE pwc_backup PASSWORD
    {sql_literal(cron["PWC_POSTGRES_BACKUP_DB_PASSWORD"])};
GRANT CONNECT ON DATABASE {database} TO pwc_staging, pwc_backup;
GRANT pg_read_all_data TO pwc_backup;
    """
    psql(database, role_sql)
    if args.roles_only:
        print("configured staging and backup PostgreSQL roles")
        return 0
    migration = (
        Path(__file__).resolve().parents[1]
        / "backend/database/migrations/consolidate_staging_schema.sql"
    )
    psql(database, migration.read_text(encoding="utf-8"))
    print("configured staging and backup PostgreSQL roles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
