# Constitución — IncidentOps

Principios e invariantes del proyecto. Complementa `AGENTS.md` (mapa operativo para
agentes), `docs/ROADMAP.md` (hitos de producto) y los ADRs (decisiones estructurales).
Ante conflicto: **dominio y ADRs aceptados** prevalecen sobre adaptadores y docs
operativas.

---

## 1. Dominio determinista único

Las reglas de negocio viven **una sola vez** en el núcleo de dominio. Adaptadores
(REST, CLI, futuro MCP, BD) **no** reimplementan triaje, SLA, estados ni duplicados.

| Tema | Invariante |
| :--- | :--- |
| Severidad | `P0` \| `P1` \| `P2` \| `P3` (`Literal`, no Enum). Triaje por **impacto/alcance**, no por keywords sueltas. |
| SLA (ADR-002) | P0/P1: **24/7**. P2/P3: horario hábil **L–V `[08:00, 18:00)`**. Acumular segundos y truncar a minutos **una sola vez**. |
| Escalamiento | Umbral **75%** del presupuesto solo si el incidente **no** está `RESOLVED` y **no** está `breached`. |
| Instantes | `resolved_at` tiene prioridad sobre `reference_time` al evaluar SLA. |
| Estados | `OPEN`, `IN_PROGRESS`, `ESCALATION_REQUIRED`, `RESOLVED`. |
| Equipos | Solo: `Backend-Core`, `Platform-SRE`, `Data-DBA`, `Security-IAM`. |
| Duplicados | `duplicate_group_key` canónica en dominio (p. ej. pagos 502 y large-dataset); capas externas no inventan claves paralelas. |

No inventar requisitos de negocio fuera de esta constitución, el roadmap o ADRs.

---

## 2. Arquitectura Hexagonal (ADR-003)

Dirección de dependencias: **hacia el núcleo**. El dominio no importa frameworks ni SQL.

| Capa | Ubicación | Rol |
| :--- | :--- | :--- |
| Dominio | `src/domain/` | Modelos y políticas puras (triaje, SLA, duplicados). |
| Aplicación | `src/application/` | Casos de uso compartidos (p. ej. `IncidentService`) y **puertos secundarios** (`typing.Protocol`). |
| Inbound | `src/adapters/inbound/` | Primarios: **API REST** y **CLI**; el núcleo queda listo para un futuro adaptador **MCP** sin duplicar lógica. |
| Outbound | `src/adapters/outbound/` | Secundarios **intercambiables** (persistencia y otros detalles de infraestructura). |

Casos de uso del roadmap (clasificar sin persistir, consultar activos, registrar con
alerta de duplicado abierto, auditar SLA en un instante) se exponen **vía aplicación**,
no por canal.

---

## 3. Gobernanza técnica y calidad

| Área | Norma |
| :--- | :--- |
| Runtime | Python **≥ 3.10**, gestión con **`uv`**. |
| REST | **FastAPI** + **Pydantic v2** (solo en adaptador inbound; no en dominio). |
| CLI | **Typer** (adaptador inbound). |
| Persistencia | **SQLite3** de la stdlib, **sin ORMs pesados**. Cualquier cambio de motor de BD exige **ADR previo**. |
| Especificación | Escenarios **BDD** en forma `Given / When / Then`. |
| Pruebas | Aceptación automatizada con **`pytest`**; dominio/aplicación verificables sin levantar web ni BD real cuando el caso lo permita. |
| Secretos | Prohibido hardcodear credenciales o secretos. |
| Decisiones | Cambios estructurales → ADR (plantilla MADR en `docs/adr/000-template.md`). |

El layout plano actual bajo `src/` es el punto de partida; la constitución define el
**destino** alineado con ADR-003, no un inventario táctico de migraciones.
