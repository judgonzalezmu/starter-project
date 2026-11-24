# Data Model: H002 Resumen de incidentes activos

**Date**: 2026-11-23  
**Spec**: [spec.md](./spec.md)  
**Contracts**: [contracts/](./contracts/)

H002 es de solo lectura sobre el catálogo persistido. No hay transiciones de estado en este hito.

## Incident (dominio, persistido)

Entidad existente en `src/domain/models.py`. H002 no añade campos.

| Campo | Tipo | Reglas |
| :--- | :--- | :--- |
| `incident_id` | `str` | Identidad. Clave primaria en SQLite. |
| `title` | `str` | Texto del incidente; se devuelve tal cual en el detalle. |
| `component` | `str` | Coincidencia exacta del filtro, después de `strip` en el servicio. |
| `severity` | `P0` \| `P1` \| `P2` \| `P3` | `Literal`, no Enum. Debe existir en `sla_policies` para que el `INNER JOIN` lo devuelva. |
| `status` | `OPEN` \| `IN_PROGRESS` \| `ESCALATION_REQUIRED` \| `RESOLVED` | Activo en el resumen solo si es `OPEN` o `IN_PROGRESS`. |
| `created_at` | `datetime` naive | ISO-8601 sin desplazamiento, persistido con `isoformat`. |
| `resolved_at` | `datetime` naive \| `None` | Si está presente, ADR-002 lo usa como fin del SLA en lugar de `reference_time`. |

Relación: un incidente tiene una severidad; la fila de `sla_policies` de esa severidad debe existir. El cálculo de minutos no lee esa fila: usa `evaluate_sla_status`.

## SLAEvaluation (dominio, no persistido, no expuesto)

Salida actual de `evaluate_sla_status`. El caso de uso consume `elapsed_minutes`, `is_breached` y `requires_escalation`. El JSON del operador no incluye `allowed_minutes`, `remaining_minutes` ni `is_breached` (el incumplimiento viaja agregado en `breached_count`).

Reglas que este hito no modifica:

- P0/P1 acumulan tiempo 24/7; P2/P3 solo Lun–Vie `[08:00, 18:00)`.
- Los segundos se truncan a minutos una sola vez.
- Incumplido cuando `elapsed_minutes > max_resolution_minutes`.
- Escalamiento al 75 % solo si el estado no es `RESOLVED` y no está incumplido.

## ActiveIncidentView (aplicación)

Proyección de un activo ya evaluado. No es esquema de transporte.

| Campo | Tipo | Origen |
| :--- | :--- | :--- |
| `incident_id` | `str` | `Incident` |
| `title` | `str` | `Incident` |
| `component` | `str` | `Incident` |
| `severity` | `P0`–`P3` | `Incident` |
| `status` | `OPEN` \| `IN_PROGRESS` | `Incident` |
| `elapsed_minutes` | `int` | `SLAEvaluation` |
| `requires_escalation` | `bool` | `SLAEvaluation` |

## ActiveIncidentsSummary (aplicación)

| Campo | Tipo | Regla |
| :--- | :--- | :--- |
| `total_active` | `int` | `len(incidents)` del conjunto ya filtrado. |
| `breached_count` | `int` | Cuántos de esos activos tienen `is_breached`. |
| `incidents` | secuencia de `ActiveIncidentView` | Orden FR-011: severidad `P0`→`P3`, `elapsed_minutes` descendente, `incident_id` lexicográfico ascendente. |

Validación de entrada del caso de uso:

| Entrada | Efecto |
| :--- | :--- |
| `component_filter` omitido, vacío o espacios | Sin filtro. |
| `component_filter` con texto | Coincidencia exacta del valor ya recortado. Componente desconocido → resumen vacío exitoso. |
| `reference_time` omitido | `datetime.now()` naive en el momento de la consulta. |
| `reference_time` ilegible | `ValidationError` antes de leer el catálogo. HTTP 422 / CLI exit 1. |

## Esquemas de transporte (inbound)

`ActiveIncidentItem` refleja `ActiveIncidentView`. `ActiveIncidentsSummaryResponse` refleja `ActiveIncidentsSummary`. Definidos con Pydantic v2 en `src/adapters/inbound/api/schemas.py`. No los importa el dominio ni la aplicación.

## IncidentRepositoryPort (aplicación)

Puerto de [contracts/incident-repository-port.md](./contracts/incident-repository-port.md). Operaciones:

- `save_incident` persiste o reemplaza un `Incident`.
- `get_incident` lo recupera o devuelve `None`.
- `find_open_duplicates(duplicate_group_key)` forma parte del puerto. H002 no lo usa y no añade persistencia de la clave. `SQLiteIncidentRepository` devuelve `[]`.
- `list_active_incidents` devuelve activos, con filtro de componente opcional, sin orden de presentación (el orden FR-011 lo aplica el servicio después del SLA).
- `check_health` informa si el almacén responde.

El resumen no llama a `save_incident`, `find_open_duplicates` ni `check_health`. Esos métodos existen para que el adaptador cumpla el puerto completo.

## Tablas SQLite (outbound)

`sla_policies`

| Columna | Tipo | Regla |
| :--- | :--- | :--- |
| `severity` | `TEXT` PK | `P0`…`P3` |
| `max_resolution_minutes` | `INTEGER NOT NULL` | Copia de `SLA_POLICY_TABLE` al iniciar |
| `operates_24x7` | `INTEGER NOT NULL` | `1` / `0` |

`incidents`

| Columna | Tipo | Regla |
| :--- | :--- | :--- |
| `incident_id` | `TEXT` PK | |
| `title` | `TEXT NOT NULL` | |
| `component` | `TEXT NOT NULL` | |
| `severity` | `TEXT NOT NULL` | |
| `status` | `TEXT NOT NULL` | |
| `created_at` | `TEXT NOT NULL` | ISO-8601 naive |
| `resolved_at` | `TEXT` | NULL si sigue abierto |

Índice: `idx_incidents_component_status` sobre `(component, status)`.

## Transiciones de estado

H002 no crea, no actualiza y no cierra incidentes. `RESOLVED` y `ESCALATION_REQUIRED` pueden existir en el catálogo y quedan fuera del resumen. El registro y el cambio de ciclo de vida siguen en H003.

## Catálogo de aceptación

Instante fijo: `2026-11-20T12:00:00` (viernes, dentro de `[08:00, 18:00)`). Los duraciones de abajo son minutos enteros, así que el truncado de ADR-002 no las altera. P3 cae en horario hábil de ese viernes; el recorte de fin de semana sigue cubierto por las pruebas de dominio ya existentes, no por este catálogo.

| incident_id | component | severity | status | created_at | Qué demuestra |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `INC-A` | `payments-gateway` | `P0` | `OPEN` | `2026-11-20T10:00:00` | 120 min, incumplido, `requires_escalation=false` |
| `INC-B` | `payments-gateway` | `P0` | `OPEN` | `2026-11-20T11:10:00` | 50 min, no incumplido, `requires_escalation=true` (umbral P0 = 45) |
| `INC-C` | `auth-identity` | `P1` | `IN_PROGRESS` | `2026-11-20T11:00:00` | 60 min, dentro de SLA (máx. 240, umbral 180) |
| `INC-M` | `reporting-api` | `P3` | `OPEN` | `2026-11-20T11:00:00` | 60 min hábiles; empata con `INC-Z` y va antes por id |
| `INC-Z` | `reporting-api` | `P3` | `OPEN` | `2026-11-20T11:00:00` | Mismo minuto que `INC-M`; id posterior |
| `INC-D` | `payments-gateway` | `P0` | `RESOLVED` | `2026-11-20T08:00:00` | Excluido aunque el componente coincida |
| `INC-E` | `reporting-api` | `P2` | `ESCALATION_REQUIRED` | `2026-11-20T08:00:00` | Excluido |

Títulos libres, estables dentro de un test, y `resolved_at` solo en `INC-D` (cualquier instante ≥ `created_at`).

Resultado global en ese instante:

- `total_active=5`, `breached_count=1`
- Orden: `INC-A`, `INC-B`, `INC-C`, `INC-M`, `INC-Z`

Resultado `component=payments-gateway`:

- `total_active=2`, `breached_count=1`
- Orden: `INC-A`, `INC-B`
- `INC-D` no aparece

Resultado `component` desconocido, o catálogo sin activos: `total_active=0`, `breached_count=0`, `incidents=[]`.

`component` en blanco o solo espacios produce el mismo JSON que el global.
