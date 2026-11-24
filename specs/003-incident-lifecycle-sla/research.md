# Research: H003 Ciclo de vida, duplicados y consulta SLA

**Date**: 2026-11-23  
**Spec**: [spec.md](./spec.md)  
**Plan**: [plan.md](./plan.md)

Todas las elecciones técnicas quedan resueltas aquí. No permanece ningún `NEEDS CLARIFICATION`.

Contexto medido en el repo antes de decidir:

- `Incident` hoy: `incident_id`, `title`, `component`, `severity`, `status`, `created_at`, `resolved_at`. Sin `recommended_team` ni `duplicate_group_key` (viven en `TriageResult`).
- `IncidentService` expone `triage_incident` (estático) y `get_active_incidents_summary`. No hay alta persistente ni auditoría SLA por id.
- `IncidentRepositoryPort` ya declara `save_incident`, `get_incident`, `find_open_duplicates`; el adaptador SQLite implementa save/get y **stub** `find_open_duplicates → []` (decisión H002).
- Tabla `incidents` sin columnas de triaje/duplicado; índice solo `(component, status)`.
- `evaluate_sla_status` compara `datetime` directamente: mezclar naive/aware provoca `TypeError`.
- `parse_reference_time` ya rechaza cadenas con `tzinfo` en los adaptadores; H003 debe endurecer el dominio para datos ya persistidos o mezclas internas.
- Equipos canónicos (constitución): `Backend-Core`, `Platform-SRE`, `Data-DBA`, `Security-IAM`.

---

## 1. Extensión de `Incident` y `TeamName`

**Decision**: En `src/domain/models.py`:

```python
TeamName = Literal["Backend-Core", "Platform-SRE", "Data-DBA", "Security-IAM"]

@dataclass
class Incident:
    incident_id: str
    title: str
    component: str
    severity: SeverityLevel
    status: IncidentStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None
    raw_text: str = ""
    recommended_team: Optional[TeamName] = None
    duplicate_group_key: Optional[str] = None
```

`TriageResult.recommended_team` puede tiparse como `TeamName` (compatible con strings actuales del clasificador). No se reabre el consenso de triaje ni se cambian las claves canónicas.

**Rationale**: El encargo H003 exige `recommended_team` y `duplicate_group_key` en la entidad persistida para `find_open_duplicates` y para devolver clasificación tras el alta. `raw_text` forma parte de la entidad registrada (Key Entities / FR-007) y debe sobrevivir al round-trip SQLite; default `""` evita romper semillas H002 que no lo envían. `Optional` en equipo/clave cubre filas heredadas sin clasificación.

**Alternatives considered**: Guardar solo en `TriageResult` sin ampliar `Incident` (imposibilita el índice SQL de FR-009). Hacer `recommended_team`/`duplicate_group_key` obligatorios sin default (rompe catálogo H002 y semillas sintéticas). Persistir `rationale` en `Incident` (útil para auditoría larga, no exigido por los escenarios BDD mínimos; la respuesta de creación lo toma del `TriageResult` en memoria).

## 2. Normalización naive/aware en `sla_calculator`

**Decision**: Añadir helper de dominio `_ensure_comparable_naive(dt: datetime) -> datetime` que, si `dt.tzinfo is not None`, devuelve `dt.replace(tzinfo=None)` (reloj de pared ya acordado por el producto; sin conversión de zona inventada). Al inicio de `evaluate_sla_status`, normalizar `incident.created_at`, `incident.resolved_at` (si hay) y `reference_time` antes de comparar o acumular segundos. **No** cambiar: presupuesto P0/P1 24/7, P2/P3 Lun–Vie `[08:00,18:00)`, truncado único a minutos, umbral 75 %, prioridad `resolved_at`.

**Rationale**: El usuario pide normalización consistente; la constitución fija reloj naive de laboratorio. Strip de `tzinfo` evita `TypeError` sin introducir `zoneinfo` ni alterar ADR-002. Los adaptadores siguen rechazando `reference_time` con offset vía `parse_reference_time`.

**Alternatives considered**: Rechazar cualquier aware con `ValueError` (rompe filas ya guardadas con offset accidental). Convertir a UTC con `astimezone` (impone política de zona que la spec no define). Usar `dateutil` (dependencia nueva).

## 3. Casos de uso de aplicación

**Decision**: En `IncidentService` (instancia con puerto):

### `create_incident(...)` → resultado de creación (dataclass de aplicación, no Pydantic)

Parámetros de negocio: `title`, `raw_text`, opcionales `incident_id`, `created_at`, `status`, `resolved_at`.

Flujo:

1. `strip` de `title` / `raw_text`; vacíos → `ValidationError` (HTTP 422 / CLI 1).
2. `status` omitido → `"OPEN"`; si viene, MUST ∈ catálogo canónico; otro → `ValidationError`.
3. `incident_id` omitido → generar `INC-` + 8 hex **mayúsculas** (`secrets.token_hex(4).upper()`).
4. Si `get_incident(id)` existe → `IncidentAlreadyExistsError` (HTTP 409 / CLI 1); no persistir.
5. `created_at` omitido → `datetime.now()` naive.
6. Si `status == "RESOLVED"`: `resolved_at` omitido → igualar a `created_at`; si `resolved_at < created_at` → `ValidationError`. Si `status != "RESOLVED"`, ignorar `resolved_at` del cliente (no persistir como resuelto).
7. `classify_incident_report(id, raw_text)` → clasificación completa.
8. `find_open_duplicates(triage.duplicate_group_key)` → ids abiertos (excluye el nuevo id por construcción: aún no guardado).
9. Construir `Incident` con campos de triaje + `raw_text`; `save_incident`.
10. Devolver vista: incidente + campos de triaje (`rationale`, `consistency_ratio`, …) + `is_duplicate` + `duplicate_of`.

### `evaluate_incident_sla(incident_id, reference_time: datetime | None)`

1. `get_incident`; `None` → `IncidentNotFoundError`.
2. `evaluated_at = reference_time or datetime.now()`.
3. Si `evaluated_at < incident.created_at` → `ValidationError` (422; no dejar solo el `ValueError` de dominio para el canal).
4. `evaluate_sla_status(incident, evaluated_at)` → `SLAEvaluation` (o proyección mínima de FR-013).

Excepciones nuevas en `services.py`:

| Excepción | Canal |
| :--- | :--- |
| `ValidationError` (existente) | 422 / exit 1 |
| `IncidentNotFoundError` | 404 / exit 1 |
| `IncidentAlreadyExistsError` | 409 / exit 1 |

`IncidentAlreadyExistsError` acompaña a `IncidentNotFoundError` porque FR-004 exige conflicto de identidad distinto de validación genérica; no es un caso de uso aparte.

**Rationale**: Un solo orquestador cumple paridad REST/CLI y la skill hexagonal. El aviso de duplicado **no** bloquea el `save` (FR-010). Validar `reference_time < created_at` en aplicación alinea H003 (422) con el contrato; H002 no exigía ese 422 en el resumen.

**Alternatives considered**: Crear solo en el adaptador HTTP (rompe paridad y hexágono). Devolver 422 también para id inexistente (contradice FR-015). Fusionar 409 en `ValidationError` (difumina el contrato HTTP).

## 4. Duplicados abiertos y SQL

**Decision**: Estados “abiertos” para FR-009: `OPEN`, `IN_PROGRESS`, `ESCALATION_REQUIRED`. `RESOLVED` nunca entra en `duplicate_of`. El id recién creado no aparece (se consulta **antes** del insert, o se filtra por `incident_id <> ?` si se consulta después).

`find_open_duplicates(duplicate_group_key: str) -> list[Incident]`:

```sql
SELECT incident_id, title, component, severity, status,
       created_at, resolved_at, raw_text, recommended_team, duplicate_group_key
FROM incidents
WHERE duplicate_group_key = ?
  AND status IN ('OPEN', 'IN_PROGRESS', 'ESCALATION_REQUIRED')
```

Índice:

```sql
CREATE INDEX IF NOT EXISTS idx_incidents_dup_key
ON incidents (duplicate_group_key, status)
```

`list_active_incidents` (H002) **no** cambia: sigue `OPEN` + `IN_PROGRESS` solamente.

**Rationale**: Constitución y FR-009 fijan el conjunto abierto del aviso. Mezclar ese conjunto con el resumen H002 alteraría SC de Spec 002. El índice pedido acelera el emparejamiento sin N+1.

**Alternatives considered**: Incluir `ESCALATION_REQUIRED` también en el resumen activo (cambia H002). Emular duplicados en Python tras `list_active_incidents` (omite `ESCALATION_REQUIRED` y pierde el índice). Clave inventada en el adaptador (viola núcleo determinista).

## 5. Esquema SQLite y migración suave

**Decision**: Ampliar `CREATE TABLE incidents` con:

| Columna | Tipo | Notas |
| :--- | :--- | :--- |
| `raw_text` | `TEXT NOT NULL DEFAULT ''` | |
| `recommended_team` | `TEXT` | nullable |
| `duplicate_group_key` | `TEXT` | nullable |

Tras `CREATE TABLE IF NOT EXISTS`, intentar `ALTER TABLE ... ADD COLUMN` para cada columna nueva capturando `sqlite3.OperationalError` (bases de archivo ya creadas en demos). `save_incident` / `_incident_from_row` leen y escriben las columnas nuevas. Semillas H002 sin los campos nuevos usan defaults del dataclass.

**Rationale**: Labs y tests crean DB frescas; demos con archivo previo no deben romper al arrancar. Sin ORM ni migraciones externas (constitución / ADR-001 citado).

**Alternatives considered**: Borrar siempre la DB al arrancar (destructivo). Exigir migración manual documentada solamente (frágil en Windows labs).

## 6. Contratos inbound (REST + CLI)

**Decision**:

| Transporte | Pieza |
| :--- | :--- |
| Pydantic | `CreateIncidentRequest`, `IncidentCreatedResponse`, `SLAEvaluationResponse` en `schemas.py` |
| HTTP | `POST /api/v1/incidents` → 201; `GET /api/v1/incidents/{incident_id}/sla` → 200 |
| Typer | `create` (`--title`, `--raw-text`, opcionales `--incident-id`, `--created-at`, `--status`, `--resolved-at`); `sla` (`--incident-id`, opcional `--reference-time`) |
| Mapeo errores | `ValidationError`→422/1; `IncidentNotFoundError`→404/1; `IncidentAlreadyExistsError`→409/1 |

Ambos canales obtienen el repo solo vía `create_incident_repository()` / `DATABASE_URL`. Invocan **exactamente** `IncidentService.create_incident` y `IncidentService.evaluate_incident_sla` (sin lógica de negocio local). `reference_time` / `created_at` / `resolved_at` de entrada se parsean con la **misma política naive** en aplicación: reutilizar `parse_reference_time` o un helper gemelo (`parse_optional_naive_datetime`) que rechaza vacío, tz-aware e ilegible con `ValidationError`; los adaptadores no implementan un parseo divergente.

Orden de rutas FastAPI: registrar `POST /api/v1/incidents` y `GET .../sla` de modo que no capturen `GET /api/v1/incidents/summary` ni `POST .../triage` existentes (rutas literales ya distintivas).

**Rationale**: Spec fija superficies; skill hexagonal exige paridad y factory. Reutilizar parseo evita divergencia H002/H003.

**Alternatives considered**: Lógica de duplicados en el router (prohibido). CLI que llame HTTP local (acopla canales y complica tests aislados).

## 7. Generación `INC-<HEX8>`

**Decision**: Prefijo literal `INC-` + exactamente 8 caracteres hexadecimales en **mayúsculas** (`A-F0-9`), vía `secrets.token_hex(4).upper()`. Si colisiona (extremadamente raro en lab), el `get_incident` previo al save ya cubre el caso 409 cuando el cliente envía id; para autogenerados, reintentar una vez o confiar en el espacio 2^32 (aceptable en laboratorio). Preferencia: un solo intento; si colisiona, `IncidentAlreadyExistsError` (el operador reintenta).

**Rationale**: Spec deja mayúsculas/minúsculas a planificación; mayúsculas alinean con ids de muestra `INC-1001` en espíritu visual. `secrets` es stdlib criptográficamente razonable sin deps.

**Alternatives considered**: `uuid4().hex[:8]` (mismo resultado práctico). Contador secuencial (requiere estado global en DB).

## 8. Aceptación BDD

**Decision**: Nuevo módulo `tests/test_spec_003_lifecycle_sla.py` con exactamente:

| Escenario spec | Test |
| :--- | :--- |
| 1 Registro 201 sin duplicados | `test_bdd_create_incident_201_without_duplicates` |
| 2 Duplicado abierto 201 | `test_bdd_create_detects_open_duplicate` |
| 3 SLA P2 hábil 120/480/360 | `test_bdd_sla_p2_business_hours_elapsed_120` |
| 4 404 y 422 SLA | `test_bdd_sla_not_found_and_reference_before_created` |
| 5 Paridad CLI create/sla | `test_bdd_cli_create_and_sla_parity` |

Cada test usa SQLite de archivo en `tmp_path` + `DATABASE_URL` (mismo patrón H002). Escenario 5 comparte almacén entre HTTP (seed/create) y CLI solo si hace falta el mismo id; en la práctica: crear vía CLI y auditar vía CLI tras seed HTTP del P2, o ambos sobre la misma URL. No reutilizar el `client` de sesión H001 sin aislar DB.

Textos de reporte: reutilizar `sample_incidents` (p. ej. INC-1001 / pagos 502) para claves de duplicado estables.

**Rationale**: Skill `bdd-acceptance` exige 1:1 `test_bdd_*`, drivers inbound y almacén aislado.

**Alternatives considered**: Tests unitarios solo de servicio (no demuestran contrato de operador). Un único test monolítico (rompe trazabilidad Given/When/Then).

## 9. Compatibilidad H001/H002 y frontera Ruff

**Decision**: No tocar contratos de `triage` ni `summary`. Ampliar `_incident_from_row` / semillas con defaults para columnas nuevas. Fixtures H002 que construyen `Incident(...)` siguen válidas gracias a defaults. Ruff: sin cambios de bans salvo que un import nuevo viole TID; verificar `uv run ruff check src/` al implementar. Dominio sigue sin `sqlite3`/`fastapi`; aplicación sin `src.adapters`; inbound sin `sqlite_repository` concreto.

**Rationale**: Constitución + skill hexagonal. Regresión es gate de merge.

**Alternatives considered**: Refactorizar H002 a incluir `ESCALATION_REQUIRED` en activos (fuera de alcance). Relajar bans Ruff (rechazado).

## 10. Stack y secretos

**Decision**: Cero dependencias nuevas. SQL parametrizado. Errores de fábrica no echoan `DATABASE_URL`. Sin credenciales en contratos/quickstart.

**Rationale**: Gobierno de la constitución y política del repo.

**Alternatives considered**: ORM, pool, o loguear la URL “para depurar”.
