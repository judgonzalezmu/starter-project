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
