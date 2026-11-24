# Contract: `GET /api/v1/incidents/summary`

**Channel**: HTTP inbound (FastAPI)  
**Use case**: `IncidentService.get_active_incidents_summary`  
**Data**: [data-model.md](../data-model.md)

## Request

`GET /api/v1/incidents/summary`

| Query | Obligatorio | Regla |
| :--- | :--- | :--- |
| `component` | No | Omitido, vacío o solo espacios: todos los activos. Con texto: coincidencia exacta tras recortar espacios de los extremos. |
| `reference_time` | No | Omitido: reloj de la consulta. Presente: instante ISO-8601. `Z` se acepta y se normaliza a UTC naive. Ilegible: no se calcula el resumen. |

No hay cuerpo. No hay autenticación, paginación ni parámetro de orden.

## Success — `200 OK`

Cuerpo JSON:

```json
{
  "total_active": 5,
  "breached_count": 1,
  "incidents": [
    {
      "incident_id": "INC-A",
      "title": "Pasarela caída",
      "component": "payments-gateway",
      "severity": "P0",
      "status": "OPEN",
      "elapsed_minutes": 120,
      "requires_escalation": false
    }
  ]
}
```

El ejemplo de fila ilustra la forma. Con el [catálogo de aceptación](../data-model.md#catálogo-de-aceptación) y `reference_time=2026-11-20T12:00:00`, la lista completa es:

| # | incident_id | component | severity | status | elapsed_minutes | requires_escalation |
| ---: | :--- | :--- | :--- | :--- | ---: | :--- |
| 1 | `INC-A` | `payments-gateway` | `P0` | `OPEN` | 120 | `false` |
| 2 | `INC-B` | `payments-gateway` | `P0` | `OPEN` | 50 | `true` |
| 3 | `INC-C` | `auth-identity` | `P1` | `IN_PROGRESS` | 60 | `false` |
| 4 | `INC-M` | `reporting-api` | `P3` | `OPEN` | 60 | `false` |
| 5 | `INC-Z` | `reporting-api` | `P3` | `OPEN` | 60 | `false` |

Agregados de ese caso: `total_active=5`, `breached_count=1`.

Misma consulta con `component=payments-gateway`: `total_active=2`, `breached_count=1`, ítems `INC-A` e `INC-B` en ese orden. Todos los ítems traen ese `component`.

Esquemas Pydantic del adaptador: `ActiveIncidentItem`, `ActiveIncidentsSummaryResponse`.

### Vacío — también `200 OK`

Si no hay activos, o el componente no tiene activos:

```json
{
  "total_active": 0,
  "breached_count": 0,
  "incidents": []
}
```

Eso incluye un componente desconocido. No es un 404.

## Validation — `422 Unprocessable Entity`

`reference_time` presente e ilegible (por ejemplo `reference_time=manana` o cadena vacía).

```json
{
  "detail": "reference_time no es un instante ISO-8601 válido."
}
```

El mensaje puede variar; el código y la ausencia de `total_active` / `incidents` no. La forma `{"detail": "..."}` es la misma que ya usa el triaje H001.

## Invariantes de la respuesta

- `status` de cada ítem es `OPEN` o `IN_PROGRESS`.
- `severity` es `P0`, `P1`, `P2` o `P3`.
- `elapsed_minutes` es entero ≥ 0 producido por ADR-002.
- Un activo incumplido suma a `breached_count` y lleva `requires_escalation=false`.
- Un activo en umbral 75 % y no incumplido lleva `requires_escalation=true` y no suma a `breached_count`.
- Orden: severidad `P0`→`P3`, minutos descendente, `incident_id` ascendente.

## Health heredado

`GET /health` permanece `200` con `{"status": "ok"}`. No consulta `check_health`.

## Fuera de este contrato

Registro de incidentes, alerta de duplicados, paginación, orden pedido por el cliente, CORS y MCP.
