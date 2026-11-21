# AGENTS.md — IncidentOps (Semana 1 / ISIA)

## Qué es este repo

Backend Python de **IncidentOps** (gestión de incidentes, triaje y SLA) usado como laboratorio de *AI for Software Engineering*. Gestionado con **`uv`**, Python **3.10+**.

## Mapa rápido

| Ruta | Rol |
| :--- | :--- |
| `src/models.py` | Tipos de dominio (`Incident`, `SLARule`, `TriageResult`, …) |
| `src/triage_rules.py` | Clasificación determinista + equipo + `duplicate_group_key` |
| `src/sla_calculator.py` | SLA 24/7 (P0/P1) vs. horario hábil Lun–Vie `[08:00,18:00)` (P2/P3); ADR-002 |
| `src/context_audit.py` | Auditoría de tokens (`tiktoken`) — fuerza bruta / grep / LSP |
| `src/incident_repository.py` | SQLite + benchmark (deuda N+1 intencional en demos) |
| `data/sample_incidents.json` | 10 incidentes de prueba de triaje |
| `docs/adr/` | ADRs (`000-template.md`, `002-calculo-sla-horario-habil.md`) |
| `CONTEXT_LOG.md` | Bitácora de prompts / context engineering del estudiante |

## Comandos canónicos

```bash
uv sync
uv run python -m src.triage_rules
uv run python -m src.sla_calculator
uv run python -m src.context_audit --symbol evaluate_sla_status
uv run python -m src.context_audit --symbol classify_incident_report
uv run python -m src.context_audit --compare-formats
uv run python -m src.incident_repository
```

## Convenciones para agentes

1. **No inventar requisitos de negocio** sin evidencia del repo, ADR o bitácora.
2. Preferir **código determinista** para SLA y reglas de triaje ya estabilizadas; LLM solo para exploración/ADR o patrones abiertos no cubiertos.
3. Mantener **cero dependencias nuevas** salvo que el usuario lo pida; SLA/triaje usan stdlib.
4. Respetar contratos existentes: `SeverityLevel` es `Literal["P0","P1","P2","P3"]` (no Enum); `resolved_at` tiene prioridad sobre `reference_time`.
5. Commits (si se piden): `prefijo [modulo]: descripcion` (`feat`, `fix`, `docs`, …).
6. No hardcodear secretos ni credenciales.
7. Tras cambiar triaje/SLA, verificar con los módulos `__main__` de arriba.

## Decisiones ya tomadas (no reabrir sin pedido)

- **Triaje**: severidad por impacto (no keywords sueltas); equipos `Backend-Core`, `Platform-SRE`, `Data-DBA`, `Security-IAM`; duplicados canónicos pagos 502 y large-dataset.
- **SLA (ADR-002)**: recorrido día a día + clipping `[08:00,18:00)`; acumular segundos y truncar minutos una sola vez; escalation 75% solo si no `RESOLVED` y no `breached`.
