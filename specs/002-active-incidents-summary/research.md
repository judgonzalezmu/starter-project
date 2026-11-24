# Research: H002 Resumen de incidentes activos

**Date**: 2026-11-23  
**Spec**: [spec.md](./spec.md)  
**Plan**: [plan.md](./plan.md)

Todas las elecciones técnicas quedan resueltas aquí. No permanece ningún `NEEDS CLARIFICATION`.

Contexto medido en el repo antes de decidir:

- `src/incident_repository.py` todavía carga `SELECT * FROM incidents` y consulta `sla_policies` por fila (N+1). El esquema base (`incidents`, `sla_policies` sembrada desde `SLA_POLICY_TABLE`) sí es el de Semana 1.
- `IncidentService` solo clasifica, sin persistencia. `GET /health` responde `{"status": "ok"}` sin base de datos.
- `Incident` no guarda `duplicate_group_key`; esa clave canónica vive hoy en `TriageResult`.
- Ruff 0.17.6 está en el grupo `dev`. `uv run ruff check src --select E4,E7,E9,F,TID` pasa sobre el árbol actual.
- Un ensayo aislado con `extend` confirmó, en Ruff 0.17.6, que banear `fastapi` marca `fastapi.routing`, que banear `src.adapters` marca `src.adapters.outbound.sqlite_repository`, y que `ban-relative-imports = "parents"` marca `TID252`.

---

## 1. Dónde se calcula el SLA y qué optimiza el SQL

**Decision**: `list_active_incidents` ejecuta una sola consulta con `INNER JOIN sla_policies` e índice `(component, status)`. Devuelve entidades `Incident`. `IncidentService.get_active_incidents_summary` llama a `evaluate_sla_status` por cada incidente devuelto y agrega `total_active`, `breached_count` y el detalle ordenado.

**Rationale**: La constitución exige un solo cálculo de SLA, el de ADR-002 (segundos acumulados, truncado a minutos una vez, umbral 75 % solo si no está resuelto ni incumplido, `resolved_at` antes que `reference_time`). El N+1 de Semana 1 leía la política en SQL y además llamaba al dominio; el `JOIN` conserva el beneficio de una sola ida a la base (y descarta severidades huérfanas) sin convertir los minutos de `sla_policies` en fuente de verdad.

**Alternatives considered**: Seguir calculando el resumen dentro del repositorio (acopla el outbound al caso de uso y duplica el servicio). Calcular incumplimiento con `max_resolution_minutes` del `JOIN` (diverge del horario hábil y del truncado de ADR-002). Dejar el N+1 y filtrar en Python (contradice el diseño pedido para H002).

## 2. Puerto `IncidentRepositoryPort`

**Decision**: Nuevo `src/application/ports.py` con un `typing.Protocol` decorado con `@runtime_checkable`:

| Método | Contrato |
| :--- | :--- |
| `save_incident(incident: Incident) -> None` | Upsert parametrizado por `incident_id`. |
| `get_incident(incident_id: str) -> Incident \| None` | `None` si no existe. |
| `find_open_duplicates(duplicate_group_key: str) -> list[Incident]` | El método está en el puerto. H002 no lo usa. `SQLiteIncidentRepository` devuelve `[]`. |
| `list_active_incidents(component_filter: str \| None = None) -> list[Incident]` | Solo `OPEN` e `IN_PROGRESS`. `None` = todos los componentes. |
| `check_health() -> bool` | `True` si `SELECT 1` responde; `False` si `sqlite3.Error`. |

La aplicación depende del protocolo. `SQLiteIncidentRepository` es la implementación concreta.

**Rationale**: ADR-003 y la constitución sitúan los puertos secundarios en `ports.py`. El diseño de H002 nombra estos cinco métodos para que el outbound sea sustituible antes de H004. `@runtime_checkable` permite la verificación pedida con `isinstance` en `tests/test_spec_002_summary.py`.

**Alternatives considered**: Puerto solo con `list_active_incidents` (obliga a romper el protocolo en H003/H004). Clase base abstracta (el proyecto ya eligió `Protocol`). Métodos que devuelven dicts de transporte (filtran el esquema HTTP hacia la aplicación).

## 3. `find_open_duplicates` sin persistir la clave

**Decision**: `find_open_duplicates` permanece en `IncidentRepositoryPort`. H002 no añade `duplicate_group_key` a `Incident` ni a la tabla `incidents`. `SQLiteIncidentRepository` devuelve `[]`. El resumen no llama a este método.

**Rationale**: La spec deja la alerta de duplicados en H003. Añadir la columna sería un cambio de persistencia sin ADR. El esquema heredado de Semana 1 no tiene esa columna. El método cumple el puerto sin inventar una regla de emparejamiento.

**Alternatives considered**: Persistir la clave en `Incident` y filtrar activos por ella (abre H003 y exige ADR). Lanzar `NotImplementedError` (el `isinstance` del protocolo sigue pasando, pero el método no cumple un contrato estable).

## 4. Fábrica y `DATABASE_URL`

**Decision**: `src/adapters/outbound/factory.py` expone `create_incident_repository(database_url: str | None = None) -> IncidentRepositoryPort`. Si el argumento es `None`, lee `DATABASE_URL`; si la variable no existe, usa `sqlite:///:memory:`. La URL debe empezar por `sqlite:///`. El resto es la ruta de `sqlite3`:

- `sqlite:///:memory:` → `:memory:`
- `sqlite:///C:/ruta/incidentes.db` o `sqlite:///./data/incidentes.db` → esa ruta

Cualquier otro esquema, o una variable definida y en blanco, lanza `ValueError` sin repetir el valor crudo de la URL. H002 solo instancia `SQLiteIncidentRepository`.

**Rationale**: La constitución exige intercambiar persistencia por `DATABASE_URL` sin que los inbound construyan el driver. El prefijo `sqlite:///` hace que el default pedido y las rutas de archivo compartan una regla. En Windows la aceptación debe armar la URL con barras POSIX (`Path.as_posix()`), porque `sqlite:///C:/...` sobrevive al `removeprefix`.

**Alternatives considered**: Pasar siempre la ruta de archivo al constructor desde cada inbound (rompe el punto único de selección). Aceptar `postgresql://` en esta fase (es H004 y exigiría un ADR de motor). Usar SQLAlchemy para parsear la URL (dependencia nueva y ORM, prohibidos).

## 5. Ciclo de vida de la conexión SQLite

**Decision**: `create_app()` crea un repositorio y un `IncidentService` al construir la app y los guarda para todas las peticiones. El CLI crea repositorio y servicio una vez por invocación de `summary`. La paridad HTTP/CLI de los tests usa un archivo SQLite, no `:memory:`.

**Rationale**: `:memory:` solo es visible dentro de la conexión que la abrió: dos llamadas a la fábrica no comparten datos, así que el default sirve para un proceso vacío y los tests de paridad necesitan archivo. H002 no fija candado ni `check_same_thread`.

**Alternatives considered**: Abrir una conexión por método (vacía el catálogo en memoria entre peticiones). Una base compartida de desarrollador bajo `data/` (los tests dejarían de ser aislados).

## 6. Caso de uso y modelos de aplicación

**Decision**: `IncidentService` recibe el puerto en `__init__`. `triage_incident` sigue siendo estático y sin repositorio, para no tocar H001. Nuevo método de instancia:

```text
get_active_incidents_summary(
    component_filter: str | None = None,
    reference_time: datetime | None = None,
) -> ActiveIncidentsSummary
```

`ActiveIncidentsSummary` y `ActiveIncidentView` son dataclasses congelados en `src/application/services.py` (o un módulo de aplicación vecino si el archivo crece; no Pydantic). Campos públicos del ítem: `incident_id`, `title`, `component`, `severity`, `status`, `elapsed_minutes`, `requires_escalation`. Los agregados `total_active` y `breached_count` viven en el resumen, no en cada ítem.

Normalización dentro del servicio:

- `component_filter` `None`, vacío o solo espacios → se llama `list_active_incidents(None)`.
- Cualquier otro valor se compara tras `strip`, coincidencia exacta, delegada al puerto.
- `reference_time is None` → `datetime.now()` naive.
- Orden: severidad `P0`→`P3`, luego `elapsed_minutes` descendente, luego `incident_id` ascendente.
- `breached_count` cuenta evaluaciones con `is_breached`. Ese booleano no sale en el ítem de transporte.
- `requires_escalation` se copia de `SLAEvaluation` (ya es falso si está incumplido).

**Rationale**: REST y CLI deben compartir números y orden. Poner el orden y los agregados en el servicio evita dos implementaciones. Mantener `triage_incident` estático preserva los tests H001, que no construyen servicio.

**Alternatives considered**: Ordenar en cada adaptador (rompe FR-008 en cuanto un canal cambie el criterio). Devolver `is_breached` en el JSON (no está en el contrato). Hacer obligatorio el repositorio también para triaje (acopla H001 a la base sin necesidad).

## 7. Parseo de `reference_time`

**Decision**: Función de aplicación `parse_reference_time(raw: str | None) -> datetime | None` usada por FastAPI y Typer antes del caso de uso.

- `None` (parámetro omitido) → `None`; el servicio usa el reloj.
- Cadena vacía, con `tzinfo`, o ilegible para `datetime.fromisoformat` → `ValidationError` (la misma excepción de H001).
- Los instantes de aceptación se envían naive (`2026-11-20T12:00:00`).

HTTP traduce `ValidationError` a `422` con `{"detail": "<mensaje>"}`. CLI escribe el mensaje en stderr, termina con código `1` y no imprime el JSON del resumen. Un instante válido anterior a `created_at` sigue siendo el `ValueError` del dominio; no se reclasifica como 422 porque la spec solo rechaza el instante ilegible.

**Rationale**: Un solo parseador mantiene la paridad. La spec rechaza lo ilegible y el dominio compara instantes naive. Un desplazamiento, incluido `Z`, no pasa `fromisoformat` como naive en Python 3.10 y se rechaza.

**Alternatives considered**: Dejar que FastAPI parsee `datetime` y que el CLI parsee aparte (mensajes distintos). Aceptar `Z` y convertirlo a UTC naive (política de zona que la spec no define). Traducir el `ValueError` de «referencia anterior a la creación» a 422 (amplía el contrato de la spec).

## 8. Adaptadores inbound

**Decision**:

- `ActiveIncidentItem` y `ActiveIncidentsSummaryResponse` en `src/adapters/inbound/api/schemas.py`.
- `GET /api/v1/incidents/summary` con query opcionales `component` y `reference_time` (este último como `str`, para usar el parseador compartido).
- Comando Typer `summary` con `--component` y `--reference-time`.
- Los dos canales serializan `ActiveIncidentsSummaryResponse` construido desde el dataclass de aplicación (`model_dump`) y el CLI lo imprime con `json.dumps`. El CLI puede importar los esquemas del paquete inbound HTTP: siguen siendo transporte, no dominio.
- `GET /health` no llama a `check_health`.

**Rationale**: La spec fija ruta, flags, JSON y códigos. Reutilizar el modelo Pydantic en ambos inbound garantiza las mismas claves. El health de H001 ya tiene contrato y el chequeo real de conectividad es H004; el método queda listo en el puerto.

**Alternatives considered**: Duplicar el dict en el CLI (deriva de claves). Mover los esquemas Pydantic a la aplicación (prohibido por la constitución). Cablear `/health` a `SELECT 1` en este hito (cambia un contrato que la spec declara complementario de H001).

## 9. Esquema SQLite optimizado

**Decision**: La implementación viva en `src/adapters/outbound/sqlite_repository.py`. Al iniciar:

- Crea `sla_policies` e `incidents` como Semana 1, sin columnas nuevas.
- Siembra `sla_policies` desde `SLA_POLICY_TABLE` con `INSERT OR REPLACE` parametrizado.
- Crea `CREATE INDEX IF NOT EXISTS idx_incidents_component_status ON incidents (component, status)`.

`list_active_incidents` con componente:

```sql
SELECT i.incident_id, i.title, i.component, i.severity, i.status,
       i.created_at, i.resolved_at
FROM incidents AS i
INNER JOIN sla_policies AS p ON p.severity = i.severity
WHERE i.status IN ('OPEN', 'IN_PROGRESS')
  AND i.component = ?
```

Sin componente, la misma sentencia sin el predicado `i.component = ?`. No se proyectan columnas de `sla_policies` hacia `Incident`. `save_incident` y `get_incident` van parametrizados. `find_open_duplicates` devuelve `[]`. `seed_synthetic_incidents` permanece en la clase concreta, fuera del protocolo.

**Rationale**: Dos sentencias permiten que el filtro use el índice compuesto `(component, status)` cuando el operador pide un componente. El `JOIN` elimina la consulta por fila. Separar el sembrado masivo del puerto evita que todo adaptador futuro herede el benchmark pedagógico.

**Alternatives considered**: Un único SQL con `(:all = 1 OR component = :component)` (el planificador puede ignorar el índice). Índice solo de `status` (no es el índice pedido). Incluir `max_resolution_minutes` en el `SELECT` y usarlo para el SLA (véase la decisión 1).

## 10. Módulo legado `src/incident_repository.py`

**Decision**: Deja de poseer esquema y de ejecutar el N+1. El benchmark `python -m src.incident_repository` construye `SQLiteIncidentRepository`, siembra con `seed_synthetic_incidents` y mide `list_active_incidents` más `evaluate_sla_status` sobre el componente de demostración. Durante la implementación se actualiza la fila de `AGENTS.md` que hoy documenta la deuda N+1.

**Rationale**: Dos esquemas romperían DRY y dejarían SQL fuera del outbound. La constitución ya ubica la persistencia en el adaptador secundario. Conservar el entrypoint mantiene el comando de Semana 1, ahora sobre el camino optimizado.

**Alternatives considered**: Borrar el módulo y el comando (pierde el benchmark que el repo documenta). Dejar el N+1 intacto junto al adaptador nuevo (segunda fuente de verdad).

## 11. Frontera Ruff

**Decision**: En `pyproject.toml`:

```toml
[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "TID"]
```

Archivos que hacen `extend` del `pyproject.toml` y fijan `TID252` más `TID251`:

| Archivo | `extend` | Módulos prohibidos (`banned-api`) |
| :--- | :--- | :--- |
| `src/domain/ruff.toml` | `../../pyproject.toml` | `fastapi`, `typer`, `pydantic`, `uvicorn`, `sqlite3`, `sqlalchemy`, `httpx`, `src.application`, `src.adapters` |
| `src/application/ruff.toml` | `../../pyproject.toml` | `fastapi`, `typer`, `pydantic`, `uvicorn`, `sqlite3`, `sqlalchemy`, `httpx`, `src.adapters` |
| `src/adapters/inbound/ruff.toml` | `../../../pyproject.toml` | `sqlite3`, `sqlalchemy`, `src.adapters.outbound.sqlite_repository` |

En cada uno:

```toml
[lint.flake8-tidy-imports]
ban-relative-imports = "parents"
```

La forma de tabla `fastapi = { msg = "..." }` es la que acepta Ruff 0.17.6. El mensaje dice la capa y por qué. No se añade `src/adapters/outbound/ruff.toml` en este hito: el skill hexagonal lo deja opcional y el diseño pedido lista solo los tres archivos. Outbound puede importar `sqlite3` y no debe importar inbound; esa última restricción se revisa en código hasta que exista un cuarto `ruff.toml`.

**Rationale**: `select` en la raíz enciende la familia `TID`. Los bans por capa evitan prohibir FastAPI en el inbound. El ensayo de Ruff 0.17.6 mostró que el nombre de paquete cubre submódulos, así que no hace falta enumerar `fastapi.routing` ni cada subpaquete de `src.adapters`.

**Alternatives considered**: Un solo `pyproject.toml` con `per-file-ignores` (más fácil de saltarse y no es la jerarquía pedida). Ban global de `sqlite3` (rompería el outbound y el benchmark). Incluir ya el `ruff.toml` de outbound (fuera de la lista obligatoria de este hito).

## 12. Aceptación automatizada

**Decision**: `tests/test_spec_002_summary.py` contiene exactamente estos tests de escenario, uno por escenario de la spec, más la comprobación del puerto:

| Escenario | Test |
| :--- | :--- |
| 1 Resumen global | `test_bdd_global_summary_excludes_inactive` |
| 2 Filtro por componente | `test_bdd_summary_filtered_by_component` |
| 3 Vacío | `test_bdd_empty_active_summary` |
| 4 Paridad CLI | `test_bdd_cli_summary_matches_http` |
| 5 Instante inválido (HTTP y CLI en el mismo test) | `test_bdd_invalid_reference_time_rejected` |
| Cumplimiento del puerto | `test_sqlite_repository_satisfies_incident_repository_port` |

Cada test de producto usa su propio archivo SQLite (`tmp_path` + `DATABASE_URL`). El catálogo concreto está en [data-model.md](./data-model.md). El Given siembra con `save_incident` sobre esa URL; no hay endpoint de registro. Las fixtures `client` / `cli_runner` de H001 no se reutilizan para el resumen, para que el triaje siga sin base compartida. El test del puerto afirma `isinstance(repo, IncidentRepositoryPort)` sobre una base de archivo vacía.

**Rationale**: El skill BDD pide un `test_bdd_*` por escenario y almacenamiento aislado desde H002. El escenario 5 nombra los dos canales en un solo Then, así que un solo test los cubre. El `isinstance` es la verificación extra que pide el diseño, y no añade un escenario de producto.

**Alternatives considered**: Tests de dominio directos sin HTTP/CLI (no demuestran el contrato del operador). Una base en memoria compartida entre TestClient y CLI (no hay un solo catálogo). Un sexto escenario para duplicados o para `/health` (fuera de la spec).

## 13. Stack y secretos

**Decision**: Cero dependencias nuevas. Consultas parametrizadas. Los errores de configuración no imprimen `DATABASE_URL`. No hay credenciales en ejemplos, contratos ni quickstart.

**Rationale**: Gobierno de la constitución y regla del repo de no ampliar el stack pedagógico sin pedido explícito.

**Alternatives considered**: Driver de terceros, pool, o volcar la URL en el `ValueError` «para depurar».
