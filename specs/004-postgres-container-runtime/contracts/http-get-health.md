# Contract: `GET /health`

**Feature**: H004  
**Adapter**: FastAPI inbound  
**Use case**: `IncidentService.check_operational_health`

## Request

- **Method / path**: `GET /health`
- **Body**: vacío
- **Query / headers**: ninguno requerido

## Success

Condición: el adaptador activo acaba de completar una consulta equivalente a `SELECT 1`.

- **Status**: `200 OK`
- **Body** (exactamente estas claves):

```json
{"status": "ok", "database": "connected"}
```

## Connectivity failure

Condición: `check_health()` devuelve `False` (host caído, conexión rechazada, consulta fallida). El proceso sí arrancó; la URL era válida.

- **Status**: `503 Service Unavailable`
- **Body** (exactamente estas claves):

```json
{"status": "error", "database": "unavailable"}
```

## Prohibido en la respuesta

- Cadena de conexión, usuario, clave, host o texto del driver.
- Claves adicionales (`detail`, `engine`, `error`).

## Notas

- No es el stub histórico `{"status": "ok"}`.
- Cada petición vuelve a consultar. No hay caché de “conectado”.
- Si `DATABASE_URL` es vacía o el esquema no está soportado, `create_app()` lanza `ValueError` y esta ruta no llega a registrarse. Ese fallo está en [database-url.md](./database-url.md), no en este JSON.
- Alta, SLA y resumen no reutilizan este cuerpo cuando el driver falla: [persistence-unavailable.md](./persistence-unavailable.md).
