"""
SQLAlchemy database connection and session management.

This module provides SQLAlchemy integration for the FastAPI backend,
building on top of the existing psycopg2-based database utilities.
"""

import argparse
import os
from typing import Generator

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from backend.config import get_settings
from backend.models.database import Base

LIVE_ENVIRONMENTS = {"production", "staging"}


class DestructiveDatabaseOperationRefused(RuntimeError):
    """Raised when dropping tables is not explicitly aimed at a disposable DB."""


def drop_refusal_reason(settings, confirm_database: str | None) -> str | None:
    """Explain why dropping every table must be refused, or return None.

    Dropping is allowed only outside production and staging, and only when the
    caller names the configured database, so a stray default or a production
    ``keys.env`` cannot silently wipe the live catalog.
    """
    environment = settings.environment.lower()
    if environment in LIVE_ENVIRONMENTS:
        return f"PWC_ENVIRONMENT={environment} names a live environment"
    if confirm_database != settings.db_name:
        return (
            f"confirmation {confirm_database!r} does not match the configured "
            f"database {settings.db_name!r}"
        )
    return None


def database_pool_configuration(settings) -> dict[str, int]:
    if settings.environment == "staging":
        worker_count = max(1, int(os.environ.get("WEB_CONCURRENCY", "1")))
        return {
            "pool_size": max(1, 32 // worker_count),
            "max_overflow": 8 // worker_count,
            "pool_timeout": 5,
        }
    return {"pool_size": 5, "max_overflow": 10, "pool_timeout": 5}


class DatabaseManager:
    """
    Database manager for SQLAlchemy integration.
    """

    def __init__(self):
        self.settings = get_settings()
        self._engine: Engine = None
        self._session_local: sessionmaker = None

    @property
    def engine(self) -> Engine:
        """Get the SQLAlchemy engine."""
        if self._engine is None:
            options = f"-c search_path={self.settings.db_search_path}"
            # The staging role defaults to read-only for every ad hoc login.
            # The application explicitly opts its connections into read/write
            # transactions; PostgreSQL privileges still limit those writes to
            # the staging-owned schema.
            if self.settings.environment == "staging":
                options += " -c default_transaction_read_only=off"
            pool_configuration = database_pool_configuration(self.settings)
            self._engine = create_engine(
                self.settings.database_url,
                connect_args={"options": options},
                poolclass=QueuePool,
                # Production stays conservative because it shares Postgres with
                # CRON jobs. Staging is sized for the isolated 32-turn durability
                # qualification. Divide that aggregate budget across Uvicorn
                # workers so scaling the web tier cannot multiply connections.
                pool_size=pool_configuration["pool_size"],
                max_overflow=pool_configuration["max_overflow"],
                # Under burst traffic, fail DB checkout quickly so requests
                # release worker threads instead of sitting behind Cloudflare's
                # timeout window.
                pool_timeout=pool_configuration["pool_timeout"],
                pool_pre_ping=True,
                pool_recycle=300,
                echo=self.settings.is_development,  # Log SQL queries in development
            )
        return self._engine

    @property
    def session_local(self) -> sessionmaker:
        """Get the session factory."""
        if self._session_local is None:
            self._session_local = sessionmaker(
                autocommit=False, autoflush=False, bind=self.engine
            )
        return self._session_local

    def create_tables(self):
        """Create all database tables."""
        Base.metadata.create_all(bind=self.engine)

    def drop_tables(self, confirm_database: str | None = None):
        """Drop all tables; ``confirm_database`` must name a disposable DB."""
        reason = drop_refusal_reason(self.settings, confirm_database)
        if reason is not None:
            raise DestructiveDatabaseOperationRefused(
                f"Refusing to drop all tables in {self.settings.database_log_identifier}: "
                f"{reason}. Point PWC_DB_* at a disposable database outside "
                "production and staging and confirm it by name."
            )
        Base.metadata.drop_all(bind=self.engine)

    def get_session(self) -> Generator[Session, None, None]:
        """
        Get a database session.

        This is a generator function that yields a SQLAlchemy session
        and ensures proper cleanup.
        """
        session = self.session_local()
        try:
            yield session
        finally:
            session.close()


# Global database manager instance
db_manager = DatabaseManager()


def get_database_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency for getting database sessions.

    Usage in FastAPI endpoints:
    ```python
    @app.get("/papers/")
    def get_papers(db: Session = Depends(get_database_session)):
        return db.query(Paper).all()
    ```
    """
    yield from db_manager.get_session()


def get_engine() -> Engine:
    """Get the SQLAlchemy engine."""
    return db_manager.engine


def create_tables():
    """Create all database tables."""
    db_manager.create_tables()


def drop_tables(confirm_database: str | None = None):
    """Drop all tables; ``confirm_database`` must name a disposable DB."""
    db_manager.drop_tables(confirm_database)


# Utility functions for testing and development


def reset_database(confirm_database: str | None = None):
    """Drop and recreate all tables in a confirmed disposable database."""
    print("⚠️  Resetting database...")
    drop_tables(confirm_database)
    create_tables()
    print("✅ Database reset complete")


def init_database():
    """Initialize the database (create tables if they don't exist)."""
    print("🔧 Initializing database...")
    create_tables()
    print("✅ Database initialized")


def check_connection():
    """Check that the configured database accepts connections."""
    print("🔍 Testing database connection...")
    try:
        from sqlalchemy import text

        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            print("✅ Database connection successful!")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.database.connection",
        description="Initialize, reset, or test the configured database.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="Create tables that do not exist yet.")
    reset_parser = subparsers.add_parser(
        "reset",
        help="Drop and recreate every table (disposable databases only).",
    )
    reset_parser.add_argument(
        "--confirm",
        required=True,
        metavar="DATABASE",
        help="Name of the configured database (PWC_DB_NAME) to wipe.",
    )
    subparsers.add_parser("test", help="Check the database connection.")
    args = parser.parse_args(argv)

    if args.command == "init":
        init_database()
    elif args.command == "reset":
        try:
            reset_database(args.confirm)
        except DestructiveDatabaseOperationRefused as error:
            print(f"❌ {error}")
            return 1
    else:
        check_connection()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
