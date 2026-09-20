import ast
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from tram.infrastructure.database import Base, make_engine

ROOT = Path(__file__).resolve().parents[1]


def test_cli_help_does_not_require_database_or_tokens():
    result = subprocess.run(
        [sys.executable, "-m", "tram.cli", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "doctor" in result.stdout and "worker" in result.stdout


def test_migrations_round_trip_and_match_models():
    with TemporaryDirectory(prefix="tram-migration-test-") as temporary:
        database = Path(temporary) / "migration.sqlite"
        url = "sqlite+pysqlite:///" + database.as_posix()
        config = Config(str(ROOT / "alembic.ini"))
        with patch.dict(os.environ, {"TRAM_DATABASE_URL": url}):
            command.upgrade(config, "head")
            engine = make_engine(url)
            try:
                with engine.connect() as connection:
                    assert not compare_metadata(
                        MigrationContext.configure(connection), Base.metadata
                    )
                assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())
            finally:
                engine.dispose()
            command.downgrade(config, "base")
            engine = make_engine(url)
            try:
                assert set(inspect(engine).get_table_names()) == {"alembic_version"}
            finally:
                engine.dispose()


def test_clean_architecture_dependency_direction():
    forbidden = {
        "domain": ("tram.application", "tram.infrastructure", "tram.api", "tram_ml"),
        "application": ("tram.infrastructure", "tram.api", "tram.composition", "tram_ml"),
    }
    for layer, disallowed in forbidden.items():
        for path in (ROOT / "backend/src/tram" / layer).glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    assert not name.startswith(disallowed), (path, name)
                    assert name.split(".")[0] in sys.stdlib_module_names or name.startswith(
                        "tram."
                    ), (
                        path,
                        name,
                    )


def test_ml_depends_only_on_domain_and_standard_library():
    for path in (ROOT / "ml/src/tram_ml").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] in sys.stdlib_module_names or name.startswith(
                    ("tram.domain.", "tram_ml.")
                ), (path, name)


def test_requirements_match_project_dependencies():
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = {
        line.strip()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert requirements == set(project["project"]["dependencies"]) | set(
        project["dependency-groups"]["dev"]
    )


def test_built_frontend_is_served_without_hiding_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from tram.composition import create_app

    (tmp_path / "index.html").write_text('<html lang="ru">Tram frontend</html>', encoding="utf-8")
    for name, value in {
        "TRAM_VIEWER_TOKEN": "v" * 32,
        "TRAM_OPERATOR_TOKEN": "o" * 32,
        "TRAM_CURSOR_SECRET": "c" * 32,
        "TRAM_FRONTEND_DIST": str(tmp_path),
        "TRAM_DATABASE_URL": "sqlite+pysqlite:///:memory:",
    }.items():
        monkeypatch.setenv(name, value)
    with TestClient(create_app()) as client:
        assert "Tram frontend" in client.get("/").text
        assert client.get("/docs").status_code == 200
        assert "/scenarios/fleet" in client.get("/openapi.json").json()["paths"]
