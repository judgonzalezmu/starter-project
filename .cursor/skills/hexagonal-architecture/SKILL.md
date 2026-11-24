---
name: hexagonal-architecture
description: >-
  Enforce IncidentOps hexagonal (ports & adapters) import boundaries, primary-
  adapter parity via IncidentService, and Ruff TID251/TID252 frontier checks.
  Use when adding or changing code under src/domain/, src/application/,
  src/adapters/, wiring DATABASE_URL/outbound factories, reviewing hexagonal
  dependencies, or configuring uv run ruff check src/.
---

# Hexagonal Architecture — IncidentOps (ADR-003)

Dependency direction: **adapters → application → domain**. Domain never depends
outward.

## Layer import rules

### `src/domain/`

**MAY**: Python stdlib only (typing, dataclasses, datetime, etc.) and other
modules inside `src.domain`.

**MUST NOT** import:

- Frameworks (FastAPI, Typer, Pydantic transport/API schemas, uvicorn)
- HTTP clients/servers or web middleware
- DB drivers, SQL, ORMs, connection pools
- `src.application`, `src.adapters`, or any other external layer

Nucleus: `models.py`, `triage_rules.py`, `sla_calculator.py`.

### `src/application/`

**MAY**: Python stdlib and `src.domain` only.

**MUST NOT** import:

- FastAPI, Typer, Pydantic request/response models
- DB drivers, ORMs, concrete repositories under `src.adapters.outbound`
- Any `src.adapters.*` module

Owns use cases (`services.py`, e.g. `IncidentService`) and secondary ports
(`ports.py`, e.g. `IncidentRepositoryPort` as `typing.Protocol`).

### `src/adapters/inbound/`

**MAY**: Delivery frameworks (FastAPI, Typer, Pydantic v2 for transport),
`src.application` (especially `IncidentService`), and
`src.adapters.outbound.factory` for obtaining outbound collaborators.

**MUST**:

- Delegate business behavior to `IncidentService` (or other application
  services); never reimplement triage/SLA/duplicates in the adapter
- Resolve persistence through `src.adapters.outbound.factory` (driven by
  `DATABASE_URL`), not by constructing concrete repos/drivers inline

**MUST NOT** import:

- DB drivers (`sqlite3` as app wiring, engines, ORMs) directly
- Concrete repository implementations under `src.adapters.outbound` (except via
  the factory module)

### `src/adapters/outbound/`

**MAY**: Infrastructure details (e.g. stdlib `sqlite3`), `src.domain` types, and
`src.application.ports` contracts.

**MUST**: Implement `IncidentRepositoryPort` (and other secondary ports) so
application code depends on the protocol, not the concrete adapter.

**MUST NOT**: Import inbound adapters (`src.adapters.inbound`) or delivery
frameworks to “reach up” into REST/CLI.

## Primary-adapter parity (REST ↔ CLI)

REST (`src/adapters/inbound/api/`) and CLI (`src/adapters/inbound/cli.py`) MUST
offer **parity**: the same product use case is invoked through the **same**
application entry point (e.g. both call `IncidentService.triage_incident`).

- Do not fork domain logic per channel
- Do not add a REST-only or CLI-only business path for the same capability
- Future MCP inbound MUST follow the same rule

## Static frontier validation (Ruff)

Boundaries are enforced statically with Ruff flake8-tidy-imports:

| Rule | Role |
| :--- | :--- |
| `TID251` | `banned-api` — forbid disallowed modules/packages per layer |
| `TID252` | `ban-relative-imports = "parents"` — ban parent relative imports that cross package edges |

Root `pyproject.toml` MUST include at least:

```toml
[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "TID"]
```

Layer-specific bans live in hierarchical `ruff.toml` files:

- `src/domain/ruff.toml`
- `src/application/ruff.toml`
- `src/adapters/inbound/ruff.toml`

(Outbound may add its own file when concrete bans are needed; inbound/domain/
application are mandatory for the current gate.)

**Canonical check** (MUST pass before merge of layer-touching changes):

```bash
uv run ruff check src/
```

When changing imports or adding adapters, update the matching layer `ruff.toml`
banned-api list so the new edge cannot silently regress.

## Agent checklist

1. New business rule → `src/domain/` only; wire through `IncidentService` if
   exposed.
2. New use case → `src/application/services.py` + port in `ports.py` if it needs
   persistence/IO.
3. New channel → inbound adapter that calls the existing service; keep REST/CLI
   (and MCP) parity.
4. New storage → outbound adapter implementing `IncidentRepositoryPort` + factory
   selection via `DATABASE_URL`.
5. Run `uv run ruff check src/` and fix any TID/E/F violations before finishing.
