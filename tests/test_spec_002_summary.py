"""Aceptación H002: resumen de incidentes activos."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.adapters.inbound.api.app import create_app
from src.adapters.inbound.cli import app as cli_app
from src.adapters.outbound.factory import create_incident_repository
from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.application.ports import IncidentRepositoryPort
from src.domain.models import Incident

REFERENCE_TIME = "2026-11-20T12:00:00"

_ACCEPTANCE_CATALOG: tuple[Incident, ...] = (
    Incident(
        incident_id="INC-A",
        title="Pasarela caída",
        component="payments-gateway",
        severity="P0",
        status="OPEN",
        created_at=datetime(2026, 11, 20, 10, 0, 0),
    ),
    Incident(
        incident_id="INC-B",
        title="Latencia de pagos",
        component="payments-gateway",
        severity="P0",
        status="OPEN",
        created_at=datetime(2026, 11, 20, 11, 10, 0),
    ),
    Incident(
        incident_id="INC-C",
        title="Identidad degradada",
        component="auth-identity",
        severity="P1",
        status="IN_PROGRESS",
        created_at=datetime(2026, 11, 20, 11, 0, 0),
    ),
    Incident(
        incident_id="INC-M",
        title="Reporte lento",
        component="reporting-api",
        severity="P3",
        status="OPEN",
        created_at=datetime(2026, 11, 20, 11, 0, 0),
    ),
    Incident(
        incident_id="INC-Z",
        title="Reporte en cola",
        component="reporting-api",
        severity="P3",
        status="OPEN",
        created_at=datetime(2026, 11, 20, 11, 0, 0),
    ),
    Incident(
        incident_id="INC-D",
        title="Pagos ya restablecidos",
        component="payments-gateway",
        severity="P0",
        status="RESOLVED",
        created_at=datetime(2026, 11, 20, 8, 0, 0),
        resolved_at=datetime(2026, 11, 20, 9, 0, 0),
    ),
    Incident(
        incident_id="INC-E",
        title="Informe escalado",
        component="reporting-api",
        severity="P2",
        status="ESCALATION_REQUIRED",
        created_at=datetime(2026, 11, 20, 8, 0, 0),
    ),
)

_GLOBAL_SUMMARY = {
    "total_active": 5,
    "breached_count": 1,
    "incidents": [
        {
            "incident_id": "INC-A",
            "title": "Pasarela caída",
            "component": "payments-gateway",
            "severity": "P0",
            "status": "OPEN",
            "elapsed_minutes": 120,
            "requires_escalation": False,
        },
        {
            "incident_id": "INC-B",
            "title": "Latencia de pagos",
            "component": "payments-gateway",
            "severity": "P0",
            "status": "OPEN",
            "elapsed_minutes": 50,
            "requires_escalation": True,
        },
        {
            "incident_id": "INC-C",
            "title": "Identidad degradada",
            "component": "auth-identity",
            "severity": "P1",
            "status": "IN_PROGRESS",
            "elapsed_minutes": 60,
            "requires_escalation": False,
        },
        {
            "incident_id": "INC-M",
            "title": "Reporte lento",
            "component": "reporting-api",
            "severity": "P3",
            "status": "OPEN",
            "elapsed_minutes": 60,
            "requires_escalation": False,
        },
        {
            "incident_id": "INC-Z",
            "title": "Reporte en cola",
            "component": "reporting-api",
            "severity": "P3",
            "status": "OPEN",
            "elapsed_minutes": 60,
            "requires_escalation": False,
        },
    ],
}


def test_sqlite_repository_satisfies_incident_repository_port(tmp_path: Path) -> None:
    """El adaptador SQLite cumple el puerto sobre un archivo aislado."""
    repository = SQLiteIncidentRepository(str(tmp_path / "port.db"))
    assert isinstance(repository, IncidentRepositoryPort)


def _database_url(path: Path) -> str:
    return "sqlite:///" + path.as_posix()


def _seed_catalog(database_url: str, incidents: tuple[Incident, ...] = _ACCEPTANCE_CATALOG) -> None:
    repository = create_incident_repository(database_url)
    for incident in incidents:
        repository.save_incident(incident)


def test_bdd_global_summary_excludes_inactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario 1 — Resumen global excluyendo no activos."""
    database_url = _database_url(tmp_path / "global.db")
    _seed_catalog(database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)

    response = TestClient(create_app()).get(
        "/api/v1/incidents/summary",
        params={"reference_time": REFERENCE_TIME},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == _GLOBAL_SUMMARY
    statuses = {item["status"] for item in body["incidents"]}
    assert statuses <= {"OPEN", "IN_PROGRESS"}
    assert "INC-D" not in {item["incident_id"] for item in body["incidents"]}
    assert "INC-E" not in {item["incident_id"] for item in body["incidents"]}


def test_bdd_cli_summary_matches_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Escenario 4 — Consulta equivalente por CLI."""
    database_url = _database_url(tmp_path / "parity.db")
    _seed_catalog(database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)

    response = TestClient(create_app()).get(
        "/api/v1/incidents/summary",
        params={"reference_time": REFERENCE_TIME},
    )
    result = CliRunner().invoke(
        cli_app,
        ["summary", "--reference-time", REFERENCE_TIME],
    )

    assert response.status_code == 200
    assert result.exit_code == 0
    assert json.loads(result.stdout) == response.json()
    assert json.loads(result.stdout) == _GLOBAL_SUMMARY


_PAYMENTS_SUMMARY = {
    "total_active": 2,
    "breached_count": 1,
    "incidents": [
        _GLOBAL_SUMMARY["incidents"][0],
        _GLOBAL_SUMMARY["incidents"][1],
    ],
}


def test_bdd_summary_filtered_by_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario 2 — Resumen filtrado por componente."""
    database_url = _database_url(tmp_path / "filtered.db")
    _seed_catalog(database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)

    response = TestClient(create_app()).get(
        "/api/v1/incidents/summary",
        params={"component": "payments-gateway", "reference_time": REFERENCE_TIME},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == _PAYMENTS_SUMMARY
    assert {item["component"] for item in body["incidents"]} == {"payments-gateway"}
    assert "INC-D" not in {item["incident_id"] for item in body["incidents"]}


_EMPTY_SUMMARY = {"total_active": 0, "breached_count": 0, "incidents": []}


def test_bdd_empty_active_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Escenario 3 — Caso vacío (sin activos o sin coincidencias)."""
    inactive = tuple(
        incident
        for incident in _ACCEPTANCE_CATALOG
        if incident.status not in ("OPEN", "IN_PROGRESS")
    )
    empty_url = _database_url(tmp_path / "empty.db")
    _seed_catalog(empty_url, inactive)
    monkeypatch.setenv("DATABASE_URL", empty_url)

    response = TestClient(create_app()).get(
        "/api/v1/incidents/summary",
        params={"reference_time": REFERENCE_TIME},
    )
    result = CliRunner().invoke(cli_app, ["summary", "--reference-time", REFERENCE_TIME])

    assert response.status_code == 200
    assert response.json() == _EMPTY_SUMMARY
    assert result.exit_code == 0
    assert json.loads(result.stdout) == _EMPTY_SUMMARY

    unknown_url = _database_url(tmp_path / "unknown.db")
    _seed_catalog(unknown_url)
    monkeypatch.setenv("DATABASE_URL", unknown_url)
    response = TestClient(create_app()).get(
        "/api/v1/incidents/summary",
        params={"component": "componente-desconocido", "reference_time": REFERENCE_TIME},
    )
    result = CliRunner().invoke(
        cli_app,
        ["summary", "--component", "componente-desconocido", "--reference-time", REFERENCE_TIME],
    )

    assert response.status_code == 200
    assert response.json() == _EMPTY_SUMMARY
    assert result.exit_code == 0
    assert json.loads(result.stdout) == _EMPTY_SUMMARY


def test_bdd_invalid_reference_time_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario 5 — reference_time inválido rechazado."""
    database_url = _database_url(tmp_path / "invalid.db")
    _seed_catalog(database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)

    response = TestClient(create_app()).get(
        "/api/v1/incidents/summary",
        params={"reference_time": "manana"},
    )
    result = CliRunner().invoke(cli_app, ["summary", "--reference-time", "manana"])

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    assert "total_active" not in body
    assert "incidents" not in body
    assert result.exit_code == 1
    assert "total_active" not in result.stdout
    assert "incidents" not in result.stdout
    assert "reference_time" in result.stderr
    assert "Traceback" not in result.stderr
