# Feature Specification: Persistencia dual y runtime en contenedores

**Feature Branch**: `004-postgres-container-runtime`

**Created**: 2026-11-24

**Status**: Draft

**Input**: User description: "Necesitamos que IncidentOps deje de depender de una base embebida ad hoc y pueda operarse de forma fiable en un entorno reproducible. Hoy el servicio clasifica y guarda incidentes, pero no tenemos una forma clara de (1) saber si la infraestructura de datos responde antes de operar, (2) usar una base relacional dedicada en despliegue, y a la vez (3) seguir trabajando en local y en pruebas rápidas sin montar ese entorno completo. Por tanto, el producto debe permitir a un operador o responsable de despliegue: comprobar la salud operativa del servicio y de su almacén de datos tanto por la API (GET /health) como por la CLI (health) — con verificación real de conectividad cuando todo está bien (200 OK, base conectada) y señal clara de indisponibilidad cuando la base no es alcanzable (503 / mismo mensaje en ambos canales); elegir el motor de datos según el entorno de forma transparente (PostgreSQL en despliegue; SQLite, incluido almacén en memoria si no se configura nada, para desarrollo local y pruebas rápidas), solo con la configuración del entorno (DATABASE_URL) y sin cambiar las reglas de triaje, duplicados ni SLA; y arrancar de forma reproducible el servicio junto a su base dedicada en dos unidades de ejecución (aplicación + base de datos), de modo que la aplicación espere a que la base esté lista y publique su propio chequeo de salud cuando ya puede operar. Esto corresponde al hito H004 (004-postgres-container-runtime), ya respaldado por ADR-004 y por la Constitución actualizada. La especificación debe incluir requisitos funcionales, requisitos no funcionales y al menos estos cuatro escenarios de aceptación Given/When/Then: (1) salud operativa exitosa API y CLI con verificación real de conectividad; (2) salud ante fallo de conectividad; (3) selección transparente SQLite/PostgreSQL según configuración del entorno; (4) orquestación reproducible aplicación + base dedicada."

## Clarifications

### Session 2026-11-24

- Q: Cuando el servicio arranca contra PostgreSQL por primera vez (sin migraciones versionadas), ¿cómo debe quedar creado el esquema de tablas necesario para operar? → A: Bootstrap idempotente al conectar (el adaptador crea el esquema si falta; p. ej. `CREATE TABLE IF NOT EXISTS` o equivalente).
- Q: ¿Cómo debe demostrarse la aceptación del Escenario 4 (orquestación `api` + `db`) en la verificación automatizada del hito? → A: Suite automatizada sin exigir Compose; Escenario 4 se valida por manifiesto (Dockerfile, `.dockerignore`, compose) + smoke manual documentado cuando haya Docker.
- Q: Si `DATABASE_URL` está vacía o usa un esquema no soportado, ¿en qué momento debe fallar el servicio? → A: Fallo inmediato al resolver el almacén (no arranca / no acepta operaciones); sin fallback silencioso a memoria.
- Q: Si el servicio ya arrancó con una `DATABASE_URL` válida pero la base deja de ser alcanzable, ¿qué deben hacer las operaciones de negocio además del chequeo de salud? → A: Health reporta indisponibilidad (`503` / CLI exit `1`); las operaciones de negocio fallan de forma explícita sin inventar datos (no se exige el mismo JSON de `/health` en cada ruta).

## 1. Objetivo

Un operador o responsable de despliegue puede **arrancar IncidentOps de forma reproducible** junto a una **base de datos relacional dedicada**, **elegir el motor de persistencia** según la configuración del entorno, y **verificar la conectividad operativa** antes de operar, tanto por el canal HTTP como por la herramienta de línea de comandos.

Esta spec es la **fuente de verdad** de aceptación del hito H004 ([`docs/ROADMAP.md`](../../docs/ROADMAP.md)). Queda respaldada por **ADR-004** (persistencia dual SQLite/PostgreSQL sin ORM y topología de dos contenedores) y por la **Constitución** vigente (gobernanza técnica de persistencia y fronteras hexagonales).

## 2. Operación y alcance

- El chequeo de salud deja de ser un stub: MUST ejecutar una **comprobación real** contra la base configurada (consulta de conectividad equivalente a `SELECT 1`) y reflejar el resultado en la respuesta.
- HTTP `GET /health` y CLI `health` MUST exponer el **mismo resultado de negocio** para el mismo estado de conectividad.
- La variable de entorno `DATABASE_URL` MUST seleccionar de forma transparente el adaptador de persistencia:
  - esquema `postgresql://...` → motor PostgreSQL dedicado;
  - esquema `sqlite:///...` → motor SQLite embebido;
  - **ausencia** de la variable → default `sqlite:///:memory:` (desarrollo local y pruebas rápidas sin contenedores).
- El runtime de referencia MUST orquestarse en **dos contenedores** (`api` + `db`) con arranque ordenado: la API solo se considera lista cuando la base está sana y el propio chequeo `/health` responde operativo.
- Credenciales y secretos MUST llegar por el entorno; no se hardcodean en código, documentación versionada ni ejemplos fijos con secretos reales.
- El dominio y los casos de uso de triaje/SLA/ciclo de vida **no** se reabren: no cambian reglas de severidad, equipos, duplicados ni cálculo de SLA (ADR-002 / Spec 001–003).

### Fuera de alcance

- Autenticación, autorización, CORS, batch, paginación.
- Migraciones versionadas de esquema, réplicas, alta disponibilidad multi-nodo o backups automatizados.
- Cambio de reglas de triaje, ciclo de vida o SLA (H001–H003).
- ORM pesado o un tercer motor de persistencia.
- Canales distintos de HTTP y CLI (p. ej. MCP).
- Sustituir SQLite como camino de aceptación rápida / demos locales sin contenedores.

## 3. Contrato HTTP — salud operativa

- **Método y ruta:** `GET /health`
- **Comportamiento:** MUST ejecutar una comprobación real de conectividad contra la base configurada (consulta equivalente a `SELECT 1` vía el adaptador de persistencia activo).
- **Éxito (conectividad OK):** `200 OK` con JSON exactamente:
  ```json
  {"status": "ok", "database": "connected"}
  ```
- **Fallo de conectividad** (la verificación de salud del adaptador indica que la base no está disponible): `503 Service Unavailable` con JSON exactamente:
  ```json
  {"status": "error", "database": "unavailable"}
  ```
- El cuerpo de respuesta MUST limitarse a esos campos de estado operativo; no MUST exponer credenciales, cadenas de conexión ni detalles internos de error.

## 4. Contrato CLI — salud operativa

- **Subcomando:** `health`
- **Éxito:** código de salida `0`; imprime en stdout el mismo JSON de negocio que HTTP `200` (`{"status": "ok", "database": "connected"}`).
- **Fallo de conectividad:** código de salida `1`; imprime en stdout el mismo JSON de negocio que HTTP `503` (`{"status": "error", "database": "unavailable"}`).
- **Paridad:** mismo estado de conectividad → mismo resultado de negocio que HTTP.

## 5. Contrato de selección de persistencia (`DATABASE_URL`)

- La fábrica outbound MUST elegir el adaptador **únicamente** a partir de `DATABASE_URL` (o del default cuando la variable no existe).
- **`postgresql://...`**: selecciona el adaptador PostgreSQL (driver autorizado por gobernanza del proyecto; sin ORM).
- **`sqlite:///...`**: selecciona el adaptador SQLite (biblioteca estándar).
- **Variable ausente**: MUST usar `sqlite:///:memory:` (desarrollo local y pruebas rápidas sin contenedores).
- **Variable definida pero vacía / solo espacios**, o esquema no soportado: MUST fallar de forma **inmediata** al resolver el almacén (la API/CLI no completa el arranque ni acepta operaciones de negocio), **sin** fallback silencioso a memoria y **sin** incluir el valor de la URL en el mensaje de error.
- Ambos motores MUST cumplir el mismo puerto de persistencia ya usado por H002/H003 (mismas operaciones de negocio); los instantes de negocio se persisten con **paridad** entre motores (misma representación observable para el núcleo).
- Al conectar (SQLite o PostgreSQL), el adaptador MUST asegurar el esquema de forma **idempotente** (crear tablas si faltan; p. ej. `CREATE TABLE IF NOT EXISTS` o equivalente). No hay migraciones versionadas en este hito.
- El dominio MUST permanecer libre de drivers SQL y de detalles de motor.

## 6. Contrato de orquestación reproducible (runtime)

- MUST existir un artefacto de construcción de imagen de la API y un manifiesto de orquestación de **dos servicios**:
  - **`db`**: motor PostgreSQL 16 en imagen Alpine; volumen persistente de datos; healthcheck nativo (`pg_isready`) que marque el servicio sano solo cuando acepte conexiones.
  - **`api`**: imagen construida con el gestor de dependencias del proyecto (`uv`) sobre base `python:3.12-slim`; `DATABASE_URL` apuntando al servicio `db`; `depends_on` con condición `service_healthy` sobre `db`; healthcheck HTTP sobre `GET /health`.
- MUST existir un `.dockerignore` que excluya artefactos locales innecesarios (cachés, entornos virtuales, tests pesados o secretos locales) para mantener el contexto de build limpio.
- Credenciales de `db` / `DATABASE_URL` MUST inyectarse por variables de entorno del compose (sin secretos reales en el repositorio).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Verificar que la infraestructura crítica responde (Priority: P1)

Un operador necesita confirmar, antes de operar, que el servicio y su base de datos configurada están **conectados y listos**, tanto por HTTP como por CLI.

**Why this priority**: Sin un chequeo real de conectividad, el hito H004 no cumple su resultado (“verificar que la infraestructura crítica responde antes de operar”).

**Independent Test**: Escenarios BDD 1 y 2 (éxito y fallo), HTTP y CLI.

**Acceptance Scenarios**:

1. **Given** la base configurada es alcanzable, **When** el operador consulta `GET /health`, **Then** recibe `200 OK` con `{"status": "ok", "database": "connected"}` tras una comprobación real de conectividad.
2. **Given** el mismo estado alcanzable, **When** ejecuta CLI `health`, **Then** obtiene código `0` y el mismo JSON de negocio.
3. **Given** la verificación de conectividad falla, **When** consulta `GET /health`, **Then** recibe `503 Service Unavailable` con `{"status": "error", "database": "unavailable"}`.
4. **Given** el mismo fallo de conectividad, **When** ejecuta CLI `health`, **Then** obtiene código `1` y el mismo JSON de negocio que HTTP `503`.

---

### User Story 2 - Elegir motor de persistencia por entorno (Priority: P1)

Un desarrollador o operador necesita **cambiar entre SQLite (local/pruebas) y PostgreSQL (runtime dedicado)** solo configurando `DATABASE_URL`, sin reescribir reglas de negocio ni acoplar el núcleo a un motor.

**Why this priority**: Es el corte estructural de ADR-004 y habilita demos locales rápidas junto al runtime reproducible.

**Independent Test**: Escenario BDD 3.

**Acceptance Scenarios**:

1. **Given** `DATABASE_URL` con esquema `postgresql://...`, **When** el servicio resuelve el almacén, **Then** usa el adaptador PostgreSQL (mismo puerto que SQLite; sin fallback a memoria). La verificación automatizada demuestra la selección sin Compose; el smoke documentado cubre alta/SLA/resumen contra `db` cuando hay runtime de contenedores.
2. **Given** `DATABASE_URL` con esquema `sqlite:///...` (archivo o memoria), **When** el servicio resuelve el almacén, **Then** usa el adaptador SQLite.
3. **Given** que `DATABASE_URL` **no** está definida, **When** el servicio resuelve el almacén, **Then** usa `sqlite:///:memory:` por defecto.

---

### User Story 3 - Arrancar un entorno reproducible api + db (Priority: P2)

Un operador necesita levantar **API y base dedicada** con un único manifiesto reproducible, de modo que la API espere a que la base esté sana y publique su propio chequeo `/health`.

**Why this priority**: Completa el resultado operativo de H004; depende de que el health y la selección PostgreSQL existan (Historias 1–2).

**Independent Test**: Escenario BDD 4 (orquestación).

**Acceptance Scenarios**:

1. **Given** el manifiesto de orquestación del proyecto, **When** se valida el contrato de orquestación (y, si hay runtime, el smoke documentado), **Then** los artefactos cumplen Dockerfile / `.dockerignore` / `api`+`db` con `pg_isready`, `depends_on: service_healthy` y healthcheck `/health`; el arranque real queda fuera del gate de pytest (Escenario 4).
2. **Given** el artefacto de imagen de la API, **When** se construye la imagen, **Then** el build usa `uv` sobre `python:3.12-slim` y un `.dockerignore` que mantiene el contexto limpio.

---

### Edge Cases

- Health exitoso MUST haber ejecutado una consulta real de conectividad; no basta con responder “ok” sin hablar con la base.
- Health fallido MUST responder `503` / CLI exit `1` sin filtrar credenciales ni la URL completa en el cuerpo o logs de respuesta al operador.
- `DATABASE_URL` vacía o con esquema desconocido: fallo **inmediato** al resolver el almacén (proceso no queda a medias); mensaje sin filtrar el valor de la URL; no hay fallback a `:memory:`.
- Ausencia de `DATABASE_URL`: default memoria SQLite; no exige contenedor `db`.
- Con `sqlite:///` el servicio `db` del compose **no** es necesario para desarrollo local.
- Con `postgresql://` (u otro URL válido) apuntando a un host inalcanzable tras un arranque previo: `/health` y CLI `health` MUST reportar indisponibilidad (`503` / exit `1`); las operaciones de negocio (alta, resumen, SLA, etc.) MUST fallar de forma explícita **sin inventar datos**; no se exige reutilizar el JSON exacto de `/health` en esas rutas.
- Paridad HTTP/CLI del health: mismo estado → mismos campos JSON de negocio.
- Dominio y casos de uso de H001–H003 MUST seguir funcionando sin cambios de reglas al cambiar de motor.
- Credenciales solo por entorno; nunca hardcodeadas en imagen o manifiestos versionados con secretos reales.
- Primer arranque contra PostgreSQL (o SQLite) sin esquema previo: el adaptador MUST crear el esquema idempotentemente al conectar; el operador no aplica DDL manual ni scripts de migración versionada.

## 7. Escenarios BDD (Given / When / Then) *(mandatory)*

Fuente de verdad de aceptación mínima (≥4). El lenguaje es operativo/de producto; rutas, códigos y JSON fijan la superficie de entrega acordada para H004.

### Escenario 1 — Salud operativa 200 y CLI health con conectividad real

**Given** el servicio está configurado contra una base alcanzable (SQLite válido o PostgreSQL disponible) y la verificación de conectividad puede completarse con éxito (consulta real equivalente a `SELECT 1`).

**When** un operador consulta `GET /health` y, de forma equivalente, ejecuta el comando CLI `health`.

**Then**:

- HTTP responde `200 OK` con cuerpo `{"status": "ok", "database": "connected"}`;
- CLI termina con código de salida `0` e imprime el mismo JSON de negocio;
- en ambos canales la respuesta refleja una comprobación real contra la base configurada (no un stub estático).

### Escenario 2 — Salud ante fallo de conectividad 503

**Given** la verificación de conectividad del adaptador de persistencia activo indica que la base **no** está disponible (p. ej. la comprobación de salud retorna fallo / no conectado).

**When** un operador consulta `GET /health` (y, de forma equivalente, CLI `health`).

**Then**:

- HTTP responde `503 Service Unavailable` con cuerpo `{"status": "error", "database": "unavailable"}`;
- CLI termina con código de salida `1` e imprime el mismo JSON de negocio;
- la respuesta no expone credenciales ni la cadena de conexión;
- en el mismo estado de indisponibilidad, alta/resumen/SLA fallan de forma explícita sin inventar datos (cuerpo distinto del JSON de `/health`; ver FR-017).

### Escenario 3 — Selección transparente SQLite / PostgreSQL vía `DATABASE_URL`

**Given** tres configuraciones de entorno distintas: (a) `DATABASE_URL=postgresql://...`, (b) `DATABASE_URL=sqlite:///...`, (c) variable **ausente**.

**When** el servicio resuelve el almacén de persistencia en cada caso.

**Then**:

- (a) selecciona el adaptador PostgreSQL;
- (b) selecciona el adaptador SQLite;
- (c) selecciona SQLite en memoria (`sqlite:///:memory:`) para desarrollo local y pruebas rápidas sin contenedores;
- en todos los casos el dominio permanece ajeno al motor y las operaciones de negocio ya aceptadas (p. ej. alta de incidente) siguen el mismo contrato de puerto.

### Escenario 4 — Orquestación reproducible en dos contenedores (`api` + `db`)

**Given** el repositorio incluye Dockerfile de la API (`uv` sobre `python:3.12-slim`), `.dockerignore` limpio, y `docker-compose.yml` con servicios `db` (`postgres:16-alpine`, volumen persistente, healthcheck `pg_isready`) y `api` (`DATABASE_URL` hacia `db`, `depends_on` con `service_healthy`, healthcheck sobre `/health`).

**When** un operador valida el manifiesto de orquestación y, si dispone de runtime de contenedores, arranca la orquestación de referencia (`api` + `db`).

**Then**:

- los artefactos del manifiesto cumplen el contrato de la sección 6 (servicios, healthchecks, `DATABASE_URL`, build con `uv` / `.dockerignore`);
- si se ejecuta el smoke de arranque: el servicio `db` alcanza estado sano según `pg_isready`; el servicio `api` arranca solo después de que `db` está sano; `api` habla con PostgreSQL vía `DATABASE_URL` apuntando a `db`; y el healthcheck de `api` sobre `GET /health` reporta conectividad operativa (`200` / `database: connected`);
- la suite automatizada del hito **no** exige `docker compose up` como gate obligatorio (CI/local sin Docker sigue siendo válida para Escenarios 1–3 y contratos de motor).

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST exponer chequeo de salud vía `GET /health` y CLI `health`.
- **FR-002**: El chequeo de salud MUST ejecutar una comprobación real de conectividad contra la base configurada (consulta equivalente a `SELECT 1` a través del adaptador activo).
- **FR-003**: Si la conectividad es exitosa, HTTP MUST responder `200 OK` con `{"status": "ok", "database": "connected"}` y CLI MUST terminar con código `0` y el mismo JSON.
- **FR-004**: Si la verificación de salud del adaptador indica fallo de conectividad, HTTP MUST responder `503 Service Unavailable` con `{"status": "error", "database": "unavailable"}` y CLI MUST terminar con código `1` y el mismo JSON.
- **FR-005**: Las respuestas de salud MUST NO exponer credenciales, URLs completas ni detalles internos de error al operador.
- **FR-006**: HTTP y CLI MUST devolver el mismo resultado de negocio de salud para el mismo estado de conectividad.
- **FR-007**: La selección del adaptador de persistencia MUST basarse únicamente en `DATABASE_URL` (o en el default cuando la variable no existe).
- **FR-008**: `DATABASE_URL` con esquema `postgresql://` MUST seleccionar el adaptador PostgreSQL (sin ORM).
- **FR-009**: `DATABASE_URL` con esquema `sqlite:///` MUST seleccionar el adaptador SQLite.
- **FR-010**: Si `DATABASE_URL` está ausente, MUST usarse `sqlite:///:memory:` por defecto.
- **FR-011**: Si `DATABASE_URL` está definida pero vacía/solo espacios, o el esquema no está soportado, MUST fallar de forma **inmediata** al resolver el almacén (no arrancar / no aceptar operaciones), sin fallback silencioso a memoria y sin incluir el valor de la URL en el mensaje.
- **FR-012**: Ambos adaptadores MUST implementar el mismo puerto de persistencia ya usado por las features de ciclo de vida / resumen, de modo que alta, consulta SLA y resumen sigan disponibles sin reabrir reglas de negocio.
- **FR-013**: El núcleo de dominio MUST permanecer libre de drivers SQL y de conocimiento del motor activo.
- **FR-014**: El runtime de referencia MUST orquestar dos servicios (`api` y `db`) según el contrato de la sección 6 (imagen API con `uv`/`python:3.12-slim`, `.dockerignore`, `db` con `postgres:16-alpine` + volumen + `pg_isready`, `api` con `DATABASE_URL` hacia `db`, `depends_on: service_healthy`, healthcheck sobre `/health`).
- **FR-015**: Credenciales de base de datos MUST inyectarse por variables de entorno; MUST NOT hardcodearse en código fuente ni en artefactos versionados con secretos reales.
- **FR-016**: Al conectar, cada adaptador MUST asegurar el esquema de forma idempotente (crear tablas si faltan); MUST NOT depender de migraciones versionadas ni de DDL manual del operador en este hito.
- **FR-017**: Si la base deja de ser alcanzable tras un arranque con `DATABASE_URL` válida, `/health` y CLI `health` MUST reportar indisponibilidad; las operaciones de negocio MUST fallar de forma explícita sin inventar datos (sin exigir el mismo cuerpo JSON de salud en cada ruta).

### Non-Functional Requirements (RNF)

- **RNF-001 Reproducibilidad**: Un operador MUST poder levantar el stack de referencia `api` + `db` desde el repositorio y obtener un entorno funcionalmente equivalente en máquinas distintas, sin pasos manuales ad hoc de instalación del motor dedicado.
- **RNF-002 Aislamiento de capas**: Los detalles de motor (SQLite vs PostgreSQL), drivers y orquestación MUST permanecer en adaptadores/outbound e infraestructura; application y domain MUST no importarlos.
- **RNF-003 Paridad temporal entre motores**: Los instantes de negocio persistidos MUST tener la misma representación observable en SQLite y PostgreSQL (paridad TEXT ISO 8601 según ADR-004), de modo que el núcleo no dependa de tipado temporal nativo de un solo motor.
- **RNF-004 Arranque ordenado**: En el compose de referencia, `api` MUST no considerarse lista para tráfico hasta que `db` esté sano y el propio `/health` de `api` reporte conectividad operativa.
- **RNF-005 Contexto de build limpio**: El build de imagen de `api` MUST usar `.dockerignore` que excluya cachés, entornos virtuales locales y secretos locales del contexto enviado al daemon.
- **RNF-006 Seguridad operativa**: Logs y respuestas de salud MUST evitar filtrar secretos; ejemplos de documentación MUST usar placeholders, no credenciales reales.
- **RNF-007 Sustituibilidad local**: El camino SQLite (archivo o `:memory:`) MUST seguir permitiendo demos y aceptación rápida **sin** exigir contenedores ni el servicio `db`.
- **RNF-008 Gobernanza de dependencias**: La única dependencia de persistencia autorizada más allá de la biblioteca estándar es el driver PostgreSQL aprobado por la constitución/ADR-004; MUST NOT introducirse un ORM pesado.
- **RNF-009 Observabilidad mínima**: El estado de conectividad MUST ser observable en ≤ 5 segundos en condiciones normales de red local del compose (health HTTP/CLI refleja el estado actual, no un caché obsoleto de larga duración).
- **RNF-010 Compatibilidad de aceptación**: Las pruebas de aceptación de H001–H003 que no requieran motor dedicado MUST poder ejecutarse contra SQLite sin arrancar PostgreSQL.

### Key Entities

- **Estado de salud operativa**: `status` (`ok` | `error`) y `database` (`connected` | `unavailable`), observable por HTTP y CLI.
- **Configuración de persistencia**: `DATABASE_URL` (o su ausencia) que determina el motor activo y el destino de datos.
- **Adaptador de persistencia**: implementación outbound intercambiable (SQLite o PostgreSQL) del puerto de repositorio, con capacidad de verificación de conectividad.
- **Servicio API (contenedor `api`)**: proceso de aplicación expuesto con `/health` y dependiente de la base cuando usa PostgreSQL.
- **Servicio de datos (contenedor `db`)**: motor PostgreSQL dedicado con volumen persistente y señal de readiness (`pg_isready`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: En el 100% de los casos con base alcanzable, `GET /health` y CLI `health` reportan estado operativo conectado (`status=ok`, `database=connected`) tras una comprobación real.
- **SC-002**: En el 100% de los casos con fallo de conectividad simulado o real, HTTP `/health` responde `503` y CLI `health` exit `1` con `status=error` y `database=unavailable`, sin filtrar secretos; las operaciones de negocio en el mismo estado fallan de forma explícita sin inventar datos.
- **SC-003**: En el 100% de las resoluciones de almacén, `postgresql://` selecciona PostgreSQL, `sqlite:///` selecciona SQLite, y la ausencia de `DATABASE_URL` usa memoria SQLite.
- **SC-004**: El repositorio incluye el manifiesto completo de orquestación (sección 6). Cuando hay runtime de contenedores, un operador puede arrancar `api` + `db` y obtener `/health` operativo (`database=connected`) con el smoke documentado; la suite automatizada no exige Compose como gate.
- **SC-005**: El 100% de las resoluciones de almacén mantienen el mismo contrato de puerto (alta / resumen / SLA) al cambiar solo el motor vía `DATABASE_URL`. La paridad de resultado observable contra PostgreSQL vivo se demuestra con el smoke de Compose documentado; la suite automatizada no exige un servidor PostgreSQL.
- **SC-006**: El 100% de los intentos de arranque/resolución con `DATABASE_URL` vacía o esquema no soportado fallan de inmediato (sin aceptar operaciones) y omiten el valor literal de la URL en el mensaje.
- **SC-007**: Las suites de aceptación que no requieren motor dedicado completan su verificación contra SQLite sin levantar el servicio `db`.

## Assumptions

- Este hito corresponde a **H004** del roadmap; las reglas de triaje, duplicados y SLA de H001–H003 permanecen vigentes y no se reabren.
- **ADR-004** y la Constitución (persistencia dual, sin ORM, selección por `DATABASE_URL`, topología `api` + `db`) son la base de decisión estructural; esta spec fija la aceptación observable.
- “Comprobación real” = al menos una consulta de conectividad equivalente a `SELECT 1` ejecutada en el momento del chequeo (no un flag estático).
- CLI `health` es un subcomando nuevo del adaptador CLI existente; paridad de JSON con HTTP es requisito de producto.
- El default `sqlite:///:memory:` aplica solo cuando la variable **no existe**; una variable vacía o un esquema no soportado es error inmediato al resolver (fail-fast), no default ni proceso “medio vivo”.
- Esquemas soportados en este hito: `sqlite:///` y `postgresql://` (incluye variantes de credenciales/host/puerto/db en la URL, inyectadas por entorno).
- PostgreSQL 16 Alpine y `python:3.12-slim` + `uv` son la topología/imagen de referencia del hito (contrato operativo H004 / ADR-004), no una elección abierta a reinterpretar en implementación.
- Credenciales de demo en compose usan placeholders o valores locales no secretos de producción.
- No se exige HA, réplicas, backups ni migraciones versionadas en este entregable; el esquema se asegura por bootstrap idempotente del adaptador al conectar (ambos motores).
- Auth, CORS, batch, paginación y canales distintos de HTTP/CLI quedan fuera.
- Ante caída de base con URL válida, el contrato JSON canónico de indisponibilidad aplica a health; el detalle de código HTTP por cada ruta de negocio (p. ej. 503 vs 500) se fija en planificación sin inventar datos de respuesta.
- La verificación automatizada de los escenarios 1–3 (y contratos de health/motor) puede usarse con almacenes aislados (incl. SQLite) **sin** Docker.
- El Escenario 4 se acepta por **validación del manifiesto** (Dockerfile, `.dockerignore`, compose) más **smoke manual documentado** cuando haya runtime de contenedores; `docker compose up` **no** es gate obligatorio de la suite automatizada.
