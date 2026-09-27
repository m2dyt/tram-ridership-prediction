from datetime import UTC, datetime, timedelta

import pytest
from tram.application.auth import AuthService
from tram.application.errors import ApplicationError


class FakeUserRepository:
    def __init__(self, users):
        self._users = {u["id"]: u for u in users}
        self._by_username = {u["username"]: u for u in users}

    def get_by_username(self, username: str):
        return self._by_username.get(username)

    def get_by_id(self, user_id: str):
        return self._users.get(user_id)


class FakePasswordHasher:
    def verify(self, hashed: str, plain: str) -> bool:
        return hashed == f"hashed_{plain}"

    def hash(self, plain: str) -> str:
        return f"hashed_{plain}"


class FakeTokenIssuer:
    def issue_access_token(self, user_id: str, role: str, now: datetime, ttl_seconds: int):
        return f"access_token_for_{user_id}", now + timedelta(seconds=ttl_seconds)


class FakeSessionStore:
    def __init__(self):
        self.sessions = {}

    def create_session(self, user_id: str, token_hash: str, now: datetime, expires_at: datetime):
        self.sessions[token_hash] = {"user_id": user_id, "expires_at": expires_at}

    def get_session(self, token_hash: str, now: datetime):
        sess = self.sessions.get(token_hash)
        if sess and sess["expires_at"] > now:
            return sess
        return None

    def rotate_session(self, old_hash: str, new_hash: str, now: datetime, expires_at: datetime):
        sess = self.get_session(old_hash, now)
        if sess:
            del self.sessions[old_hash]
            self.sessions[new_hash] = {"user_id": sess["user_id"], "expires_at": expires_at}
            return sess
        return None

    def revoke_session(self, token_hash: str, now: datetime):
        if token_hash in self.sessions:
            del self.sessions[token_hash]
            return True
        return False

    def revoke_all_sessions(self, user_id: str, now: datetime):
        to_delete = [k for k, v in self.sessions.items() if v["user_id"] == user_id]
        for k in to_delete:
            del self.sessions[k]


class FakeLoginAttemptStore:
    def __init__(self):
        self.attempts = {}

    def begin_attempt(self, username, client_ip, now, limit, window_seconds):
        key = (username, client_ip)
        count, started_at = self.attempts.get(key, (0, now))
        if now >= started_at + timedelta(seconds=window_seconds):
            count, started_at = 0, now
        count += 1
        self.attempts[key] = (count, started_at)
        if count > limit:
            return int((started_at + timedelta(seconds=window_seconds) - now).total_seconds())
        return None

    def clear(self, username, client_ip):
        self.attempts.pop((username, client_ip), None)


class FakeClock:
    def __init__(self, now: datetime):
        self._now = now

    def now(self) -> datetime:
        return self._now


@pytest.fixture
def auth_service():
    users = [
        {
            "id": "u1",
            "username": "admin",
            "password_hash": "hashed_secret",
            "role": "operator",
            "is_active": True,
        },
        {
            "id": "u2",
            "username": "guest",
            "password_hash": "hashed_123",
            "role": "viewer",
            "is_active": False,
        },
    ]
    return AuthService(
        users=FakeUserRepository(users),
        sessions=FakeSessionStore(),
        attempts=FakeLoginAttemptStore(),
        hasher=FakePasswordHasher(),
        issuer=FakeTokenIssuer(),
        clock=FakeClock(datetime(2026, 9, 27, 12, 0, tzinfo=UTC)),
        access_ttl=900,
        refresh_ttl=86400,
    )


def test_login_success(auth_service):
    access_token, access_exp, refresh_token, user = auth_service.login(
        "admin", "secret", "192.0.2.1"
    )
    assert access_token == "access_token_for_u1"
    assert user["id"] == "u1"

    # Check session created
    refresh_hash = auth_service._hash_token(refresh_token)
    assert refresh_hash in auth_service.sessions.sessions


def test_login_invalid_password(auth_service):
    with pytest.raises(ApplicationError) as exc:
        auth_service.login("admin", "wrong", "192.0.2.1")
    assert exc.value.code == "UNAUTHORIZED"


def test_login_inactive_user(auth_service):
    with pytest.raises(ApplicationError) as exc:
        auth_service.login("guest", "123", "192.0.2.1")
    assert exc.value.code == "UNAUTHORIZED"


def test_refresh_success(auth_service):
    _, _, refresh_token, _ = auth_service.login("admin", "secret", "192.0.2.1")

    acc, exp, new_refresh = auth_service.refresh(refresh_token)
    assert acc == "access_token_for_u1"
    assert new_refresh != refresh_token

    # Old token shouldn't work anymore
    with pytest.raises(ApplicationError):
        auth_service.refresh(refresh_token)


def test_logout(auth_service):
    _, _, refresh_token, _ = auth_service.login("admin", "secret", "192.0.2.1")
    auth_service.logout(refresh_token)

    with pytest.raises(ApplicationError):
        auth_service.refresh(refresh_token)


def test_logout_everywhere(auth_service):
    _, _, refresh1, _ = auth_service.login("admin", "secret", "192.0.2.1")
    _, _, refresh2, _ = auth_service.login("admin", "secret", "192.0.2.1")

    auth_service.logout(refresh1, everywhere=True)

    with pytest.raises(ApplicationError):
        auth_service.refresh(refresh1)
    with pytest.raises(ApplicationError):
        auth_service.refresh(refresh2)


def test_me(auth_service):
    user = auth_service.me("u1")
    assert user["username"] == "admin"

    with pytest.raises(ApplicationError):
        auth_service.me("u2")  # inactive


def test_login_blocks_sixth_attempt_until_window_expires(auth_service):
    for _ in range(5):
        with pytest.raises(ApplicationError) as error:
            auth_service.login("admin", "wrong", "192.0.2.1")
        assert error.value.code == "UNAUTHORIZED"

    with pytest.raises(ApplicationError) as error:
        auth_service.login("admin", "secret", "192.0.2.1")
    assert error.value.code == "RATE_LIMITED"
    assert error.value.retry_after == 900
    assert not auth_service.sessions.sessions

    auth_service.clock._now += timedelta(minutes=15)
    assert auth_service.login("admin", "secret", "192.0.2.1")[3]["id"] == "u1"


def test_login_limit_is_per_username_and_ip_and_success_resets(auth_service):
    for _ in range(5):
        with pytest.raises(ApplicationError):
            auth_service.login("admin", "wrong", "192.0.2.1")
    assert auth_service.login("admin", "secret", "192.0.2.2")[3]["id"] == "u1"

    for _ in range(4):
        with pytest.raises(ApplicationError) as error:
            auth_service.login("missing", "wrong", "192.0.2.1")
        assert error.value.code == "UNAUTHORIZED"
    with pytest.raises(ApplicationError) as error:
        auth_service.login("missing", "wrong", "192.0.2.1")
    assert error.value.code == "UNAUTHORIZED"
    with pytest.raises(ApplicationError) as error:
        auth_service.login("missing", "wrong", "192.0.2.1")
    assert error.value.code == "RATE_LIMITED"

    for _ in range(4):
        with pytest.raises(ApplicationError):
            auth_service.login("admin", "wrong", "192.0.2.3")
    auth_service.login("admin", "secret", "192.0.2.3")
    for _ in range(5):
        with pytest.raises(ApplicationError) as error:
            auth_service.login("admin", "wrong", "192.0.2.3")
        assert error.value.code == "UNAUTHORIZED"
