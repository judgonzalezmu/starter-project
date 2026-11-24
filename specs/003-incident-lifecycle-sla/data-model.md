# Data Model: H003 Ciclo de vida, duplicados y consulta SLA

**Date**: 2026-11-23  
**Spec**: [spec.md](./spec.md)  
**Research**: [research.md](./research.md)

## Entities

### TeamName (type alias)

`Literal["Backend-Core", "Platform-SRE", "Data-DBA", "Security-IAM"]` — catálogo cerrado de la constitución.

### Incident (domain, extended)

| Field | Type | Required | Notes |
| :--- | :--- | :--- | :--- |
| `incident_id` | `str` | yes | Cliente o autogenerado `INC-<HEX8>` mayúsculas |
| `title` | `str` | yes | No vacío tras `strip` |
| `component` | `str` | yes | Sale del triaje al crear |
| `severity` | `SeverityLevel` | yes | `P0`\|`P1`\|`P2`\|`P3` |
| `status` | `IncidentStatus` | yes | Default alta: `OPEN` |
| `created_at` | `datetime` | yes | Naive; default `now` |
| `resolved_at` | `datetime \| None` | no | Obligatorio en efecto si `RESOLVED` (default = `created_at`) |
| `raw_text` | `str` | yes (default `""`) | Texto del reporte persistido |
| `recommended_team` | `TeamName \| None` | no | Del triaje |
| `duplicate_group_key` | `str \| None` | no | Clave canónica del dominio |

### TriageResult (domain, reused)

Sin cambio de campos de negocio. `recommended_team` tipado preferentemente como `TeamName`. Produce la clasificación completa embebida en la respuesta de creación (`severity`, `component`, `rationale`, `recommended_team`, `duplicate_group_key`, `consistency_ratio`).

### CreationResult (application view)

No es esquema Pydantic. Incluye los datos del `Incident` persistido, los campos de clasificación del `TriageResult`, y:

| Field | Type | Notes |
| :--- | :--- | :--- |
| `is_duplicate` | `bool` | `true` si hay al menos un equivalente abierto |
| `duplicate_of` | `list[str]` | Ids abiertos equivalentes; sin el id recién creado ni `RESOLVED` |

### SLAEvaluation (domain, reused)

Campos mínimos expuestos al operador (FR-013): `incident_id`, `elapsed_minutes`, `allowed_minutes`, `remaining_minutes`, `is_breached`, `requires_escalation`. Transporte puede omitir `severity` si el contrato HTTP lo lista como mínimo; incluir `severity` en JSON es compatible si ya existe en el dataclass (no contradice el mínimo).

## Validation rules

| Rule | Effect |
| :--- | :--- |
| `title` / `raw_text` vacíos o solo espacios | Rechazo; no persistir |
| `status` ∉ catálogo | Rechazo |
| `incident_id` ya existe | Conflicto; no sobrescribir |
| `status=RESOLVED` y `resolved_at < created_at` | Rechazo |
| `status≠RESOLVED` y cliente envía `resolved_at` | Ignorar; no persistir resolución |
| `reference_time` ilegible / con tz / vacío | Rechazo SLA |
| `reference_time < created_at` | Rechazo SLA (sin métricas) |
| Incidente inexistente en SLA | No encontrado |

## State transitions (this feature)

Al **alta** únicamente (transiciones posteriores fuera de alcance):

```text
(cliente) → OPEN | IN_PROGRESS | ESCALATION_REQUIRED | RESOLVED
default → OPEN
```

No hay endpoint/comando H003 para cambiar `status` después de creado.

### Open-duplicate set (FR-009)

Cuenta para `duplicate_of`: `OPEN`, `IN_PROGRESS`, `ESCALATION_REQUIRED`.  
Excluye: `RESOLVED`, el `incident_id` recién creado.

### Active summary set (H002, unchanged)

`OPEN`, `IN_PROGRESS` only.

## Persistence mapping (SQLite)

Tabla `incidents` (columnas H003 nuevas en **negrita** conceptual):

- `incident_id` PK
- `title`, `component`, `severity`, `status`
- `created_at`, `resolved_at`
- **`raw_text`**, **`recommended_team`**, **`duplicate_group_key`**

Índices:

- `idx_incidents_component_status` (H002)
- `idx_incidents_dup_key` on `(duplicate_group_key, status)` (H003)

`sla_policies` sin cambios (sembrada desde `SLA_POLICY_TABLE`).

## Relationships

```text
TriageResult ──classifies──► Incident (al create)
Incident.duplicate_group_key ──matched by──► find_open_duplicates → [Incident]
Incident ──evaluated by──► SLAEvaluation
```
