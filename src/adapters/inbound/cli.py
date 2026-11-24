"""Adaptador inbound CLI (Typer) para triaje, resumen, alta y auditoría SLA."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import typer

from src.adapters.inbound.api.schemas import (
    ActiveIncidentsSummaryResponse,
    IncidentCreatedResponse,
    SLAEvaluationResponse,
)
from src.adapters.outbound.factory import create_incident_repository
from src.application.ports import PersistenceUnavailableError
from src.application.services import (
    IncidentAlreadyExistsError,
    IncidentNotFoundError,
    IncidentService,
    ValidationError,
    parse_optional_naive_datetime,
    parse_reference_time,
)
from src.domain.triage_rules import SAMPLE_DATA_PATH, classify_incident_report

app = typer.Typer(help="IncidentOps CLI — triaje, alta, resumen, SLA y salud.")

_PERSISTENCE_UNAVAILABLE_DETAIL = "El almacén de datos no está disponible."


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


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


@app.command("health")
def health() -> None:
    """Comprueba la conectividad del almacén e imprime el JSON operativo."""
    try:
        service = IncidentService(create_incident_repository())
        result = service.check_operational_health()
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    payload = {"status": result.status, "database": result.database}
    typer.echo(json.dumps(payload, ensure_ascii=False))
    if result.status != "ok":
        raise typer.Exit(code=1)


@app.command("create")
def create(
    title: str = typer.Option(..., "--title", help="Título del incidente."),
    raw_text: str = typer.Option(..., "--raw-text", help="Texto del reporte."),
    incident_id: str | None = typer.Option(
        None, "--incident-id", help="Id opcional; si existe → exit 1."
    ),
    created_at: str | None = typer.Option(
        None, "--created-at", help="ISO-8601 naive; omitido = ahora."
    ),
    status: str | None = typer.Option(
        None, "--status", help="OPEN|IN_PROGRESS|ESCALATION_REQUIRED|RESOLVED."
    ),
    resolved_at: str | None = typer.Option(
        None, "--resolved-at", help="ISO-8601 naive; aplica si status=RESOLVED."
    ),
) -> None:
    """Registra un incidente e imprime el CreationResult en JSON por stdout."""
    try:
        parsed_created = parse_optional_naive_datetime(
            created_at, field_name="created_at"
        )
        parsed_resolved = parse_optional_naive_datetime(
            resolved_at, field_name="resolved_at"
        )
        service = IncidentService(create_incident_repository())
        result = service.create_incident(
            title,
            raw_text,
            incident_id=incident_id,
            created_at=parsed_created,
            status=status,
            resolved_at=parsed_resolved,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except PersistenceUnavailableError as exc:
        typer.echo(_PERSISTENCE_UNAVAILABLE_DETAIL, err=True)
        raise typer.Exit(code=1) from exc
    except (ValidationError, IncidentAlreadyExistsError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    payload = IncidentCreatedResponse.model_validate(
        {**result.__dict__, "duplicate_of": list(result.duplicate_of)}
    ).model_dump(mode="json")
    typer.echo(json.dumps(payload, ensure_ascii=False, default=_json_default))


@app.command("sla")
def sla(
    incident_id: str = typer.Option(..., "--incident-id", help="Incidente a auditar."),
    reference_time: str | None = typer.Option(
        None,
        "--reference-time",
        help="Instante ISO-8601 naive. Omitido: momento de la consulta.",
    ),
) -> None:
    """Evalúa el SLA de un incidente persistido e imprime JSON por stdout."""
    try:
        parsed = parse_reference_time(reference_time)
        service = IncidentService(create_incident_repository())
        evaluation = service.evaluate_incident_sla(incident_id, parsed)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except PersistenceUnavailableError as exc:
        typer.echo(_PERSISTENCE_UNAVAILABLE_DETAIL, err=True)
        raise typer.Exit(code=1) from exc
    except (ValidationError, IncidentNotFoundError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    payload = SLAEvaluationResponse.model_validate(evaluation).model_dump()
    typer.echo(json.dumps(payload, ensure_ascii=False))


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
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except PersistenceUnavailableError as exc:
        typer.echo(_PERSISTENCE_UNAVAILABLE_DETAIL, err=True)
        raise typer.Exit(code=1) from exc
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
