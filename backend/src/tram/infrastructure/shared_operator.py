"""One operator account that every installation shares, so the team can always sign in.

The team chose to keep this credential in the repository (local stack only): the
password is written down in docs/DOCKER_STACK.md and only its argon2 hash lives in code.
The Docker stack publishes the API on 127.0.0.1 only; replace or remove this account
before any public deployment. Migration 0006 creates it; ``ensure_shared_operator``
(run by scripts/bootstrap-operator.py on every stack start) restores it if it was
deleted, demoted, disabled or given another password.
"""

from uuid import uuid4

from sqlalchemy import select

from tram.infrastructure.database import UserRow

USERNAME = "operator"
PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$6VTe8AWzqOGfq+pfK+TYrQ$FF+IC78DyTy2V9UVBNGunzZROQDLk9FotnsiEhzhcEY"


def ensure_shared_operator(sessions, now) -> str:
    """Create the account or put it back to the shared state; report what happened."""
    with sessions.begin() as session:
        row = session.scalar(select(UserRow).where(UserRow.username == USERNAME))
        if row is None:
            session.add(
                UserRow(
                    id=str(uuid4()),
                    username=USERNAME,
                    password_hash=PASSWORD_HASH,
                    role="operator",
                    is_active=True,
                    created_at=now,
                )
            )
            return "created"
        if (row.password_hash, row.role, bool(row.is_active)) == (PASSWORD_HASH, "operator", True):
            return "unchanged"
        row.password_hash, row.role, row.is_active = PASSWORD_HASH, "operator", True
        return "restored"
