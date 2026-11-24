---
description: "Task list for H004 dual persistence and container runtime"
---

# Tasks: Persistencia dual y runtime en contenedores (H004)

**Input**: Design documents from `/specs/004-postgres-container-runtime/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md, `.specify/memory/constitution.md`

**Tests**: Incluidos. La spec fija cuatro escenarios BDD y el plan exige `tests/test_spec_004_postgres_runtime.py` (cuatro `test_bdd_*` con `TestClient` + `CliRunner`; Escenarios 1–3 sin Docker; Escenario 4 por manifiesto). Escribir cada test de historia y verlo fallar antes de la implementación de esa historia.

**Organization**: Tareas agrupadas por historia de usuario. Respetar constitución v1.1.0, ADR-004 y skill hexagonal (adapters → application → domain). No tocar reglas de triaje ni SLA.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede ejecutarse en paralelo (archivos distintos, sin depender de tareas incompletas)
- **[Story]**: Historia a la que pertenece la tarea (`US1`–`US3`)
- Las fases Setup, Foundational y Polish no llevan etiqueta de historia

## Path Conventions

- Proyecto único: `src/`, `tests/`, `Dockerfile`, `.dockerignore`, `docker-compose.yml` en la raíz
- Diseño: `specs/004-postgres-container-runtime/`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Preparar el módulo de aceptación H004 sin dependencias nuevas

- [X] T001 [P] Crear el esqueleto vacío `tests/test_spec_004_postgres_runtime.py` con docstring de feature H004 según `specs/004-postgres-container-runtime/plan.md`
- [X] T002 [P] Confirmar en `pyproject.toml` y `uv.lock` que `psycopg[binary]>=3.3.9` ya está declarado; no añadir ORM ni otras dependencias según `specs/004-postgres-container-runtime/research.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Error de puerto, bans Ruff, fábrica dual, adaptador PostgreSQL y traducción de fallos en SQLite

**⚠️ CRITICAL**: Ninguna historia empieza hasta cerrar esta fase

- [X] T003 [P] Declarar `PersistenceUnavailableError` en `src/application/ports.py` según data-model.md `PersistenceUnavailableError` y `specs/004-postgres-container-runtime/contracts/incident-repository-port.md` (no la lanza `check_health`)
- [X] T004 [P] Añadir ban de `psycopg` en `src/domain/ruff.toml` y `src/application/ruff.toml` según skill hexagonal y `specs/004-postgres-container-runtime/plan.md`
- [X] T005 [P] Añadir bans de `psycopg` y `src.adapters.outbound.postgres_repository` en `src/adapters/inbound/ruff.toml` según `specs/004-postgres-container-runtime/contracts/incident-repository-port.md`
- [X] T006 Extender `create_incident_repository` en `src/adapters/outbound/factory.py` para `sqlite:///`, `postgresql://`, default `sqlite:///:memory:` si la variable está ausente, y fail-fast con mensajes exactos de `specs/004-postgres-container-runtime/contracts/database-url.md` (sin eco de la URL; sin fallback a memoria; `postgres://` rechazado; esquema case-insensitive; construir PostgreSQL sin abrir socket) según data-model.md sección Configuración de persistencia
- [X] T007 Implementar `PostgresIncidentRepository` en `src/adapters/outbound/postgres_repository.py` con `psycopg` (`connect_timeout=3`, `dict_row`, lock, reconexión), bootstrap idempotente de data-model.md `sla_policies.severity`, data-model.md `sla_policies.max_resolution_minutes`, data-model.md `sla_policies.operates_24x7`, data-model.md `incidents.incident_id`, data-model.md `incidents.title`, data-model.md `incidents.component`, data-model.md `incidents.severity`, data-model.md `incidents.status`, data-model.md `incidents.created_at`, data-model.md `incidents.resolved_at`, data-model.md `incidents.raw_text`, data-model.md `incidents.recommended_team`, data-model.md `incidents.duplicate_group_key` e índices `idx_incidents_component_status` / `idx_incidents_dup_key`; `check_health` con `SELECT 1`; DML con `%s` y `ON CONFLICT`; mapear `psycopg.Error` a `PersistenceUnavailableError` en save/get/list/duplicates (no a `None`/`[]`) según `specs/004-postgres-container-runtime/contracts/incident-repository-port.md` y `specs/004-postgres-container-runtime/research.md` (depends on T003, T006)
- [X] T008 Traducir `sqlite3.Error` a `PersistenceUnavailableError` en `save_incident` / `get_incident` / `find_open_duplicates` / `list_active_incidents` de `src/adapters/outbound/sqlite_repository.py` manteniendo `check_health` → `bool` con `SELECT 1` según data-model.md `PersistenceUnavailableError` y `specs/004-postgres-container-runtime/contracts/incident-repository-port.md` (depends on T003)

**Checkpoint**: Fábrica dual lista, PostgreSQL implementa el puerto, SQLite no inventa datos ante fallo de driver, Ruff cierra la frontera. Aún no hay `/health` real ni CLI `health`.

---

## Phase 3: User Story 1 - Verificar que la infraestructura crítica responde (Priority: P1) 🎯 MVP

**Goal**: Chequeo real de conectividad por `GET /health` y CLI `health` (éxito `200`/`0` y fallo `503`/`1` con el mismo JSON), y operaciones de negocio que fallan de forma explícita si el almacén cae

**Independent Test**: Escenarios 1 y 2 (+ FR-017) — `test_bdd_health_connected_http_and_cli` + `test_bdd_health_unavailable_and_business_ops_fail`

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T009 [US1] Escribir `test_bdd_health_connected_http_and_cli` en `tests/test_spec_004_postgres_runtime.py` con SQLite de archivo aislado (`tmp_path` + `DATABASE_URL`): `GET /health` → `200` con data-model.md `OperationalHealth.status`=`ok` y data-model.md `OperationalHealth.database`=`connected`; CLI `health` → exit `0` y el mismo JSON; según Escenario 1 de `specs/004-postgres-container-runtime/spec.md` y `specs/004-postgres-container-runtime/contracts/http-get-health.md`
- [X] T010 [US1] Escribir `test_bdd_health_unavailable_and_business_ops_fail` en `tests/test_spec_004_postgres_runtime.py` con `postgresql://incidentops:incidentops@127.0.0.1:1/incidentops`: `GET /health` → `503` con data-model.md `OperationalHealth.status`=`error` y data-model.md `OperationalHealth.database`=`unavailable`; CLI `health` → exit `1` y el mismo JSON; la respuesta de salud termina en ≤ 5 s (RNF-009 / `connect_timeout=3`); `POST /api/v1/incidents` y CLI `create` → `503` / exit `1` con `detail` fijo de `specs/004-postgres-container-runtime/contracts/persistence-unavailable.md` sin inventar incidente ni filtrar URL/credenciales; según Escenario 2 (salud) y FR-017 / edge case de ops de negocio (depends on T009: mismo archivo de tests)

### Implementation for User Story 1

- [X] T011 [US1] Añadir dataclass `OperationalHealth` (data-model.md `OperationalHealth.status`, data-model.md `OperationalHealth.database`) y `IncidentService.check_operational_health` en `src/application/services.py` traduciendo `repository.check_health()` → pares `ok`/`connected` o `error`/`unavailable` según `specs/004-postgres-container-runtime/research.md` (depends on T003)
- [X] T012 [P] [US1] Sustituir el stub de `GET /health` en `src/adapters/inbound/api/app.py` para delegar solo en `IncidentService.check_operational_health`, respondiendo `200` o `503` con exactamente data-model.md `OperationalHealth.status` y data-model.md `OperationalHealth.database` según `specs/004-postgres-container-runtime/contracts/http-get-health.md` (depends on T011)
- [X] T013 [P] [US1] Añadir el comando `health` en `src/adapters/inbound/cli.py` invocando exactamente `IncidentService.check_operational_health`, imprimiendo el mismo JSON de negocio y códigos `0`/`1` según `specs/004-postgres-container-runtime/contracts/cli-health.md`; mapear `ValueError` de fábrica a stderr + exit `1` sin JSON de salud (depends on T006, T011)
- [X] T014 [US1] Mapear `PersistenceUnavailableError` → HTTP `503` con `{"detail":"El almacén de datos no está disponible."}` en `POST /api/v1/incidents`, `GET .../sla` y `GET .../summary` de `src/adapters/inbound/api/app.py` según data-model.md `PersistenceUnavailableError` y `specs/004-postgres-container-runtime/contracts/persistence-unavailable.md`; conservar `201`/`404`/`409`/`422` cuando el almacén responde (depends on T003, T008, T012)
- [X] T015 [P] [US1] Mapear `PersistenceUnavailableError` en CLI `create` / `sla` / `summary` de `src/adapters/inbound/cli.py` a exit `1` y stderr con la frase fija de `specs/004-postgres-container-runtime/contracts/persistence-unavailable.md` sin JSON de negocio engañoso (depends on T003, T008, T013)

**Checkpoint**: Un operador verifica salud real por HTTP y CLI; con host inalcanzable recibe `503`/`1` y el alta no inventa datos.

---

## Phase 4: User Story 2 - Elegir motor de persistencia por entorno (Priority: P1)

**Goal**: `DATABASE_URL` selecciona PostgreSQL, SQLite o memoria por defecto sin tocar el dominio ni reabrir reglas de negocio

**Independent Test**: Escenario 3 — `test_bdd_database_url_engine_selection`

### Tests for User Story 2 ⚠️

- [X] T016 [US2] Escribir `test_bdd_database_url_engine_selection` en `tests/test_spec_004_postgres_runtime.py`: (a) `postgresql://...@127.0.0.1:1/...` no cae a memoria (`POST /api/v1/incidents` → `503`, no `201`); (b) dos instancias con el mismo `sqlite:///` de archivo ven el mismo incidente; (c) sin `DATABASE_URL`, dos instancias `sqlite:///:memory:` no comparten filas; (d) URL vacía y esquema `mysql://` / `postgres://` lanzan `ValueError` cuyo texto no contiene el valor; según Escenario 3, data-model.md sección Configuración de persistencia y `specs/004-postgres-container-runtime/contracts/database-url.md`

### Implementation for User Story 2

- [X] T017 [US2] Cerrar en `src/adapters/outbound/factory.py` cualquier hueco que deje fallar T016 (mensajes exactos, strip, rechazo de `postgres://`, path SQLite vacío, default solo si la variable está ausente) según `specs/004-postgres-container-runtime/contracts/database-url.md` y data-model.md sección Configuración de persistencia (depends on T006, T007, T016)
- [X] T018 [US2] Asegurar en `src/adapters/inbound/api/app.py` y `src/adapters/inbound/cli.py` que `health` / `create` / `sla` / `summary` obtienen el puerto solo con `create_incident_repository` (sin imports de `sqlite_repository` ni `postgres_repository`); `uv run ruff check src/` en verde tras el cambio, según `specs/004-postgres-container-runtime/contracts/incident-repository-port.md` (depends on T007, T014, T015, T017)

**Checkpoint**: Cambiar solo `DATABASE_URL` elige el motor; vacío/esquema ilegal falla al resolver; el dominio permanece ajeno al driver.

---

## Phase 5: User Story 3 - Arrancar un entorno reproducible api + db (Priority: P2)

**Goal**: Manifiesto reproducible de dos contenedores (`api` + `db`) con build `uv`/`python:3.12-slim`, healthchecks y `depends_on: service_healthy`

**Independent Test**: Escenario 4 — `test_bdd_compose_manifest_contract` (manifiesto; sin `docker compose up` en pytest)

### Tests for User Story 3 ⚠️

- [X] T019 [US3] Escribir `test_bdd_compose_manifest_contract` en `tests/test_spec_004_postgres_runtime.py` leyendo `Dockerfile`, `.dockerignore` y `docker-compose.yml` y afirmando el contrato de `specs/004-postgres-container-runtime/contracts/compose-runtime.md` (imágenes, `uv`, `.dockerignore`, `db`/`api`, `pg_isready`, `DATABASE_URL`, `service_healthy`, healthcheck `/health`); no ejecutar Compose; según Escenario 4

### Implementation for User Story 3

- [X] T020 [P] [US3] Crear `Dockerfile` en la raíz: `FROM python:3.12-slim`, copiar `uv` desde etiqueta fija de `ghcr.io/astral-sh/uv` (no `latest`), `uv sync --frozen --no-dev`, `CMD` uvicorn con `--factory --host 0.0.0.0 --port 8000`, sin copiar `.env` ni secretos, según `specs/004-postgres-container-runtime/contracts/compose-runtime.md`
- [X] T021 [P] [US3] Crear `.dockerignore` en la raíz excluyendo `.venv`/`venv`, cachés, `.git`, `.env`, `*.db` y `tests/`, sin excluir `pyproject.toml`, `uv.lock` ni `src/`, según `specs/004-postgres-container-runtime/contracts/compose-runtime.md`
- [X] T022 [US3] Crear `docker-compose.yml` en la raíz con servicios `db` (`postgres:16-alpine`, volumen nominado, placeholders `incidentops`, healthcheck `pg_isready`) y `api` (build local, `DATABASE_URL` hacia `db`, `depends_on` con `service_healthy`, puerto `8000:8000`, healthcheck HTTP a `/health` con stdlib Python; sin publicar `5432`), según `specs/004-postgres-container-runtime/contracts/compose-runtime.md` (depends on T020, T021)

**Checkpoint**: El manifiesto cumple el contrato de orquestación; el smoke real queda para `quickstart.md`, no para pytest.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentación operativa, gates del quickstart y regresión H001–H003

- [X] T023 [P] Actualizar la fila de comandos H004 en `AGENTS.md` (`health`, `DATABASE_URL`, Compose, pytest del spec 004) sin reinventar requisitos ni reabrir ADR-002
- [X] T024 Ejecutar la validación de `specs/004-postgres-container-runtime/quickstart.md`: `uv run ruff check src/`, `uv run python -m src.domain.triage_rules`, `uv run python -m src.domain.sla_calculator`, `uv run pytest -v` (cuatro `test_bdd_*` H004 + regresión H001–H003 en verde). El smoke `docker compose up` es opcional y no es gate

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias
- **Foundational (Phase 2)**: depende de Setup y bloquea todas las historias
- **User Stories (Phase 3+)**: dependen de Foundational
- **Polish (Phase 6)**: depende de US1–US3

### User Story Dependencies

- **User Story 1 (P1)**: tras Phase 2. MVP. No depende de US2–US3
- **User Story 2 (P1)**: tras Phase 2; se beneficia de los mapeos `503` de US1 (T014/T015) para demostrar que PostgreSQL no cae a memoria. Secuenciar tras US1 si se edita el mismo `app.py`/`cli.py`
- **User Story 3 (P2)**: tras Phase 2 a nivel de negocio; el healthcheck de `api` asume `/health` real de US1. Secuenciar tras US1. Independiente de US2 salvo compartir el mismo `DATABASE_URL` hacia `db`

### Within Each User Story

- El test de la historia se escribe primero y falla antes de implementar
- Caso de uso en `src/application/services.py` antes de adaptadores inbound
- HTTP y CLI marcados `[P]` pueden ir en paralelo tras el servicio
- Manifiestos `[P]` (Dockerfile / `.dockerignore`) en paralelo; compose después

### Parallel Opportunities

- Phase 1: T001 ∥ T002
- Phase 2: T003 ∥ T004 ∥ T005; luego T006 → T007; T008 ∥ T007 tras T003
- US1: T009 → T010 (mismo archivo); tras T011 → T012 ∥ T013; luego T014 ∥ T015
- US2: T017 tras T016; T018 tras T017
- US3: T020 ∥ T021; luego T022; T019 puede escribirse en paralelo al manifiesto y fallar hasta que existan los tres archivos
- Polish: T023 ∥ (preparación); T024 al final

---

## Parallel Example: User Story 1

```bash
# Tests primero (mismo archivo, en serie):
Task: "T009 test_bdd_health_connected_http_and_cli"
Task: "T010 test_bdd_health_unavailable_and_business_ops_fail (tras T009)"

# Tras T011:
Task: "T012 GET /health real en src/adapters/inbound/api/app.py"
Task: "T013 comando health en src/adapters/inbound/cli.py"

# Tras T012/T013:
Task: "T014 mapear PersistenceUnavailableError HTTP en app.py"
Task: "T015 mapear PersistenceUnavailableError CLI en cli.py"
```

## Parallel Example: User Story 3

```bash
# Manifiestos en paralelo:
Task: "T020 Dockerfile"
Task: "T021 .dockerignore"
# Luego:
Task: "T022 docker-compose.yml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup
2. Completar Phase 2: Foundational
3. Completar Phase 3: User Story 1
4. **STOP and VALIDATE**: `uv run pytest -v tests/test_spec_004_postgres_runtime.py -k health`
5. Demostrar `/health` y CLI `health` con SQLite alcanzable y con PostgreSQL inalcanzable

### Incremental Delivery

1. Setup + Foundational → fábrica dual + adaptador PostgreSQL + error de puerto
2. User Story 1 → salud real HTTP/CLI + fallo explícito de negocio (MVP)
3. User Story 2 → selección transparente por `DATABASE_URL`
4. User Story 3 → manifiesto `api` + `db`
5. Polish → `AGENTS.md` + gates del quickstart

### Parallel Team Strategy

Con más de una persona:

1. Equipo cierra Phase 1–2 junto
2. Una persona toma US1 (servicio de salud + inbound)
3. Otra prepara US3 (Dockerfile / `.dockerignore` / compose) tras US1 para el healthcheck
4. US2 cierra la selección y el test de fábrica tras US1

---

## Notes

- `[P]` = archivos distintos y sin depender de tareas aún abiertas
- La etiqueta `[USn]` solo aparece en fases de historia
- Cada `test_bdd_*` de Escenarios 1–3 usa almacén aislado; no exigir Docker ni `docker compose up` en pytest
- Confirmar que el test nuevo falla antes de implementar la historia
- `uv run ruff check src/` debe pasar al tocar dominio, aplicación o adaptadores
- No añadir dependencias ni reabrir ADR-002 ni el consenso de triaje
- Inbound solo vía `IncidentService` + `create_incident_repository`; nunca importar `SQLiteIncidentRepository` ni `PostgresIncidentRepository` desde inbound
- `src/incident_repository.py` (benchmark) no se reescribe en este hito
- Smoke Compose documentado en `quickstart.md` queda fuera del gate automatizado

