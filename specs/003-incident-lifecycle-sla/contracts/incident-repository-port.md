# Contract: `IncidentRepositoryPort` (H003 obligations)

**Location**: `src/application/ports.py`  
**Implementation**: `src/adapters/outbound/sqlite_repository.py`  
**Selection**: `src/adapters/outbound/factory.py` via `DATABASE_URL`

## Methods used by H003

| Method | Obligation |
| :--- | :--- |
| `save_incident(incident: Incident) -> None` | Parametrized upsert/insert by `incident_id`; persist new columns (`raw_text`, `recommended_team`, `duplicate_group_key`) |
| `get_incident(incident_id: str) -> Incident \| None` | `None` if missing; map all persisted columns |
| `find_open_duplicates(duplicate_group_key: str) -> list[Incident]` | Rows with same key and `status IN ('OPEN','IN_PROGRESS','ESCALATION_REQUIRED')`; use index `idx_incidents_dup_key` |

## Schema additions

```sql
-- columns on incidents (plus H002 columns)
raw_text TEXT NOT NULL DEFAULT ''
recommended_team TEXT
duplicate_group_key TEXT

CREATE INDEX IF NOT EXISTS idx_incidents_dup_key
ON incidents (duplicate_group_key, status)
```

## Unchanged H002 surface

- `list_active_incidents` still filters `OPEN` + `IN_PROGRESS` only
- `check_health` unchanged; `GET /health` still does not call it

## Forbidden

- Calculating SLA or inventing `duplicate_group_key` inside the repository
- Importing inbound adapters or FastAPI/Typer from outbound
