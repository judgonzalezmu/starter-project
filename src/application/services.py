"""Servicios de aplicación compartidos por los adaptadores inbound."""

from __future__ import annotations

from src.domain.models import TriageResult
from src.domain.triage_rules import classify_incident_report


class ValidationError(Exception):
    """Entrada de triaje inválida (vacía o solo espacios tras strip)."""


class IncidentService:
    """Orquesta casos de uso de incidentes sin acoplarse a REST ni CLI."""

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
