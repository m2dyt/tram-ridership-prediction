from datetime import UTC, datetime, timedelta

import pytest
from tram.application.auth import AuthService
from tram.application.errors import ApplicationError


class FakeUserRepository:
    def __init__(self, users):
        self._users = {u["id"]: u for u in users}
        self._by_username = {u["username"]: u for u in users}

    def create(self, user_id: str, username: str, password_hash: str, role: str):
        if username in self._by_username:
            raise ValueError("Username already exists")
        user = {
            "id": user_id,
            "username": username,
            "password_hash": password_hash,
            "role": role,
            "is_active": True,
        }
        self._users[user_id] = user
        self._by_username[username] = user

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
        hasher=FakePasswordHasher(),
        issuer=FakeTokenIssuer(),
        clock=FakeClock(datetime(2026, 9, 27, 12, 0, tzinfo=UTC)),
        access_ttl=900,
        refresh_ttl=86400,
    )


def test_login_success(auth_service):
    access_token, access_exp, refresh_token, user = auth_service.login("admin", "secret")
    assert access_token == "access_token_for_u1"
    assert user["id"] == "u1"

    # Check session created
    refresh_hash = auth_service._hash_token(refresh_token)
    assert refresh_hash in auth_service.sessions.sessions


def test_login_invalid_password(auth_service):
    with pytest.raises(ApplicationError) as exc:
        auth_service.login("admin", "wrong")
    assert exc.value.code == "UNAUTHORIZED"


def test_login_inactive_user(auth_service):
    with pytest.raises(ApplicationError) as exc:
        auth_service.login("guest", "123")
    assert exc.value.code == "UNAUTHORIZED"


def test_refresh_success(auth_service):
    _, _, refresh_token, _ = auth_service.login("admin", "secret")

    acc, exp, new_refresh = auth_service.refresh(refresh_token)
    assert acc == "access_token_for_u1"
    assert new_refresh != refresh_token

    # Old token shouldn't work anymore
    with pytest.raises(ApplicationError):
        auth_service.refresh(refresh_token)


def test_logout(auth_service):
    _, _, refresh_token, _ = auth_service.login("admin", "secret")
    auth_service.logout(refresh_token)

    with pytest.raises(ApplicationError):
        auth_service.refresh(refresh_token)


def test_logout_everywhere(auth_service):
    _, _, refresh1, _ = auth_service.login("admin", "secret")
    _, _, refresh2, _ = auth_service.login("admin", "secret")

    auth_service.logout(refresh1, everywhere=True)

    with pytest.raises(ApplicationError):
        auth_service.refresh(refresh1)
    with pytest.raises(ApplicationError):
        auth_service.refresh(refresh2)


def test_me(auth_service):
    user = auth_service.me("u1")
    assert user["username"] == "admin"
    assert set(user) == {"id", "username", "role"}

    with pytest.raises(ApplicationError):
        auth_service.me("u2")  # inactive


def test_register_creates_viewer(auth_service):
    result = auth_service.register("new-viewer", "password123")

    user = auth_service.users.get_by_id(result["id"])
    assert user["role"] == "viewer"
    assert user["password_hash"] == "hashed_password123"


def test_register_rejects_duplicate_username(auth_service):
    with pytest.raises(ApplicationError) as exc:
        auth_service.register("admin", "password123")

    assert exc.value.code == "VALIDATION_ERROR"


def test_create_operator_assigns_operator_role(auth_service):
    result = auth_service.create_operator("new-operator", "password123")

    user = auth_service.users.get_by_id(result["id"])
    assert user["role"] == "operator"
    assert user["password_hash"] == "hashed_password123"


def test_create_operator_rejects_duplicate_username(auth_service):
    with pytest.raises(ApplicationError) as exc:
        auth_service.create_operator("admin", "password123")

    assert exc.value.code == "VALIDATION_ERROR"
