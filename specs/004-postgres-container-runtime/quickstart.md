# Quickstart: validar H004

**Feature**: `004-postgres-container-runtime`  
**Contracts**: [contracts/](./contracts/) · **Model**: [data-model.md](./data-model.md)

Los escenarios 1–3 y el manifiesto del escenario 4 se comprueban sin Docker. El arranque real `api` + `db` es un smoke aparte, solo si la máquina tiene runtime de contenedores.

## Prerrequisitos

```bash
uv sync --group dev
```

`psycopg[binary]` ya está en el proyecto. No hace falta instalar otro driver ni un ORM.

## Gates (tienen que pasar)

```bash
uv run ruff check src/
uv run python -m src.domain.triage_rules
uv run python -m src.domain.sla_calculator
uv run pytest -v
```

Resultado esperado:

- Ruff en verde, incluidos los bans de `psycopg` fuera de outbound.
- Dominio de triaje y SLA sin cambio de política.
- H001, H002 y H003 siguen en verde sobre SQLite.
- Cuatro pruebas `test_bdd_*` en `tests/test_spec_004_postgres_runtime.py`:
  - salud `200` / CLI exit `0` contra un SQLite de archivo;
  - salud `503` / CLI exit `1` contra un PostgreSQL inalcanzable (`127.0.0.1:1`), y alta que falla sin inventar un incidente;
  - selección por `DATABASE_URL` (PostgreSQL sin fallback a memoria, archivo compartido, memoria no compartida, URL vacía o esquema ajeno);
  - `Dockerfile`, `.dockerignore` y `docker-compose.yml` cumplen [compose-runtime.md](./contracts/compose-runtime.md).

`pytest` no ejecuta `docker compose up`.

## Salud en local (SQLite)

PowerShell, archivo aislado:

```powershell
$env:DATABASE_URL = "sqlite:///$($PWD.Path.Replace('\','/'))/data/h004-demo.db"
uv run python -m src.adapters.inbound.cli health
```

Salida esperada, exit `0`:

```json
{"status": "ok", "database": "connected"}
```

El mismo JSON en `GET /health` con `200` si el servidor usa esa variable:

```bash
uv run uvicorn src.adapters.inbound.api.app:create_app --factory --reload
```

```bash
curl -s -D - http://127.0.0.1:8000/health
```

Quitar la variable (no dejarla en blanco) devuelve el default en memoria. En PowerShell:

```powershell
Remove-Item Env:DATABASE_URL
```

## URL que no debe arrancar

```powershell
$env:DATABASE_URL = "mysql://localhost/incidentops"
uv run python -m src.adapters.inbound.cli health
```

Exit `1`. stderr con el mensaje de esquema no soportado. stdout sin JSON de salud. El mensaje no repite `mysql://localhost/incidentops`.

Variable definida y vacía: el mismo tipo de fallo, con el mensaje de URL vacía.

```powershell
$env:DATABASE_URL = ""
```

Para volver al default, borrar la variable; no dejarla en blanco.

## Alta cuando PostgreSQL no acepta conexiones

```powershell
$env:DATABASE_URL = "postgresql://incidentops:incidentops@127.0.0.1:1/incidentops"
uv run python -m src.adapters.inbound.cli health
uv run python -m src.adapters.inbound.cli create --title "Pagos" --raw-text "payments gateway HTTP 502"
```

- `health`: exit `1` y JSON `database=unavailable` en stdout; la respuesta llega en ≤ 5 s (RNF-009).
- `create`: exit `1`, stderr `El almacén de datos no está disponible.`, sin JSON de incidente creado.

Detalle de códigos: [persistence-unavailable.md](./contracts/persistence-unavailable.md).

## Smoke con Docker (no es gate)

Con Docker en marcha, desde la raíz del repo y sin exportar una `DATABASE_URL` de SQLite al entorno del host (Compose inyecta la suya en `api`):

```bash
docker compose up --build -d
docker compose ps
curl -s -D - http://127.0.0.1:8000/health
docker compose down
```

Esperado cuando el smoke se ejecuta:

- `db` pasa a sano por `pg_isready` antes de que `api` arranque (`depends_on` con `service_healthy`).
- `curl` recibe `200` y `{"status":"ok","database":"connected"}`.
- El puerto `5432` no queda publicado al host.

Para repetir el smoke desde cero, borrar también el volumen nominado (`docker compose down -v`). Eso tira los datos de laboratorio; el adaptador vuelve a crear el esquema al conectar.

Los placeholders de usuario, clave y base son `incidentops` (laboratorio local, sustituibles por entorno). No usarlos como credenciales de producción.
