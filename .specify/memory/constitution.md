<!--
Sync Impact Report
- Version change: (unversioned template) → 1.0.0
- Modified principles:
  - [PRINCIPLE_1_NAME] → I. Deterministic Domain Nucleus (NON-NEGOTIABLE)
  - [PRINCIPLE_2_NAME] → II. Strict Hexagonal Architecture (ADR-003)
  - [PRINCIPLE_3_NAME] → III. Technical Governance and Quality Gates
  - [PRINCIPLE_4_NAME] / [PRINCIPLE_5_NAME] → consolidated into the three
    IncidentOps pillars (user-specified count) plus dedicated invariant /
    precedence sections below
- Added sections:
  - Domain Business Invariants
  - Conflict Precedence and Compliance
- Removed sections: N/A (initial formal adoption from Spec Kit scaffold)
- Follow-up TODOs:
  - TODO(ADR-001): Persistence rule cites ADR-001 (SQLite3 stdlib, no heavy
    ORMs), but `docs/adr/` currently has no `001-*.md` file — author or locate
    that ADR so the citation resolves.
  - `docs/constitution.md` remains an informal mirror; Spec Kit official source
    of truth is this file (alignment of the docs copy is out of scope here).
-->

# IncidentOps Constitution

## Core Principles

### I. Deterministic Domain Nucleus (NON-NEGOTIABLE)

Business rules MUST live exactly once in the domain nucleus under `src/domain/`,
in `models.py`, `triage_rules.py`, and `sla_calculator.py`. Adapters (REST, CLI,
future MCP, persistence, or any other channel) MUST NOT reimplement triage, SLA
evaluation, lifecycle states, or duplicate grouping. Domain modules MUST remain
pure: no FastAPI, Typer, Pydantic transport schemas, SQL drivers, or other
infrastructure imports. Product requirements MUST NOT be invented outside this
constitution, `docs/ROADMAP.md`, or accepted ADRs.

**Rationale**: One deterministic core keeps Spec 001 and ADR-002 contracts
identical across every delivery surface and prevents divergent severity, team
routing, or SLA behavior.

### II. Strict Hexagonal Architecture (ADR-003)

Dependency direction MUST point inward toward the domain. Inbound and outbound
adapters depend on application and domain; the domain MUST NOT import adapters,
frameworks, or persistence details.

| Layer | Location | Role |
| :--- | :--- | :--- |
| Domain | `src/domain/` | Pure models and policies (triage, SLA, duplicates); no external imports. |
| Application | `src/application/` | Shared use cases in `services.py`; secondary ports in `ports.py` (`typing.Protocol`). |
| Inbound | `src/adapters/inbound/` | Primary adapters: FastAPI (REST) and Typer (CLI); MUST stay ready for a future MCP adapter without duplicating use-case logic. |
| Outbound | `src/adapters/outbound/` | Secondary adapters for persistence and infrastructure; MUST be interchangeable via `DATABASE_URL`. |

Roadmap use cases (classify without persisting, list actives, register with open-duplicate alert, audit SLA at a reference instant) MUST be exposed through application services, not reimplemented per channel.

**Rationale**: The product needs multiple consumers and evolving persistence
(H001–H004). Hexagonal edges keep frameworks and storage substitutable around a
stable core.

### III. Technical Governance and Quality Gates

| Area | Norm |
| :--- | :--- |
| Runtime | Python **≥ 3.10**, managed with **`uv`**. |
| REST | **FastAPI** + **Pydantic v2** only in inbound adapters; never in domain. |
| CLI | **Typer** only in inbound adapters. |
| Persistence | **SQLite3** from the Python stdlib, **without heavy ORMs**, per **ADR-001**, until a dedicated ADR authorizes another engine. Outbound persistence MUST remain swappable through **`DATABASE_URL`**. |
| Hexagonal lint | Static boundary verification with Ruff is mandatory: `uv run ruff check src/` MUST pass. |
| Specification | Acceptance scenarios MUST use BDD form (`Given` / `When` / `Then`). |
| Tests | Automated acceptance is mandatory via `uv run pytest -v`. Domain and application MUST be verifiable without starting the web stack or a real database when the scenario allows. |
| Secrets | Credentials and secrets MUST NOT be hardcoded in source, docs, logs, or examples. |
| Structural decisions | Material structural or persistence changes MUST be recorded as ADRs using `docs/adr/000-template.md`. |

**Rationale**: A fixed pedagogical stack plus enforceable gates (Ruff frontiers,
BDD pytest) prevent silent erosion of hexagonal boundaries and domain purity.

## Domain Business Invariants

These invariants are non-negotiable contracts of the deterministic nucleus. Changes
require an explicit constitution amendment and, when structural, an ADR.

| Topic | Invariant |
| :--- | :--- |
| Severity | `P0` \| `P1` \| `P2` \| `P3` (`Literal`, not Enum). Triage by **impact/scope**, not loose keywords. |
| SLA (ADR-002) | P0/P1: **24/7**. P2/P3: business hours **Mon–Fri `[08:00, 18:00)`**. Accumulate seconds and truncate to minutes **once**. |
| Escalation | **75%** budget threshold only if the incident is **not** `RESOLVED` and **not** `breached`. |
| Instants | `resolved_at` takes priority over `reference_time` when evaluating SLA. |
| States | `OPEN`, `IN_PROGRESS`, `ESCALATION_REQUIRED`, `RESOLVED`. |
| Teams | Only: `Backend-Core`, `Platform-SRE`, `Data-DBA`, `Security-IAM`. |
| Duplicates | Canonical `duplicate_group_key` lives in domain (e.g. payments 502, large-dataset); external layers MUST NOT invent parallel keys. |

## Conflict Precedence and Compliance

On conflict, **this constitution and accepted ADRs** (including domain contracts)
prevail over adapters, operational docs, and informal notes. Runtime agent map:
`AGENTS.md`. Product milestones: `docs/ROADMAP.md`. Structural decisions:
`docs/adr/`.

Compliance review expectations:

- Pull requests that touch domain, application, or adapters MUST verify
  dependency direction (adapters → application → domain).
- Reviewers MUST confirm domain purity (no framework/SQL imports in
  `src/domain/`).
- Merges that affect triage, SLA, ports, or adapters MUST leave
  `uv run ruff check src/` and `uv run pytest -v` green.
- Complexity that bypasses ports, duplicates use cases per channel, or hardcodes
  persistence engines MUST be rejected unless justified by a new ADR and a
  constitution amendment when governance rules change.

## Governance

This constitution supersedes conflicting project practices for IncidentOps
governance. Amendments MUST:

1. Update `.specify/memory/constitution.md` with declarative, testable rules.
2. Bump **Version** using semantic versioning:
   - **MAJOR**: backward-incompatible removal or redefinition of principles.
   - **MINOR**: new principle/section or materially expanded guidance.
   - **PATCH**: clarifications, wording, or non-semantic refinements.
3. Keep **Ratified** as the original adoption date; set **Last Amended** to the
   amendment date (`YYYY-MM-DD`).
4. Record structural follow-through in ADRs when the change alters architecture,
   persistence, or domain calculation policy.

Guidance for day-to-day implementation remains in `AGENTS.md`; this document
defines non-negotiable rules those guides MUST NOT contradict.

**Version**: 1.0.0 | **Ratified**: 2026-11-23 | **Last Amended**: 2026-11-23
