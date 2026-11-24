# Feature Specification: Resumen de incidentes activos

**Feature Branch**: `002-active-incidents-summary`

**Created**: 2026-11-23

**Status**: Draft

**Input**: User description: "Necesitamos consultar el resumen de incidentes actualmente activos (OPEN e IN_PROGRESS) tanto por API HTTP como por CLI, indicando el total activo, cuántos incumplieron su SLA y el detalle de cada incidente (título, componente, severidad, estado, minutos transcurridos y si requiere escalamiento), permitiendo filtrar opcionalmente por componente."

## Clarifications

### Session 2026-11-23

- Q: Cuando un operador pide el resumen de incidentes activos, ¿las métricas de SLA se evalúan solo en el momento real de la consulta, o también puede indicar un instante fijo “a partir de”? → A: Instante “a partir de” opcional; si se omite, usar el momento real de la consulta (`reference_time`).
- Q: ¿Cada fila del detalle del resumen debe incluir el identificador del incidente además de título, componente, severidad, estado, minutos transcurridos y si requiere escalamiento? → A: Sí: el detalle MUST incluir el identificador del incidente en cada fila.
- Q: ¿En qué orden deben aparecer las filas del detalle del resumen cuando el operador no pide un criterio de ordenación? → A: Por severidad (P0 primero) y, a igualdad, por minutos transcurridos descendente.
- Q: Si dos incidentes activos tienen la misma severidad y los mismos minutos transcurridos, ¿cómo se desempata el orden de esas filas en el detalle? → A: Por identificador de incidente, orden lexicográfico ascendente.
- Q: Si el operador indica un instante “a partir de” inválido o ilegible, ¿qué debe hacer el sistema? → A: Rechazar la consulta (error de validación); no calcular el resumen.

## 1. Objetivo

Un operador puede consultar el resumen de incidentes **actualmente activos** (`OPEN` e `IN_PROGRESS`), con totales de activos e incumplimientos de SLA y el detalle de cada uno, desde **HTTP** y **CLI**, con filtro opcional por componente e instante de evaluación opcional.

Esta spec es la **fuente de verdad** de aceptación del hito H002 ([`docs/ROADMAP.md`](../../docs/ROADMAP.md)).

## 2. Operación y alcance

- Lectura del catálogo consultable de incidentes; **no** registra ni actualiza el ciclo de vida (H003).
- Un único caso de uso compartido expuesto por adaptadores inbound (REST y CLI); no reimplementar reglas de SLA ni de activos por canal.
- Activos = solo `OPEN` e `IN_PROGRESS` (excluye `RESOLVED` y `ESCALATION_REQUIRED`).

### Fuera de alcance

- Autenticación, autorización, CORS, batch, paginación, ordenación configurable, MCP.
- Registro persistente completo, alerta de duplicados abiertos y auditoría SLA de ciclo de vida (H003).
- Contenedores / BD relacional dedicada (H004).

## 3. Contrato HTTP

- **Método y ruta:** `GET /api/v1/incidents/summary`
- **Query parameters (opcionales):**
  - `component` — filtra por componente exacto; omitido o solo espacios = sin filtro (todos los activos).
  - `reference_time` — instante de evaluación de SLA (ISO-8601); omitido = momento real de la consulta.
- **Éxito:** `200 OK` con JSON:

```json
{
  "total_active": 0,
  "breached_count": 0,
  "incidents": [
    {
      "incident_id": "<str>",
      "title": "<str>",
      "component": "<str>",
      "severity": "P0|P1|P2|P3",
      "status": "OPEN|IN_PROGRESS",
      "elapsed_minutes": 0,
      "requires_escalation": false
    }
  ]
}
```

- **Estado vacío / sin coincidencias:** `200 OK` con `total_active=0`, `breached_count=0`, `incidents=[]`.
- **Validación:** si `reference_time` está presente pero es inválido o ilegible → `422 Unprocessable Entity` y no se calcula el resumen.
- **Orden de `incidents`:** severidad `P0` → `P1` → `P2` → `P3`; a igualdad, `elapsed_minutes` descendente; a igualdad, `incident_id` lexicográfico ascendente.
- **Health (complementario, H001):** `GET /health` → `200` con `{"status": "ok"}`.

## 4. Contrato CLI

- **Subcomando:** `summary [--component ...] [--reference-time ...]`
- **Éxito:** código de salida `0`; imprime en stdout el mismo JSON de negocio que HTTP (`total_active`, `breached_count`, `incidents`).
- **Estado vacío / sin coincidencias:** código `0` con `total_active=0`, `breached_count=0`, `incidents=[]`.
- **`reference_time` inválido o ilegible:** error y código de salida `1`; no imprime un resumen válido de activos.
- **Paridad:** misma consulta (mismo `component`, mismo `reference_time`, mismos datos) → mismo resultado de negocio que HTTP.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver resumen operativo de activos (Priority: P1)

Un operador de guardia necesita totales y detalle de activos (con identificador) para priorizar la respuesta.

**Why this priority**: Valor central de H002.

**Independent Test**: Escenarios BDD 1 y 4.

### User Story 2 - Filtrar activos por componente (Priority: P2)

Un especialista ve solo los activos de un componente.

**Why this priority**: Filtro opcional pedido para H002.

**Independent Test**: Escenario BDD 2.

### User Story 3 - Conjunto vacío de activos (Priority: P3)

Confirmar tablero limpio o filtro sin coincidencias sin interpretarlo como fallo.

**Why this priority**: Diferencia “nada activo” de error.

**Independent Test**: Escenario BDD 3.

### User Story 4 - Rechazo de instante inválido (Priority: P3)

Un instante `reference_time` ilegible no debe producir métricas engañosas.

**Why this priority**: Confiabilidad de SLA.

**Independent Test**: Escenario BDD 5.

---

## 5. Escenarios BDD (Given / When / Then)

### Escenario 1 — Resumen global excluyendo no activos

**Given** un catálogo con incidentes en estados diversos, incluyendo al menos uno `RESOLVED` y activos en `OPEN` y/o `IN_PROGRESS`, con evaluación de SLA conocida para un `reference_time` fijo.

**When** el operador consulta `GET /api/v1/incidents/summary` sin `component` (con `reference_time` opcional determinista).

**Then** la respuesta es `200 OK` y el JSON incluye:

- `total_active` igual al número de incidentes en `OPEN` o `IN_PROGRESS`
- `breached_count` igual a cuántos de esos activos incumplieron SLA en el instante de evaluación
- `incidents` solo con activos (`OPEN` / `IN_PROGRESS`); ningún `RESOLVED` ni `ESCALATION_REQUIRED`
- cada ítem con `incident_id`, `title`, `component`, `severity`, `status`, `elapsed_minutes`, `requires_escalation`
- `incidents` ordenado según el contrato (severidad, luego minutos, luego id)

### Escenario 2 — Resumen filtrado por componente

**Given** hay incidentes activos en más de un componente.

**When** el operador consulta `GET /api/v1/incidents/summary?component=<componente>` (mismo `reference_time` determinista si aplica).

**Then** la respuesta es `200 OK` y `total_active`, `breached_count` e `incidents` reflejan **solo** activos de ese componente; todos los ítems de `incidents` tienen ese `component`.

### Escenario 3 — Caso vacío (sin activos o sin coincidencias)

**Given** no existen incidentes en `OPEN` ni `IN_PROGRESS`, **o** el `component` indicado no tiene activos coincidentes.

**When** el operador consulta el resumen (global o filtrado) por HTTP.

**Then** la respuesta es `200 OK` con JSON válido `total_active=0`, `breached_count=0` e `incidents=[]` (no es error de negocio).

### Escenario 4 — Consulta equivalente por CLI

**Given** el mismo catálogo y el mismo `reference_time` (y el mismo `component` si aplica) que una consulta HTTP exitosa de los escenarios anteriores.

**When** se ejecuta:

```text
summary [--component <componente>] [--reference-time <instante>]
```

**Then** el proceso termina con código de salida `0`, imprime JSON válido en stdout con los mismos `total_active`, `breached_count` e `incidents` (mismos campos y mismo orden) que la respuesta HTTP equivalente.

### Escenario 5 — `reference_time` inválido rechazado

**Given** el operador indica un `reference_time` inválido o ilegible.

**When** solicita el resumen por HTTP (`GET /api/v1/incidents/summary?reference_time=...`) o por CLI (`summary --reference-time ...`).

**Then** la consulta se rechaza: HTTP `422 Unprocessable Entity` / CLI código de salida `1`, y no se devuelve un resumen de activos con totales y detalle.

### Edge Cases

- `RESOLVED` y `ESCALATION_REQUIRED` nunca aparecen en `incidents`.
- Activo bajo umbral de escalamiento (75%) y no incumplido: `requires_escalation=true` y no suma a `breached_count`.
- Activo incumplido: suma a `breached_count`; `requires_escalation` no aplica una vez incumplido.
- `component` vacío o solo espacios = ausencia de filtro.
- Componente desconocido = Escenario 3 (vacío exitoso).
- Misma consulta HTTP/CLI (mismo filtro e instante) = mismo JSON de negocio.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST exponer `GET /api/v1/incidents/summary` y el subcomando CLI `summary`.
- **FR-002**: Un incidente se considera activo únicamente si su estado es `OPEN` o `IN_PROGRESS`.
- **FR-003**: El resumen MUST incluir `total_active` (conteo de activos del conjunto consultado).
- **FR-004**: El resumen MUST incluir `breached_count` (activos del conjunto que incumplieron SLA en el instante de evaluación).
- **FR-005**: Cada elemento de `incidents` MUST exponer: `incident_id`, `title`, `component`, `severity`, `status`, `elapsed_minutes`, `requires_escalation`.
- **FR-006**: El query/flag `component` es opcional; con valor efectivo, totales y detalle se calculan solo sobre activos de ese componente.
- **FR-007**: La evaluación de `elapsed_minutes`, incumplimiento y `requires_escalation` MUST seguir las reglas SLA del producto respecto del instante de evaluación.
- **FR-008**: HTTP y CLI MUST devolver el mismo resultado de negocio para la misma consulta (mismo `component`, mismo `reference_time`, mismos datos).
- **FR-009**: Sin activos aplicables, MUST responder éxito con `total_active=0`, `breached_count=0`, `incidents=[]` (`200` / exit `0`).
- **FR-010**: `reference_time` es opcional; si se omite, usar el momento real de la consulta; si es inválido/ilegible, rechazar (HTTP `422` / CLI exit `1`) sin resumen.
- **FR-011**: `incidents` MUST ordenarse por severidad `P0`→`P3`, luego `elapsed_minutes` descendente, luego `incident_id` lexicográfico ascendente.

### Key Entities

- **Incidente activo**: `OPEN` | `IN_PROGRESS`, con los campos de detalle del contrato.
- **Resumen de activos**: `total_active`, `breached_count`, `incidents`.
- **Filtro por componente**: query/flag `component` opcional (coincidencia exacta).
- **Instante de evaluación**: query/flag `reference_time` opcional; default = momento real de la consulta.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Con un conjunto de prueba de al menos 5 incidentes (activos e inactivos), el operador obtiene el resumen en menos de 1 minuto por HTTP o CLI.
- **SC-002**: El 100% de los ítems en `incidents` están en `OPEN` o `IN_PROGRESS`; ninguno `RESOLVED` o `ESCALATION_REQUIRED`.
- **SC-003**: En el 100% de consultas equivalentes, HTTP y CLI coinciden en totales, campos de detalle y orden (FR-011).
- **SC-004**: Con `component`, el 100% de `incidents` pertenece a ese componente y los totales reflejan ese subconjunto.
- **SC-005**: Ante cero activos aplicables, el operador recibe `total_active=0`, `breached_count=0`, `incidents=[]` sin interpretarlo como fallo.
- **SC-006**: Ante `reference_time` inválido, el 100% de las consultas se rechazan sin devolver un resumen de activos.

## Assumptions

- Hito H002 del roadmap; H003/H004 fuera de alcance.
- Existe catálogo consultable (semilla o almacén de lectura) para demos y aceptación.
- `requires_escalation` = umbral 75% del presupuesto SLA, solo si no resuelto y no incumplido.
- SLA: P0/P1 continuo; P2/P3 horario hábil; evaluación respecto de `reference_time` o “ahora”.
- Filtro de componente = coincidencia exacta del identificador.
- Auth, paginación y ordenación configurable fuera de alcance; el orden por defecto es FR-011.
- CORS, batch y canales distintos de HTTP/CLI fuera de alcance.
