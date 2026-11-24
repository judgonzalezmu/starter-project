---
name: bdd-acceptance
description: >-
  Author Dan North–style Given/When/Then BDD scenarios in spec.md with ubiquitous
  business language, and map each scenario 1:1 to test_bdd_* acceptance tests
  using FastAPI TestClient and Typer CliRunner on isolated storage. Use when
  writing or updating specs/, acceptance criteria, tests/ BDD cases, Spec Kit
  specify/tasks/implement acceptance, or verifying uv run pytest -v.
---

# BDD Acceptance — IncidentOps

Acceptance is specified in `spec.md` (or `specs/<id>-*.md`) and proven by
automated tests under `tests/`. Spec language stays in the business domain;
tests exercise the **inbound adapters** (REST + CLI) that call the same use
case.

## Writing BDD scenarios (Dan North) in `spec.md`

Use **Given / When / Then** in the ubiquitous language of operators and
incidents — not implementation jargon.

### Structure

```markdown
### Escenario N — <título de negocio observable>

**Given** <contexto de negocio / precondiciones observables>
**When** <acción del actor vía canal de producto (HTTP o CLI)>
**Then** <resultado de negocio observable + criterios de aceptación>
```

### Vocabulary rules

**DO** write with domain terms: severidad, componente, equipo sugerido,
agrupación de duplicados, incidente activo, incumplimiento de SLA, reporte,
pasarela de pagos, cuenta bloqueada.

**DO NOT** leak into the scenario text:

- Python class/module names (`IncidentService`, `TriageResult`, `sqlite3`)
- SQL table/column names or schema details
- Internal ports, factories, or package paths (`src.domain…`)

Transport facts that are part of the **product contract** (route, status code,
CLI subcommand, exit code, JSON fields the operator sees) MAY appear in When/
Then when the spec defines that channel. Keep them as external behavior, not as
class design.

### Quality bar (Dan North)

- One scenario = one behavior worth caring about
- Title describes the outcome in business terms
- Given sets state; When is a single primary action; Then asserts observables
- Prefer concrete examples (sample report text / incident ids) over abstract
  placeholders when they fix ambiguity

### Example (good)

```markdown
### Escenario 1 — Caída crítica HTTP 502 en pasarela de pagos

**Given** un reporte de pasarela de pagos con HTTP 502 e impacto a comercios
**When** un operador clasifica el reporte por la API de triaje
**Then** la severidad es P0, el equipo sugerido es Backend-Core y la clave de
agrupación de duplicados identifica el outage 502 de la pasarela
```

### Example (bad — leaks implementation)

```markdown
**Given** un `Incident` en la tabla `incidents` con `IncidentRepositoryPort`
**When** se llama `IncidentService.triage_incident`
**Then** se retorna un `TriageResult` dataclass
```

## Mapping scenarios 1:1 → `test_bdd_*`

Every scenario in the spec MUST have **exactly one** dedicated test function
named `test_bdd_<slug>` in `tests/`.

| Spec | Test |
| :--- | :--- |
| Escenario N — … | `def test_bdd_<short_business_slug>(...):` |
| Docstring / comment | Cite the scenario title or number |
| Asserts | Mirror the **Then** observables (status/exit code + business fields) |

Naming examples:

- Escenario 1 pagos 502 → `test_bdd_payments_gateway_502_http`
- Escenario 4 paridad CLI → `test_bdd_cli_parity_payments_502`

Do **not** collapse multiple scenarios into one test, and do not invent tests
without a matching scenario (except thin fixtures/helpers in `conftest.py`).

### Drivers: `TestClient` (FastAPI) and `CliRunner` (Typer)

Exercise **adapters**, not domain functions directly, so acceptance proves the
product channels:

```python
from fastapi.testclient import TestClient
from typer.testing import CliRunner

# HTTP — Spec When/Then over REST
response = client.post(
    "/api/v1/incidents/triage",
    json={"incident_id": "...", "raw_text": "..."},
)
assert response.status_code == 200
assert response.json()["severity"] == "P0"

# CLI — same business case via Typer
result = cli_runner.invoke(
    typer_app,
    ["triage", "--incident-id", "...", "--raw-text", "..."],
)
assert result.exit_code == 0
```

Fixtures typically live in `tests/conftest.py` (`client`, `cli_runner`,
`typer_app`, sample report text). Prefer shared fixtures over duplicating app
construction.

### Isolated storage

When a scenario involves persistence (H002+), each `test_bdd_*` MUST run against
**isolated storage**:

- Unique temp DB path / empty store per test (e.g. `tmp_path` + `DATABASE_URL`)
- No shared mutable file DB across tests
- No reliance on developer machine state or `data/` as a writable store
- REST and CLI under test MUST see the **same** isolated store only when the
  scenario explicitly requires cross-channel parity on persisted data; otherwise
  keep fixtures independent

For stateless scenarios (e.g. Spec 001 triage without persistence), isolation
still applies: no accidental writes; do not introduce a shared DB fixture.

### Canonical verification

```bash
uv run pytest -v
```

Failures MUST be readable as broken scenarios (which Given/When/Then failed),
not as opaque unit-assert noise.

## Agent checklist

1. Add/change acceptance → update `spec.md` scenarios first (ubiquitous language).
2. Add matching `test_bdd_*` 1:1 in `tests/` with docstring linking the scenario.
3. Drive via `TestClient` and/or `CliRunner`; assert Then observables.
4. Use isolated storage for any persisted flow.
5. Run `uv run pytest -v` before considering the work done.
