"""Esquemas Pydantic del adaptador HTTP (no del dominio)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class CreateIncidentRequest(BaseModel):
    """Cuerpo de `POST /api/v1/incidents`."""

    title: str
    raw_text: str
    incident_id: str | None = None
    created_at: str | None = None
    status: str | None = None
    resolved_at: str | None = None


class IncidentCreatedResponse(BaseModel):
    """Respuesta de alta persistente con clasificación y aviso de duplicado."""

    model_config = ConfigDict(from_attributes=True)

    incident_id: str
    title: str
    raw_text: str
    created_at: datetime
    status: str
    resolved_at: datetime | None = None
    severity: str
    component: str
    rationale: str
    recommended_team: str
    duplicate_group_key: str
    consistency_ratio: float
    is_duplicate: bool
    duplicate_of: list[str] = Field(default_factory=list)


class SLAEvaluationResponse(BaseModel):
    """Cuerpo de `GET /api/v1/incidents/{incident_id}/sla`."""

    model_config = ConfigDict(from_attributes=True)

    incident_id: str
    elapsed_minutes: int
    allowed_minutes: int
    remaining_minutes: int
    is_breached: bool
    requires_escalation: bool
