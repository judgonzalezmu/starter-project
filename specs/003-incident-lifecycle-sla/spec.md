# Feature Specification: Ciclo de vida, duplicados y consulta SLA

**Feature Branch**: `003-incident-lifecycle-sla`

**Created**: 2026-11-23

**Status**: Draft

**Input**: User description: "Necesitamos guardar los incidentes cuando llegan, avisar si ya había otro equivalente abierto, y consultar cómo va su SLA tanto por API como desde nuestra herramienta CLI."

## Clarifications

### Session 2026-11-23

- Q: ¿Cuáles son el contrato de creación (campos, defaults, respuesta) y el criterio exacto de duplicado abierto? → A: Creación vía `POST /api/v1/incidents` y CLI `create`. Obligatorios: `title` y `raw_text` (vacíos/solo espacios → HTTP `422` / CLI exit `1`). Opcionales: `incident_id` (autogenerado `INC-<HEX8>` si se omite), `created_at` (instante actual si se omite), `status` (default `OPEN`). Éxito: HTTP `201 Created` / CLI JSON con clasificación completa, `is_duplicate` (bool) y `duplicate_of` (list[str]). Duplicado abierto = misma `duplicate_group_key` solo en `OPEN` | `IN_PROGRESS` | `ESCALATION_REQUIRED`, excluyendo `RESOLVED` y el propio identificador recién creado.
- Q: ¿Cuál es el contrato de auditoría SLA y sus rechazos? → A: `GET /api/v1/incidents/{incident_id}/sla` y CLI `sla`; `reference_time` opcional (ISO 8601) para evaluaciones deterministas; HTTP `404` si el incidente no existe; HTTP `422` / CLI exit `1` si `reference_time` < `created_at`.
- Q: Si al crear un incidente el cliente envía un `incident_id` que ya existe en el almacén, ¿qué debe hacer el sistema? → A: Rechazar con HTTP `409 Conflict` / CLI código `1`; no persistir ni sobrescribir.
- Q: Al crear un incidente, ¿qué valores de `status` puede enviar el cliente además del default `OPEN`? → A: Cualquiera de `OPEN`, `IN_PROGRESS`, `ESCALATION_REQUIRED`, `RESOLVED`; valor desconocido → HTTP `422` / CLI exit `1`.
- Q: Si al crear un incidente el cliente envía `status=RESOLVED`, ¿cómo se obtiene el instante de resolución (`resolved_at`) para la auditoría de SLA? → A: `resolved_at` opcional; si falta con `status=RESOLVED`, igualar a `created_at`.
- Q: Si al crear con `status=RESOLVED` el cliente envía un `resolved_at` anterior a `created_at`, ¿qué debe hacer el sistema? → A: Rechazar con HTTP `422` / CLI exit `1`; no persistir.

## 1. Objetivo

Un operador o sistema puede **registrar de forma persistente** un incidente entrante, recibir **aviso** si ya existe otro incidente **equivalente abierto**, y **consultar el cumplimiento de SLA** de un incidente registrado en un instante de referencia, desde el **canal HTTP** y desde la **herramienta de línea de comandos**, con el mismo resultado de negocio.

Esta spec es la **fuente de verdad** de aceptación del hito H003 ([`docs/ROADMAP.md`](../../docs/ROADMAP.md)).

## 2. Operación y alcance

- El registro **persiste** el incidente (deja de ser solo clasificación puntual sin guardar).
- Al registrar, el sistema **clasifica** el reporte a partir de `raw_text` (severidad, componente, equipo sugerido, clave de agrupación de duplicados, etc.) y lo guarda con `status` por defecto `OPEN`.
- La equivalencia de duplicados se determina por `duplicate_group_key`; “abierto” = `OPEN`, `IN_PROGRESS` o `ESCALATION_REQUIRED` (excluye `RESOLVED` y el propio id recién creado).
- El aviso de duplicado **no impide** el registro: se guarda el nuevo incidente y se informa vía `is_duplicate` / `duplicate_of`.
- La consulta de SLA evalúa un incidente ya registrado respecto de un `reference_time` opcional (si se omite, el momento real de la consulta).
- Un único conjunto de casos de uso compartido expuesto por ambos canales; no reimplementar triaje, duplicados ni SLA por canal.

### Fuera de alcance

- Autenticación, autorización, CORS, batch, paginación.
- Resumen de activos / filtrado por componente (H002).
- Contenedores y base de datos relacional dedicada de despliegue (H004).
- Transiciones de ciclo de vida posteriores al alta (cambiar estado después de creado) — fuera de este entregable salvo pedido explícito.
- Canales distintos de HTTP y CLI (p. ej. MCP).

## 3. Contrato HTTP — creación

- **Método y ruta:** `POST /api/v1/incidents`
- **Body:**
  - **Obligatorios:** `title`, `raw_text` — si están vacíos o solo espacios (tras recortar) → `422 Unprocessable Entity`, sin persistir.
  - **Opcionales:**
    - `incident_id` — si se omite, autogenerar `INC-<HEX8>` (8 dígitos hexadecimales). Si se envía y ya existe → `409 Conflict`, sin persistir ni sobrescribir.
    - `created_at` — si se omite, usar el instante actual.
    - `status` — si se omite, default `"OPEN"`; si se envía, MUST ser uno de `OPEN` | `IN_PROGRESS` | `ESCALATION_REQUIRED` | `RESOLVED`; cualquier otro valor → `422 Unprocessable Entity`.
    - `resolved_at` — opcional; si `status=RESOLVED` y se omite, MUST igualarse a `created_at` (tras aplicar su default); si se envía y `resolved_at` < `created_at` → `422 Unprocessable Entity`, sin persistir.
- **Éxito:** `201 Created` con JSON que incluye:
  - datos del incidente persistido (`incident_id`, `title`, `raw_text`, `created_at`, `status`, …)
  - **clasificación completa** del triaje (al menos: severidad, componente, justificación, equipo sugerido, `duplicate_group_key`, y el resto de campos canónicos del resultado de triaje del producto)
  - `is_duplicate` (bool)
  - `duplicate_of` (lista de strings: identificadores de equivalentes abiertos)

## 4. Contrato CLI — creación

- **Subcomando:** `create` con los mismos campos de negocio (`--title`, `--raw-text`, y opcionales `--incident-id`, `--created-at`, `--status`).
- **Éxito:** código de salida `0`; imprime en stdout el mismo JSON de negocio que el cuerpo HTTP `201`.
- **`title` / `raw_text` vacíos o solo espacios:** error y código de salida `1`; no persiste.
- **`incident_id` ya existente:** código de salida `1`; no persiste ni sobrescribe.
- **`status` desconocido (fuera del catálogo canónico):** código de salida `1`; no persiste.
- **`resolved_at` < `created_at` con `status=RESOLVED`:** código de salida `1`; no persiste.
- **Paridad:** misma entrada válida → mismo resultado de negocio que HTTP.

## 5. Contrato HTTP — auditoría SLA

- **Método y ruta:** `GET /api/v1/incidents/{incident_id}/sla`
- **Query opcional:** `reference_time` (ISO 8601) para evaluación determinista; omitido = momento real de la consulta.
- **Éxito:** `200 OK` con JSON de cumplimiento que incluye, como mínimo:
  - `incident_id`
  - `elapsed_minutes`
  - `allowed_minutes`
  - `remaining_minutes`
  - `is_breached`
  - `requires_escalation`
- **No encontrado:** `404 Not Found` si el `incident_id` no existe.
- **Validación:** `422 Unprocessable Entity` si `reference_time` es inválido/ilegible **o** si `reference_time` < `created_at` del incidente; no se devuelven métricas engañosas.

## 6. Contrato CLI — auditoría SLA

- **Subcomando:** `sla --incident-id ... [--reference-time ...]`
- **Éxito:** código `0` y mismo JSON de negocio que HTTP.
- **No encontrado / `reference_time` inválido o anterior a `created_at`:** código de salida `1`; sin métricas engañosas.
- **Paridad:** misma consulta → mismo resultado que HTTP.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Registrar un incidente entrante (Priority: P1)

Un operador recibe un reporte nuevo y necesita **guardarlo** de inmediato, con título, texto y clasificación de negocio, para que deje de ser una evaluación efímera.

**Why this priority**: Sin persistencia no hay ciclo de vida ni base para avisos de duplicado ni auditoría de SLA; es el valor central de H003.

**Independent Test**: Escenario BDD 1 (y creación vía CLI en Escenario 5).

**Acceptance Scenarios**:

1. **Given** un reporte con `title` y `raw_text` válidos (no vacíos tras recortar espacios), sin `incident_id`/`created_at`/`status` (o con defaults), y sin equivalentes abiertos, **When** el operador lo registra por `POST /api/v1/incidents`, **Then** la respuesta es `201 Created`, el incidente queda persistido (id autogenerado `INC-<HEX8>` si se omitió, `created_at` actual si se omitió, `status` `OPEN` si se omitió), incluye clasificación completa, `is_duplicate=false` y `duplicate_of=[]`.
2. **Given** el mismo reporte válido, **When** el operador lo registra por CLI `create`, **Then** obtiene código `0` y el mismo JSON de negocio que HTTP.

---

### User Story 2 - Aviso de equivalente abierto al registrar (Priority: P1)

Al llegar un reporte, el operador necesita saber si **ya hay otro incidente equivalente abierto**, para no fragmentar la respuesta operativa.

**Why this priority**: El aviso de duplicado es requisito explícito del hito y reduce trabajo duplicado desde el primer registro.

**Independent Test**: Escenario BDD 2.

**Acceptance Scenarios**:

1. **Given** existe al menos un incidente en `OPEN`, `IN_PROGRESS` o `ESCALATION_REQUIRED` con la misma `duplicate_group_key` que el reporte entrante, **When** el operador registra el nuevo reporte, **Then** el nuevo incidente se persiste **y** la respuesta tiene `is_duplicate=true` y `duplicate_of` con los identificadores de esos equivalentes (sin incluir el id recién creado).
2. **Given** solo existen equivalentes en estado `RESOLVED` (o no existen equivalentes), **When** el operador registra el nuevo reporte, **Then** se persiste con `is_duplicate=false` y `duplicate_of=[]`.
3. **Given** hay un equivalente en `IN_PROGRESS` o `ESCALATION_REQUIRED`, **When** se registra un nuevo equivalente, **Then** también se emite el aviso (`is_duplicate=true` y esos ids en `duplicate_of`).

---

### User Story 3 - Consultar el progreso de SLA de un incidente (Priority: P2)

Un operador necesita saber **cómo va el SLA** de un incidente ya registrado en un instante concreto (o “ahora”), para decidir si escalar o priorizar.

**Why this priority**: Completa el hito H003; depende de que el incidente esté persistido (Historia 1).

**Independent Test**: Escenarios BDD 3 y 5 (`sla`).

**Acceptance Scenarios**:

1. **Given** un incidente persistido con severidad y `created_at` conocidos, **When** el operador consulta `GET /api/v1/incidents/{incident_id}/sla` con `reference_time` válido ≥ `created_at` (o sin instante, usando el momento real), **Then** recibe `200` con minutos transcurridos, si incumplió SLA y si requiere escalamiento (umbral 75% solo si no resuelto y no incumplido).
2. **Given** el mismo incidente e instante, **When** consulta por CLI `sla`, **Then** obtiene el mismo resultado de negocio que por HTTP.
3. **Given** el incidente ya está `RESOLVED` con momento de resolución conocido, **When** se consulta el SLA, **Then** la evaluación respeta la prioridad del instante de resolución sobre el instante de referencia solicitado.

---

### User Story 4 - Rechazo de entradas inválidas (Priority: P3)

Entradas vacías, incidentes inexistentes o `reference_time` inválido/anterior a la creación no deben crear registros engañosos ni métricas de SLA incorrectas.

**Why this priority**: Protege la integridad de los datos y de la auditoría SLA; no es el valor principal del hito.

**Independent Test**: Escenario BDD 4 (más rechazos de creación en Acceptance Scenarios de esta historia).

**Acceptance Scenarios**:

1. **Given** un intento de creación con `title` o `raw_text` vacíos o solo espacios, **When** se solicita el alta por HTTP o CLI, **Then** se rechaza (HTTP `422` / CLI exit `1`), no se persiste y no se emite clasificación efectiva.
2. **Given** una consulta de SLA con `reference_time` inválido/ilegible **o** con `reference_time` < `created_at`, **When** se solicita por HTTP o CLI, **Then** se rechaza (HTTP `422` / CLI exit `1`) sin métricas engañosas.
3. **Given** un `incident_id` que no existe, **When** se consulta su SLA, **Then** HTTP responde `404 Not Found` / CLI exit `1`, sin inventar métricas.
4. **Given** ya existe un incidente con un `incident_id` concreto, **When** se intenta crear otro con el mismo `incident_id` por HTTP o CLI, **Then** se rechaza (HTTP `409 Conflict` / CLI exit `1`) sin modificar el existente ni crear uno nuevo.
5. **Given** un intento de creación con `status` fuera de `OPEN` | `IN_PROGRESS` | `ESCALATION_REQUIRED` | `RESOLVED`, **When** se solicita el alta por HTTP o CLI, **Then** se rechaza (HTTP `422` / CLI exit `1`) sin persistir.
6. **Given** un intento de creación con `status=RESOLVED` y `resolved_at` < `created_at`, **When** se solicita el alta por HTTP o CLI, **Then** se rechaza (HTTP `422` / CLI exit `1`) sin persistir.

---

## 7. Escenarios BDD (Given / When / Then) *(mandatory)*

Fuente de verdad de aceptación mínima (≥5). El lenguaje es de negocio; las rutas/códigos fijan la superficie de entrega ya acordada.

### Escenario 1 — Registro inicial 201 sin duplicados previos

**Given** no existen incidentes abiertos con la misma clave de agrupación de duplicados que el reporte entrante, y el operador aporta `title` y `raw_text` válidos (no vacíos tras recortar espacios).

**When** registra el incidente mediante `POST /api/v1/incidents`.

**Then** la respuesta es `201 Created`, el incidente queda persistido con clasificación completa, `is_duplicate=false` y `duplicate_of=[]`.

### Escenario 2 — Detección de duplicado abierto 201

**Given** ya existe un incidente abierto (`OPEN`, `IN_PROGRESS` o `ESCALATION_REQUIRED`) con la misma `duplicate_group_key` que el reporte entrante, y puede existir además un equivalente en `RESOLVED` que **no** debe contarse.

**When** el operador registra un nuevo incidente equivalente mediante `POST /api/v1/incidents`.

**Then** la respuesta es `201 Created`, el nuevo incidente se persiste, `is_duplicate=true`, y `duplicate_of` incluye el identificador del incidente abierto previo (sin incluir incidentes `RESOLVED` ni el identificador recién creado).

### Escenario 3 — Auditoría determinista de SLA en horario hábil (P2)

**Given** un incidente de severidad `P2` registrado el viernes `2026-11-06T17:00:00` (presupuesto de resolución 480 minutos en horario hábil laboral).

**When** el operador consulta su SLA con instante de referencia lunes `2026-11-09T09:00:00` (`GET /api/v1/incidents/{incident_id}/sla?reference_time=2026-11-09T09:00:00`).

**Then** la respuesta es `200 OK` con:

- `elapsed_minutes=120`
- `allowed_minutes=480`
- `remaining_minutes=360`
- `is_breached=false`
- `requires_escalation=false`

(solo se contabiliza tiempo hábil: el tramo del viernes hasta el cierre laboral y el del lunes desde la apertura laboral; el fin de semana no aporta minutos).

### Escenario 4 — Consulta de SLA: ID inexistente y tiempo anterior a creación

**Given** (a) un `incident_id` que no existe en el almacén, y (b) por separado, un incidente existente cuyo `created_at` es posterior a un `reference_time` solicitado.

**When** el operador consulta el SLA en cada caso (`GET /api/v1/incidents/{incident_id}/sla`, con `reference_time` en el caso b).

**Then**:

- (a) la respuesta es `404 Not Found` y no se inventan métricas;
- (b) la respuesta es `422 Unprocessable Entity` (`reference_time` < `created_at`) sin métricas engañosas.

### Escenario 5 — Paridad CLI `create` y `sla`

**Given** los mismos datos de negocio usados en una creación HTTP exitosa (Escenario 1 o 2) y, para SLA, el mismo incidente e instante del Escenario 3 (o un par equivalente determinista).

**When** el operador ejecuta la operación equivalente por CLI:

```text
create --title "..." --raw-text "..."
sla --incident-id <id> --reference-time 2026-11-09T09:00:00
```

**Then** ambos comandos terminan con código de salida `0` e imprimen en stdout el mismo resultado de negocio que la operación HTTP correspondiente (mismos campos de creación/`is_duplicate`/`duplicate_of`, o mismos `elapsed_minutes` / `allowed_minutes` / `remaining_minutes` / `is_breached` / `requires_escalation`).

---

### Edge Cases

- Registro con equivalentes solo `RESOLVED`: alta exitosa con `is_duplicate=false`, `duplicate_of=[]`.
- Varios equivalentes abiertos con la misma clave: `duplicate_of` MUST listar **todos** esos ids abiertos.
- El id recién creado **nunca** aparece en su propio `duplicate_of`.
- El aviso de duplicado **nunca** impide persistir el nuevo incidente cuando las entradas son válidas.
- Incidente incumplido de SLA: la consulta marca incumplimiento; el escalamiento por umbral 75% **no** aplica una vez incumplido.
- Incidente bajo el umbral 75% y no incumplido ni resuelto: la consulta indica que requiere escalamiento.
- Misma operación (mismos datos) por HTTP y CLI → mismo resultado de negocio.
- Consulta SLA sin `reference_time`: se usa el momento real de la consulta.
- Si el incidente tiene momento de resolución, ese instante prevalece sobre `reference_time` para la evaluación SLA.
- `reference_time` < `created_at`: rechazo de validación (no evaluación).
- `incident_id` duplicado en creación: HTTP `409` / CLI exit `1`; el incidente previo permanece intacto.
- `status` no canónico en creación: HTTP `422` / CLI exit `1`.
- Creación con `status` canónico distinto de `OPEN` (p. ej. `IN_PROGRESS` o `RESOLVED`): se persiste con ese estado; la detección de duplicados abiertos sigue las reglas de FR-009.
- Creación con `status=RESOLVED` sin `resolved_at`: se persiste con `resolved_at = created_at` para la auditoría SLA.
- Creación con `status=RESOLVED` y `resolved_at` < `created_at`: HTTP `422` / CLI exit `1`; no persistir.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST exponer creación persistente vía `POST /api/v1/incidents` y CLI `create`.
- **FR-002**: `title` y `raw_text` son obligatorios; vacíos o solo espacios MUST rechazarse (HTTP `422` / CLI exit `1`) sin persistir.
- **FR-003**: `incident_id` es opcional; si se omite, MUST autogenerarse como `INC-<HEX8>`.
- **FR-004**: Si el cliente envía un `incident_id` que ya existe, MUST rechazar con HTTP `409 Conflict` / CLI exit `1`, sin persistir ni sobrescribir.
- **FR-005**: `created_at` es opcional; si se omite, MUST usarse el instante actual. `status` es opcional; si se omite, MUST ser `"OPEN"`; si se envía, MUST ser uno de `OPEN` | `IN_PROGRESS` | `ESCALATION_REQUIRED` | `RESOLVED`; valor desconocido → HTTP `422` / CLI exit `1` sin persistir.
- **FR-006**: `resolved_at` es opcional en creación; si `status=RESOLVED` y se omite, MUST igualarse a `created_at` (ya resuelto su default); si se envía y `resolved_at` < `created_at`, MUST rechazar (HTTP `422` / CLI exit `1`) sin persistir.
- **FR-007**: Al crear con entradas válidas, el sistema MUST clasificar a partir de `raw_text` y persistir el incidente con clasificación completa en la respuesta.
- **FR-008**: La respuesta de creación exitosa MUST ser HTTP `201` (API) o JSON en stdout (CLI) e incluir `is_duplicate` (bool) y `duplicate_of` (lista de identificadores).
- **FR-009**: `is_duplicate` / `duplicate_of` MUST basarse en coincidencia de `duplicate_group_key` únicamente con incidentes en `OPEN`, `IN_PROGRESS` o `ESCALATION_REQUIRED`, excluyendo `RESOLVED` y el propio identificador recién creado.
- **FR-010**: Si no hay equivalentes abiertos, MUST responder `is_duplicate=false` y `duplicate_of=[]`; si los hay, `is_duplicate=true` y la lista completa, **sin** impedir la persistencia.
- **FR-011**: El sistema MUST exponer auditoría SLA vía `GET /api/v1/incidents/{incident_id}/sla` y CLI `sla`.
- **FR-012**: `reference_time` es opcional (ISO 8601); si se omite, usar el momento real; si es inválido/ilegible o `reference_time` < `created_at`, rechazar (HTTP `422` / CLI exit `1`).
- **FR-013**: La consulta de SLA MUST exponer, como mínimo: `incident_id`, `elapsed_minutes`, `allowed_minutes`, `remaining_minutes`, `is_breached` y `requires_escalation`.
- **FR-014**: La evaluación de SLA MUST seguir las reglas de negocio del producto (presupuesto continuo para severidades críticas; horario hábil laboral para severidades menores; umbral 75% solo si no resuelto y no incumplido; prioridad del instante de resolución sobre el de referencia).
- **FR-015**: Si el `incident_id` consultado no existe, MUST responder HTTP `404` / CLI exit `1` sin métricas inventadas.
- **FR-016**: HTTP y CLI MUST devolver el mismo resultado de negocio para la misma operación de creación o de consulta SLA (mismos datos de entrada y mismo almacén).

### Key Entities

- **Incidente registrado**: `incident_id`, `title`, `raw_text`, `created_at`, `status`, clasificación (severidad, componente, justificación, equipo sugerido, `duplicate_group_key`, …), y `resolved_at` cuando aplica (`status=RESOLVED`).
- **Resultado de creación**: incidente persistido + clasificación completa + `is_duplicate` + `duplicate_of`.
- **Aviso de duplicado abierto**: `is_duplicate` y `duplicate_of` (ids en estados abiertos con la misma `duplicate_group_key`, sin el id nuevo).
- **Resultado de consulta SLA**: `incident_id`, `elapsed_minutes`, `allowed_minutes`, `remaining_minutes`, `is_breached`, `requires_escalation`, respecto de un instante de evaluación.
- **Clave de agrupación de duplicados**: `duplicate_group_key` canónica del dominio.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Un operador puede crear un incidente válido (`title` + `raw_text`) y verlo persistido (consultable después, p. ej. vía SLA) en menos de 1 minuto por HTTP o por CLI.
- **SC-002**: En el 100% de las creaciones válidas con al menos un equivalente abierto de la misma `duplicate_group_key`, la respuesta tiene `is_duplicate=true`, `duplicate_of` correcto (sin el id nuevo) **y** el incidente queda guardado.
- **SC-003**: En el 100% de las creaciones válidas sin equivalentes abiertos, `is_duplicate=false` y `duplicate_of=[]`.
- **SC-004**: Ante el caso P2 viernes `2026-11-06T17:00:00` → lunes `2026-11-09T09:00:00`, la consulta SLA devuelve exactamente `elapsed_minutes=120`, `allowed_minutes=480`, `remaining_minutes=360`, `is_breached=false`, `requires_escalation=false` (HTTP y CLI).
- **SC-005**: El 100% de los intentos de creación con `title` o `raw_text` vacíos (o solo espacios) se rechazan sin crear un incidente nuevo.
- **SC-006**: El 100% de las consultas SLA con incidente inexistente, `reference_time` inválido o `reference_time` < `created_at` se rechazan o indican no encontrado según el caso, sin métricas engañosas.
- **SC-007**: En el 100% de operaciones equivalentes (misma creación o misma consulta), HTTP y CLI coinciden en el resultado de negocio.
- **SC-008**: El 100% de creaciones con `incident_id` ya existente se rechazan (HTTP `409` / CLI exit `1`) sin alterar el incidente previo.
- **SC-009**: El 100% de creaciones con `status` no canónico se rechazan (HTTP `422` / CLI exit `1`) sin persistir.
- **SC-010**: El 100% de creaciones con `status=RESOLVED` y `resolved_at` < `created_at` se rechazan (HTTP `422` / CLI exit `1`) sin persistir.

## Assumptions

- Este hito corresponde a **H003** del roadmap; H002 (resumen de activos) y H004 (contenedores / BD dedicada) quedan fuera.
- La clasificación al crear reutiliza las reglas de triaje ya estabilizadas del producto (impacto/alcance, equipos canónicos, claves de agrupación canónicas).
- “Clasificación completa” = el conjunto canónico de campos del resultado de triaje del producto (paridad con H001).
- `HEX8` = ocho caracteres hexadecimales; el formato concreto de mayúsculas/minúsculas se fija en planificación si no afecta aceptación.
- El aviso de duplicado es informativo: no bloquea ni fusiona automáticamente incidentes.
- Catálogo de `status` en creación = `OPEN` | `IN_PROGRESS` | `ESCALATION_REQUIRED` | `RESOLVED`; default `OPEN`. Transiciones posteriores fuera de alcance.
- Con `status=RESOLVED`, `resolved_at` opcional; si falta, `resolved_at = created_at`; si `resolved_at` < `created_at`, rechazo `422`.
- Si `status` ≠ `RESOLVED`, un `resolved_at` enviado en creación se ignora (no se persiste como resuelto).
- Colisión de `incident_id` = conflicto de identidad (`409` / exit `1`), no actualización.
- Mayúsculas/minúsculas de `HEX8` y detalle de generación se fijan en planificación si no afectan aceptación.
- Existe (o se dispone) un almacén persistente consultable para demos y aceptación; el mecanismo concreto de almacenamiento se decide en planificación.
- Reglas SLA: severidades críticas en continuo 24/7; severidades menores en horario hábil laboral; un solo truncado a minutos tras acumular; escalamiento al 75% solo si no resuelto y no incumplido.
- Auth, CORS, batch, paginación y canales distintos de HTTP/CLI fuera de alcance.
- Paridad de canales es requisito de producto.
