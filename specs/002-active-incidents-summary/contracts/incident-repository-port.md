# Contract: `IncidentRepositoryPort`

**Owner**: `src/application/ports.py`  
**Adapter (H002)**: `src/adapters/outbound/sqlite_repository.py` → `SQLiteIncidentRepository`  
**Selection**: `src/adapters/outbound/factory.py` → `create_incident_repository`  
**Entities**: [data-model.md](../data-model.md)

El puerto es interno. Los operadores no lo invocan; HTTP y CLI pasan por `IncidentService`. Este contrato existe para que el adaptador sea sustituible y para la prueba de cumplimiento del protocolo.

## Protocol

`IncidentRepositoryPort` es un `typing.Protocol` con `@runtime_checkable`.

```text
save_incident(incident: Incident) -> None
get_incident(incident_id: str) -> Incident | None
find_open_duplicates(duplicate_group_key: str) -> list[Incident]
list_active_incidents(component_filter: str | None = None) -> list[Incident]
check_health() -> bool
```

Cumplimiento mínimo exigido en tests: `isinstance(SQLiteIncidentRepository(...), IncidentRepositoryPort)` es verdadero.

## Comportamiento

| Método | Comportamiento |
| :--- | :--- |
| `save_incident` | Inserta o reemplaza por `incident_id`. Persiste `resolved_at` (NULL si es `None`). Parámetros enlazados, sin concatenar valores en el SQL. |
| `get_incident` | Devuelve el `Incident` o `None`. Los instantes naive round-trip por ISO-8601. |
| `find_open_duplicates` | Forma parte del puerto. H002 no lo usa y no añade persistencia de la clave. `SQLiteIncidentRepository` devuelve `[]`. |
| `list_active_incidents` | Solo `OPEN` e `IN_PROGRESS`. `component_filter is None` no filtra componente. Con texto, igualdad exacta (el servicio ya hizo `strip`). No calcula SLA ni aplica el orden FR-011. |
| `check_health` | `True` tras `SELECT 1`. `False` si la operación SQLite falla. `GET /health` no lo usa en H002. |

## Obligación SQL de `SQLiteIncidentRepository`

Esquema, sembrado de `sla_policies` desde `SLA_POLICY_TABLE` e índice `idx_incidents_component_status` sobre `(component, status)`, como en [data-model.md](../data-model.md).

Lectura activa con componente (la variante sin componente omite la última condición):

```sql
SELECT i.incident_id, i.title, i.component, i.severity, i.status,
       i.created_at, i.resolved_at
FROM incidents AS i
INNER JOIN sla_policies AS p ON p.severity = i.severity
WHERE i.status IN ('OPEN', 'IN_PROGRESS')
  AND i.component = ?
```

El `JOIN` sustituye el N+1 de Semana 1. Las columnas de `sla_policies` no se mapean al dominio y no deciden `elapsed_minutes` ni `is_breached`.

Conexión: una instancia de repositorio por proceso de la app. `row_factory = sqlite3.Row`.

`seed_synthetic_incidents` puede vivir en la clase concreta para el benchmark. No forma parte del protocolo.

## Fábrica

`create_incident_repository(database_url: str | None = None) -> IncidentRepositoryPort`

| URL | Ruta SQLite |
| :--- | :--- |
| argumento `None` y variable ausente | `sqlite:///:memory:` → `:memory:` |
| `sqlite:///:memory:` | `:memory:` |
| `sqlite:///` + ruta | esa ruta (`C:/...` o relativa) |

Un esquema distinto, o `DATABASE_URL` definida y vacía, lanza `ValueError` sin incluir el valor de la URL en el mensaje.

Los inbound obtienen el repositorio solo por esta fábrica. No importan `sqlite3` ni `SQLiteIncidentRepository`.
