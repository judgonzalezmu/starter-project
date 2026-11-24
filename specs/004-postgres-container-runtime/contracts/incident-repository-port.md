# Contract: `IncidentRepositoryPort` (H004)

**Feature**: H004  
**Port**: `src/application/ports.py`  
**Adapters**: `SQLiteIncidentRepository`, `PostgresIncidentRepository`  
**Factory**: [database-url.md](./database-url.md)

El puerto de H002/H003 no cambia de operaciones ni de significado. H004 fija la salud, el fallo explícito y la paridad física entre motores.

## Operaciones de negocio (sin cambio de contrato)

| Método | Éxito | Si el driver no puede ejecutar |
| :--- | :--- | :--- |
| `save_incident(incident)` | Inserta o reemplaza por `incident_id` | `PersistenceUnavailableError` |
| `get_incident(incident_id)` | `Incident` o `None` si la fila no existe | `PersistenceUnavailableError` (no `None`) |
| `find_open_duplicates(duplicate_group_key)` | Abiertos con esa clave (`OPEN`, `IN_PROGRESS`, `ESCALATION_REQUIRED`) | `PersistenceUnavailableError` (no `[]`) |
| `list_active_incidents(component_filter=None)` | `OPEN` e `IN_PROGRESS` | `PersistenceUnavailableError` (no `[]`) |

Los instantes que entran y salen son `datetime` naive del núcleo. En tabla viajan como TEXT ISO 8601. Ver [data-model.md](../data-model.md).

`seed_synthetic_incidents` sigue fuera del puerto, solo en el adaptador SQLite del benchmark.

## Salud

```text
check_health() -> bool
```

- Ejecuta una consulta equivalente a `SELECT 1` contra la conexión actual.
- `True`: la consulta terminó.
- `False`: no hubo conexión o la consulta lanzó error del driver.
- No lanza `PersistenceUnavailableError`.
- No memoriza el booleano. Una llamada posterior puede reconectar.
- PostgreSQL: al conectar, `connect_timeout=3`. SQLite: apertura local en el constructor, como hoy (`check_same_thread=False`).

## Esquema

Al establecer conexión, el adaptador crea tablas e índices si faltan y siembra `sla_policies` desde `SLA_POLICY_TABLE`. Repetir el arranque no duplica filas de política ni exige DDL manual. Detalle de columnas: [data-model.md](../data-model.md).

## Paridad observable

Para el mismo `Incident` guardado y leído en cualquiera de los dos motores:

- mismos identificadores, textos, severidad, estado y equipo;
- `created_at` y `resolved_at` round-trip por `isoformat()` / `fromisoformat()`;
- `operates_24x7` almacenado como entero `1`/`0`.

La diferencia permitida es solo el dialecto (`?` frente a `%s`, `INSERT OR REPLACE` frente a `ON CONFLICT DO UPDATE`). El dominio no importa ninguno de los dos drivers.

## Frontera

- `src/domain/` no importa `sqlite3` ni `psycopg`.
- `src/application/` no importa drivers ni adaptadores concretos.
- Inbound obtiene el puerto solo con `create_incident_repository`.
- Ruff debe prohibir `psycopg` en dominio, aplicación e inbound, y prohibir `src.adapters.outbound.postgres_repository` en inbound (igual que ya prohíbe el adaptador SQLite).
