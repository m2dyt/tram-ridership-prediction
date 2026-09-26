from datetime import datetime, UTC
import jwt
from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from tram.application.ports import Document
from tram.infrastructure.database import UserRow, RefreshTokenRow


class SqlUserRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def get_by_username(self, username: str) -> Document | None:
        with self.session_factory() as session:
            stmt = select(UserRow).where(UserRow.username == username)
            user = session.scalars(stmt).first()
            if not user:
                return None
            return {
                "id": user.id,
                "username": user.username,
                "password_hash": user.password_hash,
                "role": user.role,
                "is_active": bool(user.is_active),
                "created_at": user.created_at,
            }

    def get_by_id(self, user_id: str) -> Document | None:
        with self.session_factory() as session:
            stmt = select(UserRow).where(UserRow.id == user_id)
            user = session.scalars(stmt).first()
            if not user:
                return None
            return {
                "id": user.id,
                "username": user.username,
                "password_hash": user.password_hash,
                "role": user.role,
                "is_active": bool(user.is_active),
                "created_at": user.created_at,
            }


class Argon2PasswordHasher:
    def __init__(self):
        self.ph = Argon2Hasher()

    def hash(self, plain: str) -> str:
        return self.ph.hash(plain)

    def verify(self, hashed: str, plain: str) -> bool:
        try:
            return self.ph.verify(hashed, plain)
        except VerifyMismatchError:
            return False


class JwtTokenIssuer:
    def __init__(self, secret: str):
        self.secret = secret

    def issue_access_token(self, user_id: str, role: str, now: datetime, ttl_seconds: int) -> tuple[str, datetime]:
        import time
        expires_at = now.timestamp() + ttl_seconds
        payload = {
            "sub": user_id,
            "role": role,
            "iat": int(now.timestamp()),
            "exp": int(expires_at),
        }
        token = jwt.encode(payload, self.secret, algorithm="HS256")
        # now + timedelta can be computed, but we return datetime from the timestamp to avoid microsecond issues
        return token, datetime.fromtimestamp(expires_at, tz=UTC)


class SqlSessionStore:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def create_session(self, user_id: str, token_hash: str, now: datetime, expires_at: datetime) -> None:
        import uuid
        with self.session_factory() as session:
            row = RefreshTokenRow(
                id=str(uuid.uuid4()),
                user_id=user_id,
                token_hash=token_hash,
                issued_at=now,
                expires_at=expires_at,
                revoked_at=None,
                replaced_by=None,
            )
            session.add(row)
            session.commit()

    def get_session(self, token_hash: str, now: datetime) -> Document | None:
        with self.session_factory() as session:
            stmt = select(RefreshTokenRow).where(
                RefreshTokenRow.token_hash == token_hash,
                RefreshTokenRow.revoked_at.is_(None),
                RefreshTokenRow.expires_at > now
            )
            row = session.scalars(stmt).first()
            if not row:
                return None
            return {
                "id": row.id,
                "user_id": row.user_id,
                "token_hash": row.token_hash,
                "expires_at": row.expires_at,
            }

    def rotate_session(self, old_hash: str, new_hash: str, now: datetime, expires_at: datetime) -> Document | None:
        import uuid
        with self.session_factory() as session:
            stmt = select(RefreshTokenRow).where(
                RefreshTokenRow.token_hash == old_hash,
                RefreshTokenRow.revoked_at.is_(None),
                RefreshTokenRow.expires_at > now
            )
            old_row = session.scalars(stmt).first()
            if not old_row:
                return None
            
            old_row.revoked_at = now
            
            new_id = str(uuid.uuid4())
            old_row.replaced_by = new_id
            
            new_row = RefreshTokenRow(
                id=new_id,
                user_id=old_row.user_id,
                token_hash=new_hash,
                issued_at=now,
                expires_at=expires_at,
                revoked_at=None,
                replaced_by=None,
            )
            session.add(new_row)
            session.commit()
            
            return {
                "id": new_id,
                "user_id": new_row.user_id,
                "token_hash": new_row.token_hash,
                "expires_at": new_row.expires_at,
            }

    def revoke_session(self, token_hash: str, now: datetime) -> bool:
        with self.session_factory() as session:
            stmt = select(RefreshTokenRow).where(
                RefreshTokenRow.token_hash == token_hash,
                RefreshTokenRow.revoked_at.is_(None)
            )
            row = session.scalars(stmt).first()
            if not row:
                return False
            row.revoked_at = now
            session.commit()
            return True

    def revoke_all_sessions(self, user_id: str, now: datetime) -> None:
        with self.session_factory() as session:
            stmt = update(RefreshTokenRow).where(
                RefreshTokenRow.user_id == user_id,
                RefreshTokenRow.revoked_at.is_(None)
            ).values(revoked_at=now)
            session.execute(stmt)
            session.commit()
