"""Atomic login attempt counters shared by API processes."""

import hashlib
import hmac
import math
from datetime import datetime, timedelta

from sqlalchemy import case, delete, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from tram.infrastructure.database import LoginAttemptRow


class SqlLoginAttemptStore:
    def __init__(self, session_factory, key_secret: str):
        self.session_factory = session_factory
        self.key_secret = key_secret.encode("utf-8")

    def _key(self, username: str, client_ip: str) -> str:
        identity = username.encode("utf-8") + b"\0" + client_ip.encode("utf-8")
        return hmac.new(self.key_secret, identity, hashlib.sha256).hexdigest()

    def begin_attempt(
        self, username: str, client_ip: str, now: datetime, limit: int, window_seconds: int
    ) -> int | None:
        key = self._key(username, client_ip)
        cutoff = now - timedelta(seconds=window_seconds)
        with self.session_factory.begin() as session:
            session.execute(
                delete(LoginAttemptRow).where(LoginAttemptRow.window_started_at <= cutoff)
            )
            insert = sqlite_insert if session.bind.dialect.name == "sqlite" else postgres_insert
            session.execute(
                insert(LoginAttemptRow)
                .values(key=key, attempts=0, window_started_at=now)
                .on_conflict_do_nothing(index_elements=[LoginAttemptRow.key])
            )
            session.execute(
                update(LoginAttemptRow)
                .where(LoginAttemptRow.key == key)
                .values(
                    attempts=case(
                        (LoginAttemptRow.attempts >= limit, limit + 1),
                        else_=LoginAttemptRow.attempts + 1,
                    ),
                )
            )
            attempts, started_at = session.execute(
                select(LoginAttemptRow.attempts, LoginAttemptRow.window_started_at).where(
                    LoginAttemptRow.key == key
                )
            ).one()

        if attempts <= limit:
            return None
        return max(
            1, math.ceil((started_at + timedelta(seconds=window_seconds) - now).total_seconds())
        )

    def clear(self, username: str, client_ip: str) -> None:
        with self.session_factory.begin() as session:
            session.execute(
                delete(LoginAttemptRow).where(LoginAttemptRow.key == self._key(username, client_ip))
            )
