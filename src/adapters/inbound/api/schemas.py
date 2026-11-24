"""Esquemas Pydantic del adaptador HTTP (no del dominio)."""

from pydantic import BaseModel, ConfigDict


class TriageRequest(BaseModel):
    """Cuerpo de `POST /api/v1/incidents/triage`."""

    incident_id: str
    raw_text: str


class TriageResponse(BaseModel):
    """Respuesta alineada con `TriageResult` del dominio."""

    model_config = ConfigDict(from_attributes=True)

    incident_id: str
    severity: str
    component: str
    rationale: str
    recommended_team: str
    duplicate_group_key: str
    consistency_ratio: float


class ActiveIncidentItem(BaseModel):
    """Ítem de transporte del resumen de activos."""

    model_config = ConfigDict(from_attributes=True)

    incident_id: str
    title: str
    component: str
    severity: str
    status: str
    elapsed_minutes: int
    requires_escalation: bool


class ActiveIncidentsSummaryResponse(BaseModel):
    """Cuerpo JSON de `GET /api/v1/incidents/summary` y del CLI `summary`."""

    model_config = ConfigDict(from_attributes=True)

    total_active: int
    breached_count: int
    incidents: list[ActiveIncidentItem]
