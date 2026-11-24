# Contract: CLI `summary`

**Channel**: Typer (`src/adapters/inbound/cli.py`)  
**Use case**: el mismo `IncidentService.get_active_incidents_summary` que HTTP  
**HTTP equivalente**: [http-get-incidents-summary.md](./http-get-incidents-summary.md)

## Invocation

```text
python -m src.adapters.inbound.cli summary [--component TEXTO] [--reference-time INSTANTE]
```

| Flag | Obligatorio | Regla |
| :--- | :--- | :--- |
| `--component` | No | Misma semántica que el query `component`. |
| `--reference-time` | No | Misma semántica que el query `reference_time`. |

El proceso lee el catálogo desde el repositorio elegido por `DATABASE_URL` (default `sqlite:///:memory:`, vacío en cada proceso).

## Success — exit `0`

stdout es un JSON de negocio con las mismas claves y los mismos valores que el `200` HTTP de la misma consulta (mismo componente, mismo instante, mismos datos):

- `total_active`
- `breached_count`
- `incidents[]` con `incident_id`, `title`, `component`, `severity`, `status`, `elapsed_minutes`, `requires_escalation`

El orden de `incidents` es el de FR-011. La paridad se juzga sobre el JSON parseado, no sobre el orden de las claves ni sobre espacios.

Con el catálogo de [data-model.md](../data-model.md) y `--reference-time 2026-11-20T12:00:00`, stdout parseado coincide con la tabla global del contrato HTTP. Añadiendo `--component payments-gateway`, coincide con el subconjunto de dos ítems.

Vacío (sin activos o sin coincidencias): exit `0` y

```json
{"total_active": 0, "breached_count": 0, "incidents": []}
```

## Validation — exit `1`

`--reference-time` presente e ilegible.

- Código de salida `1`.
- El mensaje va a stderr.
- stdout no es un resumen de activos (`total_active` / `incidents` no se imprimen como resultado válido).

## Paridad

Para un archivo SQLite compartido, la misma semilla y los mismos argumentos, el objeto JSON del CLI es igual al cuerpo JSON del `GET`. Cada canal abre el adaptador por la fábrica; por eso la paridad de aceptación usa ruta de archivo y no `:memory:`.

## Fuera de este contrato

Los subcomandos `triage` y `audit` no cambian. `summary` no registra incidentes ni acepta un flag de orden.
