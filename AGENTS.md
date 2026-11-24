# AGENTS.md — IncidentOps (Semana 1 / ISIA)

## Qué es este repo

Backend Python de **IncidentOps** (gestión de incidentes, triaje y SLA) usado como laboratorio de *AI for Software Engineering*. Gestionado con **`uv`**, Python **3.10+**. Layout hexagonal (ADR-003): dominio puro, casos de uso en aplicación, adaptadores inbound REST/CLI.

## Mapa rápido

| Ruta | Rol |
| :--- | :--- |
| `src/domain/models.py` | Tipos de dominio (`Incident`, `SLARule`, `TriageResult`, …) |
| `src/domain/triage_rules.py` | Clasificación determinista + equipo + `duplicate_group_key` |
| `src/domain/sla_calculator.py` | SLA 24/7 (P0/P1) vs. horario hábil Lun–Vie `[08:00,18:00)` (P2/P3); ADR-002 |
| `src/application/services.py` | Casos de uso (`triage_incident`, `create_incident`, `evaluate_incident_sla`, `get_active_incidents_summary`) |
| `src/adapters/inbound/api/` | FastAPI: triage, `POST /api/v1/incidents`, `GET .../sla`, summary, `/health` |
| `src/adapters/inbound/cli.py` | Typer: `triage`, `create`, `sla`, `summary`, `audit` |
| `src/context_audit.py` | Auditoría de tokens (`tiktoken`) — fuerza bruta / grep / LSP |
| `src/incident_repository.py` | Entrypoint del benchmark; delega en `SQLiteIncidentRepository` (JOIN, sin N+1) |
| `data/sample_incidents.json` | 10 incidentes de prueba de triaje |
| `specs/001-triage-endpoint-manual.md` | Aceptación H001 (triaje multi-interfaz) |
| `docs/adr/` | ADRs (`000-template.md`, `002-…`, `003-arquitectura-hexagonal.md`) |
| `CONTEXT_LOG.md` | Bitácora de prompts / context engineering del estudiante |
| `tests/` | Aceptación BDD Spec 001 (`pytest`) |

## Comandos canónicos

```bash
uv sync --group dev
uv run python -m src.domain.triage_rules
uv run python -m src.domain.sla_calculator
uv run uvicorn src.adapters.inbound.api.app:create_app --factory --reload
uv run python -m src.adapters.inbound.cli triage --incident-id INC-1001 --raw-text "..."
uv run python -m src.adapters.inbound.cli create --title "..." --raw-text "..."
uv run python -m src.adapters.inbound.cli sla --incident-id INC-... --reference-time 2026-11-09T09:00:00
uv run pytest
uv run pytest -v tests/test_spec_003_lifecycle_sla.py
uv run python -m src.context_audit --symbol evaluate_sla_status
uv run python -m src.context_audit --symbol classify_incident_report
uv run python -m src.context_audit --compare-formats
uv run python -m src.incident_repository
```

## Convenciones para agentes

1. **No inventar requisitos de negocio** sin evidencia del repo, ADR, constitución o specs.
2. Preferir **código determinista** para SLA y reglas de triaje ya estabilizadas; LLM solo para exploración/ADR o patrones abiertos no cubiertos.
3. **Stack H001** en adaptadores: FastAPI, Pydantic v2, Typer, uvicorn; dominio/aplicación sin frameworks. No añadir más dependencias salvo pedido explícito.
4. Respetar contratos existentes: `SeverityLevel` es `Literal["P0","P1","P2","P3"]` (no Enum); `resolved_at` tiene prioridad sobre `reference_time`.
5. Commits (si se piden): `prefijo [modulo]: descripcion` (`feat`, `fix`, `docs`, …).
6. No hardcodear secretos ni credenciales.
7. Tras cambiar triaje/SLA, verificar con `python -m src.domain.triage_rules`, `python -m src.domain.sla_calculator` y `pytest`.
8. Dirección de dependencias: adaptadores → application → domain; el dominio no importa FastAPI/Typer/SQL.

## Decisiones ya tomadas (no reabrir sin pedido)

- **Triaje (Spec 001)**: severidad por impacto (no keywords sueltas); equipos `Backend-Core`, `Platform-SRE`, `Data-DBA`, `Security-IAM`; pagos 502 → `Backend-Core` / `payments-gateway:http-502-outage`; cuenta individual bloqueada → `P2` / `Security-IAM` ("hoy" no eleva a P0); duplicado large-dataset canónico en dominio.
- **SLA (ADR-002)**: recorrido día a día + clipping `[08:00,18:00)`; acumular segundos y truncar minutos una sola vez; escalation 75% solo si no `RESOLVED` y no `breached`.
- **Arquitectura (ADR-003)**: hexagonal; H001 expone triaje sin persistencia vía API y CLI.
