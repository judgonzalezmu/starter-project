# Contract: CLI `create`

**Feature**: H003  
**Adapter**: Typer inbound (`src/adapters/inbound/cli.py`)  
**Use case**: `IncidentService.create_incident` (same as HTTP)

## Invocation

```text
uv run python -m src.adapters.inbound.cli create \
  --title "..." \
  --raw-text "..." \
  [--incident-id INC-...] \
  [--created-at 2026-11-06T17:00:00] \
  [--status OPEN] \
  [--resolved-at 2026-11-06T18:00:00]
```

## Success

- Exit code `0`
- Stdout: JSON with the same business payload as HTTP `201` body

## Errors

| Condition | Exit |
| :--- | :--- |
| Empty `title`/`raw_text`, bad `status`, bad timestamps, `resolved_at` < `created_at` | `1` |
| `incident_id` already exists | `1` |

Message on stderr; no misleading create JSON on failure.

## Parity

Same valid inputs + same `DATABASE_URL` store → same business JSON as `POST /api/v1/incidents`.
