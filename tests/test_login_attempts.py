from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from tram.infrastructure.database import Base, LoginAttemptRow, make_engine, session_factory
from tram.infrastructure.login_attempts import SqlLoginAttemptStore


def test_login_attempts_are_shared_and_expire(tmp_path):
    engine = make_engine(f"sqlite+pysqlite:///{tmp_path / 'attempts.sqlite'}")
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)
    first = SqlLoginAttemptStore(sessions, "test-secret")
    second = SqlLoginAttemptStore(sessions, "test-secret")
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)

    try:
        for _ in range(5):
            assert first.begin_attempt("admin", "192.0.2.1", now, 5, 900) is None
        assert second.begin_attempt("admin", "192.0.2.1", now, 5, 900) == 900
        assert second.begin_attempt("admin", "192.0.2.2", now, 5, 900) is None
        assert second.begin_attempt("other", "192.0.2.1", now, 5, 900) is None
        assert second.begin_attempt("admin", "192.0.2.1", now + timedelta(seconds=899), 5, 900) == 1
        assert (
            first.begin_attempt("admin", "192.0.2.1", now + timedelta(seconds=900), 5, 900) is None
        )

        with sessions() as session:
            keys = session.scalars(select(LoginAttemptRow.key)).all()
        assert len(keys) == 1
        assert all(len(key) == 64 and "admin" not in key and "192.0.2.1" not in key for key in keys)

        second.clear("admin", "192.0.2.1")
        assert (
            first.begin_attempt("admin", "192.0.2.1", now + timedelta(seconds=900), 5, 900) is None
        )
    finally:
        engine.dispose()
