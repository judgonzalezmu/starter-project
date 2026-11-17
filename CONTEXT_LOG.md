# Bitácora de Ingeniería de Prompts y Contexto — Semana 1 (`CONTEXT_LOG.md`)

**Estudiante(s)**: `Juan David González Muñoz`  
**Fecha**: `2026-11-17`  
**Modelos / Asistentes Utilizados**: `GPT 6.1 -sol`

---

## 1. De Prompts Pobres a Técnicas Clásicas de *Prompt Engineering* (Reto 1: `src/triage_rules.py`)

### 1.1 Diagnóstico de un Prompt Pobre y Ambiguo
Analiza el siguiente prompt deficiente para el Reto 1:
> *"El archivo `triage_rules.py` funciona mal con algunos tickets del JSON. Agrégale el equipo recomendado y una clave para duplicados, y no pongas P0 cuando no sea urgente."*

Documenta al menos **3 modos de fallo o ambigüedades** de este prompt (p. ej., ausencia de contexto de dominio, restricciones negativas difusas, falta de enumeración de equipos válidos o ausencia de ejemplos canónicos):
1. **Falta de especificidad y claridad (Claude: “Sé explícito y claro” / “Sé específico”)**: el prompt dice que `triage_rules.py` “funciona mal con algunos tickets del JSON”, pero no identifica cuáles (`INC-1002`, `INC-1007`, `INC-1009`, etc.), qué salida incorrecta producen hoy ni cuál es el resultado esperado (severidad, componente, equipo, clave de duplicados). Sin requisitos ni estructura de salida explícitos, el modelo debe adivinar el alcance.
2. **Restricción negativa difusa sin contexto ni motivación (Claude: “Proporciona contexto” y “dile qué HACER, no qué NO hacer”)**: la frase “no pongas P0 cuando no sea urgente” es una negación vaga: no define qué cuenta como *urgente* (¿caída global? ¿palabra “hoy”? ¿IDOR?), no justifica el *porqué* de la regla de negocio y no ofrece criterios positivos de asignación `P0`/`P1`/`P2`/`P3`, lo que invita a interpretaciones inconsistentes.
3. **Ausencia de ejemplos canónicos y de enumeración de valores válidos (Claude: “Usa ejemplos” / few-shot)**: no hay ejemplos one-shot/few-shot de clasificación correcta, ni lista cerrada de equipos (`Backend-Core`, `Platform-SRE`, `Data-DBA`, `Security-IAM`), ni convención para `duplicate_group_key` (p. ej. agrupar `INC-1001`/`INC-1006` y `INC-1003`/`INC-1008`). Sin ejemplos ni catálogo, el formato y el criterio de duplicados quedan abiertos a alucinación.

### 1.2 Uso de *Self-Consistency*, *Chain-of-Thought* y *Few-Shot Prompting*
- ¿Cómo utilizaste *Chain-of-Thought* (`<analysis>`) y *Self-Consistency* (múltiples consultas independientes) para definir las reglas de clasificación de los casos ambiguos (`INC-1002`, `INC-1007`, `INC-1009`) y la agrupación de duplicados (`INC-1001`/`INC-1006` e `INC-1003`/`INC-1008`)?

Ejecuté el mismo prompt con los 10 incidentes en dos chats nuevos e independientes (modo rápido y modo thinking), pidiendo razonamiento por alcance, riesgo y duplicados. Ninguno expuso cadena privada en `<analysis>`, pero ambos justificaron por impacto real. Self-Consistency: coincidencia total en severidades y pares duplicados. Consenso: `INC-1001`/`INC-1006` → P0 pagos 502; `INC-1002` → P3 (bloqueo individual, “hoy” no eleva); `INC-1003`/`INC-1008` → P2 rendimiento con >10k registros; `INC-1007` → P0 IDOR cross-tenant; `INC-1009` → P2 (export lenta pero completa). Solo divergieron los nombres de `duplicate_group_key`, no la agrupación.

- Copia el prompt mejorado que empleaste aplicando las técnicas clásicas (`<role>`, `<domain_rules>` con justificación del *porqué*, `<examples>` *Few-Shot* y `<task>`):

```xml
<role>
Eres un analista de triaje de IncidentOps. Clasificas reportes en lenguaje natural
asignando severity (P0-P3), component, recommended_team y duplicate_group_key.
Equipos válidos: Backend-Core, Platform-SRE, Data-DBA, Security-IAM.
</role>

<domain_rules>
- Severidad por impacto real, no por palabras sueltas ("urgente", "hoy"):
  P0 = indisponibilidad general o exposición crítica activa (p. ej. IDOR cross-tenant).
  P1 = degradación grave o riesgo inmediato (p. ej. pool DB al 94% con timeouts).
  P2 = impacto limitado con servicio aún usable (latencia / exportación lenta).
  P3 = mejora cosmética, caso individual o mantenimiento preventivo.
- Por qué: las heurísticas por keyword generan falsos P0 (INC-1002, INC-1009) y omiten
  P0 de seguridad (INC-1007) cuando no aparece "urgente"/"502".
- Duplicados: misma causa raíz / mismo síntoma operativo → mismo duplicate_group_key
  (p. ej. pagos 502; consultas lentas con >10k registros).
</domain_rules>

<examples>
<!-- Few-Shot canónico derivado del consenso rápido + thinking -->
INC-1001/INC-1006 → P0, payments-gateway, Platform-SRE, PAYMENTS-502-GATEWAY
INC-1002 → P3, auth-identity, Security-IAM (bloqueo de un usuario; "hoy" no eleva)
INC-1003/INC-1008 → P2, reporting-api, Backend-Core, LARGE-DATASET-REPORT-PERFORMANCE
INC-1007 → P0, reporting-api, Security-IAM (IDOR company_id entre tenants)
INC-1009 → P2, reporting-api, Backend-Core (Excel ~20s pero completa; no P0)
</examples>

<task>
Razona primero en <analysis> sobre alcance, riesgo y duplicados. Luego clasifica cada
incidente y devuelve: id | severity | component | recommended_team | duplicate_group_key | rationale.
</task>
```

---

## 2. Flujo Explorar $\rightarrow$ Destilar $\rightarrow$ Ejecutar en Contexto Limpio (Reto 2: Cálculo de SLA en Horario Hábil y ADR-002)

### 2.1 Exploración de Diseño (Sin Generar Código Aún) y Destilación
- **Objetivo explorado**: Diseño del algoritmo de cálculo de SLA en horario hábil (`P2`/`P3`, Lunes–Viernes 08:00–18:00) vs. 24/7 (`P0`/`P1`) y regla de escalamiento preventivo al 75%.
- **Síntesis de tu exploración de alternativas y resumen destilado (máx. 10 líneas)**:
  > Problema: `evaluate_sla_status` ignora `operates_24x7`: P0/P1 deben seguir 24/7; P2/P3 solo cuentan lunes–viernes de 08:00 a 18:00.
  > Casos clave: viernes 18:30 → lunes 08:30 = 30 minutos; sábado 10:00 → lunes 09:00 = 60 minutos; fines de semana completos = 0.
  > Límites: usar intervalos semiabiertos `[inicio, fin)` y jornadas `[08:00, 18:00)`; recortar por intersección sin modificar las fechas originales.
  > Validación: fin anterior a creación genera error; instantes iguales aportan cero; múltiples fines de semana no requieren tratamiento especial.
  > Precisión: acumular segundos de todas las jornadas y truncar a minutos una sola vez al final, evitando perder fracciones entre días.
  > Escalamiento: conservar el 75 %, solo para incidentes no resueltos y no incumplidos; apagarlo al vencer es intencional, y `is_breached` debe gestionarse por separado.
  > Compatibilidad: mantener incumplimiento cuando los minutos enteros superen el presupuesto, restantes negativos y prioridad de `resolved_at` sobre `reference_time`.
  > Descartadas: librerías business-hours por dependencias innecesarias; avance entre franjas por mayor complejidad de límites y estados.
  > Decisión: recorrido día a día con clipping de cada jornada hábil, separado de la evaluación de estados; Python stdlib, O(D) en tiempo y O(1) en memoria.
  > Contrato pendiente: definir zona horaria de negocio y coherencia de fechas; festivos, pausas y cambios de política quedan fuera del alcance.

### 2.2 Ejecución con Contexto Curado en Nuevo Chat Limpio (*Context Engineering*)
Copia el prompt estructurado con etiquetas XML que utilizaste en un nuevo chat limpio para generar el **ADR (`docs/adr/002-calculo-sla-horario-habil.md`)** y la refactorización de `src/sla_calculator.py`:

```xml
<context>
Proyecto IncidentOps. Chat 2 limpio (sin alternativas descartadas del Chat 1).
Pegar <lsp_context> de evaluate_sla_status + plantilla docs/adr/000-template.md.
</context>

<decision_summary>
P0/P1 24/7; P2/P3 Lun–Vie [08:00,18:00). Intervalos semiabiertos; clipping día a día;
acumular segundos y truncar minutos al final; escalation 75% solo si no RESOLVED y no breached.
Descartadas: libs business-hours y avance entre franjas. Decisión: O(D)/O(1), stdlib.
Casos: vie 18:30→lun 08:30=30; sáb 10:00→lun 09:00=60; vie 17:00→lun 09:00=120.
</decision_summary>

<constraints>
Solo Markdown del ADR-002. Sin código Python. Sin micromanagement. Autor: Juan David
González Muñoz. Fecha: 2026-11-17. Estado: Aceptado. Incluir Mermaid flowchart TD
del cálculo hábil y transición a escalamiento/breach. Componente: src/sla_calculator.py.
</constraints>

<task>
Redactar docs/adr/002-calculo-sla-horario-habil.md siguiendo ADR-000
(contexto, opciones, decisión+diagrama, consecuencias/verificación).
</task>
```

ADR generado y guardado en [`docs/adr/002-calculo-sla-horario-habil.md`](docs/adr/002-calculo-sla-horario-habil.md).

---

## 3. Tipos de Modelos y Matriz de Decisión Arquitectónica

### 3.1 Comparación de Tipos de Modelos
Compara el comportamiento que observaste al interactuar con:
1. **Modelo Rápido / Estándar (ej. Flash, Mini, Haiku o modo estándar)**:
   Respondió rápido con una tabla de triaje usable (severidad, equipo, `duplicate_group_key`). No expuso cadena privada en `<analysis>`, pero sí justificó por alcance/riesgo. Bastó para Self-Consistency del Reto 1: coincidió en los casos ambiguos (`INC-1002` P3, `INC-1007` P0, `INC-1009` P2) y en los pares duplicados.
2. **Modelo de Razonamiento Extendido (*Thinking Model*)**:
   Tampoco reveló thinking interno en `<analysis>`, pero entregó supuestos de severidad más explícitos, priorización operativa (contener IDOR → pagos → DB → rendimiento) y el mismo consenso de clasificación. Fue más útil en el Reto 2 al explorar casos borde de horario hábil, descartar alternativas y destilar el ADR-002 sin generar código prematuro.
- ¿En cuál de las tareas de la semana fue indispensable el modelo de razonamiento y en cuál bastó el modelo rápido?
  - **Indispensable el thinking**: exploración de diseño SLA (casos borde, semiabiertos `[08:00,18:00)`, escalamiento al 75%) y redacción del ADR antes de tocar código.
  - **Bastó el rápido**: clasificación/Self-Consistency del triaje y tareas mecánicas (auditoría `tiktoken`, pegar tablas en la bitácora) cuando el prompt ya traía reglas y ejemplos canónicos.

### 3.2 Matriz de Decisión Arquitectónica
Para la plataforma *IncidentOps* y su evolución futura, justifica qué paradigma es el adecuado en cada escenario:

| Escenario / Requerimiento | Paradigma Elegido (Código Determinista / ML Clásico / Asistente GenAI en Chat / LLM en Tiempo de Ejecución) | Justificación Técnica (Determinismo, Costo, Latencia, Riesgo de Alucinación) |
| :--- | :--- | :--- |
| 1. Contabilizar minutos hábiles transcurridos y verificar si un ticket superó el 75% de su SLA | Código determinista | Debe ser reproducible y auditable (ADR-002). Costo/latencia mínimos en stdlib; un LLM introduciría alucinaciones en minutos y no aporta valor frente a un algoritmo O(D). |
| 2. Explorar casos borde y redactar un ADR antes de modificar la arquitectura de consultas SQL | Asistente GenAI en chat | La exploración es creativa y de diseño; el chat permite Compactación y Context Engineering sin ejecutar SQL. No va en runtime: el artefacto final es un ADR humano-revisable, no una inferencia en producción. |
| 3. Detectar anomalías numéricas en millones de métricas de CPU/RAM por minuto | ML clásico | Volumen alto y señales numéricas: modelos estadísticos/series temporales escalan mejor que un LLM. Menor costo y latencia por punto; el LLM no es eficiente ni determinista para scoring masivo. |
| 4. Clasificar reportes de incidentes redactados en lenguaje natural abierto cuando las reglas deterministas no cubren nuevos patrones | LLM en tiempo de ejecución (con salida estructurada + fallback a reglas) | El lenguaje abierto supera heurísticas fijas; un LLM aporta cobertura de patrones nuevos. Mitigar alucinación con schema/`TriageResult`, few-shot y validación; reservar reglas deterministas para casos canónicos ya estabilizados. |

---

## 4. Economía de Tokens y Curaduría de Contexto con `tiktoken` (LSP vs. `grep`/`read` vs. `glob`/`read`)

### 4.1 Medición Empírica en *IncidentOps*
Completa la tabla con los resultados obtenidos al auditar los símbolos con `uv run python -m src.context_audit --symbol evaluate_sla_status` (y `classify_incident_report`):

**Símbolo `evaluate_sla_status` (Reto 2 — SLA):**

| Estrategia de Recolección de Contexto | Alcance (Archivos / Nodos) | Caracteres Totales | Tokens (`tiktoken o200k_base`) | % de Reducción vs. Fuerza Bruta |
| :--- | :--- | :---: | :---: | :---: |
| **1. Fuerza Bruta (`glob` + `read` todo)** | 9 archivos | 51004 | 12773 | 0% (Línea base) |
| **2. Búsqueda Textual (`grep` + `read` `.py`)** | 4 archivos `.py` | 26697 | 6728 | 47.3% |
| **3. Semántica vía LSP (`definition` + `references` + `hover`)** | Definición + tipos + refs | 4543 | 1183 | 90.7% |

**Símbolo `classify_incident_report` (Reto 1 — Triaje):**

| Estrategia de Recolección de Contexto | Alcance (Archivos / Nodos) | Caracteres Totales | Tokens (`tiktoken o200k_base`) | % de Reducción vs. Fuerza Bruta |
| :--- | :--- | :---: | :---: | :---: |
| **1. Fuerza Bruta (`glob` + `read` todo)** | 9 archivos | 51004 | 12773 | 0% (Línea base) |
| **2. Búsqueda Textual (`grep` + `read` `.py`)** | 2 archivos `.py` | 11911 | 2785 | 78.2% |
| **3. Semántica vía LSP (`definition` + `references` + `hover`)** | Definición + tipos + refs | 9724 | 2263 | 82.3% |

**Análisis del ahorro en los Pasos 1 y 2:** al inyectar solo `<lsp_context>` en lugar de todo el repo, el Paso 1 (triaje) ahorró ~10 510 tokens vs. fuerza bruta (82.3%) y el Paso 2 (SLA) ahorró ~11 590 tokens (90.7%). Frente a `grep`+`read`, el LSP sigue ganando: 18.7% en triaje (el cuerpo de `classify_incident_report` es grande) y 82.4% en SLA. Eso confirma que la curaduría semántica fue la que permitió los prompts de exploración/ADR sin saturar la ventana ni arrastrar *context rot*.

### 4.2 Comparación de Formatos de Serialización (`--compare-formats`)
Registra los tokens medidos con `tiktoken` para los 10 incidentes en JSON indentado, JSON compacto, YAML y CSV, y explica qué formato elegirías al inyectar datos tabulares o logs largos en la ventana de contexto.

| Formato | Caracteres | Tokens (`o200k_base`) |
| :--- | :---: | :---: |
| JSON indentado (`indent=2`) | 2942 | 878 |
| JSON compacto (minified) | 2641 | 728 |
| YAML equivalente | 2579 | 755 |
| CSV delimitado por `\|` | 2171 | 617 |

Para inyectar datos tabulares o logs largos elegiría **CSV delimitado** (617 tokens, el más barato) o, si el consumidor necesita estructura anidada, **JSON compacto** (728). Evitaría JSON indentado en contexto masivo: gasta ~42% más tokens que CSV solo por whitespace, sin aportar información.
