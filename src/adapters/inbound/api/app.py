"""Aplicación FastAPI: adaptador inbound REST para triaje y resumen."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from src.adapters.inbound.api.schemas import (
    ActiveIncidentsSummaryResponse,
    TriageRequest,
    TriageResponse,
)
from src.adapters.outbound.factory import create_incident_repository
from src.application.services import IncidentService, ValidationError, parse_reference_time


def create_app() -> FastAPI:
    """Factory de la API HTTP. El repositorio se crea una vez por proceso."""
    service = IncidentService(create_incident_repository())
    app = FastAPI(title="IncidentOps", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/incidents/triage", response_model=TriageResponse)
    def triage_incident(body: TriageRequest) -> TriageResponse:
        try:
            result = IncidentService.triage_incident(body.incident_id, body.raw_text)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return TriageResponse.model_validate(result)

    @app.get("/api/v1/incidents/summary", response_model=ActiveIncidentsSummaryResponse)
    def active_incidents_summary(
        component: str | None = None,
        reference_time: str | None = None,
    ) -> ActiveIncidentsSummaryResponse:
        try:
            parsed = parse_reference_time(reference_time)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        summary = service.get_active_incidents_summary(
            component_filter=component,
            reference_time=parsed,
        )
        return ActiveIncidentsSummaryResponse.model_validate(summary)

    return app
