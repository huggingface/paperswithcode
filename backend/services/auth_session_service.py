"""Server-side browser sessions, so logout revokes copied session tokens.

Every session cookie the production authority issues carries a random ``sid``
backed by an ``auth_sessions`` row. A token is accepted only while its row is
unrevoked and unexpired, so logging out (or signing out everywhere) also
invalidates any copy of the cookie taken earlier.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from backend.models.database import AuthSession

# Expired rows are kept for a day so a just-expired cookie still reads as
# expired rather than unknown in logs; afterwards logins purge them.
EXPIRED_ROW_RETENTION = timedelta(days=1)


def create_session(db: Session, hf_subject: str, *, ttl_seconds: int) -> str:
    """Record a new session for ``hf_subject`` and return its id."""

    now = datetime.now(UTC)
    db.execute(
        delete(AuthSession).where(AuthSession.expires_at < now - EXPIRED_ROW_RETENTION)
    )
    session_id = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            id=session_id,
            hf_subject=hf_subject,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
    )
    db.commit()
    return session_id


def session_is_active(db: Session, session_id: str, hf_subject: object) -> bool:
    row = db.get(AuthSession, session_id)
    return (
        row is not None
        and row.hf_subject == hf_subject
        and row.revoked_at is None
        and row.expires_at > datetime.now(UTC)
    )


def revoke_sessions(db: Session, session_ids: set[str]) -> None:
    if not session_ids:
        return
    db.execute(
        update(AuthSession)
        .where(AuthSession.id.in_(session_ids), AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    db.commit()


def revoke_all_sessions(db: Session, hf_subject: str) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.hf_subject == hf_subject, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    db.commit()
