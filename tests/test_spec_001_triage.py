"""Escenarios BDD de Spec 001 — triaje multi-interfaz sin persistencia."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner


TRIAGE_URL = "/api/v1/incidents/triage"


def test_scenario_1_payments_gateway_502_http(
    client: TestClient, sample_incidents: dict[str, str]
) -> None:
    """Escenario 1 — Caída crítica HTTP 502 en pasarela de pagos."""
    raw_text = sample_incidents["INC-1001"]
    response = client.post(
        TRIAGE_URL,
        json={"incident_id": "INC-1001", "raw_text": raw_text},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["severity"] == "P0"
    assert body["component"] == "payments-gateway"
    assert body["recommended_team"] == "Backend-Core"
    assert body["duplicate_group_key"] == "payments-gateway:http-502-outage"


def test_scenario_2_individual_account_blocked_hoy_not_p0(
    client: TestClient, sample_incidents: dict[str, str]
) -> None:
    """Escenario 2 — Cuenta individual bloqueada mencionando \"hoy\"."""
    raw_text = sample_incidents["INC-1002"]
    assert "hoy" in raw_text.casefold()
    response = client.post(
        TRIAGE_URL,
        json={"incident_id": "INC-1002", "raw_text": raw_text},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["severity"] == "P2"
    assert body["recommended_team"] == "Security-IAM"
    assert body["severity"] != "P0"


def test_scenario_3_empty_or_whitespace_inputs_return_422(client: TestClient) -> None:
    """Escenario 3 — Entradas vacías o solo espacios → 422."""
    whitespace = client.post(
        TRIAGE_URL,
        json={"incident_id": "INC-EMPTY", "raw_text": " "},
    )
    empty_id = client.post(
        TRIAGE_URL,
        json={"incident_id": "", "raw_text": "reporte con texto válido"},
    )
    assert whitespace.status_code == 422
    assert empty_id.status_code == 422


def test_scenario_4_cli_parity_with_payments_502(
    cli_runner: CliRunner,
    typer_app,
    sample_incidents: dict[str, str],
) -> None:
    """Escenario 4 — Paridad CLI con el caso crítico HTTP 502."""
    raw_text = sample_incidents["INC-1001"]
    result = cli_runner.invoke(
        typer_app,
        ["triage", "--incident-id", "INC-1001", "--raw-text", raw_text],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["severity"] == "P0"
    assert payload["recommended_team"] == "Backend-Core"
