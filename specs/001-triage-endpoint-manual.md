# Spec 001 — Triaje multi-interfaz (manual)

Especificación de aceptación del **H001** ([`docs/ROADMAP.md`](../docs/ROADMAP.md)): exponer el motor de triaje como servicio HTTP y como comando CLI, **sin persistencia**.

Esta spec es la **fuente de verdad** de aceptación. Si el motor actual diverge, se alinea el dominio en la implementación; no se rebajan estos escenarios.

---

## 1. Objetivo

Un operador o sistema puede clasificar un reporte al momento y obtener severidad, componente, equipo sugerido y señal de agrupación de duplicados, sin guardar el incidente.

## 2. Operación y arquitectura

- Operación **stateless**: no persiste en base de datos.
- Un único caso de uso compartido: `IncidentService.triage_incident`.
- Adaptadores inbound (REST y CLI) invocan ese caso de uso; no reimplementan reglas de triaje.
- Layout destino: arquitectura hexagonal (ADR-003) al implementar.

### Fuera de alcance

- CORS, autenticación, batch, persistencia, consulta de activos (H002), ciclo de vida/SLA (H003), contenedores (H004).

---

## 3. Contrato HTTP

- **Método y ruta:** `POST /api/v1/incidents/triage`
- **Request body:**

```json
{
  "incident_id": "<str>",
  "raw_text": "<str>"
}
```

- **Éxito:** `200 OK` con **todos** los campos de `TriageResult`:
  - `incident_id`
  - `severity`
  - `component`
  - `rationale`
  - `recommended_team`
  - `duplicate_group_key`
  - `consistency_ratio`
- **Validación:** si `incident_id` o `raw_text` están vacíos o contienen solo espacios (después de `.strip()`), responder `422 Unprocessable Entity` y no clasificar.
- **Health (complementario):** `GET /health` → `200` con `{"status": "ok"}`.

## 4. Contrato CLI (Typer)

- **Subcomando:** `triage --incident-id ... --raw-text ...`
- **Éxito:** imprimir el mismo `TriageResult` en **JSON por stdout**; código de salida `0`.
- **Entradas vacías / solo espacios:** error y código de salida `1`.
- **Paridad:** misma entrada válida → mismo resultado de negocio que HTTP.
- **Legado (complementario):** subcomando `audit` sobre `data/sample_incidents.json` (fuera del contrato mínimo de triaje).

---

## 5. Escenarios BDD (Given / When / Then)

### Escenario 1 — Caída crítica HTTP 502 en pasarela de pagos

**Given** un reporte de gateway/pasarela de pagos con HTTP 502 e impacto a comercios, por ejemplo el texto de `INC-1001`:

> URGENTE: El gateway de pagos devuelve HTTP 502 Bad Gateway en todas las transacciones con tarjeta de crédito desde hace 12 minutos. Ningún comercio puede cobrar.

**When** se invoca `POST /api/v1/incidents/triage` con `incident_id` y `raw_text` válidos (no vacíos tras `.strip()`).

**Then** la respuesta es `200 OK` y el cuerpo incluye:

- `severity="P0"`
- `component="payments-gateway"`
- `recommended_team="Backend-Core"`
- `duplicate_group_key="payments-gateway:http-502-outage"`

### Escenario 2 — Cuenta individual bloqueada mencionando "hoy"

**Given** un reporte de cuenta individual bloqueada que menciona "hoy", por ejemplo el texto de `INC-1002`:

> He intentado ingresar a mi cuenta tres veces y ahora aparece bloqueada. Necesito acceder hoy mismo porque debo enviar el informe de cierre a la junta directiva.

**When** se invoca `POST /api/v1/incidents/triage` con `incident_id` y `raw_text` válidos.

**Then** la respuesta es `200 OK` con:

- `severity="P2"`
- `recommended_team="Security-IAM"`

y **no** se clasifica como `P0` (la palabra "hoy" no provoca falso positivo de criticidad).

### Escenario 3 — Entradas vacías o solo espacios

**Given** una petición donde `raw_text=" "` **o** `incident_id=""`.

**When** se invoca `POST /api/v1/incidents/triage`.

**Then** la respuesta es `422 Unprocessable Entity` y no se ejecuta una clasificación efectiva del reporte.

### Escenario 4 — Paridad en CLI

**Given** el mismo caso crítico de pasarela con HTTP 502 del Escenario 1 (`INC-1001` y su `raw_text`).

**When** se ejecuta el CLI:

```text
triage --incident-id INC-1001 --raw-text "<texto del reporte 502>"
```

**Then** el proceso termina con código de salida `0`, imprime JSON válido en stdout con al menos:

- `severity="P0"`
- `recommended_team="Backend-Core"`

en paridad con el resultado HTTP del Escenario 1.

---

## 6. Notas

- Un solo reporte por llamada (HTTP o CLI).
- Esta spec manda sobre el comportamiento previo del motor plano en `src/triage_rules.py` para los casos de aceptación anteriores.
