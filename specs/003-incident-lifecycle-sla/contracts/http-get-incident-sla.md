# Contract: `GET /api/v1/incidents/{incident_id}/sla`

**Feature**: H003  
**Adapter**: FastAPI inbound  
**Use case**: `IncidentService.evaluate_incident_sla`

## Request

- **Method / path**: `GET /api/v1/incidents/{incident_id}/sla`
- **Path**: `incident_id` (string)
- **Query**:
  - `reference_time` (optional, ISO-8601 naive string) — omit → evaluation at request time

## Success

- **Status**: `200 OK`
- **Body** (`SLAEvaluationResponse`), minimum fields:

| Field | Type |
| :--- | :--- |
| `incident_id` | string |
| `elapsed_minutes` | int |
| `allowed_minutes` | int |
| `remaining_minutes` | int |
| `is_breached` | bool |
| `requires_escalation` | bool |

## Errors

| Condition | HTTP |
| :--- | :--- |
| Incident missing | `404` |
| `reference_time` invalid/unreadable/tz-aware, or `< created_at` | `422` |

## Deterministic acceptance anchor (Escenario 3)

P2, `created_at=2026-11-06T17:00:00`, `reference_time=2026-11-09T09:00:00` →  
`elapsed_minutes=120`, `allowed_minutes=480`, `remaining_minutes=360`, `is_breached=false`, `requires_escalation=false`.

## Notes

- Domain policy: ADR-002; `resolved_at` wins over `reference_time` inside `evaluate_sla_status`.
- Router maps `IncidentNotFoundError` → 404, `ValidationError` → 422.
