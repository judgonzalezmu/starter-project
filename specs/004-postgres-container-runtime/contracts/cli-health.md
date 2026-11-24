# Contract: CLI `health`

**Feature**: H004  
**Adapter**: Typer inbound  
**Use case**: `IncidentService.check_operational_health`  
**Paridad**: mismo resultado de negocio que [http-get-health.md](./http-get-health.md)

## Invocation

```text
uv run python -m src.adapters.inbound.cli health
```

Sin opciones. El almacén sale de `DATABASE_URL` (o del default en memoria si la variable no existe).

## Success

- **Exit code**: `0`
- **stdout**: el JSON de HTTP `200`, y nada más salvo el salto de línea final

```json
{"status": "ok", "database": "connected"}
```

## Connectivity failure

- **Exit code**: `1`
- **stdout**: el JSON de HTTP `503`

```json
{"status": "error", "database": "unavailable"}
```

- **stderr**: vacío de secretos. No es el canal del JSON de negocio.

## URL ilegible

Si la fábrica lanza `ValueError` (variable vacía o esquema no soportado):

- **Exit code**: `1`
- **stderr**: el mensaje de la fábrica, sin el valor de la URL
- **stdout**: no imprime el JSON de salud

Ese caso no es “base no disponible”. Es “no hay almacén que consultar”.

## Notas

- Mismo estado de conectividad que HTTP → mismos dos campos y los mismos literales.
- `triage` y `audit` no ganan esta comprobación: no abren almacén.
