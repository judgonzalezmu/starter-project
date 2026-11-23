"""Fixtures compartidas para aceptación Spec 001."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.adapters.inbound.api.app import create_app
from src.adapters.inbound.cli import app as cli_app

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_INCIDENTS_PATH = PROJECT_ROOT / "data" / "sample_incidents.json"


@pytest.fixture(scope="session")
def sample_incidents() -> dict[str, str]:
    """Mapa id → raw_text desde data/sample_incidents.json."""
    items = json.loads(SAMPLE_INCIDENTS_PATH.read_text(encoding="utf-8"))
    return {item["id"]: item["raw_text"] for item in items}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def typer_app():
    return cli_app
