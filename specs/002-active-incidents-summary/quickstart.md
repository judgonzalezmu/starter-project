# Quickstart: validar H002

Guía de comprobación del resumen de incidentes activos. El detalle de campos está en [data-model.md](./data-model.md) y en [contracts/](./contracts/). Aquí no está la implementación.

## Prerequisites

Desde la raíz del repo, con Python ≥ 3.10:

```bash
uv sync --group dev
```

Variable opcional:

```text
DATABASE_URL=sqlite:///:memory:
```

Si no existe, la fábrica usa ese default. Una base en memoria nace vacía en cada proceso. Para una consulta manual con datos, apunta la variable a un archivo, por ejemplo `sqlite:///./data/incidentops-h002.db` (barras `/`, también en Windows).

## 1. Frontera hexagonal

```bash
uv run ruff check src/
```

Resultado esperado: sin hallazgos. La configuración que debe estar presente:

- `pyproject.toml`: `[tool.ruff.lint]` con `select = ["E4", "E7", "E9", "F", "TID"]`.
- `src/domain/ruff.toml`, `src/application/ruff.toml` y `src/adapters/inbound/ruff.toml` hacen `extend` hacia `pyproject.toml`, prohíben imports de padres (`TID252`) y declaran `banned-api` (`TID251`) de la capa.

## 2. Aceptación BDD y puerto

```bash
uv run pytest -v tests/test_spec_002_summary.py
uv run pytest -v
```

Resultado esperado del primer comando: los cinco `test_bdd_*` y `test_sqlite_repository_satisfies_incident_repository_port` en verde.

Cada escenario de producto usa su propio archivo SQLite bajo el `tmp_path` de pytest y siembra el catálogo de [data-model.md](./data-model.md) con el puerto (`save_incident`), no con un endpoint de registro.

| Test | Qué queda demostrado |
| :--- | :--- |
| `test_bdd_global_summary_excludes_inactive` | `200`, 5 activos, 1 incumplido, sin `RESOLVED` ni `ESCALATION_REQUIRED`, orden `INC-A` … `INC-Z`, `INC-B` con escalamiento |
| `test_bdd_summary_filtered_by_component` | `component=payments-gateway` → 2 activos, 1 incumplido, solo ese componente |
| `test_bdd_empty_active_summary` | `200` con ceros y `incidents=[]` |
| `test_bdd_cli_summary_matches_http` | Mismo archivo, mismos argumentos, mismo JSON parseado, exit `0` |
| `test_bdd_invalid_reference_time_rejected` | HTTP `422` y CLI exit `1`, sin resumen |
| `test_sqlite_repository_satisfies_incident_repository_port` | `isinstance(repo, IncidentRepositoryPort)` |

La segunda orden de pytest incluye la regresión de H001 (triaje sin persistencia).

## 3. Núcleo de dominio (no debe cambiar de política)

```bash
uv run python -m src.domain.triage_rules
uv run python -m src.domain.sla_calculator
```

Siguen siendo las verificaciones deterministas de Semana 1 / ADR-002.

## 4. Consulta manual

Con la app y el CLI ya implementados, y un archivo sembrado con el catálogo de aceptación:

```bash
uv run uvicorn src.adapters.inbound.api.app:create_app --factory --reload
```

```text
GET /api/v1/incidents/summary?reference_time=2026-11-20T12:00:00
GET /api/v1/incidents/summary?component=payments-gateway&reference_time=2026-11-20T12:00:00
GET /health
```

Resultados esperados: el JSON global y el filtrado de [contracts/http-get-incidents-summary.md](./contracts/http-get-incidents-summary.md), y `{"status": "ok"}` en health.

CLI sobre la misma `DATABASE_URL` de archivo:

```bash
uv run python -m src.adapters.inbound.cli summary --reference-time 2026-11-20T12:00:00
uv run python -m src.adapters.inbound.cli summary --component payments-gateway --reference-time 2026-11-20T12:00:00
uv run python -m src.adapters.inbound.cli summary --reference-time manana
```

Los dos primeros terminan en `0` y su stdout parseado coincide con el HTTP. El tercero termina en `1` y no imprime el resumen.

Instante omitido: la consulta responde `200` / exit `0` usando el reloj real; los minutos no son comparables con la tabla fija. La aceptación determinista siempre envía `2026-11-20T12:00:00`.
