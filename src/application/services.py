"""Servicios de aplicación compartidos por los adaptadores inbound."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from src.application.ports import IncidentRepositoryPort
from src.domain.models import (
    Incident,
    IncidentStatus,
    SLAEvaluation,
    SeverityLevel,
    TeamName,
    TriageResult,
)
from src.domain.sla_calculator import evaluate_sla_status
from src.domain.triage_rules import classify_incident_report

_SEVERITY_RANK: dict[SeverityLevel, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_VALID_STATUSES: frozenset[str] = frozenset(
    {"OPEN", "IN_PROGRESS", "ESCALATION_REQUIRED", "RESOLVED"}
)


class ValidationError(Exception):
    """Entrada inválida para un caso de uso (triaje o instante de evaluación)."""


class IncidentNotFoundError(Exception):
    """El incidente pedido no existe en el almacén."""


class IncidentAlreadyExistsError(Exception):
    """El `incident_id` ya está registrado; no se sobrescribe."""


@dataclass(frozen=True)
class OperationalHealth:
    """Estado operativo del almacén observable por HTTP y CLI."""

    status: Literal["ok", "error"]
    database: Literal["connected", "unavailable"]


@dataclass(frozen=True)
class ActiveIncidentView:
    """Proyección de un incidente activo ya evaluado. No es esquema de transporte."""

    incident_id: str
    title: str
    component: str
    severity: SeverityLevel
    status: IncidentStatus
    elapsed_minutes: int
    requires_escalation: bool


@dataclass(frozen=True)
class ActiveIncidentsSummary:
    """Agregado de activos para el operador."""

    total_active: int
    breached_count: int
    incidents: tuple[ActiveIncidentView, ...]


@dataclass(frozen=True)
class CreationResult:
    """Vista de aplicación tras registrar un incidente (no es Pydantic)."""

    incident_id: str
    title: str
    raw_text: str
    created_at: datetime
    status: IncidentStatus
    resolved_at: datetime | None
    severity: SeverityLevel
    component: str
    rationale: str
    recommended_team: TeamName
    duplicate_group_key: str
    consistency_ratio: float
    is_duplicate: bool
    duplicate_of: tuple[str, ...]


def parse_optional_naive_datetime(
    raw: str | None,
    *,
    field_name: str = "timestamp",
) -> datetime | None:
    """Parsea un instante ISO-8601 naive opcional para HTTP y CLI.

    `None` (omitido) → `None`. Vacío, tz-aware o ilegible → `ValidationError`.
    """
    if raw is None:
        return None
    if raw.strip() == "":
        raise ValidationError(f"{field_name} no es un instante ISO-8601 válido.")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError(f"{field_name} no es un instante ISO-8601 válido.") from exc
    if parsed.tzinfo is not None:
        raise ValidationError(f"{field_name} no es un instante ISO-8601 válido.")
    return parsed


def parse_reference_time(raw: str | None) -> datetime | None:
    """Normaliza el instante de evaluación que envían HTTP y CLI."""
    return parse_optional_naive_datetime(raw, field_name="reference_time")


def _normalize_component_filter(component_filter: str | None) -> str | None:
    if component_filter is None:
        return None
    stripped = component_filter.strip()
    if stripped == "":
        return None
    return stripped


def _generate_incident_id() -> str:
    return "INC-" + secrets.token_hex(4).upper()


class IncidentService:
    """Orquesta casos de uso de incidentes sin acoplarse a REST ni CLI."""

    def __init__(self, repository: IncidentRepositoryPort) -> None:
        self._repository = repository

    def check_operational_health(self) -> OperationalHealth:
        """Comprueba conectividad real del almacén (`SELECT 1` en el adaptador)."""
        if self._repository.check_health():
            return OperationalHealth(status="ok", database="connected")
        return OperationalHealth(status="error", database="unavailable")

    @staticmethod
    def triage_incident(incident_id: str, raw_text: str) -> TriageResult:
        """Clasifica un reporte sin persistirlo.

        Raises:
            ValidationError: si `incident_id` o `raw_text` quedan vacíos tras `.strip()`.
        """
        cleaned_id = incident_id.strip()
        cleaned_text = raw_text.strip()
        if not cleaned_id or not cleaned_text:
            raise ValidationError(
                "incident_id y raw_text son obligatorios y no pueden estar vacíos."
            )
        return classify_incident_report(cleaned_id, cleaned_text)

    def create_incident(
        self,
        title: str,
        raw_text: str,
        *,
        incident_id: str | None = None,
        created_at: datetime | None = None,
        status: str | None = None,
        resolved_at: datetime | None = None,
    ) -> CreationResult:
        """Registra un incidente, clasifica y avisa de duplicados abiertos."""
        cleaned_title = title.strip()
        cleaned_text = raw_text.strip()
        if not cleaned_title or not cleaned_text:
            raise ValidationError(
                "title y raw_text son obligatorios y no pueden estar vacíos."
            )

        if status is None or status.strip() == "":
            resolved_status: IncidentStatus = "OPEN"
        else:
            candidate = status.strip()
            if candidate not in _VALID_STATUSES:
                raise ValidationError(
                    "status debe ser OPEN, IN_PROGRESS, ESCALATION_REQUIRED o RESOLVED."
                )
            resolved_status = candidate  # type: ignore[assignment]

        if incident_id is None or incident_id.strip() == "":
            new_id = _generate_incident_id()
        else:
            new_id = incident_id.strip()
            if self._repository.get_incident(new_id) is not None:
                raise IncidentAlreadyExistsError(
                    f"Ya existe un incidente con id {new_id}."
                )

        created = created_at if created_at is not None else datetime.now()
        persisted_resolved: datetime | None = None
        if resolved_status == "RESOLVED":
            persisted_resolved = resolved_at if resolved_at is not None else created
            if persisted_resolved < created:
                raise ValidationError(
                    "resolved_at no puede ser anterior a created_at."
                )

        triage = classify_incident_report(new_id, cleaned_text)
        open_duplicates = self._repository.find_open_duplicates(triage.duplicate_group_key)
        duplicate_ids = tuple(
            item.incident_id
            for item in open_duplicates
            if item.incident_id != new_id
        )

        incident = Incident(
            incident_id=new_id,
            title=cleaned_title,
            component=triage.component,
            severity=triage.severity,
            status=resolved_status,
            created_at=created,
            resolved_at=persisted_resolved,
            raw_text=cleaned_text,
            recommended_team=triage.recommended_team,
            duplicate_group_key=triage.duplicate_group_key,
        )
        self._repository.save_incident(incident)

        return CreationResult(
            incident_id=incident.incident_id,
            title=incident.title,
            raw_text=incident.raw_text,
            created_at=incident.created_at,
            status=incident.status,
            resolved_at=incident.resolved_at,
            severity=triage.severity,
            component=triage.component,
            rationale=triage.rationale,
            recommended_team=triage.recommended_team,
            duplicate_group_key=triage.duplicate_group_key,
            consistency_ratio=triage.consistency_ratio,
            is_duplicate=bool(duplicate_ids),
            duplicate_of=duplicate_ids,
        )

    def evaluate_incident_sla(
        self,
        incident_id: str,
        reference_time: datetime | None = None,
    ) -> SLAEvaluation:
        """Audita el SLA de un incidente persistido."""
        incident = self._repository.get_incident(incident_id.strip())
        if incident is None:
            raise IncidentNotFoundError(f"Incidente no encontrado: {incident_id}")
        evaluated_at = reference_time if reference_time is not None else datetime.now()
        if evaluated_at < incident.created_at:
            raise ValidationError(
                "reference_time no puede ser anterior a created_at del incidente."
            )
        return evaluate_sla_status(incident, evaluated_at)

    def get_active_incidents_summary(
        self,
        component_filter: str | None = None,
        reference_time: datetime | None = None,
    ) -> ActiveIncidentsSummary:
        """Resume los activos del catálogo en el instante pedido.

        Un filtro ausente, vacío o solo espacios lista todos los componentes.
        Cualquier otro valor se compara exacto, ya recortado.
        """
        evaluated_at = reference_time if reference_time is not None else datetime.now()
        views: list[ActiveIncidentView] = []
        breached_count = 0
        for incident in self._repository.list_active_incidents(
            _normalize_component_filter(component_filter)
        ):
            evaluation = evaluate_sla_status(incident, evaluated_at)
            if evaluation.is_breached:
                breached_count += 1
            views.append(
                ActiveIncidentView(
                    incident_id=incident.incident_id,
                    title=incident.title,
                    component=incident.component,
                    severity=incident.severity,
                    status=incident.status,
                    elapsed_minutes=evaluation.elapsed_minutes,
                    requires_escalation=evaluation.requires_escalation,
                )
            )
        views.sort(
            key=lambda view: (
                _SEVERITY_RANK[view.severity],
                -view.elapsed_minutes,
                view.incident_id,
            )
        )
        return ActiveIncidentsSummary(
            total_active=len(views),
            breached_count=breached_count,
            incidents=tuple(views),
        )
