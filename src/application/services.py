"""Servicios de aplicación compartidos por los adaptadores inbound."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.application.ports import IncidentRepositoryPort
from src.domain.models import IncidentStatus, SeverityLevel, TriageResult
from src.domain.sla_calculator import evaluate_sla_status
from src.domain.triage_rules import classify_incident_report

_SEVERITY_RANK: dict[SeverityLevel, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


class ValidationError(Exception):
    """Entrada inválida para un caso de uso (triaje o instante de evaluación)."""


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


def parse_reference_time(raw: str | None) -> datetime | None:
    """Normaliza el instante de evaluación que envían HTTP y CLI.

    `None` (parámetro omitido) deja que el caso de uso use el reloj.
    Una cadena vacía, un instante con desplazamiento o un texto ilegible
    levantan `ValidationError` antes de leer el catálogo.
    """
    if raw is None:
        return None
    if raw.strip() == "":
        raise ValidationError("reference_time no es un instante ISO-8601 válido.")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError("reference_time no es un instante ISO-8601 válido.") from exc
    if parsed.tzinfo is not None:
        raise ValidationError("reference_time no es un instante ISO-8601 válido.")
    return parsed


def _normalize_component_filter(component_filter: str | None) -> str | None:
    if component_filter is None:
        return None
    stripped = component_filter.strip()
    if stripped == "":
        return None
    return stripped


class IncidentService:
    """Orquesta casos de uso de incidentes sin acoplarse a REST ni CLI."""

    def __init__(self, repository: IncidentRepositoryPort) -> None:
        self._repository = repository

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
