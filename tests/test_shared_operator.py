from sqlalchemy import select
from tram.infrastructure.auth import Argon2PasswordHasher
from tram.infrastructure.database import Base, UserRow, make_engine, session_factory
from tram.infrastructure.shared_operator import PASSWORD_HASH, USERNAME, ensure_shared_operator

from tests.support import NOW, ROOT


def test_documented_password_matches_the_stored_hash():
    docs = (ROOT / "docs/DOCKER_STACK.md").read_text(encoding="utf-8")
    assert "| `operator` | `Tram-Operator-2025` |" in docs
    web_doc = (ROOT / "WEB_SERVICE_DOC.md").read_text(encoding="utf-8")
    assert "- Логин: operator\n- Пароль: Tram-Operator-2025\n" in web_doc
    assert Argon2PasswordHasher().verify(PASSWORD_HASH, "Tram-Operator-2025")


def test_shared_operator_is_created_and_restored():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)
    assert ensure_shared_operator(sessions, NOW) == "created"
    assert ensure_shared_operator(sessions, NOW) == "unchanged"
    with sessions.begin() as session:
        row = session.scalar(select(UserRow).where(UserRow.username == USERNAME))
        row.role, row.is_active, row.password_hash = "viewer", False, "changed"
    assert ensure_shared_operator(sessions, NOW) == "restored"
    with sessions() as session:
        row = session.scalar(select(UserRow).where(UserRow.username == USERNAME))
        assert (row.role, bool(row.is_active), row.password_hash) == (
            "operator",
            True,
            PASSWORD_HASH,
        )
    engine.dispose()
