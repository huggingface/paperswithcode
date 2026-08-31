"""
SQLAlchemy database connection and session management.

This module provides SQLAlchemy integration for the FastAPI backend,
building on top of the existing psycopg2-based database utilities.
"""

from typing import Generator

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from backend.config import get_settings
from backend.models.database import Base


def database_pool_configuration(settings) -> dict[str, int]:
    if settings.environment == "staging":
        return {"pool_size": 32, "max_overflow": 8, "pool_timeout": 5}
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
                # qualification while remaining bounded below `max_connections`.
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

    def drop_tables(self):
        """Drop all database tables (use with caution!)."""
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


def drop_tables():
    """Drop all database tables."""
    db_manager.drop_tables()


# Utility functions for testing and development


def reset_database():
    """Reset the database (drop and recreate all tables)."""
    print("⚠️  Resetting database...")
    drop_tables()
    create_tables()
    print("✅ Database reset complete")


def init_database():
    """Initialize the database (create tables if they don't exist)."""
    print("🔧 Initializing database...")
    create_tables()
    print("✅ Database initialized")


if __name__ == "__main__":
    # For testing the database connection
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "init":
            init_database()
        elif command == "reset":
            reset_database()
        elif command == "test":
            print("🔍 Testing database connection...")
            try:
                from sqlalchemy import text

                engine = get_engine()
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT 1"))
                    print("✅ Database connection successful!")
            except Exception as e:
                print(f"❌ Database connection failed: {e}")
        else:
            print("Usage: python -m backend.database.connection [init|reset|test]")
    else:
        print("Database connection module")
        print("Available commands: init, reset, test")
