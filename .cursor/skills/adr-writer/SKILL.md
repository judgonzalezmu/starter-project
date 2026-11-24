---
name: adr-writer
description: >-
  Write or supersede exactly one immutable append-only Architectural Decision
  Record under docs/adr/ from docs/adr/000-template.md (Estado, Fecha,
  Autor(es), Reemplaza a / Reemplazado por). Require at least two real
  architectural options with authentic advantages and disadvantages; keep
  Mermaid optional and structural only (layers, boundaries, component
  topology). Use when the user asks to write, add, accept, review, or replace
  an ADR, decisión arquitectónica, MADR, or a file in docs/adr/. Do not use
  for spec.md functional or BDD criteria, plan.md file or task lists, or
  tactical command notes.
---

# ADR Writer — IncidentOps

Registro inmutable **append-only** en `docs/adr/`. Antes de redactar, lee
`docs/adr/000-template.md` y copia su esqueleto. Si un título de sección
difiere, gana la plantilla; las prohibiciones de esta skill siguen vigentes.

Cada archivo registra **exactamente 1 sola decisión arquitectónica estructural
y difícil de revertir**. Una decisión nueva es un archivo nuevo. No reescribas
el cuerpo de un ADR ya registrado.

## Cuándo usarla

El cambio mueve fronteras, dirección de dependencias, topología de
persistencia o runtime, y revertirlo obliga a reestructurar el sistema.

No la uses para criterios funcionales o BDD (Given/When/Then) de `spec.md`,
ni para listas de archivos o tareas de `plan.md`. Un ajuste de una regla ya
cerrada (triaje, SLA) referencia el ADR existente; no abre otro archivo para
repetirla.

## Procedimiento

1. Lee la plantilla y solo los encabezados de `docs/adr/*.md` (número, título,
   Estado, Reemplaza a). No uses como molde un ADR anterior a la plantilla
   actual.
2. Formula la decisión en una frase. Si aparecen dos decisiones difíciles de
   revertir, son dos archivos.
3. Toma el siguiente número libre `NNN` (tres dígitos). `000` es la plantilla.
   Ruta: `docs/adr/NNN-titulo-kebab.md`.
4. Fecha `YYYY-MM-DD` de hoy. **Autor(es)**: el que indique el usuario; si no
   lo indica, reutiliza la línea del ADR más reciente. No inventes nombres.
5. Estado inicial: `Propuesto`, salvo que el usuario pida `Aceptado`.
6. Si esta decisión sustituye a otra:
   - En el archivo nuevo, **Reemplaza a**: `ADR-XXX` (parcial o totalmente).
   - En el ADR sustituido, cambia **solo** **Estado** a
     `Reemplazado por ADR-NNN`. No edites contexto, opciones ni decisión.
7. Contrasta el borrador con la lista de prohibiciones antes de cerrarlo.

## Metadatos (los únicos)

```markdown
- **Estado**: Propuesto | Aceptado | Reemplazado por ADR-XXX
- **Fecha**: YYYY-MM-DD
- **Autor(es)**: [Nombre del Ingeniero / Equipo]
- **Reemplaza a**: *(Opcional: `ADR-XXX`, parcial o totalmente)*
```

**Reemplazado por** se escribe en **Estado** (`Reemplazado por ADR-XXX`).
**Reemplaza a** apunta al ADR anterior. No añadas **Componentes Afectados**
ni enlaces a rutas de código.

## Esqueleto

```markdown
# ADR-NNN: [Título corto de la decisión]

- **Estado**: Propuesto
- **Fecha**: YYYY-MM-DD
- **Autor(es)**: ...
- **Reemplaza a**: *(N/A — no sustituye un ADR previo)*

## 1. Contexto y Problema

[Una sola decisión estructural, por qué es difícil de revertir, restricciones vigentes.]

## 2. Opciones Consideradas

1. **Opción A — [Nombre]**:
   - *Ventajas*: ...
   - *Desventajas*: ...
2. **Opción B — [Nombre]**:
   - *Ventajas*: ...
   - *Desventajas*: ...

## 3. Decisión Arquitectónica

[Opción elegida y por qué. Mermaid solo si aporta estructura.]

## 4. Consecuencias y Trade-offs

- **Positivas**: desacoplamiento, mantenibilidad, escalabilidad o portabilidad.
- **Negativas / Trade-offs**: complejidad, restricción operativa o coste de mantenimiento.
```

## Opciones reales

Al menos **2 opciones arquitectónicas reales**, cada una con *Ventajas* y
*Desventajas* auténticas. Una opción cuenta solo si un equipo competente
podría adoptarla en este repositorio.

- La opción rechazada tiene al menos una ventaja real.
- La opción elegida tiene al menos una desventaja real.
- Prohibidas las opciones de relleno o strawmen que nadie sostendría con las
  restricciones ya escritas.

No declares una opción descartada sin escribir sus ventajas y desventajas.

## Mermaid (opcional)

Solo en la sección 3, y solo si clarifica **capas, límites o topología de
componentes** (quién depende de quién). Si no cambia esa lectura, omítelo.

Permitido: nodos de capa o componente y flechas de dependencia.

Prohibido: rombos de decisión, ramas `if/else`, pasos de algoritmo, estados
de un cálculo o secuencias de validación. El diagrama es exclusivamente
estructural; nunca un flujo algorítmico.

## Prohibido en el cuerpo

- Duplicar criterios funcionales o BDD de `spec.md` (Given/When/Then, tablas
  de aceptación, umbrales de negocio). Cita el documento en una frase; no
  copies el criterio.
- Duplicar listas de archivos o tareas de `plan.md` (checklists, orden de
  implementación, rutas como plan de trabajo). Nombrar un paquete está
  permitido cuando el nombre **es** la frontera decidida.
- Viñetas tácticas de comandos (`uv run`, `pytest`, `uvicorn`, shell o
  snippets de implementación).
- Más de una decisión estructural en el mismo archivo.
- Reescribir una decisión ya registrada. El registro es append-only: archivo
  nuevo y, en el anterior, solo el metadato **Reemplazado por**.

## Referencia

`docs/adr/003-arquitectura-hexagonal.md` cumple el estándar (una frontera, dos
opciones defendibles, Mermaid de capas). No lo copies.
`docs/adr/002-calculo-sla-horario-habil.md` es anterior a la plantilla: no
repliques su encabezado, su procedimiento ni su diagrama de flujo.

## Cierre

- [ ] Un archivo nuevo, un número libre, una sola decisión difícil de revertir
- [ ] Metadatos de la plantilla, sin Componentes Afectados
- [ ] Al menos dos opciones reales con ventajas y desventajas auténticas
- [ ] Mermaid ausente, o solo capas, límites o topología
- [ ] Sin criterios de `spec.md`, sin listas de `plan.md`, sin comandos
- [ ] Si sustituye a otro ADR, el anterior solo cambió **Estado** a
      `Reemplazado por ADR-NNN`
