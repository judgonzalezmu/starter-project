"""Adaptador inbound CLI (Typer) para triaje y auditoría de muestras."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import typer

from src.application.services import IncidentService, ValidationError
from src.domain.triage_rules import SAMPLE_DATA_PATH, classify_incident_report

app = typer.Typer(help="IncidentOps CLI — triaje determinista sin persistencia.")


@app.command("triage")
def triage(
    incident_id: str = typer.Option(..., "--incident-id", help="Identificador del incidente."),
    raw_text: str = typer.Option(..., "--raw-text", help="Texto del reporte a clasificar."),
) -> None:
    """Clasifica un reporte e imprime el TriageResult en JSON por stdout."""
    try:
        result = IncidentService.triage_incident(incident_id, raw_text)
    except ValidationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(asdict(result), ensure_ascii=False))


@app.command("audit")
def audit(
    sample_path: Path = typer.Option(
        SAMPLE_DATA_PATH,
        "--sample-path",
        help="JSON de incidentes de prueba.",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
) -> None:
    """Auditoría complementaria sobre data/sample_incidents.json."""
    incidents = json.loads(sample_path.read_text(encoding="utf-8"))
    for item in incidents:
        triage_result = classify_incident_report(item["id"], item["raw_text"])
        typer.echo(json.dumps(asdict(triage_result), ensure_ascii=False))


if __name__ == "__main__":
    app()
