"""Adaptador PostgreSQL del puerto de incidentes (psycopg, sin ORM)."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from src.application.ports import PersistenceUnavailableError
from src.domain.models import Incident
from src.domain.sla_calculator import SLA_POLICY_TABLE

_INCIDENT_COLUMNS = """
i.incident_id, i.title, i.component, i.severity, i.status,
i.created_at, i.resolved_at, i.raw_text, i.recommended_team, i.duplicate_group_key
"""

_ACTIVE_COLUMNS = f"""
SELECT {_INCIDENT_COLUMNS}
FROM incidents AS i
INNER JOIN sla_policies AS p ON p.severity = i.severity
WHERE i.status IN ('OPEN', 'IN_PROGRESS')
"""

_ACTIVE_BY_COMPONENT = _ACTIVE_COLUMNS + "  AND i.component = %s"

_OPEN_DUPLICATE_STATUSES = ("OPEN", "IN_PROGRESS", "ESCALATION_REQUIRED")
_CONNECT_TIMEOUT_SECONDS = 3


class PostgresIncidentRepository:
    """Persiste incidentes en PostgreSQL con el mismo esquema lógico que SQLite."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._connection: psycopg.Connection[Any] | None = None
        self._lock = threading.Lock()

    def save_incident(self, incident: Incident) -> None:
        with self._lock:
            try:
                conn = self._ensure_connection()
                conn.execute(
                    """
                    INSERT INTO incidents
                        (incident_id, title, component, severity, status, created_at,
                         resolved_at, raw_text, recommended_team, duplicate_group_key)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (incident_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        component = EXCLUDED.component,
                        severity = EXCLUDED.severity,
                        status = EXCLUDED.status,
                        created_at = EXCLUDED.created_at,
                        resolved_at = EXCLUDED.resolved_at,
                        raw_text = EXCLUDED.raw_text,
                        recommended_team = EXCLUDED.recommended_team,
                        duplicate_group_key = EXCLUDED.duplicate_group_key
                    """,
                    (
                        incident.incident_id,
                        incident.title,
                        incident.component,
                        incident.severity,
                        incident.status,
                        incident.created_at.isoformat(),
                        incident.resolved_at.isoformat() if incident.resolved_at else None,
                        incident.raw_text,
                        incident.recommended_team,
                        incident.duplicate_group_key,
                    ),
                )
                conn.commit()
            except psycopg.Error as exc:
                self._recover_after_error()
                raise PersistenceUnavailableError(
                    "El almacén de datos no está disponible."
                ) from exc

    def get_incident(self, incident_id: str) -> Incident | None:
        with self._lock:
            try:
                conn = self._ensure_connection()
                row = conn.execute(
                    f"""
                    SELECT {_INCIDENT_COLUMNS}
                    FROM incidents AS i
                    WHERE i.incident_id = %s
                    """,
                    (incident_id,),
                ).fetchone()
                if row is None:
                    return None
                return _incident_from_row(row)
            except psycopg.Error as exc:
                self._recover_after_error()
                raise PersistenceUnavailableError(
                    "El almacén de datos no está disponible."
                ) from exc

    def find_open_duplicates(self, duplicate_group_key: str) -> list[Incident]:
        placeholders = ", ".join("%s" for _ in _OPEN_DUPLICATE_STATUSES)
        with self._lock:
            try:
                conn = self._ensure_connection()
                rows = conn.execute(
                    f"""
                    SELECT {_INCIDENT_COLUMNS}
                    FROM incidents AS i
                    WHERE i.duplicate_group_key = %s
                      AND i.status IN ({placeholders})
                    """,
                    (duplicate_group_key, *_OPEN_DUPLICATE_STATUSES),
                ).fetchall()
                return [_incident_from_row(row) for row in rows]
            except psycopg.Error as exc:
                self._recover_after_error()
                raise PersistenceUnavailableError(
                    "El almacén de datos no está disponible."
                ) from exc

    def list_active_incidents(self, component_filter: str | None = None) -> list[Incident]:
        with self._lock:
            try:
                conn = self._ensure_connection()
                if component_filter is None:
                    rows = conn.execute(_ACTIVE_COLUMNS).fetchall()
                else:
                    rows = conn.execute(_ACTIVE_BY_COMPONENT, (component_filter,)).fetchall()
                return [_incident_from_row(row) for row in rows]
            except psycopg.Error as exc:
                self._recover_after_error()
                raise PersistenceUnavailableError(
                    "El almacén de datos no está disponible."
                ) from exc

    def check_health(self) -> bool:
        with self._lock:
            try:
                conn = self._ensure_connection()
                conn.execute("SELECT 1")
                return True
            except psycopg.Error:
                self._recover_after_error()
                return False

    def _ensure_connection(self) -> psycopg.Connection[Any]:
        if self._connection is not None and not self._connection.closed:
            return self._connection
        self._connection = psycopg.connect(
            self._database_url,
            connect_timeout=_CONNECT_TIMEOUT_SECONDS,
            row_factory=dict_row,
        )
        self._init_schema(self._connection)
        return self._connection

    def _init_schema(self, conn: psycopg.Connection[Any]) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sla_policies (
                severity TEXT PRIMARY KEY,
                max_resolution_minutes INTEGER NOT NULL,
                operates_24x7 INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                incident_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                component TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                raw_text TEXT NOT NULL DEFAULT '',
                recommended_team TEXT,
                duplicate_group_key TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_incidents_component_status
            ON incidents (component, status)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_incidents_dup_key
            ON incidents (duplicate_group_key, status)
            """
        )
        for rule in SLA_POLICY_TABLE.values():
            conn.execute(
                """
                INSERT INTO sla_policies
                    (severity, max_resolution_minutes, operates_24x7)
                VALUES (%s, %s, %s)
                ON CONFLICT (severity) DO UPDATE SET
                    max_resolution_minutes = EXCLUDED.max_resolution_minutes,
                    operates_24x7 = EXCLUDED.operates_24x7
                """,
                (
                    rule.severity,
                    rule.max_resolution_minutes,
                    1 if rule.operates_24x7 else 0,
                ),
            )
        conn.commit()

    def _recover_after_error(self) -> None:
        if self._connection is None:
            return
        try:
            self._connection.rollback()
        except psycopg.Error:
            pass
        try:
            self._connection.close()
        except psycopg.Error:
            pass
        self._connection = None


def _incident_from_row(row: dict[str, Any]) -> Incident:
    resolved_at = row.get("resolved_at")
    raw_text = row.get("raw_text")
    return Incident(
        incident_id=row["incident_id"],
        title=row["title"],
        component=row["component"],
        severity=row["severity"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        resolved_at=datetime.fromisoformat(resolved_at) if resolved_at else None,
        raw_text=raw_text if raw_text is not None else "",
        recommended_team=row.get("recommended_team"),
        duplicate_group_key=row.get("duplicate_group_key"),
    )
