"""Create one private local operator account on the first Docker startup."""

from __future__ import annotations

import os
from uuid import uuid4

from sqlalchemy import func, select
from tram.infrastructure.auth import Argon2PasswordHasher, SqlUserRepository
from tram.infrastructure.database import UserRow, make_engine, session_factory
from tram.infrastructure.settings import Settings


def main() -> None:
    username = os.environ.get("TRAM_BOOTSTRAP_OPERATOR_USERNAME", "tram-admin")
    password = os.environ.get("TRAM_BOOTSTRAP_OPERATOR_PASSWORD", "")
    if len(password) < 16:
        raise SystemExit("TRAM_BOOTSTRAP_OPERATOR_PASSWORD must contain at least 16 characters")

    settings = Settings()
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        sessions = session_factory(engine)
        with sessions() as session:
            operator_count = (
                session.scalar(
                    select(func.count()).select_from(UserRow).where(UserRow.role == "operator")
                )
                or 0
            )
            username_taken = session.scalar(
                select(func.count()).select_from(UserRow).where(UserRow.username == username)
            )
        if operator_count:
            print("Operator bootstrap skipped; the database already has an operator.")
            return
        if username_taken:
            raise SystemExit(
                "Bootstrap username already belongs to another role; choose another name."
            )
        SqlUserRepository(sessions).create(
            str(uuid4()), username, Argon2PasswordHasher().hash(password), "operator"
        )
        print(f"Created initial operator account: {username}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
