---
description: "Task list for H002 active incidents summary"
---

# Tasks: Resumen de incidentes activos (H002)

**Input**: Design documents from `/specs/002-active-incidents-summary/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Incluidos. La spec define escenarios BDD y el plan exige `tests/test_spec_002_summary.py` (cinco `test_bdd_*` más el cumplimiento de `IncidentRepositoryPort`). Escribir cada test de historia y verlo fallar antes de la implementación de esa historia.

**Organization**: Tareas agrupadas por historia de usuario para implementar y probar cada una por separado.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede ejecutarse en paralelo (archivos distintos, sin depender de tareas incompletas)
- **[Story]**: Historia a la que pertenece la tarea (`US1`–`US4`)
- Las fases Setup, Foundational y Polish no llevan etiqueta de historia

## Path Conventions

- Proyecto único: `src/`, `tests/` en la raíz del repositorio
- Diseño: `specs/002-active-incidents-summary/`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Activar la frontera Ruff y el paquete outbound sin dependencias nuevas

- [X] T001 [P] Crear el paquete outbound vacío en `src/adapters/outbound/__init__.py` según la estructura de `specs/002-active-incidents-summary/plan.md`
- [X] T002 [P] Añadir `[tool.ruff.lint]` con `select = ["E4", "E7", "E9", "F", "TID"]` en `pyproject.toml`
- [X] T003 [P] Crear `src/domain/ruff.toml` con `extend = "../../pyproject.toml"`, `ban-relative-imports = "parents"` y `banned-api` de fastapi, typer, pydantic, uvicorn, sqlite3, sqlalchemy, httpx, `src.application` y `src.adapters` según `specs/002-active-incidents-summary/research.md`
- [X] T004 [P] Crear `src/application/ruff.toml` con `extend = "../../pyproject.toml"`, `ban-relative-imports = "parents"` y `banned-api` de fastapi, typer, pydantic, uvicorn, sqlite3, sqlalchemy, httpx y `src.adapters` según `specs/002-active-incidents-summary/research.md`
- [X] T005 [P] Crear `src/adapters/inbound/ruff.toml` con `extend = "../../../pyproject.toml"`, `ban-relative-imports = "parents"` y `banned-api` de sqlite3, sqlalchemy y `src.adapters.outbound.sqlite_repository` según `specs/002-active-incidents-summary/research.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Puerto, SQLite optimizado, fábrica y tipos de aplicación que todas las historias comparten

**⚠️ CRITICAL**: Ninguna historia empieza hasta cerrar esta fase

- [X] T007 [P] Declarar los dataclasses `ActiveIncidentView` y `ActiveIncidentsSummary` y la función `parse_reference_time` en `src/application/services.py` según data-model.md `ActiveIncidentView.incident_id`, data-model.md `ActiveIncidentView.title`, data-model.md `ActiveIncidentView.component`, data-model.md `ActiveIncidentView.severity`, data-model.md `ActiveIncidentView.status`, data-model.md `ActiveIncidentView.elapsed_minutes`, data-model.md `ActiveIncidentView.requires_escalation`, data-model.md `ActiveIncidentsSummary.total_active`, data-model.md `ActiveIncidentsSummary.breached_count` y data-model.md `ActiveIncidentsSummary.incidents` (`None` si el argumento viene omitido; `datetime.fromisoformat` si es naive; `ValidationError` si está vacío, si trae desplazamiento o si `fromisoformat` falla)
- [X] T008 Definir `IncidentRepositoryPort` con `@runtime_checkable` y los métodos `save_incident`, `get_incident`, `find_open_duplicates`, `list_active_incidents` y `check_health` en `src/application/ports.py` según `specs/002-active-incidents-summary/contracts/incident-repository-port.md`
- [X] T009 Implementar `SQLiteIncidentRepository` en `src/adapters/outbound/sqlite_repository.py` con el esquema heredado, índice `idx_incidents_component_status` e `INNER JOIN sla_policies`, mapeando data-model.md `incidents.incident_id`, data-model.md `incidents.title`, data-model.md `incidents.component`, data-model.md `incidents.severity`, data-model.md `incidents.status`, data-model.md `incidents.created_at`, data-model.md `incidents.resolved_at`, data-model.md `sla_policies.severity`, data-model.md `sla_policies.max_resolution_minutes` y data-model.md `sla_policies.operates_24x7`. `find_open_duplicates` devuelve `[]` (depends on T008)
- [X] T010 [P] Implementar `create_incident_repository` en `src/adapters/outbound/factory.py` leyendo `DATABASE_URL` con default `sqlite:///:memory:` y sin repetir la URL en el `ValueError` de esquema no soportado (depends on T009)
- [X] T011 [P] Añadir `test_sqlite_repository_satisfies_incident_repository_port` en `tests/test_spec_002_summary.py` comprobando `isinstance` de `SQLiteIncidentRepository` frente a `IncidentRepositoryPort` sobre un archivo SQLite de `tmp_path` (depends on T009)

**Checkpoint**: El puerto se cumple, la fábrica abre SQLite y el parseo de instantes existe. El resumen de operador todavía no está expuesto.

---

## Phase 3: User Story 1 - Ver resumen operativo de activos (Priority: P1) 🎯 MVP

**Goal**: Totales y detalle de activos (`OPEN` e `IN_PROGRESS`), con SLA y orden FR-011, por HTTP y CLI, sin filtro de componente

**Independent Test**: `test_bdd_global_summary_excludes_inactive` y `test_bdd_cli_summary_matches_http` con el catálogo de `specs/002-active-incidents-summary/data-model.md` y `reference_time=2026-11-20T12:00:00` (5 activos, 1 incumplido, orden `INC-A`…`INC-Z`, mismo JSON en ambos canales)

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T012 [US1] Escribir `test_bdd_global_summary_excludes_inactive` en `tests/test_spec_002_summary.py` sembrando el catálogo de aceptación con `save_incident` en un SQLite de archivo aislado y exigiendo `200` con data-model.md `ActiveIncidentsSummary.total_active`, data-model.md `ActiveIncidentsSummary.breached_count` y data-model.md `ActiveIncidentsSummary.incidents` del caso global
- [X] T013 [US1] Escribir `test_bdd_cli_summary_matches_http` en `tests/test_spec_002_summary.py` comparando el JSON parseado de `summary --reference-time` con el `GET` sobre el mismo archivo y el mismo instante (depends on T012)

### Implementation for User Story 1

- [X] T014 [US1] Implementar `IncidentService.get_active_incidents_summary` en `src/application/services.py` para el camino global (`component_filter` ausente), evaluando el SLA solo con `evaluate_sla_status` y rellenando data-model.md `SLAEvaluation.elapsed_minutes`, data-model.md `SLAEvaluation.is_breached`, data-model.md `SLAEvaluation.requires_escalation`, data-model.md `ActiveIncidentView.incident_id`, data-model.md `ActiveIncidentView.title`, data-model.md `ActiveIncidentView.component`, data-model.md `ActiveIncidentView.severity`, data-model.md `ActiveIncidentView.status`, data-model.md `ActiveIncidentView.elapsed_minutes`, data-model.md `ActiveIncidentView.requires_escalation`, data-model.md `ActiveIncidentsSummary.total_active`, data-model.md `ActiveIncidentsSummary.breached_count` y data-model.md `ActiveIncidentsSummary.incidents` (depends on T007, T009)
- [X] T015 [US1] Añadir `ActiveIncidentItem` y `ActiveIncidentsSummaryResponse` en `src/adapters/inbound/api/schemas.py` como espejo Pydantic de data-model.md `ActiveIncidentView.incident_id`, data-model.md `ActiveIncidentView.title`, data-model.md `ActiveIncidentView.component`, data-model.md `ActiveIncidentView.severity`, data-model.md `ActiveIncidentView.status`, data-model.md `ActiveIncidentView.elapsed_minutes`, data-model.md `ActiveIncidentView.requires_escalation`, data-model.md `ActiveIncidentsSummary.total_active`, data-model.md `ActiveIncidentsSummary.breached_count` y data-model.md `ActiveIncidentsSummary.incidents`
- [X] T016 [P] [US1] Exponer `GET /api/v1/incidents/summary` en `src/adapters/inbound/api/app.py`, con el repositorio de aplicación creado una vez vía `src/adapters/outbound/factory.py`, pasando un `reference_time` válido al servicio y respondiendo `200` según `specs/002-active-incidents-summary/contracts/http-get-incidents-summary.md` (depends on T010, T014, T015)
- [X] T017 [P] [US1] Añadir el comando `summary` en `src/adapters/inbound/cli.py` con `--reference-time`, serializando `ActiveIncidentsSummaryResponse` a stdout y código `0` según `specs/002-active-incidents-summary/contracts/cli-summary.md` (depends on T010, T014, T015)

**Checkpoint**: El resumen global y la paridad CLI funcionan sin filtro de componente.

---

## Phase 4: User Story 2 - Filtrar activos por componente (Priority: P2)

**Goal**: Totales y detalle limitados al componente pedido, con coincidencia exacta

**Independent Test**: `test_bdd_summary_filtered_by_component` con `component=payments-gateway` y el mismo instante: `total_active=2`, `breached_count=1`, solo ese componente, sin el `RESOLVED` de pagos

### Tests for User Story 2 ⚠️

- [X] T018 [US2] Escribir `test_bdd_summary_filtered_by_component` en `tests/test_spec_002_summary.py` para `GET /api/v1/incidents/summary?component=payments-gateway&reference_time=2026-11-20T12:00:00` según el subconjunto de `specs/002-active-incidents-summary/data-model.md`

### Implementation for User Story 2

- [X] T019 [US2] Aplicar el filtro en `get_active_incidents_summary` de `src/application/services.py`: tras `strip`, `None` o vacío llama a `list_active_incidents(None)`; cualquier otro valor usa coincidencia exacta de data-model.md `Incident.component` (depends on T014)
- [X] T020 [P] [US2] Aceptar el query `component` en `GET /api/v1/incidents/summary` dentro de `src/adapters/inbound/api/app.py` según `specs/002-active-incidents-summary/contracts/http-get-incidents-summary.md` (depends on T019)
- [X] T021 [P] [US2] Aceptar `--component` en el comando `summary` de `src/adapters/inbound/cli.py` según `specs/002-active-incidents-summary/contracts/cli-summary.md` (depends on T019)

**Checkpoint**: El resumen global de US1 sigue igual y el filtro devuelve solo el componente pedido.

---

## Phase 5: User Story 3 - Conjunto vacío de activos (Priority: P3)

**Goal**: Cero activos o un componente sin coincidencias responden éxito, no error

**Independent Test**: `test_bdd_empty_active_summary` obtiene HTTP `200` y CLI salida `0`, ambos con `total_active=0`, `breached_count=0` e `incidents=[]`

### Tests for User Story 3 ⚠️

- [X] T022 [US3] Escribir `test_bdd_empty_active_summary` en `tests/test_spec_002_summary.py` para catálogo sin activos y para componente desconocido: `GET` responde `200` y `summary` termina en `0`, con el mismo JSON vacío, según FR-009 y el contrato HTTP

### Implementation for User Story 3

- [X] T023 [US3] Devolver agregados en cero desde `get_active_incidents_summary` en `src/application/services.py` cuando no hay filas activas, manteniendo data-model.md `ActiveIncidentsSummary.total_active`, data-model.md `ActiveIncidentsSummary.breached_count` y data-model.md `ActiveIncidentsSummary.incidents` (depends on T014, T019)
- [X] T024 [US3] Responder `200` con ese cuerpo vacío desde `GET /api/v1/incidents/summary` en `src/adapters/inbound/api/app.py` según `specs/002-active-incidents-summary/contracts/http-get-incidents-summary.md` (depends on T023)

**Checkpoint**: La ausencia de activos no se convierte en 404, 422 ni en salida de error del CLI.

---

## Phase 6: User Story 4 - Rechazo de instante inválido (Priority: P3)

**Goal**: Un `reference_time` ilegible no produce métricas de SLA

**Independent Test**: `test_bdd_invalid_reference_time_rejected` con un valor ilegible: HTTP `422` y CLI código `1`, sin JSON de resumen

### Tests for User Story 4 ⚠️

- [X] T025 [US4] Escribir `test_bdd_invalid_reference_time_rejected` en `tests/test_spec_002_summary.py` ejercitando el query HTTP y `--reference-time` del CLI con el mismo valor ilegible, según `specs/002-active-incidents-summary/spec.md` escenario 5

### Implementation for User Story 4

- [X] T026 [P] [US4] Traducir `ValidationError` de `parse_reference_time` a `422` con `{"detail": ...}` en `src/adapters/inbound/api/app.py` sin calcular el resumen, según `specs/002-active-incidents-summary/contracts/http-get-incidents-summary.md` (depends on T007, T016)
- [X] T027 [P] [US4] Traducir esa misma `ValidationError` a stderr y salida `1` en `src/adapters/inbound/cli.py` sin imprimir el JSON del resumen, según `specs/002-active-incidents-summary/contracts/cli-summary.md` (depends on T007, T017)

**Checkpoint**: Un instante válido sigue devolviendo el resumen de US1–US3; uno ilegible se rechaza en los dos canales.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Retirar el N+1 de la ruta de persistencia y cerrar la validación del quickstart

- [X] T028 [P] Delegar el benchmark de `src/incident_repository.py` en `SQLiteIncidentRepository` (`seed_synthetic_incidents`, `list_active_incidents` y `evaluate_sla_status`) y actualizar la fila N+1 de `AGENTS.md`
- [X] T029 [P] Conservar `GET /health` en `src/adapters/inbound/api/app.py` respondiendo `{"status": "ok"}` sin llamar a `check_health`, según `specs/002-active-incidents-summary/contracts/http-get-incidents-summary.md`
- [X] T030 Ejecutar la validación de `specs/002-active-incidents-summary/quickstart.md`: `uv run ruff check src/`, `uv run pytest -v` y los módulos `src.domain.triage_rules` y `src.domain.sla_calculator`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias
- **Foundational (Phase 2)**: depende de Setup y bloquea todas las historias
- **User Stories (Phase 3+)**: dependen de Foundational
- **Polish (Phase 7)**: depende de las historias que se quieran entregar

### User Story Dependencies

- **User Story 1 (P1)**: empieza tras Phase 2. No depende de US2–US4. Es el MVP
- **User Story 2 (P2)**: empieza tras US1 porque amplía `src/application/services.py`, `src/adapters/inbound/api/app.py` y `src/adapters/inbound/cli.py`
- **User Story 3 (P3)**: empieza tras US2. El caso vacío reutiliza el mismo endpoint y el mismo agregado
- **User Story 4 (P3)**: empieza tras US1 (el parser ya está en Phase 2). Secuenciarla después de US3 porque también edita `src/adapters/inbound/api/app.py` y `tests/test_spec_002_summary.py`

### Within Each User Story

- El test de la historia se escribe primero y falla antes de implementar
- El caso de uso en `src/application/services.py` precede a los adaptadores
- Los esquemas de `src/adapters/inbound/api/schemas.py` preceden a HTTP y CLI
- HTTP y CLI de una misma historia, cuando están marcados `[P]`, pueden ir en paralelo entre sí

### Parallel Opportunities

- Phase 1: T001, T002, T003, T004 y T005 en paralelo
- Phase 2: T007 y T008 en paralelo; después T009; después T010 y T011 en paralelo
- US1: T016 y T017 en paralelo tras T014 y T015
- US2: T020 y T021 en paralelo tras T019
- US4: T026 y T027 en paralelo tras T025
- Polish: T028 y T029 en paralelo; T030 al final

---

## Parallel Example: User Story 1

```bash
# Tras T014 y T015, los dos inbound no se pisan:
Task: "T016 GET /api/v1/incidents/summary en src/adapters/inbound/api/app.py"
Task: "T017 comando summary en src/adapters/inbound/cli.py"
```

## Parallel Example: User Story 2

```bash
# Tras T019:
Task: "T020 query component en src/adapters/inbound/api/app.py"
Task: "T021 flag --component en src/adapters/inbound/cli.py"
```

## Parallel Example: User Story 4

```bash
# Tras T025:
Task: "T026 HTTP 422 en src/adapters/inbound/api/app.py"
Task: "T027 CLI exit 1 en src/adapters/inbound/cli.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup
2. Completar Phase 2: Foundational
3. Completar Phase 3: User Story 1
4. **STOP and VALIDATE**: `uv run pytest -v tests/test_spec_002_summary.py -k "global_summary or cli_summary or satisfies_incident_repository"`
5. Demostrar el resumen global por HTTP y CLI

### Incremental Delivery

1. Setup + Foundational → puerto SQLite y tipos listos
2. User Story 1 → resumen global y paridad CLI (MVP)
3. User Story 2 → filtro por componente
4. User Story 3 → vacío con `200`
5. User Story 4 → rechazo del instante ilegible
6. Polish → benchmark delegado, health intacto y quickstart completo

### Parallel Team Strategy

Con más de una persona:

1. Todo el equipo cierra Phase 1 y Phase 2
2. Una persona toma US1 (archivos de servicio, esquemas, API y CLI)
3. US2, US3 y US4 esperan porque comparten `src/application/services.py`, `src/adapters/inbound/api/app.py` y `tests/test_spec_002_summary.py`
4. Dentro de US1, US2 y US4, HTTP y CLI sí pueden repartirse cuando la tarea lleva `[P]`

---

## Notes

- `[P]` = archivos distintos y sin depender de tareas aún abiertas
- La etiqueta `[USn]` solo aparece en fases de historia
- Cada historia se prueba con su `test_bdd_*` sobre un archivo SQLite propio, sin reutilizar la fixture `client` de H001
- Confirmar que el test nuevo falla antes de implementar la historia
- `uv run ruff check src/` debe pasar al tocar dominio, aplicación o adaptadores
- No añadir dependencias ni reabrir el cálculo de SLA de ADR-002
