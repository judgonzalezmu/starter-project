# Implementation Plan: Persistencia dual y runtime en contenedores (H004)

**Branch**: `004-postgres-container-runtime` | **Date**: 2026-11-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-postgres-container-runtime/spec.md`, más ADR-004 y `.specify/memory/constitution.md` v1.1.0 (persistencia dual SQLite/PostgreSQL sin ORM, fábrica por `DATABASE_URL`, topología `api` + `db`).

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Un operador **comprueba la conectividad real** del almacén (`GET /health` y CLI `health`), **elige el motor** solo con `DATABASE_URL` (PostgreSQL en el runtime dedicado; SQLite, o `sqlite:///:memory:` si la variable no existe, en local y en pruebas) y **arranca** API + PostgreSQL 16 con un manifiesto reproducible.

El caso de uso de salud vive una sola vez en `IncidentService.check_operational_health` y delega en `IncidentRepositoryPort.check_health` (`SELECT 1`). La fábrica outbound sigue siendo el único sitio que interpreta `DATABASE_URL`. Un adaptador nuevo `PostgresIncidentRepository` (`psycopg[binary]`, ya declarado en `pyproject.toml`) implementa el mismo puerto que `SQLiteIncidentRepository`, con instantes en TEXT ISO 8601 y esquema idempotente al conectar. Si la base cae después de un arranque válido, la salud responde `503` / CLI exit `1` y las operaciones que persisten fallan con `PersistenceUnavailableError` (HTTP `503`, cuerpo distinto del JSON de salud). El dominio de triaje y SLA no se toca.

## Technical Context

**Language/Version**: Python ≥ 3.10 (`requires-python` en `pyproject.toml`), imagen de referencia `python:3.12-slim`, gestionado con `uv`.

**Primary Dependencies**: FastAPI, Pydantic v2 y Typer solo en `src/adapters/inbound/`; uvicorn como servidor. Dominio y aplicación: stdlib. SQLite: `sqlite3` stdlib. PostgreSQL: `psycopg[binary]>=3.3.9` (ya en `pyproject.toml` y `uv.lock`; driver, no ORM). Calidad: pytest, httpx (TestClient), Ruff. Sin dependencias nuevas.

**Storage**: Puerto `IncidentRepositoryPort`. `sqlite:///` → `SQLiteIncidentRepository` (default `sqlite:///:memory:` solo si `DATABASE_URL` no existe). `postgresql://` → `PostgresIncidentRepository`. Mismas tablas `incidents` y `sla_policies`, instantes TEXT ISO 8601 (ADR-004). Bootstrap `CREATE TABLE IF NOT EXISTS` al conectar. Sin migraciones versionadas.

**Testing**: `uv run pytest -v`. Aceptación BDD en `tests/test_spec_004_postgres_runtime.py` (4 escenarios, `TestClient` + `CliRunner`). Escenarios 1–3 con almacén aislado y sin Docker. Escenario 4: aserción del manifiesto (Dockerfile, `.dockerignore`, `docker-compose.yml`); el smoke `docker compose up` queda documentado y no es gate. Regresión H001–H003 en verde. Frontera: `uv run ruff check src/`.

**Target Platform**: Proceso local de laboratorio (Windows/Linux) y dos contenedores Linux (`api` + `db`) cuando hay runtime Docker.

**Project Type**: Backend hexagonal (dominio + aplicación + adaptadores inbound REST/CLI y outbound SQLite/PostgreSQL) con manifiesto de orquestación en la raíz del repo.

**Performance Goals**: El chequeo de salud ejecuta `SELECT 1` en el momento de la petición (sin caché). `connect_timeout=3` en PostgreSQL para que un host inalcanzable se observe en menos de 5 segundos (RNF-009). Sin SLO de throughput.

**Constraints**: Dirección adapters → application → domain (ADR-003). Dominio sin `sqlite3` ni `psycopg`. Aplicación sin drivers. Inbound solo abre persistencia por `create_incident_repository`. No reabrir ADR-002 ni el consenso de triaje. `SeverityLevel` permanece `Literal`. Secretos solo por entorno; mensajes de error sin la URL. URL vacía o esquema ajeno: `ValueError` al resolver, sin fallback a memoria. H001–H003 intactos en reglas de negocio. Auth, CORS, batch, paginación, ORM, migraciones versionadas y MCP fuera de alcance.

**Scale/Scope**: Dos adaptadores de un mismo puerto; un compose de dos servicios; cuatro escenarios BDD. El benchmark `src/incident_repository.py` sigue sembrando SQLite en memoria y no entra en el camino de producto.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Fuente: `.specify/memory/constitution.md` v1.1.0, ADR-004 (tratado como aprobado por la constitución el 2026-11-24) y skill `hexagonal-architecture`. Evaluación previa a la investigación: **PASS**. Ninguna puerta obliga a marcar `NEEDS CLARIFICATION` ni a justificar una violación.

| Puerta | Resultado | Cómo se cumple en este diseño |
| :--- | :--- | :--- |
| I. Núcleo determinista | PASS | Triaje, duplicados y SLA siguen solo en `src/domain/`. La salud operativa no es regla de negocio: vive en aplicación y outbound. |
| II. Hexagonal (ADR-003) | PASS | `check_operational_health` en `IncidentService`; `check_health` ya está en el puerto; REST y CLI delegan al mismo servicio; la fábrica elige el adaptador. |
| III. Gobierno y calidad | PASS | Python ≥ 3.10, `uv`, FastAPI/Pydantic v2, Typer, SQLite stdlib, `psycopg[binary]` solo outbound, Ruff, BDD + pytest. Sin ORM y sin dependencia nueva. |
| Invariantes de dominio | PASS | Severidades, equipos, estados, umbral 75 %, horario hábil, prioridad `resolved_at` y claves canónicas no se redefinen. |
| Persistencia dual | PASS | `DATABASE_URL` es la única selección. Instants en TEXT ISO 8601. Topología `api` + `db` (`postgres:16-alpine`). |
| Secretos | PASS | Credenciales de compose por variables de entorno con placeholders de laboratorio, no secretos de producción. |
| Skill hexagonal | PASS | Bans de `psycopg` en dominio, aplicación e inbound. Inbound no importa el adaptador concreto de PostgreSQL. |

El encabezado de `docs/adr/004-persistencia-postgresql-y-runtime-contenedores.md` sigue diciendo Estado Propuesto. La constitución 1.1.0 ya adopta la decisión. Este plan no reescribe el ADR.

## Project Structure

### Documentation (this feature)

```text
specs/004-postgres-container-runtime/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── http-get-health.md
│   ├── cli-health.md
│   ├── database-url.md
│   ├── persistence-unavailable.md
│   ├── incident-repository-port.md
│   └── compose-runtime.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── domain/                          # sin cambio de reglas; ruff.toml banea psycopg
│   └── ruff.toml
├── application/
│   ├── ports.py                     # PersistenceUnavailableError; check_health ya declarado
│   ├── services.py                  # OperationalHealth + check_operational_health
│   └── ruff.toml                    # banea psycopg
├── adapters/
│   ├── inbound/
│   │   ├── api/app.py               # GET /health real; 503 de persistencia en alta/SLA/resumen
│   │   ├── cli.py                   # subcomando health; mismos errores de almacén
│   │   └── ruff.toml                # banea psycopg y postgres_repository
│   └── outbound/
│       ├── factory.py               # sqlite:/// | postgresql:// | default memoria | fail-fast
│       ├── sqlite_repository.py     # check_health ya hace SELECT 1; traduce fallos del driver
│       └── postgres_repository.py   # mismo puerto, psycopg, esquema idempotente
├── incident_repository.py           # benchmark SQLite; fuera del camino H004
Dockerfile                           # uv sobre python:3.12-slim
.dockerignore
docker-compose.yml                   # servicios api + db
tests/
├── test_spec_001_triage.py          # regresión
├── test_spec_002_summary.py         # regresión
├── test_spec_003_lifecycle_sla.py   # regresión
└── test_spec_004_postgres_runtime.py
```

**Structure Decision**: Se mantiene el layout hexagonal (ADR-003). H004 añade el segundo adaptador outbound, endurece la fábrica y sustituye el stub de `/health`. No hay frontend ni paquete nuevo. `psycopg` ya está en el manifiesto de dependencias; no se añade un ORM ni un pool externo. `tasks.md` queda para `/speckit-tasks`.

Orden de construcción: error de puerto + bans Ruff → fábrica y adaptador PostgreSQL (esquema + `SELECT 1`) → traducción de fallos en SQLite → caso de uso de salud → HTTP/CLI → manifiestos de contenedor → `tests/test_spec_004_postgres_runtime.py`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No hay violaciones. Esta sección no aplica.

## Phase 0 — Research

Artefacto: [research.md](./research.md).

Decisiones cerradas allí (ninguna queda en `NEEDS CLARIFICATION`):

- Salud en `IncidentService`, no en el dominio ni como JSON armado en cada adaptador.
- Fábrica: `postgresql://` / `sqlite:///` / ausencia → memoria; vacío o esquema ajeno → `ValueError` sin eco de la URL.
- PostgreSQL diferido: construir el adaptador no abre la red; el primer uso conecta con `connect_timeout=3`, crea el esquema y ejecuta la operación.
- Código HTTP de negocio cuando el almacén cae: `503` con `{"detail":"El almacén de datos no está disponible."}`, distinto del JSON de `/health`.
- Paridad temporal TEXT ISO 8601; upsert por dialecto (`INSERT OR REPLACE` vs `ON CONFLICT DO UPDATE`).
- Escenario 4 automatizado por manifiesto; smoke Compose solo en `quickstart.md`.
- `src/incident_repository.py` no se reescribe.

## Phase 1 — Design & Contracts

| Artefacto | Rol |
| :--- | :--- |
| [data-model.md](./data-model.md) | Salud operativa, configuración de almacén, esquema físico compartido |
| [contracts/http-get-health.md](./contracts/http-get-health.md) | `GET /health` |
| [contracts/cli-health.md](./contracts/cli-health.md) | CLI `health` |
| [contracts/database-url.md](./contracts/database-url.md) | Resolución de `DATABASE_URL` |
| [contracts/persistence-unavailable.md](./contracts/persistence-unavailable.md) | Fallo explícito de alta / SLA / resumen |
| [contracts/incident-repository-port.md](./contracts/incident-repository-port.md) | Puerto H004 (mismo contrato H002/H003 + salud) |
| [contracts/compose-runtime.md](./contracts/compose-runtime.md) | Dockerfile, `.dockerignore`, compose `api` + `db` |
| [quickstart.md](./quickstart.md) | Gates locales y smoke opcional con Docker |

### Constitution Check (post-design)

Revisión después de `research.md`, `data-model.md`, `contracts/` y `quickstart.md`: **PASS**.

- `OperationalHealth` y `PersistenceUnavailableError` están en aplicación; `src/domain/models.py`, `triage_rules.py` y `sla_calculator.py` no cambian de comportamiento.
- `GET /health` y CLI `health` llaman a `IncidentService.check_operational_health`. El SQL `SELECT 1` queda dentro de cada adaptador outbound.
- La fábrica sigue siendo el único lector de `DATABASE_URL`. Inbound no importa `psycopg` ni `PostgresIncidentRepository`.
- Los instantes siguen saliendo de `datetime.isoformat()` / `fromisoformat()` en columnas TEXT. No hay `timestamptz` ni ORM.
- Los cuatro escenarios BDD de la spec mapean 1:1 a `test_bdd_*`. Los escenarios 1–3 no levantan Compose. El escenario 4 automatiza el manifiesto y deja el arranque real en el smoke de `quickstart.md`.
- H001–H003 conservan códigos 201 / 404 / 409 / 422 cuando el almacén responde. El `503` nuevo solo aparece si el driver falla.
- Credenciales de laboratorio del compose son placeholders sustituibles por entorno y no se documentan como secretos reales.
