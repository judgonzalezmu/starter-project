"""Cálculo determinista de SLA (ADR-002: horario hábil vs. 24/7).

P0/P1 contabilizan tiempo calendario continuo.
P2/P3 solo acumulan intersección con jornadas Lun–Vie [08:00, 18:00).
"""

from datetime import date, datetime, timedelta, time
from typing import Dict, List, Tuple

from src.domain.models import Incident, SLAEvaluation, SLARule, SeverityLevel

SLA_POLICY_TABLE: Dict[SeverityLevel, SLARule] = {
    "P0": SLARule(severity="P0", max_resolution_minutes=60, operates_24x7=True),
    "P1": SLARule(severity="P1", max_resolution_minutes=240, operates_24x7=True),
    "P2": SLARule(severity="P2", max_resolution_minutes=480, operates_24x7=False),
    "P3": SLARule(severity="P3", max_resolution_minutes=1440, operates_24x7=False),
}

BUSINESS_DAY_START = time(8, 0, 0)
BUSINESS_DAY_END = time(18, 0, 0)


def get_sla_rule_for_severity(severity: SeverityLevel) -> SLARule:
    """Obtiene la regla de SLA aplicable a una severidad validada contra la tabla."""
    if severity not in SLA_POLICY_TABLE:
        raise ValueError(f"Severidad no válida: {severity}")
    return SLA_POLICY_TABLE[severity]


def _business_elapsed_seconds(start: datetime, end: datetime) -> float:
    """Acumula segundos de intersección con jornadas hábiles [08:00, 18:00) Lun–Vie.

    Intervalo evaluado: semiabierto [start, end). Complejidad O(D) en fechas, O(1) memoria.
    """
    if start == end:
        return 0.0

    total_seconds = 0.0
    current_day: date = start.date()
    last_day: date = end.date()
    one_day = timedelta(days=1)

    while current_day <= last_day:
        if current_day.weekday() < 5:  # Lunes=0 … Viernes=4
            window_start = datetime.combine(current_day, BUSINESS_DAY_START)
            window_end = datetime.combine(current_day, BUSINESS_DAY_END)
            overlap_start = max(start, window_start)
            overlap_end = min(end, window_end)
            if overlap_end > overlap_start:
                total_seconds += (overlap_end - overlap_start).total_seconds()
        current_day = current_day + one_day

    return total_seconds


def _elapsed_seconds(start: datetime, end: datetime, operates_24x7: bool) -> float:
    if start == end:
        return 0.0
    if operates_24x7:
        return (end - start).total_seconds()
    return _business_elapsed_seconds(start, end)


def _ensure_comparable_naive(dt: datetime) -> datetime:
    """Normaliza a naive de reloj de pared (laboratorio); no inventa zona horaria."""
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def evaluate_sla_status(incident: Incident, reference_time: datetime) -> SLAEvaluation:
    """Evalúa incumplimiento y escalamiento preventivo según ADR-002."""
    rule = get_sla_rule_for_severity(incident.severity)
    created_at = _ensure_comparable_naive(incident.created_at)
    reference_time = _ensure_comparable_naive(reference_time)
    resolved_at = (
        _ensure_comparable_naive(incident.resolved_at)
        if incident.resolved_at is not None
        else None
    )
    end_time = resolved_at or reference_time

    if end_time < created_at:
        raise ValueError("El tiempo de referencia no puede ser anterior a la creación.")

    elapsed_seconds = _elapsed_seconds(created_at, end_time, rule.operates_24x7)
    # Truncar a minutos enteros una sola vez al final (ADR-002).
    elapsed_minutes = int(elapsed_seconds // 60)

    remaining_minutes = rule.max_resolution_minutes - elapsed_minutes
    is_breached = elapsed_minutes > rule.max_resolution_minutes

    escalation_limit = int(rule.max_resolution_minutes * rule.escalation_threshold_ratio)
    requires_escalation = (
        incident.status != "RESOLVED"
        and not is_breached
        and elapsed_minutes >= escalation_limit
    )

    return SLAEvaluation(
        incident_id=incident.incident_id,
        severity=incident.severity,
        elapsed_minutes=elapsed_minutes,
        allowed_minutes=rule.max_resolution_minutes,
        remaining_minutes=remaining_minutes,
        is_breached=is_breached,
        requires_escalation=requires_escalation,
    )


def _make_incident(
    incident_id: str,
    severity: SeverityLevel,
    created_at: datetime,
    *,
    status: str = "OPEN",
    resolved_at: datetime | None = None,
) -> Incident:
    return Incident(
        incident_id=incident_id,
        title=f"Caso de verificación {incident_id}",
        component="reporting-api",
        severity=severity,
        status=status,  # type: ignore[arg-type]
        created_at=created_at,
        resolved_at=resolved_at,
    )


def _run_demo() -> None:
    """Verifica al menos 5 casos borde del ADR-002 de forma determinista."""
    print("=== Verificación Determinista de SLA (ADR-002) ===")
    print(
        f"{'Caso':<42} | {'Sev':<3} | {'Esperado':>8} | {'Obtenido':>8} | {'OK?'}"
    )
    print("-" * 90)

    cases: List[Tuple[str, Incident, datetime, int]] = [
        (
            "Vie 18:30 → Lun 08:30 (fuera horario)",
            _make_incident("EDGE-01", "P2", datetime(2026, 11, 6, 18, 30, 0)),
            datetime(2026, 11, 9, 8, 30, 0),
            30,
        ),
        (
            "Sáb 10:00 → Lun 09:00 (fin de semana)",
            _make_incident("EDGE-02", "P2", datetime(2026, 11, 7, 10, 0, 0)),
            datetime(2026, 11, 9, 9, 0, 0),
            60,
        ),
        (
            "Sáb 10:00 → Dom 18:00 (solo weekend)",
            _make_incident("EDGE-03", "P3", datetime(2026, 11, 7, 10, 0, 0)),
            datetime(2026, 11, 8, 18, 0, 0),
            0,
        ),
        (
            "Vie 17:00 → Lun 09:00 (demo P2)",
            _make_incident("EDGE-04", "P2", datetime(2026, 11, 6, 17, 0, 0)),
            datetime(2026, 11, 9, 9, 0, 0),
            120,
        ),
        (
            "Vie 17:00 → Lun 09:00 (P0 24/7)",
            _make_incident("EDGE-05", "P0", datetime(2026, 11, 6, 17, 0, 0)),
            datetime(2026, 11, 9, 9, 0, 0),
            3840,  # 64 horas calendario (Vie 17:00 → Lun 09:00)
        ),
        (
            "Lun 08:00 → Lun 18:00 (jornada completa)",
            _make_incident("EDGE-06", "P2", datetime(2026, 11, 9, 8, 0, 0)),
            datetime(2026, 11, 9, 18, 0, 0),
            600,
        ),
        (
            "Instantes iguales → 0",
            _make_incident("EDGE-07", "P2", datetime(2026, 11, 9, 10, 0, 0)),
            datetime(2026, 11, 9, 10, 0, 0),
            0,
        ),
    ]

    passed = 0
    for label, incident, reference, expected in cases:
        evaluation = evaluate_sla_status(incident, reference_time=reference)
        ok = evaluation.elapsed_minutes == expected
        passed += int(ok)
        mark = "PASS" if ok else "FAIL"
        print(
            f"{label:<42} | {incident.severity:<3} | {expected:>8} | "
            f"{evaluation.elapsed_minutes:>8} | {mark}"
        )

    print("-" * 90)
    print(f"Resultado: {passed}/{len(cases)} casos correctos")

    # Caso de error de validación
    try:
        evaluate_sla_status(
            _make_incident("EDGE-ERR", "P2", datetime(2026, 11, 9, 10, 0, 0)),
            reference_time=datetime(2026, 11, 9, 9, 0, 0),
        )
        print("Validación fin < creación: FAIL (no lanzó error)")
    except ValueError:
        print("Validación fin < creación: PASS (ValueError esperado)")


if __name__ == "__main__":
    _run_demo()
