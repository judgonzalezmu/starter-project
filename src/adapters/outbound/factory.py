"""Selección del adaptador de persistencia a partir de DATABASE_URL."""

from __future__ import annotations

import os

from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.application.ports import IncidentRepositoryPort

_SQLITE_PREFIX = "sqlite:///"
_DEFAULT_URL = "sqlite:///:memory:"


def create_incident_repository(database_url: str | None = None) -> IncidentRepositoryPort:
    """Abre el repositorio indicado por el argumento o por `DATABASE_URL`.

    Si el argumento es `None` y la variable no existe, usa `sqlite:///:memory:`.
    Un esquema distinto, o la variable definida y en blanco, lanza `ValueError`
    sin incluir el valor de la URL.
    """
    resolved = _resolve_url(database_url)
    if not resolved.startswith(_SQLITE_PREFIX):
        raise ValueError("Esquema de base de datos no soportado. Solo se admite sqlite:///")
    sqlite_path = resolved.removeprefix(_SQLITE_PREFIX)
    if sqlite_path == "":
        raise ValueError("Esquema de base de datos no soportado. Solo se admite sqlite:///")
    return SQLiteIncidentRepository(sqlite_path)


def _resolve_url(database_url: str | None) -> str:
    if database_url is not None:
        return database_url
    from_env = os.environ.get("DATABASE_URL")
    if from_env is None:
        return _DEFAULT_URL
    if from_env.strip() == "":
        raise ValueError("DATABASE_URL está definida pero vacía. Solo se admite sqlite:///")
    return from_env
