# Contract: `POST /api/v1/incidents`

**Feature**: H003  
**Adapter**: FastAPI inbound  
**Use case**: `IncidentService.create_incident`

## Request

- **Method / path**: `POST /api/v1/incidents`
- **Body** (`CreateIncidentRequest`, Pydantic v2):

| Field | Required | Type | Notes |
| :--- | :--- | :--- | :--- |
| `title` | yes | string | Empty/whitespace → 422 |
| `raw_text` | yes | string | Empty/whitespace → 422 |
| `incident_id` | no | string | Else `INC-<HEX8>` uppercase |
| `created_at` | no | string ISO-8601 naive | Else server now |
| `status` | no | string | Default `OPEN`; catalog only |
| `resolved_at` | no | string ISO-8601 naive | Rules for `RESOLVED` in spec |

## Success

- **Status**: `201 Created`
- **Body** (`IncidentCreatedResponse`): incident fields + full triage classification + `is_duplicate` (bool) + `duplicate_of` (string[])

## Errors

| Condition | HTTP |
| :--- | :--- |
| Validation (empty fields, bad status, bad timestamps, `resolved_at` < `created_at`) | `422` |
| `incident_id` already exists | `409` |

## Notes

- Duplicate alert never blocks persistence of a valid create.
- Delegates only to `IncidentService.create_incident`; no triage/SLA logic in the router.
