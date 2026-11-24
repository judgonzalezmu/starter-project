"""Adaptador SQLite del puerto de incidentes.

Una conexión por instancia. El SLA no se calcula aquí: el JOIN solo garantiza
que la severidad existe en `sla_policies`.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from src.domain.models import Incident, SeverityLevel
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

_ACTIVE_BY_COMPONENT = _ACTIVE_COLUMNS + "  AND i.component = ?"

_OPEN_DUPLICATE_STATUSES = ("OPEN", "IN_PROGRESS", "ESCALATION_REQUIRED")


class SQLiteIncidentRepository:
    """Persiste incidentes en SQLite con el esquema heredado de Semana 1."""

    def __init__(self, db_path: str = ":memory:") -> None:
        # Una sola conexión vive con el proceso. FastAPI atiende el request en
        # otro hilo; sin este flag sqlite3 rechaza usar la conexión allí.
        self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cursor = self._connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sla_policies (
                severity TEXT PRIMARY KEY,
                max_resolution_minutes INTEGER NOT NULL,
                operates_24x7 INTEGER NOT NULL
            )
            """
        )
        cursor.execute(
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
        for column_sql in (
            "ALTER TABLE incidents ADD COLUMN raw_text TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE incidents ADD COLUMN recommended_team TEXT",
            "ALTER TABLE incidents ADD COLUMN duplicate_group_key TEXT",
        ):
            try:
                cursor.execute(column_sql)
            except sqlite3.OperationalError:
                pass
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_incidents_component_status
            ON incidents (component, status)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_incidents_dup_key
            ON incidents (duplicate_group_key, status)
            """
        )
        for rule in SLA_POLICY_TABLE.values():
            cursor.execute(
                """
                INSERT OR REPLACE INTO sla_policies
                    (severity, max_resolution_minutes, operates_24x7)
                VALUES (?, ?, ?)
                """,
                (
                    rule.severity,
                    rule.max_resolution_minutes,
                    1 if rule.operates_24x7 else 0,
                ),
            )
        self._connection.commit()

    def save_incident(self, incident: Incident) -> None:
        self._connection.execute(
            """
            INSERT OR REPLACE INTO incidents
                (incident_id, title, component, severity, status, created_at,
                 resolved_at, raw_text, recommended_team, duplicate_group_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        self._connection.commit()

    def get_incident(self, incident_id: str) -> Incident | None:
        row = self._connection.execute(
            f"""
            SELECT {_INCIDENT_COLUMNS}
            FROM incidents AS i
            WHERE i.incident_id = ?
            """,
            (incident_id,),
        ).fetchone()
        if row is None:
            return None
        return _incident_from_row(row)

    def find_open_duplicates(self, duplicate_group_key: str) -> list[Incident]:
        placeholders = ", ".join("?" for _ in _OPEN_DUPLICATE_STATUSES)
        rows = self._connection.execute(
            f"""
            SELECT {_INCIDENT_COLUMNS}
            FROM incidents AS i
            WHERE i.duplicate_group_key = ?
              AND i.status IN ({placeholders})
            """,
            (duplicate_group_key, *_OPEN_DUPLICATE_STATUSES),
        ).fetchall()
        return [_incident_from_row(row) for row in rows]

    def list_active_incidents(self, component_filter: str | None = None) -> list[Incident]:
        if component_filter is None:
            rows = self._connection.execute(_ACTIVE_COLUMNS).fetchall()
        else:
            rows = self._connection.execute(_ACTIVE_BY_COMPONENT, (component_filter,)).fetchall()
        return [_incident_from_row(row) for row in rows]

    def check_health(self) -> bool:
        try:
            self._connection.execute("SELECT 1")
        except sqlite3.Error:
            return False
        return True

    def seed_synthetic_incidents(self, total_records: int = 10000) -> None:
        """Puebla la base con registros sintéticos para el benchmark. Fuera del puerto."""
        components = [
            "payments-gateway",
            "auth-identity",
            "database-cluster",
            "reporting-api",
            "frontend-ui",
        ]
        severities: list[SeverityLevel] = ["P0", "P1", "P2", "P3"]
        statuses = ["RESOLVED", "RESOLVED", "RESOLVED", "OPEN", "IN_PROGRESS"]
        base_time = datetime(2026, 11, 1, 8, 0, 0)

        rows: list[tuple[str, str, str, str, str, str, str | None, str, None, None]] = []
        for idx in range(1, total_records + 1):
            severity = severities[idx % len(severities)]
            status = statuses[(idx * 3 + idx // 5) % len(statuses)]
            component = components[idx % len(components)]
            created = base_time + timedelta(minutes=((idx - 1) % 10000 + 1) * 2)
            resolved = (
                (created + timedelta(minutes=45)).isoformat() if status == "RESOLVED" else None
            )
            rows.append(
                (
                    f"INC-{idx:05d}",
                    f"Reporte sintético #{idx} en {component}",
                    component,
                    severity,
                    status,
                    created.isoformat(),
                    resolved,
                    "",
                    None,
                    None,
                )
            )

        self._connection.executemany(
            """
            INSERT OR REPLACE INTO incidents
                (incident_id, title, component, severity, status, created_at,
                 resolved_at, raw_text, recommended_team, duplicate_group_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._connection.commit()


def _incident_from_row(row: sqlite3.Row) -> Incident:
    resolved_at = row["resolved_at"]
    keys = row.keys()
    raw_text = row["raw_text"] if "raw_text" in keys and row["raw_text"] is not None else ""
    recommended_team = row["recommended_team"] if "recommended_team" in keys else None
    duplicate_group_key = (
        row["duplicate_group_key"] if "duplicate_group_key" in keys else None
    )
    return Incident(
        incident_id=row["incident_id"],
        title=row["title"],
        component=row["component"],
        severity=row["severity"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        resolved_at=datetime.fromisoformat(resolved_at) if resolved_at else None,
        raw_text=raw_text,
        recommended_team=recommended_team,  # type: ignore[arg-type]
        duplicate_group_key=duplicate_group_key,
    )
