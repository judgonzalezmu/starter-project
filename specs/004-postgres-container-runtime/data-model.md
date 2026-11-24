# Data Model: H004 Persistencia dual y runtime

**Feature**: `004-postgres-container-runtime`  
**Date**: 2026-11-24  
**Spec**: [spec.md](./spec.md) · **Research**: [research.md](./research.md)

H004 no añade campos al núcleo. `Incident`, `TriageResult`, `SLAEvaluation` y `SLARule` quedan como en H003. Lo nuevo es el estado operativo del almacén, la configuración que elige el motor y el esquema físico que ambos motores comparten.

## 1. OperationalHealth (aplicación)

Vista de `IncidentService.check_operational_health`. No se persiste y no es un estado de `Incident`.

| Campo | Valores | Regla |
| :--- | :--- | :--- |
| `status` | `ok` \| `error` | `ok` solo si `check_health()` acaba de devolver `True` |
| `database` | `connected` \| `unavailable` | Pareja fija: `ok`+`connected`, `error`+`unavailable` |

No hay otros campos. No incluye URL, host, motor ni texto del driver.

Origen: `IncidentRepositoryPort.check_health()` → `SELECT 1` en el adaptador activo, en esa llamada. Un `False` anterior no se reutiliza.

## 2. Configuración de persistencia

No es una entidad guardada. Es la entrada de `create_incident_repository`.

| Condición | Motor | Destino |
| :--- | :--- | :--- |
| `DATABASE_URL` ausente y argumento `None` | SQLite stdlib | `:memory:` (una base distinta por conexión) |
| `sqlite:///` + path | SQLite stdlib | path de archivo, o `:memory:` si el path es ese literal |
| `postgresql://` | `psycopg` | URL completa (usuario, clave, host, puerto, base, query de libpq) |
| Vacía, solo espacios, u otro esquema | ninguno | `ValueError` antes de abrir conexión; el proceso HTTP no arranca |

Validación:

- El mensaje de error no contiene el valor de la URL.
- No hay fallback a memoria cuando la variable existe y no es usable.
- `postgres://` (sin `ql`) es esquema no soportado.
- La comparación del esquema ignora mayúsculas; el resto de la URL no se normaliza a minúsculas.

## 3. PersistenceUnavailableError (aplicación)

Excepción del puerto (`src/application/ports.py`). La lanzan los adaptadores cuando `sqlite3.Error` o `psycopg.Error` impide completar `save_incident`, `get_incident`, `find_open_duplicates` o `list_active_incidents`.

No la lanza `check_health` (ese método devuelve `False`). No sustituye a:

| Excepción existente | Cuándo sigue aplicando |
| :--- | :--- |
| `ValidationError` | Entrada inválida y el almacén responde |
| `IncidentAlreadyExistsError` | El `incident_id` ya está guardado |
| `IncidentNotFoundError` | `get_incident` devuelve `None` porque la fila no está |

Un error de red o de conexión no es `None` ni lista vacía.

## 4. Esquema físico compartido

Ambos adaptadores aseguran este esquema al abrir una conexión (`CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`). Volver a conectar es seguro. No hay tabla de versiones ni scripts de migración.

### `sla_policies`

| Columna | Tipo | Regla |
| :--- | :--- | :--- |
| `severity` | `TEXT` | Clave primaria. Valores del núcleo: `P0`, `P1`, `P2`, `P3` |
| `max_resolution_minutes` | `INTEGER NOT NULL` | Copiado de `SLA_POLICY_TABLE` |
| `operates_24x7` | `INTEGER NOT NULL` | `1` o `0`, no un booleano nativo de PostgreSQL |

Semilla idempotente en cada conexión nueva: `INSERT OR REPLACE` (SQLite) o `ON CONFLICT (severity) DO UPDATE` (PostgreSQL), con las mismas filas de `SLA_POLICY_TABLE`.

### `incidents`

| Columna | Tipo | Regla |
| :--- | :--- | :--- |
| `incident_id` | `TEXT` | Clave primaria |
| `title` | `TEXT NOT NULL` | |
| `component` | `TEXT NOT NULL` | |
| `severity` | `TEXT NOT NULL` | `P0`–`P3` |
| `status` | `TEXT NOT NULL` | `OPEN`, `IN_PROGRESS`, `ESCALATION_REQUIRED`, `RESOLVED` |
| `created_at` | `TEXT NOT NULL` | ISO 8601 producido por `datetime.isoformat()` |
| `resolved_at` | `TEXT` | Nulo si no hay resolución; si no, el mismo ISO 8601 |
| `raw_text` | `TEXT NOT NULL` | Default `''` |
| `recommended_team` | `TEXT` | Equipo canónico o nulo |
| `duplicate_group_key` | `TEXT` | Clave canónica de dominio o nula |

Índices (nombres idénticos en los dos motores):

- `idx_incidents_component_status` sobre `(component, status)`
- `idx_incidents_dup_key` sobre `(duplicate_group_key, status)`

SQLite puede seguir aplicando `ALTER TABLE` defensivo si un archivo antiguo no tiene `raw_text`, `recommended_team` o `duplicate_group_key`. PostgreSQL crea esas columnas en el `CREATE TABLE` inicial y no depende de `ALTER`.

Upsert de incidente por `incident_id`: reemplaza la fila entera. La representación que vuelve a leer el núcleo es la misma en los dos motores porque las fechas no pasan por un tipo temporal del motor.

## 5. Relaciones

```text
DATABASE_URL
    → fábrica
        → SQLiteIncidentRepository  ──implementa──► IncidentRepositoryPort
        → PostgresIncidentRepository ──implementa──► IncidentRepositoryPort
                │
                ▼
         incidents / sla_policies
                │
                ▼
IncidentService.check_operational_health → OperationalHealth
        ▲
        ├── GET /health
        └── CLI health
```

El contenedor `db` (PostgreSQL 16) solo entra en esta relación cuando la URL es `postgresql://` y el hostname apunta a ese servicio. SQLite no usa `db`.

## 6. Transiciones

`Incident` no gana estados. La salud no tiene historial:

| Desde | Hacia | Disparador |
| :--- | :--- | :--- |
| proceso sin almacén resuelto | proceso no iniciado (HTTP) o comando rechazado (CLI) | URL vacía o esquema no soportado |
| `database=unavailable` | `database=connected` | una llamada posterior a `check_health` logra `SELECT 1` (reconexión incluida) |
| `database=connected` | `database=unavailable` | la llamada actual no logra `SELECT 1` |
| operación de negocio en curso | `PersistenceUnavailableError` | el driver falla durante save/get/list/duplicates |

No se cachea el último estado sano.

## 7. Servicios de runtime (no son tablas)

| Pieza | Identidad | Datos que guarda |
| :--- | :--- | :--- |
| Contenedor `api` | Proceso IncidentOps | Ninguno propio; habla con el motor elegido |
| Contenedor `db` | `postgres:16-alpine` | Volumen nominado con el directorio de datos de PostgreSQL |
| Imagen `api` | Build `uv` + `python:3.12-slim` | Código y dependencias; sin `.env`, sin `*.db`, sin `.venv` del host |

Las credenciales del servicio `db` llegan por variables de entorno del compose. El volumen sobrevive a `docker compose down` sin `-v` y se recrea vacío si se borra el volumen. El hito no define backups ni réplicas.
