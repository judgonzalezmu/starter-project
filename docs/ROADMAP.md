# Roadmap — IncidentOps

Evolución del producto y de la operación. Los hitos son secuenciales: cada uno asume el valor del anterior.

## H001 — Triaje multi-interfaz

Exponer la clasificación y el enrutamiento determinista de reportes **sin persistencia**, para consumo inmediato desde **web** y **terminal**.

**Resultado:** un operador o sistema puede clasificar un reporte al momento y obtener severidad, componente, equipo sugerido y señal de agrupación de duplicados, sin guardar el incidente.

**Spec:** [`specs/001-triage-endpoint-manual.md`](../specs/001-triage-endpoint-manual.md)

## H002 — Resumen de incidentes activos

Permitir consultar incidentes **actualmente activos**, incumplimientos de SLA y filtrado por componente, desde **web** y **terminal**.

**Resultado:** visibilidad operativa del estado actual (qué está abierto, qué incumple SLA, qué afecta un componente) sin aún completar el ciclo de vida de registro.

## H003 — Ciclo de vida, duplicados y SLA

Registrar incidentes entrantes de forma **persistente**, alertar si ya existe otro equivalente abierto y auditar su SLA en cualquier instante de referencia.

**Resultado:** el sistema deja de ser solo lectura/clasificación puntual: guarda entradas, detecta posibles duplicados abiertos y permite evaluar el cumplimiento de SLA en el momento que se necesite.

## H004 — Persistencia relacional dedicada y runtime en contenedores

Preparar el servicio para ejecución **reproducible en contenedores**, con **base de datos relacional dedicada** y chequeo real de **conectividad operativa**.

**Resultado:** el entorno de despliegue y la persistencia dejan de ser ad hoc; el servicio arranca de forma consistente y puede verificar que la infraestructura crítica responde antes de operar.

---

### Notas de alcance

- Este roadmap describe **capacidades de producto y operación**, no diseño de API ni stack concreto.
- Decisiones de implementación (contratos, tecnologías, topología) se documentan en ADRs cuando se estabilicen.
