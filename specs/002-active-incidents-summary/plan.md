# Implementation Plan: Resumen de incidentes activos (H002)

**Branch**: `002-active-incidents-summary` | **Date**: 2026-11-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-active-incidents-summary/spec.md`, plus the H002 design constraints (puerto hexagonal, SQLite outbound, caso de uso compartido, adaptadores REST/CLI, frontera Ruff TID251/TID252 y `tests/test_spec_002_summary.py`).

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Un operador consulta los incidentes activos (`OPEN` e `IN_PROGRESS`) por `GET /api/v1/incidents/summary` y por el subcomando CLI `summary`, con filtro opcional de componente e instante opcional de evaluación. El caso de uso vive una sola vez en `IncidentService.get_active_incidents_summary` y calcula minutos, incumplimiento y escalamiento con `evaluate_sla_status` (ADR-002).

La lectura sale de `IncidentRepositoryPort`. `SQLiteIncidentRepository` hereda el esquema SQLite de Semana 1 y sustituye el escaneo en memoria y el N+1 de `src/incident_repository.py` por una consulta con `INNER JOIN sla_policies` y el índice compuesto `(component, status)`. `DATABASE_URL` elige el adaptador; el default es `sqlite:///:memory:`. FastAPI y Typer solo traducen el mismo resultado de aplicación. Ruff (`E4`, `E7`, `E9`, `F`, `TID`) vigila la dirección de dependencias en dominio, aplicación e inbound.

## Technical Context

**Language/Version**: Python ≥ 3.10 (`requires-python` en `pyproject.toml`), gestionado con `uv`.

**Primary Dependencies**: FastAPI, Pydantic v2 y Typer solo en `src/adapters/inbound/`; uvicorn como servidor. Dominio y aplicación: stdlib. Persistencia: `sqlite3` de la stdlib. Calidad: pytest, httpx (TestClient) y Ruff ≥ 0.17.6, ya presentes. Sin dependencias nuevas.

**Storage**: SQLite vía adaptador outbound intercambiable. URL por defecto `sqlite:///:memory:`. Aceptación y paridad HTTP/CLI usan un archivo aislado (`sqlite:///<ruta>`). Esquema de Semana 1 (`incidents`, `sla_policies`) e índice `idx_incidents_component_status`.

**Testing**: `uv run pytest -v`. Aceptación BDD en `tests/test_spec_002_summary.py` con `TestClient` y `CliRunner` sobre un SQLite de archivo por test. El mismo archivo comprueba que `SQLiteIncidentRepository` cumple `IncidentRepositoryPort` (`@runtime_checkable`). Regresión H001 existente debe seguir en verde.

**Target Platform**: Proceso local de laboratorio (Windows/Linux), API HTTP y CLI en el mismo código.

**Project Type**: Backend hexagonal (dominio + aplicación + adaptadores inbound REST/CLI y outbound SQLite).

**Performance Goals**: El listado activo es una sola consulta SQL (el `JOIN` reemplaza el N+1). El SLA se evalúa en proceso solo sobre las filas ya filtradas. El índice `(component, status)` cubre el resumen filtrado. La meta de producto sigue siendo SC-001: un operador obtiene el resumen en menos de 1 minuto. No se añade un SLO de latencia distinto al de la spec.

**Constraints**: Dirección adapters → application → domain. Sin ORM, sin secretos, sin reimplementar SLA/triaje en adaptadores. `resolved_at` sigue teniendo prioridad dentro de `evaluate_sla_status`. `SeverityLevel` permanece como `Literal`. SQL parametrizado. `GET /health` de H001 se mantiene `{"status": "ok"}`. H003/H004 (registro con alerta de duplicados, motor dedicado, contenedores) no se exponen como producto.

**Scale/Scope**: Catálogo de aceptación de 7 incidentes (5 activos). El sembrado sintético de Semana 1 puede seguir existiendo en la clase concreta para el benchmark, fuera del puerto. Un adaptador SQLite; la fábrica rechaza cualquier otro esquema de URL.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Fuente: `.specify/memory/constitution.md` v1.0.0 (ADR-003, ADR-002, gobierno técnico). Evaluación previa a la investigación: **PASS**. Ninguna puerta obliga a marcar `NEEDS CLARIFICATION` ni a justificar una violación.

| Puerta | Resultado | Cómo se cumple en este diseño |
| :--- | :--- | :--- |
| I. Núcleo determinista | PASS | `elapsed_minutes`, `is_breached` y `requires_escalation` salen solo de `src/domain/sla_calculator.py`. Los adaptadores no recalculan SLA. |
| II. Hexagonal (ADR-003) | PASS | Puerto `Protocol` en `src/application/ports.py`. Caso de uso en `IncidentService`. REST y CLI llaman a ese método. SQLite queda en `src/adapters/outbound/` y se selecciona con `DATABASE_URL`. |
| III. Gobierno y calidad | PASS | Python ≥ 3.10, `uv`, FastAPI/Pydantic v2, Typer, SQLite stdlib, Ruff obligatorio, BDD + `uv run pytest -v`. Sin dependencias nuevas ni secretos. |
| Invariantes de dominio | PASS | Severidades, equipos, estados, umbral 75 %, horario hábil y prioridad de `resolved_at` no se redefinen. |
| Precedencia | PASS | La spec H002 y esta constitución mandan sobre el benchmark N+1 de Semana 1. |

ADR-001 (SQLite stdlib, sin ORM) está citado por la constitución y aún no tiene archivo en `docs/adr/`. H002 no abre ese ADR: obedece la regla ya escrita usando `sqlite3`.

## Project Structure

### Documentation (this feature)

```text
specs/002-active-incidents-summary/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── http-get-incidents-summary.md
│   ├── cli-summary.md
│   └── incident-repository-port.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── domain/
│   ├── models.py                 # Incident sin campos nuevos
│   ├── sla_calculator.py         # sin cambios de política ADR-002
│   ├── triage_rules.py
│   └── ruff.toml                 # TID251 + TID252, extend pyproject.toml
├── application/
│   ├── ports.py                  # IncidentRepositoryPort (nuevo)
│   ├── services.py               # get_active_incidents_summary
│   └── ruff.toml
├── adapters/
│   ├── inbound/
│   │   ├── api/app.py            # GET /api/v1/incidents/summary
│   │   ├── api/schemas.py        # ActiveIncidentItem, ActiveIncidentsSummaryResponse
│   │   ├── cli.py                # command summary
│   │   └── ruff.toml
│   └── outbound/
│       ├── sqlite_repository.py  # SQLiteIncidentRepository
│       └── factory.py            # create_incident_repository(DATABASE_URL)
├── incident_repository.py        # entrypoint de benchmark delegado
pyproject.toml                    # [tool.ruff.lint] select E4, E7, E9, F, TID
tests/
├── conftest.py                   # fixtures H001 intactas
└── test_spec_002_summary.py      # 5 escenarios BDD + cumplimiento del puerto
```

**Structure Decision**: Se mantiene el layout hexagonal ya adoptado (ADR-003). H002 añade el puerto de persistencia, el primer adaptador outbound y el caso de uso de lectura. No hay frontend ni segundo paquete. `tasks.md` queda para `/speckit-tasks`.

Orden de construcción que respeta las dependencias: configuración Ruff y modelos de aplicación → `ports.py` → `sqlite_repository.py` + `factory.py` → `get_active_incidents_summary` → esquemas y rutas inbound → `tests/test_spec_002_summary.py`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No hay violaciones. Esta sección no aplica.

## Phase 0 — Research

Artefacto: [research.md](./research.md).

Decisiones cerradas allí (ninguna queda en `NEEDS CLARIFICATION`):

- El `INNER JOIN` optimiza la lectura; el SLA se calcula en el dominio.
- Puerto con los cinco métodos pedidos y fábrica `DATABASE_URL`. Una instancia de repositorio por proceso de la app.
- Modelos de aplicación frente a esquemas Pydantic de transporte.
- Parseo de `reference_time` con `datetime.fromisoformat` y orden FR-011 dentro del caso de uso.
- `find_open_duplicates` está en el puerto y H002 no define su emparejamiento: no hay columna nueva y el adaptador devuelve lista vacía.
- `check_health` existe en el puerto y no cambia `GET /health`.
- Tres `ruff.toml` jerárquicos verificados con Ruff 0.17.6: un ban de `fastapi` cubre submódulos y un ban de `src.adapters` cubre el repositorio concreto.
- El árbol `src/` actual ya pasa `--select E4,E7,E9,F,TID` antes de añadir bans por capa.

## Phase 1 — Design & Contracts

| Artefacto | Rol |
| :--- | :--- |
| [data-model.md](./data-model.md) | Entidades, campos, validación, catálogo de aceptación y transiciones (ninguna en H002). |
| [contracts/http-get-incidents-summary.md](./contracts/http-get-incidents-summary.md) | `GET /api/v1/incidents/summary` |
| [contracts/cli-summary.md](./contracts/cli-summary.md) | `summary` y paridad con HTTP |
| [contracts/incident-repository-port.md](./contracts/incident-repository-port.md) | Puerto y obligación SQL del adaptador SQLite |
| [quickstart.md](./quickstart.md) | Cómo comprobar Ruff, pytest y una consulta manual |

### Constitution Check (post-design)

Revisión después de `research.md`, `data-model.md`, `contracts/` y `quickstart.md`: **PASS**.

- El contrato HTTP/CLI no arrastra SQL, FastAPI ni el puerto hacia el dominio.
- `ActiveIncidentItem` y `ActiveIncidentsSummaryResponse` viven en el adaptador inbound. El servicio devuelve dataclasses de aplicación.
- La consulta optimizada no selecciona minutos de SLA desde `sla_policies` para decidir incumplimiento; esa tabla solo participa en el `JOIN` de integridad y en el sembrado heredado.
- Los cinco escenarios BDD de la spec tienen un `test_bdd_*` cada uno. La comprobación del puerto es la verificación extra pedida para este hito, en el mismo módulo de tests.
- Los cinco métodos del puerto vienen del encargo de H002. La constitución solo exige un `Protocol` en `ports.py`. H002 no publica registro, alerta de duplicados ni health de infraestructura, y no cambia `Incident`.
