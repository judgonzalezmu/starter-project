# Contract: CLI `sla`

**Feature**: H003  
**Adapter**: Typer inbound (`src/adapters/inbound/cli.py`)  
**Use case**: `IncidentService.evaluate_incident_sla` (same as HTTP)

## Invocation

```text
uv run python -m src.adapters.inbound.cli sla \
  --incident-id INC-... \
  [--reference-time 2026-11-09T09:00:00]
```

## Success

- Exit code `0`
- Stdout: JSON with the same business payload as HTTP `200` SLA body

## Errors

| Condition | Exit |
| :--- | :--- |
| Incident missing | `1` |
| Invalid / tz-aware `reference_time`, or `reference_time` < `created_at` | `1` |

No fabricated SLA metrics on failure.

## Parity

Same `incident_id` + same `reference_time` + same store → same business JSON as  
`GET /api/v1/incidents/{incident_id}/sla`.
