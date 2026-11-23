"""Aplicación FastAPI: adaptador inbound REST para triaje."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from src.adapters.inbound.api.schemas import TriageRequest, TriageResponse
from src.application.services import IncidentService, ValidationError


def create_app() -> FastAPI:
    """Factory de la API HTTP (sin estado ni persistencia)."""
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

    return app
