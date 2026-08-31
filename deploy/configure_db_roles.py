#!/usr/bin/env python3
"""Create least-privilege runtime roles, then isolate staging state."""

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


def trending_role_sql(*, database: str, password: str) -> str:
    """Return the fail-closed capability boundary for repairable scoring jobs."""
    return f"""
DO $$
DECLARE
    granted_role text;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'pwc_cron_trending'
    ) THEN
        CREATE ROLE pwc_cron_trending LOGIN NOINHERIT;
    END IF;
    FOR granted_role IN
        SELECT quote_ident(parent.rolname)
          FROM pg_auth_members membership
          JOIN pg_roles member ON member.oid = membership.member
          JOIN pg_roles parent ON parent.oid = membership.roleid
         WHERE member.rolname = 'pwc_cron_trending'
    LOOP
        EXECUTE 'REVOKE ' || granted_role || ' FROM pwc_cron_trending';
    END LOOP;
END $$;
ALTER ROLE pwc_cron_trending WITH
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION;
ALTER ROLE pwc_cron_trending PASSWORD {sql_literal(password)};
ALTER ROLE pwc_cron_trending SET search_path = public;
ALTER ROLE pwc_cron_trending SET statement_timeout = '45min';
REVOKE pg_read_all_data, pg_write_all_data FROM pwc_cron_trending;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM pwc_cron_trending;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM pwc_cron_trending;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM pwc_cron_trending;
REVOKE ALL ON SCHEMA public FROM pwc_cron_trending;
REVOKE CREATE ON SCHEMA public FROM pwc_cron_trending;
GRANT CONNECT ON DATABASE {database} TO pwc_cron_trending;
GRANT USAGE ON SCHEMA public TO pwc_cron_trending;
GRANT SELECT ON papers, paper_repositories, repositories, repository_star_history, paper_hf_artifacts, hf_artifacts TO pwc_cron_trending;
GRANT UPDATE (trending_score, trending_score_updated_at, updated_at) ON repositories TO pwc_cron_trending;
GRANT UPDATE (trending_score, github_trending_component, hf_trending_component, trending_score_updated_at, updated_at) ON papers TO pwc_cron_trending;

DO $$
DECLARE
    taxonomy_table text;
    prohibited_privilege text;
BEGIN
    IF EXISTS (
        SELECT 1
          FROM pg_auth_members membership
          JOIN pg_roles member ON member.oid = membership.member
         WHERE member.rolname = 'pwc_cron_trending'
    ) THEN
        RAISE EXCEPTION 'trending role retains a role membership';
    END IF;
    IF has_schema_privilege('pwc_cron_trending', 'public', 'CREATE') THEN
        RAISE EXCEPTION 'trending role can create schema objects';
    END IF;
    FOREACH taxonomy_table IN ARRAY ARRAY[
        'tasks', 'methods', 'datasets', 'metrics', 'conferences'
    ] LOOP
        FOREACH prohibited_privilege IN ARRAY ARRAY[
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
            'REFERENCES', 'TRIGGER'
        ] LOOP
            IF has_table_privilege(
                'pwc_cron_trending', taxonomy_table, prohibited_privilege
            ) THEN
                RAISE EXCEPTION 'trending role can % taxonomy table %',
                    prohibited_privilege, taxonomy_table;
            END IF;
        END LOOP;
    END LOOP;
    FOREACH taxonomy_table IN ARRAY ARRAY['papers', 'repositories'] LOOP
        FOREACH prohibited_privilege IN ARRAY ARRAY[
            'INSERT', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'
        ] LOOP
            IF has_table_privilege(
                'pwc_cron_trending', taxonomy_table, prohibited_privilege
            ) THEN
                RAISE EXCEPTION 'trending role can % scoring table %',
                    prohibited_privilege, taxonomy_table;
            END IF;
        END LOOP;
    END LOOP;
    IF EXISTS (
        SELECT 1
          FROM pg_attribute attribute
          JOIN pg_class relation ON relation.oid = attribute.attrelid
          JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = 'public'
           AND attribute.attnum > 0
           AND NOT attribute.attisdropped
           AND relation.relname IN ('papers', 'repositories')
           AND has_column_privilege(
               'pwc_cron_trending', relation.oid, attribute.attnum, 'UPDATE'
           )
           AND NOT (
               relation.relname = 'repositories'
               AND attribute.attname IN (
                   'trending_score', 'trending_score_updated_at', 'updated_at'
               )
           )
           AND NOT (
               relation.relname = 'papers'
               AND attribute.attname IN (
                   'trending_score', 'github_trending_component',
                   'hf_trending_component', 'trending_score_updated_at',
                   'updated_at'
               )
           )
    ) THEN
        RAISE EXCEPTION 'trending role can update a prohibited scoring column';
    END IF;
END $$;
"""


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
    parser.add_argument(
        "--trending-env",
        type=Path,
        default=Path("/etc/paperswithcode/trending-cron.env"),
    )
    parser.add_argument("--roles-only", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo")
    staging = read_env(args.staging_env)
    cron = read_env(args.cron_env)
    trending = read_env(args.trending_env)
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
    role_sql += trending_role_sql(
        database=database,
        password=trending["PWC_TRENDING_DB_PASSWORD"],
    )
    psql(database, role_sql)
    if args.roles_only:
        print("configured staging, backup, and trending PostgreSQL roles")
        return 0
    migration = (
        Path(__file__).resolve().parents[1]
        / "backend/database/migrations/consolidate_staging_schema.sql"
    )
    psql(database, migration.read_text(encoding="utf-8"))
    print("configured staging, backup, and trending PostgreSQL roles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
