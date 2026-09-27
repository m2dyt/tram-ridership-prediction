import hashlib
import secrets
from datetime import datetime, timedelta
from uuid import uuid4

from tram.application.errors import ApplicationError
from tram.application.ports import (
    Clock,
    LoginAttemptStore,
    PasswordHasher,
    SessionStore,
    TokenIssuer,
    UserRepository,
)

LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW_SECONDS = 15 * 60


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        sessions: SessionStore,
        attempts: LoginAttemptStore,
        hasher: PasswordHasher,
        issuer: TokenIssuer,
        clock: Clock,
        access_ttl: int,
        refresh_ttl: int,
    ):
        self.users = users
        self.sessions = sessions
        self.attempts = attempts
        self.hasher = hasher
        self.issuer = issuer
        self.clock = clock
        self.access_ttl = access_ttl
        self.refresh_ttl = refresh_ttl

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def register(self, username: str, password: str) -> dict:
        return self._create_user(username, password, "viewer")

    def create_operator(self, username: str, password: str) -> dict:
        return self._create_user(username, password, "operator")

    def _create_user(self, username: str, password: str, role: str) -> dict:
        user_id = str(uuid4())
        hashed = self.hasher.hash(password)
        try:
            self.users.create(user_id, username, hashed, role)
        except ValueError as exc:
            raise ApplicationError("VALIDATION_ERROR", "Username already exists") from exc
        return {"id": user_id}

    def login(
        self, username: str, password: str, client_ip: str
    ) -> tuple[str, datetime, str, dict]:
        now = self.clock.now()
        retry_after = self.attempts.begin_attempt(
            username, client_ip, now, LOGIN_ATTEMPT_LIMIT, LOGIN_ATTEMPT_WINDOW_SECONDS
        )
        if retry_after is not None:
            raise ApplicationError(
                "RATE_LIMITED", "Too many login attempts", retry_after=retry_after
            )

        user = self.users.get_by_username(username)
        if not user or not user.get("is_active"):
            raise ApplicationError("UNAUTHORIZED", "Invalid credentials")

        if not self.hasher.verify(user["password_hash"], password):
            raise ApplicationError("UNAUTHORIZED", "Invalid credentials")

        self.attempts.clear(username, client_ip)
        access_token, access_exp = self.issuer.issue_access_token(
            user["id"], user["role"], now, self.access_ttl
        )
        refresh_token = secrets.token_urlsafe(32)
        refresh_hash = self._hash_token(refresh_token)
        expires_at = now + timedelta(seconds=self.refresh_ttl)

        self.sessions.create_session(user["id"], refresh_hash, now, expires_at)
        return access_token, access_exp, refresh_token, user

    def refresh(self, refresh_token: str) -> tuple[str, datetime, str, dict]:
        now = self.clock.now()
        old_hash = self._hash_token(refresh_token)

        new_refresh_token = secrets.token_urlsafe(32)
        new_refresh_hash = self._hash_token(new_refresh_token)
        expires_at = now + timedelta(seconds=self.refresh_ttl)

        session = self.sessions.rotate_session(old_hash, new_refresh_hash, now, expires_at)
        if not session:
            raise ApplicationError("UNAUTHORIZED", "Invalid or expired session")

        user = self.users.get_by_id(session["user_id"])
        if not user or not user.get("is_active"):
            raise ApplicationError("UNAUTHORIZED", "User deactivated")

        access_token, access_exp = self.issuer.issue_access_token(
            user["id"], user["role"], now, self.access_ttl
        )
        # Mirrors login(): the caller already re-read the user row above, so the
        # role/identity returned here is guaranteed to match the freshly issued
        # access token, not a stale value cached by the client.
        return access_token, access_exp, new_refresh_token, user

    def logout(self, refresh_token: str | None, everywhere: bool = False) -> None:
        if not refresh_token:
            return

        now = self.clock.now()
        token_hash = self._hash_token(refresh_token)

        if everywhere:
            session = self.sessions.get_session(token_hash, now)
            if session:
                self.sessions.revoke_all_sessions(session["user_id"], now)
        else:
            self.sessions.revoke_session(token_hash, now)

    def me(self, user_id: str) -> dict:
        user = self.users.get_by_id(user_id)
        if not user or not user.get("is_active"):
            raise ApplicationError("UNAUTHORIZED", "User not found or deactivated")
        return {key: user[key] for key in ("id", "username", "role")}
