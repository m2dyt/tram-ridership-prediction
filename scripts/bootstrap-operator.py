"""Make sure the shared operator account exists on every Docker startup.

The account (login ``operator``) is the same for everyone; see docs/DOCKER_STACK.md.
It is created by migration 0006 and restored here if it was deleted, demoted,
disabled or given another password.
"""

from __future__ import annotations

from datetime import UTC, datetime

from tram.infrastructure.database import make_engine, session_factory
from tram.infrastructure.settings import Settings
from tram.infrastructure.shared_operator import USERNAME, ensure_shared_operator


def main() -> None:
    settings = Settings()
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        outcome = ensure_shared_operator(session_factory(engine), datetime.now(UTC))
    finally:
        engine.dispose()
    print(f"Shared operator account '{USERNAME}': {outcome}")


if __name__ == "__main__":
    main()
