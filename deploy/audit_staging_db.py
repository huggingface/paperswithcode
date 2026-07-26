#!/usr/bin/env python3
"""Content-free privilege and name-resolution audit for the staging DB role."""

from __future__ import annotations

import os
import uuid

import psycopg2
from psycopg2 import errors


def main() -> int:
    connection = psycopg2.connect(
        host=os.environ["PWC_DB_HOST"],
        port=os.environ.get("PWC_DB_PORT", "5432"),
        dbname=os.environ["PWC_DB_NAME"],
        user=os.environ["PWC_DB_USER"],
        password=os.environ["PWC_DB_PASSWORD"],
        options="-c search_path=staging,public",
    )
    connection.autocommit = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ WRITE")
            cursor.execute(
                "SELECT current_user, current_setting('default_transaction_read_only')"
            )
            role, read_only_default = cursor.fetchone()
            if role != "pwc_staging" or read_only_default != "on":
                raise RuntimeError("staging role defaults are not enforced")

            cursor.execute("SELECT id FROM papers LIMIT 1")
            if cursor.fetchone() is None:
                raise RuntimeError("staging cannot read the live paper catalog")

            cursor.execute("SAVEPOINT catalog_write_probe")
            try:
                cursor.execute("UPDATE public.papers SET id = id WHERE false")
            except errors.InsufficientPrivilege:
                cursor.execute("ROLLBACK TO SAVEPOINT catalog_write_probe")
            else:
                raise RuntimeError("staging unexpectedly updated the public catalog")

            cursor.execute(
                "SELECT to_regclass('chat_sessions')::text, "
                "to_regclass('staging.chat_sessions')::text"
            )
            unqualified, qualified = cursor.fetchone()
            if unqualified != "chat_sessions" or qualified != "chat_sessions":
                raise RuntimeError("chat_sessions does not resolve through staging")

            session_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO staging.chat_sessions
                    (id, hf_user_id, hf_username, selected_model)
                VALUES (%s, 'privilege-audit', 'privilege-audit', 'audit-model')
                """,
                (session_id,),
            )
            cursor.execute(
                "UPDATE staging.chat_sessions SET title = 'audit' WHERE id = %s",
                (session_id,),
            )
            cursor.execute(
                "DELETE FROM staging.chat_sessions WHERE id = %s",
                (session_id,),
            )
        connection.rollback()
    finally:
        connection.close()
    print("staging database privilege audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
