# Contract: almacén inalcanzable en operaciones de negocio

**Feature**: H004  
**Error**: `PersistenceUnavailableError`  
**Use cases**: `create_incident`, `evaluate_incident_sla`, `get_active_incidents_summary`

Aplica cuando la URL ya era válida, el proceso arrancó, y el driver falla al ejecutar la operación (conexión rechazada, timeout, conexión cerrada, error operativo). No aplica a la validación de entrada ni a “el incidente no existe”.

## HTTP

| Ruta | Status | Body |
| :--- | :--- | :--- |
| `POST /api/v1/incidents` | `503 Service Unavailable` | `{"detail":"El almacén de datos no está disponible."}` |
| `GET /api/v1/incidents/{incident_id}/sla` | `503 Service Unavailable` | el mismo `detail` |
| `GET /api/v1/incidents/summary` | `503 Service Unavailable` | el mismo `detail` |

El cuerpo no es el JSON de [http-get-health.md](./http-get-health.md). No incluye `incident_id`, filas inventadas, URL, credenciales ni el mensaje del driver.

Cuando el almacén responde, los códigos de H003 se mantienen: `201`, `404`, `409`, `422`.

`POST /api/v1/incidents/triage` no consulta el almacén. No adopta este `503`.

## CLI

| Comando | Exit | stderr | stdout |
| :--- | :--- | :--- | :--- |
| `create` | `1` | `El almacén de datos no está disponible.` | sin JSON de alta |
| `sla` | `1` | la misma frase | sin JSON de SLA |
| `summary` | `1` | la misma frase | sin JSON de resumen |

## Garantía de no inventar datos

- `save_incident` que falla no deja que el caso de uso responda `201`.
- `get_incident` que no puede consultar no se convierte en `404`.
- `find_open_duplicates` que no puede consultar no se convierte en “no hay duplicados”.
- `list_active_incidents` que no puede consultar no se convierte en resumen vacío.

## Salud en el mismo estado

En paralelo, `GET /health` y CLI `health` usan su propio contrato (`503` / exit `1` con `database=unavailable`). Una operación de negocio y un chequeo de salud no comparten cuerpo.
