"""Adaptador inbound CLI (Typer) para triaje, resumen y auditoría."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import typer

from src.adapters.inbound.api.schemas import ActiveIncidentsSummaryResponse
from src.adapters.outbound.factory import create_incident_repository
from src.application.services import IncidentService, ValidationError, parse_reference_time
from src.domain.triage_rules import SAMPLE_DATA_PATH, classify_incident_report

app = typer.Typer(help="IncidentOps CLI — triaje y resumen de incidentes activos.")


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


@app.command("summary")
def summary(
    component: str | None = typer.Option(
        None,
        "--component",
        help="Componente exacto. Omitido, vacío o solo espacios: todos los activos.",
    ),
    reference_time: str | None = typer.Option(
        None,
        "--reference-time",
        help="Instante ISO-8601 naive. Omitido: momento de la consulta.",
    ),
) -> None:
    """Imprime el resumen de incidentes activos en JSON por stdout."""
    try:
        parsed = parse_reference_time(reference_time)
        service = IncidentService(create_incident_repository())
        result = service.get_active_incidents_summary(
            component_filter=component,
            reference_time=parsed,
        )
    except ValidationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    payload = ActiveIncidentsSummaryResponse.model_validate(result).model_dump()
    typer.echo(json.dumps(payload, ensure_ascii=False))


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
