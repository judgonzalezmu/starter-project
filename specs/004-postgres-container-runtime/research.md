# Research: H004 Persistencia dual y runtime en contenedores

**Date**: 2026-11-24  
**Spec**: [spec.md](./spec.md)  
**Plan**: [plan.md](./plan.md)

Todas las elecciones técnicas quedan resueltas aquí. No permanece ningún `NEEDS CLARIFICATION`.

Contexto medido en el repo antes de decidir:

- `GET /health` en `src/adapters/inbound/api/app.py` devuelve `{"status": "ok"}` sin consultar el almacén. No hay subcomando CLI `health`.
- `IncidentRepositoryPort.check_health` ya existe. `SQLiteIncidentRepository.check_health` ejecuta `SELECT 1` y devuelve `False` ante `sqlite3.Error`.
- `create_incident_repository` solo acepta `sqlite:///` y, si `DATABASE_URL` no existe, usa `sqlite:///:memory:`. Una variable vacía lanza `ValueError` sin incluir la URL. Cualquier otro esquema se rechaza.
- `create_app()` construye el repositorio al arrancar el proceso. La CLI lo construye dentro de `create`, `sla` y `summary`. `triage` y `audit` no abren almacén.
- El esquema vigente está en `SQLiteIncidentRepository._init_schema`: tablas `incidents` y `sla_policies`, instantes `TEXT` vía `isoformat()`, índices `idx_incidents_component_status` e `idx_incidents_dup_key`.
- `psycopg[binary]>=3.3.9` ya está en `pyproject.toml` y en `uv.lock`. No hay Dockerfile, `.dockerignore` ni `docker-compose.yml`.
- Los bans Ruff de dominio, aplicación e inbound cubren `sqlite3` y `sqlalchemy`. Todavía no nombran `psycopg`.
- ADR-004 (Opción C) y la constitución 1.1.0 fijan motor dual, sin ORM, TEXT ISO 8601 y Compose `api` + `db`. El archivo del ADR sigue en Estado Propuesto; la constitución ya lo da por aprobado. Este hito no edita el ADR.
- La spec deja para planificación el código HTTP de las rutas de negocio cuando la base cae, y exige que el Escenario 4 no use `docker compose up` como gate.

---

## 1. Dónde vive el chequeo de salud

**Decision**: Añadir en `src/application/services.py` un resultado de aplicación, no de dominio:

```python
@dataclass(frozen=True)
class OperationalHealth:
    status: Literal["ok", "error"]
    database: Literal["connected", "unavailable"]
```

`IncidentService.check_operational_health()` llama a `repository.check_health()` y traduce `True` → `status="ok"`, `database="connected"`; `False` → `status="error"`, `database="unavailable"`. FastAPI y Typer solo serializan ese resultado. El `SELECT 1` permanece dentro de cada adaptador outbound.

**Rationale**: La constitución reserva el dominio a triaje, SLA y duplicados. La paridad REST/CLI exige un solo caso de uso. El puerto ya expone `check_health`; falta el caso de uso que los dos canales comparten.

**Alternatives considered**: Armar el JSON en cada adaptador inbound (duplica la regla de paridad). Mover `OperationalHealth` a `src/domain/models.py` (mete un estado de infraestructura en el núcleo). Devolver el booleano crudo y dejar que cada canal invente los literales (riesgo de divergencia).

## 2. Resolución de `DATABASE_URL`

**Decision**: `create_incident_repository` sigue siendo el único lector.

| Entrada | Resultado |
| :--- | :--- |
| Argumento `None` y variable ausente | `sqlite:///:memory:` |
| Esquema `sqlite:///` (mayúsculas ignoradas solo en el esquema) | `SQLiteIncidentRepository` con el path original tras el prefijo |
| Esquema `postgresql://` | `PostgresIncidentRepository` con la URL ya recortada, sin bajar a minúsculas el resto |
| Argumento o variable definida, vacía o solo espacios | `ValueError("DATABASE_URL está definida pero vacía.")` |
| Otro esquema, `sqlite://` sin tercera barra, path SQLite vacío, o `postgres://` | `ValueError("Esquema de base de datos no soportado. Solo se admite sqlite:/// y postgresql://.")` |

El mensaje no incluye el valor recibido. Se hace `strip()` antes de clasificar; una URL válida con espacios alrededor sí se acepta. El esquema se compara en minúsculas; usuario, clave y path conservan su caja.

Construir el adaptador PostgreSQL no abre socket. La conexión ocurre en el primer `check_health` o en la primera operación de negocio.

**Rationale**: La spec separa “variable ausente” (memoria) de “variable vacía” (fallo inmediato). `postgres://` no está en el contrato. No conectar en el constructor permite que el proceso HTTP arranque con una URL válida pero un host caído, y que `/health` responda `503` en lugar de no existir. El `ValueError` de esquema sigue saliendo en `create_app()`: ese proceso no llega a servir rutas.

**Alternatives considered**: Aceptar `postgres://` como alias (la spec nombra solo `postgresql://`). Conectar en `__init__` y tumbar el proceso si el host no responde (impide el `503` de una URL válida inalcanzable). Fallback silencioso a `:memory:` (prohibido por FR-011).

## 3. Adaptador PostgreSQL y paridad de esquema

**Decision**: Nuevo `src/adapters/outbound/postgres_repository.py`. Una conexión `psycopg` por instancia, `connect_timeout=3`, `row_factory=dict_row`, `threading.Lock` alrededor del uso. Si la conexión muere, se descarta y el siguiente uso vuelve a conectar y a asegurar el esquema.

DDL idempotente, el mismo subconjunto en los dos motores:

- `sla_policies (severity TEXT PRIMARY KEY, max_resolution_minutes INTEGER NOT NULL, operates_24x7 INTEGER NOT NULL)` con `operates_24x7` en `0`/`1`.
- `incidents` con las columnas ya presentes en SQLite, `created_at` y `resolved_at` como `TEXT` (`datetime.isoformat()` / `fromisoformat()`).
- Índices `idx_incidents_component_status` y `idx_incidents_dup_key`.
- Semilla de `SLA_POLICY_TABLE` en cada conexión nueva.

DML distinto, resultado igual:

- SQLite conserva `?` e `INSERT OR REPLACE`.
- PostgreSQL usa `%s` e `INSERT ... ON CONFLICT DO UPDATE`.
- SQLite conserva los `ALTER TABLE` defensivos para archivos anteriores a H003. PostgreSQL crea el esquema completo con `CREATE TABLE IF NOT EXISTS` y no ejecuta esos `ALTER`.

`check_health` ejecuta `SELECT 1` en el momento de la llamada. Si no puede conectar o la consulta falla, devuelve `False` y no guarda ese resultado para la siguiente llamada.

Los métodos de negocio capturan `psycopg.Error` (y `sqlite3.Error` en el adaptador existente), hacen rollback si hay transacción, y lanzan `PersistenceUnavailableError`. Un fallo de driver no se traduce a `None` ni a `[]`: eso fingiría “no existe” o “no hay duplicados”.

**Rationale**: ADR-004 pide dos dialectos sobre un subconjunto común y TEXT ISO 8601 para que el núcleo no dependa de `timestamptz`. El lock cubre el threadpool de FastAPI sin añadir `psycopg_pool`. El timeout de 3 segundos cumple RNF-009 también cuando el host no rechaza la conexión. `psycopg[binary]` ya está autorizado y bloqueado en el lock; no hace falta otra librería.

**Alternatives considered**: Un ORM o SQLAlchemy Core (prohibido). Un solo módulo SQL compartido con un mini-compilador de dialectos (más maquinaria que las dos sentencias que realmente difieren). Pool de conexiones (dependencia y superficie que el hito no pide). Tipos `timestamptz` (rompen la paridad con SQLite). Traducir un error de conexión a `None` en `get_incident` (el SLA respondería `404` e inventaría ausencia).

## 4. HTTP y CLI cuando el almacén no responde

**Decision**: La spec pedía fijar aquí el código de las rutas de negocio.

| Situación | HTTP | CLI |
| :--- | :--- | :--- |
| Salud con `SELECT 1` correcto | `200` y `{"status":"ok","database":"connected"}` | stdout con ese JSON, exit `0` |
| Salud con conectividad fallida | `503` y `{"status":"error","database":"unavailable"}` | stdout con ese JSON, exit `1` |
| Alta, SLA o resumen y el driver falla | `503` y `{"detail":"El almacén de datos no está disponible."}` | el mismo texto en stderr, exit `1` |
| URL vacía o esquema no soportado | `create_app()` lanza `ValueError` y el servidor no arranca | el comando que abre almacén imprime el `ValueError` en stderr y sale `1`, sin JSON de salud |

El `detail` es una frase fija. No se concatena `str(exc)` del driver, ni host, ni usuario, ni URL.

Rutas que no abren almacén (`POST /api/v1/incidents/triage`, CLI `triage` y `audit`) siguen igual. En HTTP, un esquema inválido impide arrancar todo el proceso porque la fábrica corre dentro de `create_app()`. En CLI, `triage` no resuelve almacén y no se le obliga a hacerlo.

Códigos ya aceptados cuando el almacén sí responde: `201`, `404`, `409`, `422`. No se reasignan.

**Rationale**: `503` dice “la dependencia no está” y coincide con el estado de salud, pero el cuerpo de negocio no copia el JSON de `/health` (la spec lo permite y lo pide distinto). No devolver `201` ni listas vacías evita inventar datos. Separar “URL ilegible” de “host caído” conserva el fail-fast de FR-011 y el proceso vivo de FR-017.

**Alternatives considered**: `500` genérico (pierde la señal de dependencia y la spec lo citaba solo como alternativa). Reutilizar el JSON de `/health` en alta/SLA/resumen (la spec no lo exige y mezclaría contratos). Tumbar también `triage` CLI cuando la URL es inválida (acopla un caso de uso sin persistencia al motor).

## 5. Qué prueba la suite y qué queda en smoke

**Decision**: Un archivo `tests/test_spec_004_postgres_runtime.py` con cuatro `test_bdd_*`, uno por escenario.

1. **Salud conectada.** `DATABASE_URL` SQLite de archivo en `tmp_path`. `GET /health` es `200` con el JSON exacto. CLI `health` sale `0` con el mismo JSON. El adaptador es el real (`SELECT 1`), no un doble.
2. **Salud caída.** `postgresql://incidentops:incidentops@127.0.0.1:1/incidentops` (puerto cerrado, `connect_timeout=3`). HTTP `503` y CLI exit `1` con el JSON de indisponibilidad. `POST /api/v1/incidents` y CLI `create` responden el `detail` fijo, sin `incident_id` inventado y sin la URL ni la clave en cuerpo o stderr. No hace falta Docker: la conexión rechazada es la comprobación real.
3. **Selección.** (a) la URL de PostgreSQL anterior no cae a memoria: el alta HTTP es `503`, no `201`; (b) dos instancias con el mismo `sqlite:///` de archivo ven el mismo incidente; (c) sin variable, dos instancias `sqlite:///:memory:` no comparten filas. URL vacía y `mysql://...` lanzan `ValueError` cuyo texto no contiene el valor prohibido.
4. **Manifiesto.** El test lee `Dockerfile`, `.dockerignore` y `docker-compose.yml` y exige el contrato de [compose-runtime.md](./contracts/compose-runtime.md). No ejecuta `docker compose`.

La paridad de alta/SLA/resumen contra un PostgreSQL vivo se comprueba con el smoke de [quickstart.md](./quickstart.md) cuando el operador tiene Docker. La regresión H001–H003 sigue en SQLite y no levanta `db`.

**Rationale**: La spec prohíbe convertir Compose en gate y a la vez pide una comprobación real, no un stub. El puerto TCP cerrado demuestra el fallo de conectividad en CI. Comparar dos conexiones `:memory:` demuestra el default sin leer atributos privados. El type-check del adaptador no sustituye ese comportamiento.

**Alternatives considered**: Un doble que devuelve `check_health → False` (la spec lo pone como ejemplo, pero no prueba que el adaptador hable con la base). Testcontainers o `docker compose` dentro de pytest (contradice el gate opcional). Afirmar solo `isinstance(..., PostgresIncidentRepository)` (no demuestra que no haya fallback a memoria).

## 6. Runtime de contenedores

**Decision**: Tres archivos en la raíz del repo.

- `Dockerfile`: `FROM python:3.12-slim`; copiar el binario `uv` desde una etiqueta fija de `ghcr.io/astral-sh/uv` (la que corresponda al `uv` del lock en el momento de implementar, no `latest`); `uv sync --frozen --no-dev`; `CMD` uvicorn con `--factory`, `--host 0.0.0.0`, `--port 8000`.
- `.dockerignore`: excluye `.venv`, cachés, `.git`, `.env`, `*.db`, `tests/`, secretos locales. No excluye `pyproject.toml`, `uv.lock` ni `src/`.
- `docker-compose.yml` sin clave `version`: servicio `db` (`postgres:16-alpine`, volumen nominado, `pg_isready`) y servicio `api` (build local, `DATABASE_URL` hacia el hostname `db`, `depends_on.db.condition: service_healthy`, healthcheck HTTP a `http://127.0.0.1:8000/health` con la stdlib de Python porque la imagen slim no trae `curl`).

Placeholders de laboratorio, sustituibles y URL-safe: usuario, clave y base `incidentops`. Se documentan como valores locales, no como secretos de producción. El puerto `5432` no se publica al host. El puerto `8000` de `api` sí, para el smoke.

**Rationale**: La spec fija imagen, tag de Postgres, `uv`, healthchecks y `depends_on`. Fijar la etiqueta de `uv` evita que `latest` cambie el build entre máquinas. No publicar Postgres reduce la superficie; el smoke solo necesita `/health`.

**Alternatives considered**: Instalar `uv` con pip dentro de la imagen (más lento y menos reproducible). Healthcheck con `curl` (paquete extra no exigido). Publicar `5432` (innecesario para la aceptación). Contraseña de aspecto productivo en el manifiesto (prohibido).

## 7. Qué no cambia

**Decision**: No se modifican reglas en `models.py`, `triage_rules.py` ni `sla_calculator.py`. No se reescribe `src/incident_repository.py`: el benchmark sigue construyendo `SQLiteIncidentRepository` en memoria y usando `seed_synthetic_incidents`, método que no forma parte del puerto. Los bans nuevos son solo de frontera: `psycopg` en `src/domain/ruff.toml` y `src/application/ruff.toml`; `psycopg` y `src.adapters.outbound.postgres_repository` en `src/adapters/inbound/ruff.toml`.

**Rationale**: H004 cambia el borde de persistencia y el runtime. El benchmark es una medida de SQLite, no un caso de uso de producto. Meterle la fábrica lo acoplaría a PostgreSQL sin un requisito.

**Alternatives considered**: Hacer que el benchmark lea `DATABASE_URL` (fuera de alcance y rompe el entrypoint actual de 10k filas en memoria).
