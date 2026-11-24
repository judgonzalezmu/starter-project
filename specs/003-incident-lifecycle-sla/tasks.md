---
description: "Task list for H003 incident lifecycle, duplicates and SLA"
---

# Tasks: Ciclo de vida, duplicados y consulta SLA (H003)

**Input**: Design documents from `/specs/003-incident-lifecycle-sla/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md, `.specify/memory/constitution.md`

**Tests**: Incluidos. La spec define cinco escenarios BDD y el plan exige `tests/test_spec_003_lifecycle_sla.py` (cinco `test_bdd_*` con `TestClient` + `CliRunner` y almacén aislado). Escribir cada test de historia y verlo fallar antes de la implementación de esa historia.

**Organization**: Tareas agrupadas por historia de usuario para implementar y probar cada una por separado. Respetar constitución y skill hexagonal (adapters → application → domain).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede ejecutarse en paralelo (archivos distintos, sin depender de tareas incompletas)
- **[Story]**: Historia a la que pertenece la tarea (`US1`–`US4`)
- Las fases Setup, Foundational y Polish no llevan etiqueta de historia

## Path Conventions

- Proyecto único: `src/`, `tests/` en la raíz del repositorio
- Diseño: `specs/003-incident-lifecycle-sla/`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Preparar el módulo de aceptación H003 sin dependencias nuevas

- [X] T001 [P] Crear el esqueleto vacío `tests/test_spec_003_lifecycle_sla.py` con docstring de feature H003 según `specs/003-incident-lifecycle-sla/plan.md`
- [X] T002 [P] Confirmar en `pyproject.toml` que el grupo `dev` ya cubre pytest, httpx y Ruff; no añadir dependencias nuevas según `specs/003-incident-lifecycle-sla/research.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Dominio ampliado, normalización SLA, persistencia de duplicados y excepciones de aplicación compartidas

**⚠️ CRITICAL**: Ninguna historia empieza hasta cerrar esta fase

- [X] T003 [P] Añadir `TeamName` y extender `Incident` en `src/domain/models.py` con data-model.md `TeamName`, data-model.md `Incident.incident_id`, data-model.md `Incident.title`, data-model.md `Incident.component`, data-model.md `Incident.severity`, data-model.md `Incident.status`, data-model.md `Incident.created_at`, data-model.md `Incident.resolved_at`, data-model.md `Incident.raw_text`, data-model.md `Incident.recommended_team` y data-model.md `Incident.duplicate_group_key`; tipar `TriageResult.recommended_team` como `TeamName` sin reabrir reglas de triaje
- [X] T004 [P] Añadir `_ensure_comparable_naive` y normalizar instantes al inicio de `evaluate_sla_status` en `src/domain/sla_calculator.py` según `specs/003-incident-lifecycle-sla/research.md` sin cambiar la política ADR-002
- [X] T005 Ampliar el esquema SQLite en `src/adapters/outbound/sqlite_repository.py`: columnas data-model.md `Incident.raw_text`, data-model.md `Incident.recommended_team`, data-model.md `Incident.duplicate_group_key`; índice `idx_incidents_dup_key` sobre `(duplicate_group_key, status)`; `ALTER TABLE` suave para DBs previas; actualizar `save_incident`, `get_incident` y `_incident_from_row` según `specs/003-incident-lifecycle-sla/contracts/incident-repository-port.md` (depends on T003)
- [X] T006 Implementar `find_open_duplicates` real en `src/adapters/outbound/sqlite_repository.py` filtrando `OPEN` \| `IN_PROGRESS` \| `ESCALATION_REQUIRED` por data-model.md `Incident.duplicate_group_key` y data-model.md `Incident.status`, usando `idx_incidents_dup_key`, según `specs/003-incident-lifecycle-sla/contracts/incident-repository-port.md` (depends on T005)
- [X] T007 [P] Declarar `IncidentNotFoundError`, `IncidentAlreadyExistsError` y el dataclass de aplicación `CreationResult` (data-model.md `CreationResult.is_duplicate`, data-model.md `CreationResult.duplicate_of`) en `src/application/services.py`; añadir parseo ISO-8601 naive compartido para `created_at`/`resolved_at` de creación (misma política que `parse_reference_time`: omitido→`None`; vacío/tz-aware/ilegible→`ValidationError`) según `specs/003-incident-lifecycle-sla/research.md`

**Checkpoint**: `Incident` persistible con clave de duplicado, índice listo, SLA tolerante a aware/naive, parseo de instantes de alta unificado. Aún no hay `POST /incidents` ni `.../sla`.

---

## Phase 3: User Story 1 - Registrar un incidente entrante (Priority: P1) 🎯 MVP

**Goal**: Alta persistente con clasificación completa, defaults (`INC-<HEX8>`, `created_at`, `status=OPEN`) y respuesta `201` / CLI `0` sin equivalentes abiertos

**Independent Test**: Escenario 1 — `test_bdd_create_incident_201_without_duplicates`: `POST /api/v1/incidents` con `title`+`raw_text` válidos → `201`, persistido, clasificación completa, `is_duplicate=false`, `duplicate_of=[]`

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T008 [US1] Escribir `test_bdd_create_incident_201_without_duplicates` en `tests/test_spec_003_lifecycle_sla.py` sobre SQLite de archivo aislado (`tmp_path` + `DATABASE_URL`), exigiendo `201` y data-model.md `CreationResult.is_duplicate=false` con data-model.md `CreationResult.duplicate_of=[]` según Escenario 1 de `specs/003-incident-lifecycle-sla/spec.md`

### Implementation for User Story 1

- [X] T009 [US1] Implementar `IncidentService.create_incident` en `src/application/services.py`: validar data-model.md `Incident.title` y data-model.md `Incident.raw_text` (no vacíos tras `strip`); defaults de data-model.md `Incident.incident_id` (`INC-`+HEX8 mayúsculas), data-model.md `Incident.created_at`, data-model.md `Incident.status` (`OPEN`); catálogo de data-model.md `Incident.status`; reglas de data-model.md `Incident.resolved_at` si `RESOLVED`; colisión → `IncidentAlreadyExistsError`; clasificar con `classify_incident_report`; persistir vía `save_incident` rellenando data-model.md `Incident.component`, data-model.md `Incident.severity`, data-model.md `Incident.recommended_team`, data-model.md `Incident.duplicate_group_key`; llamar `find_open_duplicates` y rellenar data-model.md `CreationResult.is_duplicate` y data-model.md `CreationResult.duplicate_of` con el resultado completo (FR-009/FR-010) (depends on T003, T006, T007)
- [X] T010 [P] [US1] Añadir `CreateIncidentRequest` e `IncidentCreatedResponse` en `src/adapters/inbound/api/schemas.py` como transporte de data-model.md `Incident.title`, data-model.md `Incident.raw_text`, data-model.md `Incident.incident_id`, data-model.md `Incident.created_at`, data-model.md `Incident.status`, data-model.md `Incident.resolved_at`, data-model.md `Incident.component`, data-model.md `Incident.severity`, data-model.md `Incident.recommended_team`, data-model.md `Incident.duplicate_group_key`, data-model.md `CreationResult.is_duplicate` y data-model.md `CreationResult.duplicate_of` según `specs/003-incident-lifecycle-sla/contracts/http-post-incidents.md`
- [X] T011 [P] [US1] Exponer `POST /api/v1/incidents` en `src/adapters/inbound/api/app.py` parseando `created_at`/`resolved_at` con el helper de T007, delegando solo en `IncidentService.create_incident`, mapeando `ValidationError`→`422` e `IncidentAlreadyExistsError`→`409`, respondiendo `201` según `specs/003-incident-lifecycle-sla/contracts/http-post-incidents.md` (depends on T007, T009, T010)
- [X] T012 [P] [US1] Añadir el comando `create` en `src/adapters/inbound/cli.py` con `--resolved-at`, parseando instantes con el helper de T007 e invocando exactamente `IncidentService.create_incident`, imprimiendo el mismo JSON de negocio y códigos `0`/`1` según `specs/003-incident-lifecycle-sla/contracts/cli-create.md` (depends on T007, T009, T010)

**Checkpoint**: Un operador puede registrar un incidente válido por HTTP y CLI sin aviso de duplicado.

---

## Phase 4: User Story 2 - Aviso de equivalente abierto al registrar (Priority: P1)

**Goal**: Al crear, si hay abiertos con la misma `duplicate_group_key`, responder `is_duplicate=true` y `duplicate_of` sin bloquear la persistencia; ignorar `RESOLVED`

**Independent Test**: Escenario 2 — `test_bdd_create_detects_open_duplicate`: dado un abierto (y opcionalmente un `RESOLVED` equivalente), el nuevo alta es `201` con `is_duplicate=true` y el id abierto en `duplicate_of` (sin el nuevo ni el resuelto)

### Tests for User Story 2 ⚠️

- [X] T013 [US2] Escribir `test_bdd_create_detects_open_duplicate` en `tests/test_spec_003_lifecycle_sla.py` sembrando un abierto y un `RESOLVED` con la misma data-model.md `Incident.duplicate_group_key`, registrando uno nuevo y afirmando data-model.md `CreationResult.is_duplicate=true` y data-model.md `CreationResult.duplicate_of` solo con ids abiertos (sin el nuevo ni el `RESOLVED`) según Escenario 2

### Implementation for User Story 2

- [X] T014 [US2] Asegurar en `IncidentService.create_incident` (`src/application/services.py`) los bordes FR-009 ya cableados en T009: data-model.md `CreationResult.duplicate_of` excluye `RESOLVED` y el id nuevo, incluye todos los `OPEN`\|`IN_PROGRESS`\|`ESCALATION_REQUIRED`, y el aviso nunca impide `save_incident` (depends on T006, T009)
- [X] T015 [US2] Ampliar `test_bdd_create_detects_open_duplicate` en `tests/test_spec_003_lifecycle_sla.py` (o asserts del mismo test) con al menos un equivalente en `IN_PROGRESS` o `ESCALATION_REQUIRED` y/o varios abiertos, comprobando data-model.md `CreationResult.duplicate_of` completo vía HTTP según Escenario 2 (depends on T013, T014)

**Checkpoint**: El aviso de duplicado informa y no bloquea; US1 sin abiertos sigue con `is_duplicate=false`.

---

## Phase 5: User Story 3 - Consultar el progreso de SLA (Priority: P2)

**Goal**: Auditar un incidente persistido en un instante de referencia (o “ahora”) por HTTP y CLI con métricas ADR-002

**Independent Test**: Escenario 3 — `test_bdd_sla_p2_business_hours_elapsed_120`: P2 creado `2026-11-06T17:00:00`, `reference_time=2026-11-09T09:00:00` → `elapsed_minutes=120`, `allowed_minutes=480`, `remaining_minutes=360`, `is_breached=false`, `requires_escalation=false`

### Tests for User Story 3 ⚠️

- [X] T016 [US3] Escribir `test_bdd_sla_p2_business_hours_elapsed_120` en `tests/test_spec_003_lifecycle_sla.py` sembrando el P2 con data-model.md `Incident.severity`, data-model.md `Incident.created_at` y data-model.md `Incident.status`, consultando `GET /api/v1/incidents/{id}/sla` y afirmando data-model.md `SLAEvaluation.elapsed_minutes`, data-model.md `SLAEvaluation.allowed_minutes`, data-model.md `SLAEvaluation.remaining_minutes`, data-model.md `SLAEvaluation.is_breached` y data-model.md `SLAEvaluation.requires_escalation` según Escenario 3

### Implementation for User Story 3

- [X] T017 [US3] Implementar `IncidentService.evaluate_incident_sla` en `src/application/services.py`: `get_incident` → `IncidentNotFoundError` si falta; `reference_time` omitido → `datetime.now()`; si `reference_time` < data-model.md `Incident.created_at` → `ValidationError`; delegar en `evaluate_sla_status` devolviendo data-model.md `SLAEvaluation.incident_id`, data-model.md `SLAEvaluation.elapsed_minutes`, data-model.md `SLAEvaluation.allowed_minutes`, data-model.md `SLAEvaluation.remaining_minutes`, data-model.md `SLAEvaluation.is_breached` y data-model.md `SLAEvaluation.requires_escalation` (depends on T004, T005, T007)
- [X] T018 [P] [US3] Añadir `SLAEvaluationResponse` en `src/adapters/inbound/api/schemas.py` con data-model.md `SLAEvaluation.incident_id`, data-model.md `SLAEvaluation.elapsed_minutes`, data-model.md `SLAEvaluation.allowed_minutes`, data-model.md `SLAEvaluation.remaining_minutes`, data-model.md `SLAEvaluation.is_breached` y data-model.md `SLAEvaluation.requires_escalation` según `specs/003-incident-lifecycle-sla/contracts/http-get-incident-sla.md`
- [X] T019 [P] [US3] Exponer `GET /api/v1/incidents/{incident_id}/sla` en `src/adapters/inbound/api/app.py` con query `reference_time`, delegando en `evaluate_incident_sla`, mapeando `IncidentNotFoundError`→`404` y `ValidationError`→`422`, según `specs/003-incident-lifecycle-sla/contracts/http-get-incident-sla.md` (depends on T017, T018)
- [X] T020 [P] [US3] Añadir el comando `sla` en `src/adapters/inbound/cli.py` invocando exactamente `IncidentService.evaluate_incident_sla` con `--incident-id` y `--reference-time` opcionales según `specs/003-incident-lifecycle-sla/contracts/cli-sla.md` (depends on T017, T018)

**Checkpoint**: La auditoría SLA determinista del viernes→lunes P2 pasa por HTTP y CLI.

---

## Phase 6: User Story 4 - Rechazo de entradas inválidas (Priority: P3)

**Goal**: Rechazar altas y consultas engañosas (vacíos, id colisionado, status inválido, `resolved_at` ilegal, SLA 404/422) sin persistir ni inventar métricas

**Independent Test**: Escenario 4 — `test_bdd_sla_not_found_and_reference_before_created` (404 + 422); más aserciones de creación inválida cubiertas en el mismo módulo o en este test ampliado según FR-002/004/005/006

### Tests for User Story 4 ⚠️

- [X] T021 [US4] Escribir `test_bdd_sla_not_found_and_reference_before_created` en `tests/test_spec_003_lifecycle_sla.py` para (a) id inexistente → HTTP `404`, (b) `reference_time` < data-model.md `Incident.created_at` → HTTP `422` sin métricas, y (c) `reference_time` ilegible o con tz → HTTP `422` / CLI exit `1` sin métricas, según Escenario 4 y FR-012; incluir (o tests auxiliares en el mismo archivo) rechazos de creación: title/raw_text vacíos → `422`, id existente → `409`, status no canónico → `422`, `resolved_at` < `created_at` con `RESOLVED` → `422`

### Implementation for User Story 4

- [X] T022 [US4] Asegurar en `IncidentService.create_incident` y `evaluate_incident_sla` (`src/application/services.py`) todos los rechazos de la tabla de validación de `specs/003-incident-lifecycle-sla/data-model.md` (title/raw_text, status, colisión de data-model.md `Incident.incident_id`, data-model.md `Incident.resolved_at`, reference_time vs data-model.md `Incident.created_at`, no encontrado) sin persistir ni devolver métricas engañosas (depends on T009, T017)
- [X] T023 [P] [US4] Confirmar mapeo HTTP en `src/adapters/inbound/api/app.py`: `422` / `409` / `404` según `specs/003-incident-lifecycle-sla/contracts/http-post-incidents.md` y `specs/003-incident-lifecycle-sla/contracts/http-get-incident-sla.md` (depends on T022)
- [X] T024 [P] [US4] Confirmar mapeo CLI en `src/adapters/inbound/cli.py`: exit `1` y stderr sin JSON engañoso para los mismos fallos según `specs/003-incident-lifecycle-sla/contracts/cli-create.md` y `specs/003-incident-lifecycle-sla/contracts/cli-sla.md` (depends on T022)

**Checkpoint**: Ninguna entrada inválida crea filas ni inventa SLA; US1–US3 con entradas válidas siguen verdes.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Paridad CLI Escenario 5, regresión H001/H002 y gates del quickstart

- [X] T025 Escribir `test_bdd_cli_create_and_sla_parity` en `tests/test_spec_003_lifecycle_sla.py` comparando JSON de negocio HTTP vs CLI `create` y `sla` sobre el mismo `DATABASE_URL` aislado (Escenario 5)
- [X] T026 [P] Ajustar semillas/constructores de `tests/test_spec_002_summary.py` (y cualquier uso de `Incident(...)`) para convivir con los defaults nuevos de data-model.md `Incident.raw_text`, data-model.md `Incident.recommended_team` y data-model.md `Incident.duplicate_group_key` sin cambiar el contrato H002
- [X] T027 [P] Actualizar la fila de comandos H003 en `AGENTS.md` si hace falta (`create`, `sla`, pytest del spec 003) sin reinventar requisitos
- [X] T028 Ejecutar la validación de `specs/003-incident-lifecycle-sla/quickstart.md`: `uv run ruff check src/`, `uv run python -m src.domain.triage_rules`, `uv run python -m src.domain.sla_calculator`, `uv run pytest -v`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias
- **Foundational (Phase 2)**: depende de Setup y bloquea todas las historias
- **User Stories (Phase 3+)**: dependen de Foundational
- **Polish (Phase 7)**: depende de US1–US4 (Escenario 5 necesita create + sla)

### User Story Dependencies

- **User Story 1 (P1)**: tras Phase 2. MVP. No depende de US2–US4
- **User Story 2 (P1)**: tras US1 (amplía el mismo `create_incident` y los mismos adaptadores de alta)
- **User Story 3 (P2)**: tras Phase 2 puede sembrarse con `save_incident`; secuenciar tras US1 para no pelear por `app.py`/`cli.py`/`schemas.py`. Independiente de US2 a nivel de negocio
- **User Story 4 (P3)**: tras US1 y US3 (cubre rechazos de create y de SLA)

### Within Each User Story

- El test de la historia se escribe primero y falla antes de implementar
- Caso de uso en `src/application/services.py` antes de adaptadores
- Esquemas Pydantic antes o en paralelo de HTTP/CLI cuando no comparten el mismo archivo de edición conflictiva
- HTTP y CLI marcados `[P]` pueden ir en paralelo tras el servicio

### Parallel Opportunities

- Phase 1: T001 ∥ T002
- Phase 2: T003 ∥ T004 ∥ T007; luego T005 → T006
- US1: T010 ∥ T009 (tras T007); luego T011 ∥ T012
- US2: T015 tras T013 y T014 (no paralelo con T014 si edita el mismo test)
- US3: T018 ∥ (tras T017) T019 ∥ T020
- US4: T023 ∥ T024 tras T022
- Polish: T026 ∥ T027; T025 antes o junto a T028; T028 al final

---

## Parallel Example: User Story 1

```bash
# Tras T009 y T010:
Task: "T011 POST /api/v1/incidents en src/adapters/inbound/api/app.py"
Task: "T012 comando create en src/adapters/inbound/cli.py"
```

## Parallel Example: User Story 3

```bash
# Tras T017 y T018:
Task: "T019 GET .../sla en src/adapters/inbound/api/app.py"
Task: "T020 comando sla en src/adapters/inbound/cli.py"
```

## Parallel Example: User Story 4

```bash
# Tras T022:
Task: "T023 mapeo HTTP 422/409/404 en src/adapters/inbound/api/app.py"
Task: "T024 mapeo CLI exit 1 en src/adapters/inbound/cli.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup
2. Completar Phase 2: Foundational
3. Completar Phase 3: User Story 1
4. **STOP and VALIDATE**: `uv run pytest -v tests/test_spec_003_lifecycle_sla.py -k create_incident_201`
5. Demostrar alta HTTP/CLI sin duplicados

### Incremental Delivery

1. Setup + Foundational → modelo, índice y excepciones
2. User Story 1 → alta persistente (MVP)
3. User Story 2 → aviso de duplicado abierto
4. User Story 3 → auditoría SLA
5. User Story 4 → rechazos
6. Polish → Escenario 5, regresión H002, quickstart completo

### Parallel Team Strategy

Con más de una persona:

1. Equipo cierra Phase 1–2 junto
2. Una persona toma US1 (servicio create + schemas + API/CLI)
3. US2 espera el create de US1
4. US3 puede prepararse en paralelo solo si se acuerdan merges cuidadosos en `app.py`/`cli.py`; si no, tras US1
5. US4 al final sobre ambos canales

---

## Notes

- `[P]` = archivos distintos y sin depender de tareas aún abiertas
- La etiqueta `[USn]` solo aparece en fases de historia
- Cada `test_bdd_*` usa SQLite de archivo propio; no reutilizar el `client` de sesión H001 sin aislar `DATABASE_URL`
- Confirmar que el test nuevo falla antes de implementar la historia
- `uv run ruff check src/` debe pasar al tocar dominio, aplicación o adaptadores
- No añadir dependencias ni reabrir ADR-002 ni el consenso de triaje
- Inbound solo vía `IncidentService` + `create_incident_repository`; nunca importar `SQLiteIncidentRepository` desde inbound
