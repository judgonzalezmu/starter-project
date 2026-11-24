"""Puertos secundarios de la aplicación. Los adaptadores outbound los implementan."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.models import Incident


@runtime_checkable
class IncidentRepositoryPort(Protocol):
    """Contrato de persistencia de incidentes. La aplicación no conoce el motor."""

    def save_incident(self, incident: Incident) -> None:
        """Inserta o reemplaza un incidente por `incident_id`."""

    def get_incident(self, incident_id: str) -> Incident | None:
        """Recupera un incidente o `None` si no existe."""

    def find_open_duplicates(self, duplicate_group_key: str) -> list[Incident]:
        """Busca activos con la misma clave de duplicado. H002 no empareja."""

    def list_active_incidents(self, component_filter: str | None = None) -> list[Incident]:
        """Devuelve incidentes `OPEN` e `IN_PROGRESS`, sin orden de presentación."""

    def check_health(self) -> bool:
        """Informa si el almacén responde."""
