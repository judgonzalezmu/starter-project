# Bitácora de Desarrollo Guiado por Especificaciones — Semana 2 (`SDD_LOG.md`)

**Estudiante(s)**: `Juan David González Muñoz`  
**Fecha**: `2026-11-24`  
**Modelos Utilizados en OpenCode (Plan/Razonamiento vs. Build/Implementación)**: `Cursor Grok 4.5 (razonamiento extendido) para /speckit.clarify, /speckit.plan y /speckit.analyze; modelo rápido / modo Agent directo para /speckit.implement y remediaciones mecánicas de tasks/pytest`

---

## 1. Elicitación con `/speckit.clarify` y Auditoría con `/speckit.analyze`

### 1.1 Feature `003-incident-lifecycle-sla`

- **Ambigüedades y casos borde detectados con `/speckit.clarify`**:
  1. **Contrato de creación incompleto**: no bastaba “guardar el incidente”; había que fijar campos obligatorios (`title`, `raw_text`), defaults (`status=OPEN`, `created_at` ahora, `incident_id=INC-<HEX8>`), códigos de rechazo (`422` por vacíos) y el payload de éxito con clasificación completa + `is_duplicate` / `duplicate_of`.
  2. **Criterio de “duplicado abierto”**: la clave `duplicate_group_key` sola no basta; se clarificó que solo cuentan estados `OPEN` | `IN_PROGRESS` | `ESCALATION_REQUIRED`, excluyendo `RESOLVED` y el propio id recién creado, y que el aviso **no bloquea** la persistencia.
  3. **Colisión de `incident_id`**: no estaba dicho si sobrescribir o rechazar; se cerró en HTTP `409` / CLI exit `1` sin persistir.
  4. **Catálogo de `status` y `resolved_at`**: se aceptó cualquier estado canónico en el alta; si `status=RESOLVED` sin `resolved_at`, se iguala a `created_at`; si `resolved_at` < `created_at` → `422`.
  5. **Auditoría SLA**: `reference_time` opcional; `404` si no existe el incidente; `422` si `reference_time` < `created_at` (evita métricas engañosas).
- **Hallazgos o validaciones de `/speckit.analyze` antes de implementar**:  
  El plan contra Constitución v1.0.0 / ADR-003 pasó las puertas hexagonales (PASS). La remediación post-analyze del 2026-11-23 fue concreta, no cosmética: (a) CLI `create` debía exponer `--resolved-at` para paridad real con HTTP; (b) `tasks.md` debía explicitar el helper de parseo de timestamps y el límite US1/US2 de duplicados; (c) T021 debía cubrir `reference_time` ilegible además del caso “anterior a `created_at`”. Eso evitó implementar una CLI asimétrica y un escenario BDD incompleto.

### 1.2 Feature `004-postgres-container-runtime`

- **Ambigüedades y RNF aclarados antes de diseñar PostgreSQL/Compose**:
  1. **Bootstrap de esquema sin migraciones**: al primer arranque contra PostgreSQL vacío, el adaptador crea tablas de forma idempotente (`CREATE TABLE IF NOT EXISTS`); no se introduce Alembic ni un tercer proceso de migrate.
  2. **Aceptación del Escenario 4 sin acoplar CI a Docker Desktop**: la suite automatizada valida el **manifiesto** (Dockerfile, `.dockerignore`, `docker-compose.yml`); el smoke `docker compose up --build` + `GET /health` queda como evidencia manual cuando el daemon está disponible.
  3. **`DATABASE_URL` inválida / vacía**: fallo inmediato al resolver el almacén, **sin** fallback silencioso a `:memory:`; el mensaje no debe filtrar la URL.
  4. **Degradación en caliente**: si la base deja de ser alcanzable tras un arranque válido, `/health` y CLI `health` reportan `503` / exit `1` con `database=unavailable`, y las operaciones de negocio fallan de forma explícita (no inventan datos ni reutilizan el JSON de health en cada ruta).
  5. **RNF de topología**: dos contenedores (`api` + `db`), `depends_on: service_healthy` sobre `pg_isready`, healthcheck HTTP de la API sobre `/health`, credenciales solo por entorno — fijados por ADR-004 y Constitución 1.1.0 antes de especificar.

---

## 2. Comparación Crítica: SDD Manual (Iteración 1) vs. GitHub Spec Kit (Iteración 2 y Retos)

| Dimensión Comparada | SDD Manual (Iteración 1: `001`) | GitHub Spec Kit (Iteración 2 y Retos: `002`–`004`) |
| :--- | :--- | :--- |
| **Separación *QUÉ* vs. *CÓMO* vs. *TAREAS*** | Un solo Markdown (`specs/001-triage-endpoint-manual.md`) mezcla objetivo, contrato HTTP/CLI y escenarios. El *cómo* (FastAPI/Typer, layout hexagonal) se negoció en chat y ADR-003 aparte; no había `plan.md`/`tasks.md` generados. | Pipeline explícito: `spec.md` = QUÉ + BDD; `plan.md`/`research.md`/`contracts/` = CÓMO; `tasks.md` = orden de implementación. En H004, el QUÉ cita outcomes operativos y el CÓMO queda anclado a ADR-004 (psycopg, Compose) sin reabrir triaje/SLA. |
| **Gestión de ambigüedades (`/speckit.clarify`)** | Ambigüedades se resolvieron ad hoc (prompts, consensus de triaje, checklist informal). Riesgo: decisiones implícitas (“hoy” no eleva a P0) solo en código/`CONTEXT_LOG`. | Sesiones `Clarifications` versionadas en la propia spec (p. ej. `409` por id colisionado; bootstrap idempotente; fallo sin fallback). Cada Q→A se convierte en requisito comprobable antes de plan/tasks. |
| **Consistencia contra la Constitución (`/speckit.analyze`)** | No existía constitución formal en H001; la gobernanza vivía en ADRs sueltos y reglas de agente. Inconsistencias (p. ej. paridad CLI) se cazaban al escribir tests. | `/speckit.analyze` + checklist cruzan spec/plan/tasks contra `.specify/memory/constitution.md`. En H003 detectó asimetría `--resolved-at`; en H004 exige Constitución 1.1.0 + ADR-004 **antes** de implementar. |
| **Riesgo de verbosidad / exceso de Markdown** | Un archivo denso pero acotado (~100–150 líneas). Fácil de revisar; difícil de escalar a varios hitos sin duplicar contratos. | Mayor superficie (`spec` + `plan` + `research` + N contracts + `tasks` + checklists). Mitigado con `docs/ROADMAP.md` corto (solo capacidades), contracts de 1 página por superficie y BDD 1:1 con `test_bdd_*`. |

- **Análisis basado en MartinFowler.com (Birgitta Böckeler)**:
  1. De los tres niveles descritos por Böckeler (**Spec-first**, **Spec-anchored**, **Spec-as-source**), ¿en cuál ubicas este proyecto de *IncidentOps* y por qué?  
     **Spec-anchored (con tramos Spec-first)**. Las specs 002–004 son la fuente de verdad de *aceptación* y se escriben antes del código del hito (Spec-first táctico), pero el sistema de registro sigue siendo el código + ADRs inmutables + pruebas deterministas: la spec no genera el runtime ni sustituye a `IncidentService`/`sla_calculator`. Cuando dominio y spec divergen, se alinea la implementación a la spec de aceptación (como en H001), no se regenera el producto desde Markdown. Tampoco es Spec-as-source: no hay compilador de specs ni despliegue dirigido solo por el documento.
  2. Böckeler advierte que los *toolkits* SDD pueden generar "montañas de Markdown" difíciles de revisar para un humano. ¿Qué técnicas aplicaste (concisión en `docs/ROADMAP.md`, curaduría en `clarify`/`plan`/`tasks` y pruebas deterministas en `pytest`) para evitar aprobar especificaciones verbosas a ciegas?  
     - **`docs/ROADMAP.md`**: cuatro hitos en lenguaje de producto, sin rutas ni stack; evita que el roadmap duplique la spec.  
     - **`clarify` acotado**: solo preguntas que cambian aceptación (códigos, defaults, fallos); no repreguntar lo ya cerrado en ADR-002/003/004.  
     - **`plan`/`research`**: decisiones cerradas en viñetas; contracts por superficie (`http-get-health.md`, `database-url.md`) en lugar de un monólogo.  
     - **`tasks.md`**: IDs enlazados a escenarios BDD, no essays.  
     - **Verdad operativa en `pytest`**: 19 escenarios Spec 001–004; si el Markdown sobra pero el test falla, no se “aprueba” el hito. Complemento: `ruff` TID251/TID252 sobre fronteras hexagonales.

---

## 3. *Commands* vs. *Agent Skills*, Arquitectura Hexagonal, ADRs y Uso de *Reasoning*

- **Diferencia entre *Commands* (`/speckit.*`) y *Agent Skills* (`hexagonal-architecture`, `bdd-acceptance`, `adr-writer`)**:  
  Los **commands** Spec Kit son el *workflow* de producto (specify → clarify → plan → tasks → analyze → implement / converge): orquestan artefactos bajo `specs/<feature>/` y deciden *cuándo* avanzar de fase. Las **Agent Skills** son *playbooks* cargados bajo demanda cuando el contexto del turno encaja (p. ej. al tocar `src/adapters/` se aplica `hexagonal-architecture`; al escribir Given/When/Then, `bdd-acceptance`; al abrir `docs/adr/`, `adr-writer`). OpenCode/Cursor no inyecta todas las skills en cada prompt: el agente lee `SKILL.md` solo si la tarea lo requiere, lo que mantiene el contexto curado.  
  El **orden causal ADR → Constitución → Hito** es obligatorio porque la constitución *cita* decisiones ya tomadas; no las inventa. En clase, **ADR-003** (puertos/adaptadores, `IncidentService` compartido) precedió a `docs/constitution.md` / `.specify/memory/constitution.md`, para que los principios hexagonales no fueran desiderata vacíos. En el Reto 2, **ADR-004** (persistencia dual sin ORM + Compose `api`/`db`) y el bump a Constitución **v1.1.0** se cerraron **antes** de `/speckit.specify` e `/speckit.implement` de H004: así `DATABASE_URL`, `psycopg` y el health real dejan de ser “detalle de implementación” improvisado y pasan a gobernanza auditable que `/speckit.analyze` puede contrastar.

- **Valor de la Arquitectura Hexagonal**:  
  `IncidentRepositoryPort` + `IncidentService` concentran create/triage/summary/SLA/health. FastAPI y Typer solo adaptan I/O; el adaptador PostgreSQL implementa el mismo puerto que SQLite. Añadir Postgres (H004) no tocó `domain/triage_rules.py` ni `domain/sla_calculator.py`, y un futuro adaptador (p. ej. cola o lectura réplica) se enchufa en outbound sin reescribir casos de uso. La fábrica por `DATABASE_URL` es el único punto de selección de motor.

- **Uso intencional de *Reasoning / Extended Thinking* en OpenCode**:  
  - **Mayor valor del razonamiento extendido**: `/speckit.clarify` (enumerar casos borde que rompen aceptación: `409`, `resolved_at`, URL vacía, degradación en caliente), `/speckit.plan` (gates constitucionales, research de dialecto SQL común vs. dos adaptadores) y `/speckit.analyze` (cruce spec↔tasks↔paridad HTTP/CLI).  
  - **Modelo rápido más eficiente**: `/speckit.implement` y remediaciones mecánicas (esqueleto de tests BDD, stubs de healthcheck, `CREATE TABLE IF NOT EXISTS`) una vez las decisiones ya están ancladas; el thinking aquí añade latencia sin cambiar el contrato.

---

## 4. Evidencia de Verificación Determinista

- **Análisis estático de fronteras hexagonales (`uv run ruff check src/`)**:

```text
All checks passed!
```

- **Salida completa de `uv run pytest -v`**:

```text
============================= test session starts =============================
platform win32 -- Python 3.13.0, pytest-9.2.0, pluggy-1.7.0 -- C:\Users\1072667312\Documents\GitHub\Univeristy\ISAI\starter-project\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\1072667312\Documents\GitHub\Univeristy\ISAI\starter-project
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.16.0
collecting ... collected 19 items

tests/test_spec_001_triage.py::test_scenario_1_payments_gateway_502_http PASSED [  5%]
tests/test_spec_001_triage.py::test_scenario_2_individual_account_blocked_hoy_not_p0 PASSED [ 10%]
tests/test_spec_001_triage.py::test_scenario_3_empty_or_whitespace_inputs_return_422 PASSED [ 15%]
tests/test_spec_001_triage.py::test_scenario_4_cli_parity_with_payments_502 PASSED [ 21%]
tests/test_spec_002_summary.py::test_sqlite_repository_satisfies_incident_repository_port PASSED [ 26%]
tests/test_spec_002_summary.py::test_bdd_global_summary_excludes_inactive PASSED [ 31%]
tests/test_spec_002_summary.py::test_bdd_cli_summary_matches_http PASSED [ 36%]
tests/test_spec_002_summary.py::test_bdd_summary_filtered_by_component PASSED [ 42%]
tests/test_spec_002_summary.py::test_bdd_empty_active_summary PASSED     [ 47%]
tests/test_spec_002_summary.py::test_bdd_invalid_reference_time_rejected PASSED [ 52%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_create_incident_201_without_duplicates PASSED [ 57%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_create_detects_open_duplicate PASSED [ 63%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_sla_p2_business_hours_elapsed_120 PASSED [ 68%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_sla_not_found_and_reference_before_created PASSED [ 73%]
tests/test_spec_003_lifecycle_sla.py::test_bdd_cli_create_and_sla_parity PASSED [ 78%]
tests/test_spec_004_postgres_runtime.py::test_bdd_health_connected_http_and_cli PASSED [ 84%]
tests/test_spec_004_postgres_runtime.py::test_bdd_health_unavailable_and_business_ops_fail PASSED [ 89%]
tests/test_spec_004_postgres_runtime.py::test_bdd_database_url_engine_selection PASSED [ 94%]
tests/test_spec_004_postgres_runtime.py::test_bdd_compose_manifest_contract PASSED [100%]

======================= 19 passed, 1 warning in 17.42s ========================
```

- **Evidencia de CLI Typer y containerización (`docker compose config` / `docker compose up --build`)**:

```text
### CLI — health (almacén reachable)
$ uv run python -m src.adapters.inbound.cli health
{"status": "ok", "database": "connected"}

### CLI — create (paridad de negocio con POST /api/v1/incidents)
$ uv run python -m src.adapters.inbound.cli create --title "SDD log check" --raw-text "pago 502 gateway caido"
{"incident_id": "INC-EA057F77", "title": "SDD log check", "raw_text": "pago 502 gateway caido",
 "status": "OPEN", "severity": "P0", "component": "payments-gateway",
 "recommended_team": "Backend-Core",
 "duplicate_group_key": "payments-gateway:http-502-outage",
 "is_duplicate": false, "duplicate_of": []}

### Compose — validación de manifiesto
$ docker compose config -q && echo "Compose OK"
Compose OK

### Compose — runtime api + db (smoke cuando el daemon Docker Desktop está activo)
$ docker compose up --build -d
# ... build starter-project-api, pull postgres:16-alpine ...
Container starter-project-db-1  Healthy
Container starter-project-api-1 Started

$ docker compose ps
NAME                    IMAGE                 SERVICE   STATUS
starter-project-api-1   starter-project-api   api       Up (healthy)   0.0.0.0:8000->8000/tcp
starter-project-db-1    postgres:16-alpine    db        Up (healthy)   5432/tcp

$ Invoke-WebRequest http://localhost:8000/health
Status: 200
{"status":"ok","database":"connected"}
```
