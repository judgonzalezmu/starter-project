# Quickstart: Validate H003 locally

**Feature**: `003-incident-lifecycle-sla`  
**Contracts**: [contracts/](./contracts/) · **Model**: [data-model.md](./data-model.md)

## Prerequisites

```bash
uv sync --group dev
```

Optional file DB for manual parity (POSIX path on Windows):

```powershell
$env:DATABASE_URL = "sqlite:///$($PWD.Path.Replace('\','/'))/data/h003-demo.db"
```

## Gates (must pass)

```bash
uv run ruff check src/
uv run python -m src.domain.triage_rules
uv run python -m src.domain.sla_calculator
uv run pytest -v
```

Expect Spec 001/002 green and five `test_bdd_*` in `tests/test_spec_003_lifecycle_sla.py` green.

## Manual create (HTTP)

```bash
uv run uvicorn src.adapters.inbound.api.app:create_app --factory --reload
```

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/incidents ^
  -H "Content-Type: application/json" ^
  -d "{\"title\":\"Pagos 502\",\"raw_text\":\"...payments gateway HTTP 502...\"}"
```

Expect `201`, classification fields, `is_duplicate` / `duplicate_of`.

## Manual SLA (HTTP) — Escenario 3 numbers

Create (or seed) a **P2** incident with `created_at=2026-11-06T17:00:00`, then:

```text
GET /api/v1/incidents/{id}/sla?reference_time=2026-11-09T09:00:00
```

Expect `elapsed_minutes=120`, `allowed_minutes=480`, `remaining_minutes=360`, `is_breached=false`, `requires_escalation=false`.

## Manual CLI parity

```bash
uv run python -m src.adapters.inbound.cli create --title "..." --raw-text "..."
uv run python -m src.adapters.inbound.cli sla --incident-id INC-... --reference-time 2026-11-09T09:00:00
```

Same `DATABASE_URL` as the API process → same business JSON as HTTP.

## Out of scope checks

- Do not expect auth, pagination, post-create status transitions, or MCP.
- `GET /api/v1/incidents/summary` remains H002 behavior (`OPEN`/`IN_PROGRESS` only).
