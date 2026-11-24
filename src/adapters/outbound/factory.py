"""Selección del adaptador de persistencia a partir de DATABASE_URL."""

from __future__ import annotations

import os

from src.adapters.outbound.postgres_repository import PostgresIncidentRepository
from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.application.ports import IncidentRepositoryPort

_SQLITE_PREFIX = "sqlite:///"
_POSTGRES_PREFIX = "postgresql://"
_DEFAULT_URL = "sqlite:///:memory:"
_EMPTY_MSG = "DATABASE_URL está definida pero vacía."
_UNSUPPORTED_MSG = (
    "Esquema de base de datos no soportado. Solo se admite sqlite:/// y postgresql://."
)


def create_incident_repository(database_url: str | None = None) -> IncidentRepositoryPort:
    """Abre el repositorio indicado por el argumento o por `DATABASE_URL`.

    Si el argumento es `None` y la variable no existe, usa `sqlite:///:memory:`.
    Una variable/argumento en blanco, o un esquema distinto, lanza `ValueError`
    sin incluir el valor de la URL. PostgreSQL no abre socket en la fábrica.
    """
    resolved = _resolve_url(database_url)
    trimmed = resolved.strip()
    if trimmed == "":
        raise ValueError(_EMPTY_MSG)

    lowered = trimmed.lower()
    if lowered.startswith(_POSTGRES_PREFIX):
        return PostgresIncidentRepository(trimmed)

    if lowered.startswith(_SQLITE_PREFIX):
        sqlite_path = trimmed[len(_SQLITE_PREFIX) :]
        if sqlite_path == "":
            raise ValueError(_UNSUPPORTED_MSG)
        return SQLiteIncidentRepository(sqlite_path)

    raise ValueError(_UNSUPPORTED_MSG)


def _resolve_url(database_url: str | None) -> str:
    if database_url is not None:
        if database_url.strip() == "":
            raise ValueError(_EMPTY_MSG)
        return database_url
    from_env = os.environ.get("DATABASE_URL")
    if from_env is None:
        return _DEFAULT_URL
    if from_env.strip() == "":
        raise ValueError(_EMPTY_MSG)
    return from_env
