import argparse
import importlib
import importlib.metadata
import sys
import time
from pathlib import Path


def doctor() -> int:
    """Check the installed runtime without opening the database or training a model."""
    print(f"Python: {sys.version.split()[0]}")
    print(f"Interpreter: {sys.executable}")
    dependencies = {
        "fastapi": "fastapi",
        "pydantic-settings": "pydantic_settings",
        "sqlalchemy": "sqlalchemy",
        "psycopg": "psycopg",
        "alembic": "alembic",
        "jsonschema": "jsonschema",
        "PyYAML": "yaml",
        "uvicorn": "uvicorn",
        "tzdata": "tzdata",
        "httpx": "httpx",
    }
    failed = False
    for package, module in dependencies.items():
        try:
            importlib.import_module(module)
            print(f"OK {package}=={importlib.metadata.version(package)}")
        except (ImportError, importlib.metadata.PackageNotFoundError) as error:
            print(f"MISSING {package}: {type(error).__name__}")
            failed = True
    return int(failed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tram backend foundations; no model training")
    subparsers = parser.add_subparsers(dest="command", required=True)
    from tram import commands

    commands.register(subparsers)
    subparsers.add_parser("doctor", help="Check installed runtime dependencies")
    subparsers.add_parser(
        "init-config", help="Create .env with random local credentials (never overwrite)"
    )
    serve = subparsers.add_parser("serve", help="Start HTTP API and Swagger UI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    publish = subparsers.add_parser(
        "publish", help="Validate and atomically publish a prepared dataset"
    )
    publish.add_argument("directory", type=Path)
    demo = subparsers.add_parser(
        "demo", help="Write synthetic data and example requests into a new directory"
    )
    demo.add_argument("directory", type=Path)
    migrate = subparsers.add_parser("migrate", help="Apply database migrations to head")
    migrate.add_argument("--config", type=Path, default=Path("alembic.ini"))
    worker = subparsers.add_parser(
        "worker", help="Apply the prepared seasonal baseline to queued jobs"
    )
    worker.add_argument("--once", action="store_true", help="Process at most one job, then exit")
    args = parser.parse_args(argv)
    if args.command in (
        "context-refresh",
        "import-geo",
        "replay-trip",
        "evaluate",
        "prepare-csv",
        "export-occupancy",
    ):
        from jsonschema.exceptions import ValidationError

        from tram.application.errors import ApplicationError

        try:
            return commands.execute(args)
        except ApplicationError as error:
            print(f"{error.code}: {error.message}", file=sys.stderr)
            return 1
        except (ValueError, KeyError, TypeError, OSError, ValidationError) as error:
            print(
                f"Invalid input: {type(error).__name__}; see command documentation", file=sys.stderr
            )
            return 1
    if args.command == "doctor":
        return doctor()
    if args.command == "init-config":
        import secrets

        password = secrets.token_hex(24)
        config = {
            "TRAM_POSTGRES_PASSWORD": password,
            "TRAM_POSTGRES_PORT": "15433",
            "TRAM_DATABASE_URL": f"postgresql+psycopg://tram:{password}@127.0.0.1:15433/tram",
            "TRAM_VIEWER_TOKEN": secrets.token_urlsafe(32),
            "TRAM_OPERATOR_TOKEN": secrets.token_urlsafe(32),
            "TRAM_CURSOR_SECRET": secrets.token_urlsafe(32),
        }
        try:
            with Path(".env").open("x", encoding="utf-8", newline="\n") as stream:
                stream.writelines(f"{key}={value}\n" for key, value in config.items())
        except FileExistsError:
            parser.error(".env already exists; existing configuration was preserved")
        print("Created .env with random local credentials; keep this file private")
        return 0
    if args.command == "serve":
        import uvicorn

        uvicorn.run("tram.composition:create_app", factory=True, host=args.host, port=args.port)
        return 0
    if args.command == "demo":
        from tram.infrastructure.demo import write_demo
        from tram.infrastructure.runtime import SystemClock

        try:
            revision = write_demo(args.directory, SystemClock().now())
        except FileExistsError:
            parser.error("Output directory already exists; choose a new directory")
        print(f"Created {revision} in {args.directory}; source_mode=demo; no training")
        return 0
    if args.command == "publish":
        from jsonschema.exceptions import ValidationError

        from tram.application.errors import ApplicationError
        from tram.composition import publish_bundle
        from tram.infrastructure.settings import Settings

        try:
            revision, created = publish_bundle(Settings(), args.directory)
        except ApplicationError as error:
            print(f"{error.code}: {error.message}", file=sys.stderr)
            return 1
        except ValidationError as error:
            print(f"Invalid bundle schema at {error.json_path}", file=sys.stderr)
            return 1
        except (ValueError, TypeError, KeyError, OSError) as error:
            print(
                f"Invalid bundle: {type(error).__name__}; publication rolled back", file=sys.stderr
            )
            return 1
        print(f"{'Published' if created else 'Already published'}: {revision}")
        return 0
    if args.command == "migrate":
        from alembic import command
        from alembic.config import Config

        if not args.config.is_file():
            parser.error("alembic.ini was not found; run from the repository or pass --config")
        command.upgrade(Config(str(args.config.resolve())), "head")
        return 0

    from tram.composition import build_worker
    from tram.infrastructure.settings import Settings

    settings = Settings()
    try:
        with build_worker(settings) as runner:
            while True:
                processed = runner.execute_one()
                if args.once:
                    return 0
                if not processed:
                    time.sleep(settings.poll_seconds)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
