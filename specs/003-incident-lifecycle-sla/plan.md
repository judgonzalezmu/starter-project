# Implementation Plan: Ciclo de vida, duplicados y consulta SLA (H003)

**Branch**: `003-incident-lifecycle-sla` | **Date**: 2026-11-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-incident-lifecycle-sla/spec.md`, plus the H003 design constraints (extensión de `Incident`, normalización temporal en SLA, `create_incident` / `evaluate_incident_sla`, columnas e índice de duplicados en SQLite, contratos REST/CLI y `tests/test_spec_003_lifecycle_sla.py`), respetando estrictamente `.specify/memory/constitution.md` y la skill `hexagonal-architecture`.

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Un operador **registra de forma persistente** un incidente entrante (`POST /api/v1/incidents` / CLI `create`), recibe aviso si ya hay equivalentes abiertos (`is_duplicate` / `duplicate_of`) y **audita el SLA** de un incidente guardado (`GET /api/v1/incidents/{incident_id}/sla` / CLI `sla`).

Los casos de uso viven una sola vez en `IncidentService.create_incident` y `IncidentService.evaluate_incident_sla`. El dominio aporta triaje (`classify_incident_report`), claves canónicas de duplicado, evaluación SLA (ADR-002) y normalización consistente de instantes naive/aware. El adaptador SQLite persiste `recommended_team` y `duplicate_group_key`, indexa `(duplicate_group_key, status)` y completa `find_open_duplicates`. FastAPI y Typer solo traducen transporte ↔ servicio (paridad REST/CLI). Ruff TID251/TID252 sigue vigilando la frontera hexagonal.

## Technical Context

**Language/Version**: Python ≥ 3.10 (`requires-python` en `pyproject.toml`), gestionado con `uv`.

**Primary Dependencies**: FastAPI, Pydantic v2 y Typer solo en `src/adapters/inbound/`; uvicorn como servidor. Dominio y aplicación: stdlib (`datetime`, `secrets`/`uuid` para `INC-<HEX8>`, `typing`). Persistencia: `sqlite3` stdlib. Calidad: pytest, httpx (TestClient), Ruff. Sin dependencias nuevas.

**Storage**: SQLite vía `IncidentRepositoryPort` + `SQLiteIncidentRepository` + fábrica `DATABASE_URL` (default `sqlite:///:memory:`). Esquema H002 ampliado con columnas `raw_text`, `recommended_team`, `duplicate_group_key` e índice `idx_incidents_dup_key` sobre `(duplicate_group_key, status)`. Aceptación usa archivo aislado por test.

**Testing**: `uv run pytest -v`. Aceptación BDD en `tests/test_spec_003_lifecycle_sla.py` (5 escenarios, `TestClient` + `CliRunner`, almacén aislado). Regresión H001/H002 debe seguir en verde. Verificación de frontera: `uv run ruff check src/`. Tras cambios de dominio: `uv run python -m src.domain.triage_rules` y `uv run python -m src.domain.sla_calculator`.

**Target Platform**: Proceso local de laboratorio (Windows/Linux), API HTTP y CLI en el mismo código.

**Project Type**: Backend hexagonal (dominio + aplicación + adaptadores inbound REST/CLI y outbound SQLite).

**Performance Goals**: Alta y consulta SLA en < 1 minuto de operador (SC-001). Búsqueda de duplicados abiertos vía índice `(duplicate_group_key, status)` sin N+1. Sin SLO de latencia adicional.

**Constraints**: Dirección adapters → application → domain (ADR-003 / skill hexagonal). Dominio puro (sin FastAPI/Typer/Pydantic/SQL). Aplicación sin inbound ni repositorio concreto. Inbound no importa `sqlite3` ni `SQLiteIncidentRepository` (solo `factory`). No reimplementar triaje/SLA/duplicados por canal. No reabrir ADR-002 ni consenso de triaje. `SeverityLevel` permanece `Literal`. Secretos no hardcodeados. H002 (`summary`) e H001 (`triage`) intactos en contrato. Transiciones de estado posteriores al alta, auth, CORS, batch, paginación, MCP y H004 fuera de alcance.

**Scale/Scope**: Un adaptador SQLite; fábrica rechaza otros esquemas. Cinco escenarios BDD de producto. Colisión de `incident_id` → 409; validaciones de entrada → 422; inexistente en SLA → 404.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Fuente: `.specify/memory/constitution.md` v1.0.0 y skill `hexagonal-architecture`. Evaluación previa a la investigación: **PASS**. Ninguna puerta obliga a marcar `NEEDS CLARIFICATION` ni a justificar una violación.

| Puerta | Resultado | Cómo se cumple en este diseño |
| :--- | :--- | :--- |
| I. Núcleo determinista | PASS | Triaje, `duplicate_group_key` canónica y SLA solo en `src/domain/`. Adaptadores no recalculan. |
| II. Hexagonal (ADR-003) | PASS | Casos de uso en `IncidentService`; puerto en `ports.py`; REST/CLI delegan al mismo servicio; SQLite solo en outbound vía fábrica. |
| III. Gobierno y calidad | PASS | Python ≥ 3.10, `uv`, FastAPI/Pydantic v2, Typer, SQLite stdlib, Ruff, BDD + pytest. Sin deps nuevas ni secretos. |
| Invariantes de dominio | PASS | Severidades, equipos, estados, umbral 75 %, horario hábil, prioridad `resolved_at`, claves canónicas de duplicado no se redefinen. |
| Precedencia | PASS | Spec H003 + constitución + ADR-002/003 mandan sobre notas informales. |
| Skill hexagonal | PASS | Import bans por capa; paridad primary adapters; `find_open_duplicates` / `save` / `get` en el puerto; inbound no construye el repo concreto. |

ADR-001 (SQLite stdlib, sin ORM) sigue citado por la constitución sin archivo `001-*.md`; H003 no abre ese ADR: obedece la regla usando `sqlite3`.

## Project Structure

### Documentation (this feature)

```text
specs/003-incident-lifecycle-sla/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── http-post-incidents.md
│   ├── http-get-incident-sla.md
│   ├── cli-create.md
│   ├── cli-sla.md
│   └── incident-repository-port.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── domain/
│   ├── models.py                 # TeamName; Incident += recommended_team, duplicate_group_key (+ raw_text)
│   ├── sla_calculator.py         # normalización naive/aware; política ADR-002 intacta
│   ├── triage_rules.py           # sin reabrir consenso (reutilizado al crear)
│   └── ruff.toml
├── application/
│   ├── ports.py                  # find_open_duplicates / save / get ya declarados; contrato H003
│   ├── services.py               # create_incident, evaluate_incident_sla, IncidentNotFoundError
│   └── ruff.toml
├── adapters/
│   ├── inbound/
│   │   ├── api/app.py            # POST /api/v1/incidents; GET .../sla
│   │   ├── api/schemas.py        # CreateIncidentRequest, IncidentCreatedResponse, SLAEvaluationResponse
│   │   ├── cli.py                # create, sla → IncidentService
│   │   └── ruff.toml
│   └── outbound/
│       ├── sqlite_repository.py  # columnas + idx_incidents_dup_key; find_open_duplicates real
│       └── factory.py            # sin cambio de contrato (DATABASE_URL)
tests/
├── conftest.py
├── test_spec_001_triage.py       # regresión
├── test_spec_002_summary.py      # regresión (Incident ampliado: defaults opcionales)
└── test_spec_003_lifecycle_sla.py  # 5 escenarios BDD
```

**Structure Decision**: Se mantiene el layout hexagonal (ADR-003). H003 completa el ciclo de escritura del puerto ya esbozado en H002 (`save_incident`, `get_incident`, `find_open_duplicates` dejan de ser stubs/parciales) y añade los dos casos de uso de producto. No hay frontend ni segundo paquete. `tasks.md` queda para `/speckit-tasks`.

Orden de construcción que respeta las dependencias: dominio (`TeamName` / `Incident` / normalización SLA) → aplicación (`create_incident`, `evaluate_incident_sla`, errores) → outbound (columnas, índice, SQL de duplicados) → esquemas y rutas inbound + CLI → `tests/test_spec_003_lifecycle_sla.py`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No hay violaciones. Esta sección no aplica.

## Phase 0 — Research

Artefacto: [research.md](./research.md).

Decisiones cerradas allí (ninguna queda en `NEEDS CLARIFICATION`):

- Extensión de `Incident` con `TeamName`, `recommended_team`, `duplicate_group_key` y `raw_text` para cumplir entidad registrada + FR-009.
- Normalización temporal naive/aware en `evaluate_sla_status` sin cambiar la política ADR-002.
- Flujo `create_incident` (defaults, 409, aviso de duplicado no bloqueante) y `evaluate_incident_sla` (`IncidentNotFoundError` → 404).
- Esquema SQLite + `idx_incidents_dup_key`; `find_open_duplicates` filtra `OPEN` \| `IN_PROGRESS` \| `ESCALATION_REQUIRED`.
- Contratos Pydantic / Typer con paridad; generación `INC-<HEX8>` en mayúsculas.
- Cinco `test_bdd_*` en `tests/test_spec_003_lifecycle_sla.py` con almacén aislado.

## Phase 1 — Design & Contracts

| Artefacto | Rol |
| :--- | :--- |
| [data-model.md](./data-model.md) | Entidades, campos, validación, estados y transiciones al alta |
| [contracts/http-post-incidents.md](./contracts/http-post-incidents.md) | `POST /api/v1/incidents` |
| [contracts/http-get-incident-sla.md](./contracts/http-get-incident-sla.md) | `GET /api/v1/incidents/{incident_id}/sla` |
| [contracts/cli-create.md](./contracts/cli-create.md) | CLI `create` |
| [contracts/cli-sla.md](./contracts/cli-sla.md) | CLI `sla` |
| [contracts/incident-repository-port.md](./contracts/incident-repository-port.md) | Puerto H003 (save/get/find_open_duplicates) |
| [quickstart.md](./quickstart.md) | Validación end-to-end manual y gates |

### Constitution Check (post-design)

Revisión después de `research.md`, `data-model.md`, `contracts/` y `quickstart.md`: **PASS**.

- Esquemas Pydantic y flags Typer viven solo en inbound; el dominio no los importa.
- `create_incident` / `evaluate_incident_sla` son el único camino de negocio; REST y CLI no bifurcan reglas.
- `duplicate_group_key` canónica sigue saliendo de `triage_rules`; el índice SQL no inventa claves.
- SLA permanece en `sla_calculator` (ADR-002); la normalización temporal no altera minutos hábiles ni el umbral 75 %.
- Los cinco escenarios BDD de la spec mapean 1:1 a `test_bdd_*` con almacenamiento aislado.
- H001/H002 no cambian de contrato de producto; `list_active_incidents` sigue limitándose a `OPEN`/`IN_PROGRESS` (el aviso de duplicados usa el conjunto abierto más amplio de FR-009, incluido `ESCALATION_REQUIRED`).
