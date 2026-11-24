# Contract: runtime `api` + `db`

**Feature**: H004  
**Files**: `Dockerfile`, `.dockerignore`, `docker-compose.yml` (raíz del repositorio)  
**Gate automatizado**: lectura de estos archivos. `docker compose up` no forma parte de pytest.  
**Smoke**: [quickstart.md](../quickstart.md)

## `Dockerfile`

| Requisito | Valor |
| :--- | :--- |
| Imagen base | `python:3.12-slim` |
| Gestor | `uv`, copiado de una etiqueta fija de `ghcr.io/astral-sh/uv` (no `latest`) |
| Dependencias | `uv sync --frozen --no-dev` usando `pyproject.toml` y `uv.lock` |
| Proceso | `uvicorn src.adapters.inbound.api.app:create_app --factory --host 0.0.0.0 --port 8000` |
| Secretos | No copia `.env` ni escribe credenciales en la imagen |

El contexto de build solo necesita el manifiesto de `uv` y `src/`.

## `.dockerignore`

Debe excluir, como mínimo:

- entornos virtuales (`.venv`, `venv`)
- cachés (`__pycache__`, `.pytest_cache`, `.ruff_cache`)
- `.git`
- `.env` y `*.db`
- `tests/`

No debe excluir `pyproject.toml`, `uv.lock` ni `src/`.

## `docker-compose.yml`

Dos servicios. Sin publicar el puerto de PostgreSQL al host.

### `db`

| Campo | Valor |
| :--- | :--- |
| Imagen | `postgres:16-alpine` |
| Volumen | nominado, montado en el directorio de datos de PostgreSQL |
| Entorno | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |
| Default de laboratorio | `incidentops` / `incidentops` / `incidentops` (placeholders URL-safe, no secretos de producción; el operador puede sustituirlos) |
| Healthcheck | `pg_isready` contra ese usuario y esa base. El servicio solo queda sano cuando acepta conexiones |

### `api`

| Campo | Valor |
| :--- | :--- |
| Build | contexto del repositorio (el `Dockerfile` de arriba) |
| `DATABASE_URL` | `postgresql://` hacia el hostname `db`, puerto `5432`, con el mismo usuario, clave y base que `db` |
| `depends_on` | `db` con condición `service_healthy` |
| Puerto publicado | `8000:8000` |
| Healthcheck | petición HTTP a `http://127.0.0.1:8000/health` hecha con la biblioteca estándar de Python (la imagen no asume `curl`). Un `503` deja el contenedor no sano |

`api` no se considera lista hasta que su healthcheck recibe `200` con base conectada. Eso implica que `db` ya pasó `pg_isready` y que la API ya completó su propio `SELECT 1`.

## Credenciales

Los valores viajan por el entorno del compose. El repositorio no contiene una clave de producción ni un `.env` real. Los defaults `incidentops` se documentan como laboratorio local.

## Fuera de este manifiesto

- Réplicas, backups, migraciones versionadas.
- Un servicio de SQLite: el archivo o la memoria viven dentro del proceso y no necesitan `db`.
- Publicación del puerto `5432`.
