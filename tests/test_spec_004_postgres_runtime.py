"""Escenarios BDD de Spec 004 — persistencia dual y runtime en contenedores."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.adapters.inbound.api.app import create_app
from src.adapters.inbound.cli import app as cli_app
from src.adapters.outbound.factory import create_incident_repository
from src.adapters.outbound.postgres_repository import PostgresIncidentRepository
from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.domain.models import Incident
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[1]
UNREACHABLE_PG = "postgresql://incidentops:incidentops@127.0.0.1:1/incidentops"
PAYMENTS_RAW = (
    "URGENTE: El gateway de pagos devuelve HTTP 502 Bad Gateway en todas las "
    "transacciones con tarjeta de crédito desde hace 12 minutos. "
    "Ningún comercio puede cobrar."
)
PERSISTENCE_DETAIL = "El almacén de datos no está disponible."


def _database_url(path: Path) -> str:
    return "sqlite:///" + path.as_posix()


def _client(monkeypatch: pytest.MonkeyPatch, database_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", database_url)
    return TestClient(create_app())


def test_bdd_health_connected_http_and_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario 1 — Salud operativa 200 y CLI health con conectividad real."""
    database_url = _database_url(tmp_path / "health_ok.db")
    client = _client(monkeypatch, database_url)

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}

    runner = CliRunner()
    result = runner.invoke(cli_app, ["health"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"status": "ok", "database": "connected"}


def test_bdd_health_unavailable_and_business_ops_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Escenario 2 + FR-017 — Salud 503 y ops sin inventar datos."""
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_PG)
    client = TestClient(create_app())

    started = time.perf_counter()
    response = client.get("/health")
    elapsed = time.perf_counter() - started
    assert elapsed <= 5.0
    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}
    body_text = response.text
    assert "incidentops" not in body_text
    assert UNREACHABLE_PG not in body_text

    runner = CliRunner()
    health_cli = runner.invoke(cli_app, ["health"])
    assert health_cli.exit_code == 1
    assert json.loads(health_cli.stdout) == {
        "status": "error",
        "database": "unavailable",
    }
    assert UNREACHABLE_PG not in health_cli.stdout
    assert UNREACHABLE_PG not in (health_cli.stderr or "")

    create_http = client.post(
        "/api/v1/incidents",
        json={"title": "Pagos", "raw_text": PAYMENTS_RAW},
    )
    assert create_http.status_code == 503
    assert create_http.json() == {"detail": PERSISTENCE_DETAIL}
    assert "incident_id" not in create_http.json()
    assert UNREACHABLE_PG not in create_http.text

    create_cli = runner.invoke(
        cli_app,
        ["create", "--title", "Pagos", "--raw-text", PAYMENTS_RAW],
    )
    assert create_cli.exit_code == 1
    assert PERSISTENCE_DETAIL in (create_cli.stderr or "")
    assert "incident_id" not in create_cli.stdout
    assert UNREACHABLE_PG not in (create_cli.stderr or "")


def test_bdd_database_url_engine_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario 3 — Selección transparente SQLite / PostgreSQL vía DATABASE_URL."""
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_PG)
    client = TestClient(create_app())
    create_http = client.post(
        "/api/v1/incidents",
        json={"title": "Pagos", "raw_text": PAYMENTS_RAW},
    )
    assert create_http.status_code == 503
    assert create_http.status_code != 201

    pg_repo = create_incident_repository(UNREACHABLE_PG)
    assert isinstance(pg_repo, PostgresIncidentRepository)

    file_url = _database_url(tmp_path / "shared.db")
    first = create_incident_repository(file_url)
    assert isinstance(first, SQLiteIncidentRepository)
    first.save_incident(
        Incident(
            incident_id="INC-SHARED",
            title="Shared",
            component="payments-gateway",
            severity="P0",
            status="OPEN",
            created_at=datetime(2026, 11, 9, 9, 0, 0),
            raw_text=PAYMENTS_RAW,
        )
    )
    second = create_incident_repository(file_url)
    stored = second.get_incident("INC-SHARED")
    assert stored is not None
    assert stored.incident_id == "INC-SHARED"

    monkeypatch.delenv("DATABASE_URL", raising=False)
    mem_a = create_incident_repository()
    mem_b = create_incident_repository()
    assert isinstance(mem_a, SQLiteIncidentRepository)
    assert isinstance(mem_b, SQLiteIncidentRepository)
    mem_a.save_incident(
        Incident(
            incident_id="INC-MEM",
            title="Memory",
            component="payments-gateway",
            severity="P1",
            status="OPEN",
            created_at=datetime(2026, 11, 9, 9, 0, 0),
            raw_text=PAYMENTS_RAW,
        )
    )
    assert mem_b.get_incident("INC-MEM") is None

    with pytest.raises(ValueError) as empty_exc:
        create_incident_repository("   ")
    assert "vacía" in str(empty_exc.value)
    assert "   " not in str(empty_exc.value)

    monkeypatch.setenv("DATABASE_URL", "")
    with pytest.raises(ValueError) as env_empty:
        create_incident_repository()
    assert "vacía" in str(env_empty.value)

    bad_url = "mysql://localhost/incidentops"
    with pytest.raises(ValueError) as mysql_exc:
        create_incident_repository(bad_url)
    assert bad_url not in str(mysql_exc.value)
    assert "sqlite:///" in str(mysql_exc.value)
    assert "postgresql://" in str(mysql_exc.value)

    with pytest.raises(ValueError) as postgres_alias:
        create_incident_repository("postgres://localhost/incidentops")
    assert "postgres://localhost/incidentops" not in str(postgres_alias.value)


def test_bdd_compose_manifest_contract() -> None:
    """Escenario 4 — Orquestación reproducible (manifiesto, sin Compose up)."""
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "FROM python:3.12-slim" in dockerfile
    assert "ghcr.io/astral-sh/uv:" in dockerfile
    assert ":latest" not in dockerfile.split("ghcr.io/astral-sh/uv:")[1].split()[0]
    assert "uv sync --frozen --no-dev" in dockerfile
    assert "src.adapters.inbound.api.app:create_app" in dockerfile
    assert "--factory" in dockerfile
    assert "--host" in dockerfile and "0.0.0.0" in dockerfile
    assert "--port" in dockerfile and "8000" in dockerfile

    for pattern in (
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".git",
        ".env",
        "*.db",
        "tests",
    ):
        assert pattern in dockerignore
    ignore_lines = {
        line.strip()
        for line in dockerignore.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert "pyproject.toml" not in ignore_lines
    assert "uv.lock" not in ignore_lines
    assert "src/" not in ignore_lines
    assert "src" not in ignore_lines

    assert "postgres:16-alpine" in compose
    assert "pg_isready" in compose
    assert "POSTGRES_USER" in compose
    assert "POSTGRES_PASSWORD" in compose
    assert "POSTGRES_DB" in compose
    assert "incidentops" in compose
    assert "DATABASE_URL" in compose
    assert "postgresql://" in compose
    assert "service_healthy" in compose
    assert "depends_on" in compose
    assert "8000:8000" in compose
    assert "/health" in compose
    assert "5432:5432" not in compose
    assert not any(
        line.strip().startswith("version:")
        for line in compose.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )