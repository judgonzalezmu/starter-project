"""Escenarios BDD de Spec 003 — ciclo de vida, duplicados y consulta SLA."""

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
from src.domain.models import Incident

CREATE_URL = "/api/v1/incidents"
PAYMENTS_RAW = (
    "URGENTE: El gateway de pagos devuelve HTTP 502 Bad Gateway en todas las "
    "transacciones con tarjeta de crédito desde hace 12 minutos. "
    "Ningún comercio puede cobrar."
)
DUP_KEY = "payments-gateway:http-502-outage"


def _database_url(path: Path) -> str:
    return "sqlite:///" + path.as_posix()


def _client(monkeypatch: pytest.MonkeyPatch, database_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", database_url)
    return TestClient(create_app())


def test_bdd_create_incident_201_without_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario 1 — Registro inicial 201 sin duplicados previos."""
    database_url = _database_url(tmp_path / "create.db")
    client = _client(monkeypatch, database_url)

    response = client.post(
        CREATE_URL,
        json={"title": "Caída de pagos", "raw_text": PAYMENTS_RAW},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Caída de pagos"
    assert body["raw_text"] == PAYMENTS_RAW
    assert body["status"] == "OPEN"
    assert body["severity"] == "P0"
    assert body["component"] == "payments-gateway"
    assert body["recommended_team"] == "Backend-Core"
    assert body["duplicate_group_key"] == DUP_KEY
    assert body["is_duplicate"] is False
    assert body["duplicate_of"] == []
    assert body["incident_id"].startswith("INC-")
    assert len(body["incident_id"]) == 12

    stored = create_incident_repository(database_url).get_incident(body["incident_id"])
    assert stored is not None
    assert stored.duplicate_group_key == DUP_KEY


def test_bdd_create_detects_open_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario 2 — Detección de duplicado abierto 201."""
    database_url = _database_url(tmp_path / "dup.db")
    repo = create_incident_repository(database_url)
    repo.save_incident(
        Incident(
            incident_id="INC-OPEN1",
            title="Pagos caídos",
            component="payments-gateway",
            severity="P0",
            status="OPEN",
            created_at=datetime(2026, 11, 6, 10, 0, 0),
            raw_text=PAYMENTS_RAW,
            recommended_team="Backend-Core",
            duplicate_group_key=DUP_KEY,
        )
    )
    repo.save_incident(
        Incident(
            incident_id="INC-PROG",
            title="Pagos en progreso",
            component="payments-gateway",
            severity="P0",
            status="IN_PROGRESS",
            created_at=datetime(2026, 11, 6, 10, 30, 0),
            raw_text=PAYMENTS_RAW,
            recommended_team="Backend-Core",
            duplicate_group_key=DUP_KEY,
        )
    )
    repo.save_incident(
        Incident(
            incident_id="INC-DONE",
            title="Pagos resueltos",
            component="payments-gateway",
            severity="P0",
            status="RESOLVED",
            created_at=datetime(2026, 11, 5, 9, 0, 0),
            resolved_at=datetime(2026, 11, 5, 10, 0, 0),
            raw_text=PAYMENTS_RAW,
            recommended_team="Backend-Core",
            duplicate_group_key=DUP_KEY,
        )
    )

    client = _client(monkeypatch, database_url)
    response = client.post(
        CREATE_URL,
        json={
            "title": "Otro outage 502",
            "raw_text": PAYMENTS_RAW,
            "incident_id": "INC-NEW",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["is_duplicate"] is True
    assert set(body["duplicate_of"]) == {"INC-OPEN1", "INC-PROG"}
    assert "INC-DONE" not in body["duplicate_of"]
    assert "INC-NEW" not in body["duplicate_of"]
    assert create_incident_repository(database_url).get_incident("INC-NEW") is not None


def test_bdd_sla_p2_business_hours_elapsed_120(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario 3 — Auditoría determinista de SLA en horario hábil (P2)."""
    database_url = _database_url(tmp_path / "sla.db")
    create_incident_repository(database_url).save_incident(
        Incident(
            incident_id="INC-P2",
            title="Latencia de reportes",
            component="reporting-api",
            severity="P2",
            status="OPEN",
            created_at=datetime(2026, 11, 6, 17, 0, 0),
            raw_text="reporte lento",
            recommended_team="Data-DBA",
            duplicate_group_key="UNIQUE-INC-P2",
        )
    )
    client = _client(monkeypatch, database_url)

    response = client.get(
        "/api/v1/incidents/INC-P2/sla",
        params={"reference_time": "2026-11-09T09:00:00"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "incident_id": "INC-P2",
        "elapsed_minutes": 120,
        "allowed_minutes": 480,
        "remaining_minutes": 360,
        "is_breached": False,
        "requires_escalation": False,
    }


def test_bdd_sla_not_found_and_reference_before_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario 4 — Consulta de SLA: ID inexistente y tiempo anterior a creación."""
    database_url = _database_url(tmp_path / "rejects.db")
    create_incident_repository(database_url).save_incident(
        Incident(
            incident_id="INC-EXIST",
            title="Existente",
            component="reporting-api",
            severity="P2",
            status="OPEN",
            created_at=datetime(2026, 11, 10, 12, 0, 0),
            raw_text="texto",
        )
    )
    client = _client(monkeypatch, database_url)
    runner = CliRunner()

    missing = client.get("/api/v1/incidents/INC-MISSING/sla")
    assert missing.status_code == 404

    before = client.get(
        "/api/v1/incidents/INC-EXIST/sla",
        params={"reference_time": "2026-11-09T09:00:00"},
    )
    assert before.status_code == 422
    assert "elapsed_minutes" not in before.json().get("detail", {})

    illegible = client.get(
        "/api/v1/incidents/INC-EXIST/sla",
        params={"reference_time": "not-a-timestamp"},
    )
    assert illegible.status_code == 422

    tz_aware = client.get(
        "/api/v1/incidents/INC-EXIST/sla",
        params={"reference_time": "2026-11-11T09:00:00+00:00"},
    )
    assert tz_aware.status_code == 422

    monkeypatch.setenv("DATABASE_URL", database_url)
    cli_bad = runner.invoke(
        cli_app,
        ["sla", "--incident-id", "INC-EXIST", "--reference-time", "bad"],
    )
    assert cli_bad.exit_code == 1

    empty_title = client.post(
        CREATE_URL,
        json={"title": "  ", "raw_text": PAYMENTS_RAW},
    )
    assert empty_title.status_code == 422

    client.post(
        CREATE_URL,
        json={
            "title": "Primero",
            "raw_text": PAYMENTS_RAW,
            "incident_id": "INC-DUP-ID",
        },
    )
    conflict = client.post(
        CREATE_URL,
        json={
            "title": "Segundo",
            "raw_text": PAYMENTS_RAW,
            "incident_id": "INC-DUP-ID",
        },
    )
    assert conflict.status_code == 409

    bad_status = client.post(
        CREATE_URL,
        json={"title": "X", "raw_text": PAYMENTS_RAW, "status": "CLOSED"},
    )
    assert bad_status.status_code == 422

    bad_resolved = client.post(
        CREATE_URL,
        json={
            "title": "Resuelto mal",
            "raw_text": PAYMENTS_RAW,
            "status": "RESOLVED",
            "created_at": "2026-11-10T12:00:00",
            "resolved_at": "2026-11-10T11:00:00",
        },
    )
    assert bad_resolved.status_code == 422


def test_bdd_cli_create_and_sla_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario 5 — Paridad CLI `create` y `sla`."""
    runner = CliRunner()
    create_payload = {
        "title": "Paridad create",
        "raw_text": PAYMENTS_RAW,
        "incident_id": "INC-PARITY",
        "created_at": "2026-11-06T10:00:00",
    }

    http_url = _database_url(tmp_path / "parity-http.db")
    monkeypatch.setenv("DATABASE_URL", http_url)
    http_create = TestClient(create_app()).post(CREATE_URL, json=create_payload)
    assert http_create.status_code == 201

    cli_url = _database_url(tmp_path / "parity-cli.db")
    monkeypatch.setenv("DATABASE_URL", cli_url)
    cli_create = runner.invoke(
        cli_app,
        [
            "create",
            "--title",
            create_payload["title"],
            "--raw-text",
            create_payload["raw_text"],
            "--incident-id",
            create_payload["incident_id"],
            "--created-at",
            create_payload["created_at"],
        ],
    )
    assert cli_create.exit_code == 0
    http_body = http_create.json()
    cli_body = json.loads(cli_create.stdout)
    for key in (
        "incident_id",
        "title",
        "severity",
        "component",
        "recommended_team",
        "duplicate_group_key",
        "is_duplicate",
        "duplicate_of",
        "status",
    ):
        assert cli_body[key] == http_body[key]

    sla_url = _database_url(tmp_path / "parity-sla.db")
    create_incident_repository(sla_url).save_incident(
        Incident(
            incident_id="INC-SLA-P",
            title="P2 parity",
            component="reporting-api",
            severity="P2",
            status="OPEN",
            created_at=datetime(2026, 11, 6, 17, 0, 0),
            raw_text="reporte",
            recommended_team="Data-DBA",
            duplicate_group_key="UNIQUE-SLA-P",
        )
    )
    monkeypatch.setenv("DATABASE_URL", sla_url)
    http_sla = TestClient(create_app()).get(
        "/api/v1/incidents/INC-SLA-P/sla",
        params={"reference_time": "2026-11-09T09:00:00"},
    )
    cli_sla = runner.invoke(
        cli_app,
        [
            "sla",
            "--incident-id",
            "INC-SLA-P",
            "--reference-time",
            "2026-11-09T09:00:00",
        ],
    )
    assert http_sla.status_code == 200
    assert cli_sla.exit_code == 0
    assert json.loads(cli_sla.stdout) == http_sla.json()
