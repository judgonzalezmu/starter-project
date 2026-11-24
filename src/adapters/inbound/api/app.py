"""Aplicación FastAPI: adaptador inbound REST para triaje, resumen, alta y SLA."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from src.adapters.inbound.api.schemas import (
    ActiveIncidentsSummaryResponse,
    CreateIncidentRequest,
    IncidentCreatedResponse,
    SLAEvaluationResponse,
    TriageRequest,
    TriageResponse,
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

_PERSISTENCE_UNAVAILABLE_DETAIL = "El almacén de datos no está disponible."


def create_app() -> FastAPI:
    """Factory de la API HTTP. El repositorio se crea una vez por proceso."""
    service = IncidentService(create_incident_repository())
    app = FastAPI(title="IncidentOps", version="0.1.0")

    @app.get("/health")
    def health() -> JSONResponse:
        result = service.check_operational_health()
        payload = {"status": result.status, "database": result.database}
        status_code = 200 if result.status == "ok" else 503
        return JSONResponse(content=payload, status_code=status_code)

    @app.post("/api/v1/incidents/triage", response_model=TriageResponse)
    def triage_incident(body: TriageRequest) -> TriageResponse:
        try:
            result = IncidentService.triage_incident(body.incident_id, body.raw_text)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return TriageResponse.model_validate(result)

    @app.post(
        "/api/v1/incidents",
        response_model=IncidentCreatedResponse,
        status_code=201,
    )
    def create_incident(body: CreateIncidentRequest) -> IncidentCreatedResponse:
        try:
            created_at = parse_optional_naive_datetime(
                body.created_at, field_name="created_at"
            )
            resolved_at = parse_optional_naive_datetime(
                body.resolved_at, field_name="resolved_at"
            )
            result = service.create_incident(
                body.title,
                body.raw_text,
                incident_id=body.incident_id,
                created_at=created_at,
                status=body.status,
                resolved_at=resolved_at,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except IncidentAlreadyExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PersistenceUnavailableError as exc:
            raise HTTPException(
                status_code=503, detail=_PERSISTENCE_UNAVAILABLE_DETAIL
            ) from exc
        return IncidentCreatedResponse.model_validate(
            {
                **result.__dict__,
                "duplicate_of": list(result.duplicate_of),
            }
        )

    @app.get(
        "/api/v1/incidents/{incident_id}/sla",
        response_model=SLAEvaluationResponse,
    )
    def evaluate_incident_sla(
        incident_id: str,
        reference_time: str | None = None,
    ) -> SLAEvaluationResponse:
        try:
            parsed = parse_reference_time(reference_time)
            evaluation = service.evaluate_incident_sla(incident_id, parsed)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except IncidentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PersistenceUnavailableError as exc:
            raise HTTPException(
                status_code=503, detail=_PERSISTENCE_UNAVAILABLE_DETAIL
            ) from exc
        return SLAEvaluationResponse.model_validate(evaluation)

    @app.get("/api/v1/incidents/summary", response_model=ActiveIncidentsSummaryResponse)
    def active_incidents_summary(
        component: str | None = None,
        reference_time: str | None = None,
    ) -> ActiveIncidentsSummaryResponse:
        try:
            parsed = parse_reference_time(reference_time)
            summary = service.get_active_incidents_summary(
                component_filter=component,
                reference_time=parsed,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except PersistenceUnavailableError as exc:
            raise HTTPException(
                status_code=503, detail=_PERSISTENCE_UNAVAILABLE_DETAIL
            ) from exc
        return ActiveIncidentsSummaryResponse.model_validate(summary)

    return app
