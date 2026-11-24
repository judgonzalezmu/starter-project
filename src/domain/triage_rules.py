"""Motor determinista de clasificación y enrutamiento de incidentes (IncidentOps).

Clasifica reportes por alcance e impacto (no por keywords sueltas), asigna el equipo
de guardia (`Backend-Core`, `Platform-SRE`, `Data-DBA`, `Security-IAM`) y genera
`duplicate_group_key` para correlacionar fallas repetidas.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List

from src.domain.models import SeverityLevel, TeamName, TriageResult

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "sample_incidents.json"


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _contains(text: str, *phrases: str) -> bool:
    return any(phrase in text for phrase in phrases)


def _connection_pressure(text: str) -> bool:
    """Detecta saturación explícita o porcentajes elevados de conexiones."""
    explicit_pressure = _contains(
        text,
        "too many connections",
        "pool agotado",
        "conexiones agotadas",
        "saturacion de conexiones",
    )
    percentages = (
        float(match.replace(",", "."))
        for match in re.findall(r"(\d+(?:[.,]\d+)?)\s*%", text)
    )
    high_utilization = any(90 <= value <= 100 for value in percentages)
    connection_context = _contains(text, "conexion", "connection", "pool")
    return explicit_pressure or (connection_context and high_utilization)


def _latency_over_three_seconds(text: str) -> bool:
    values = re.findall(
        r"\b(\d+(?:[.,]\d+)?)\s*(?:segundos?|seconds?|secs?|s)\b",
        text,
    )
    return any(float(value.replace(",", ".")) > 3 for value in values)


def _large_dataset(text: str) -> bool:
    return bool(
        re.search(
            r"(?:10[., ]?000|10\s*k|10000)\s*(?:registros|filas|ordenes|orders|rows|records)",
            text,
        )
    ) or _contains(text, "large dataset", "grandes volumenes", "gran volumen de datos")


def classify_incident_report(incident_id: str, raw_text: str) -> TriageResult:
    """Clasifica un reporte por alcance, riesgo y causa raíz probable."""
    text = _normalize(raw_text)

    def result(
        severity: SeverityLevel,
        component: str,
        team: TeamName,
        rationale: str,
        duplicate_key: str | None = None,
    ) -> TriageResult:
        return TriageResult(
            incident_id=incident_id,
            severity=severity,
            component=component,
            rationale=rationale,
            recommended_team=team,
            duplicate_group_key=duplicate_key or f"UNIQUE-{incident_id}",
            consistency_ratio=1.0,
        )

    payments = _contains(
        text, "pago", "payment", "checkout", "cobro", "tarjeta", "pasarela"
    )
    reporting = _contains(
        text, "report", "informe", "export", "excel", "listado", "dashboard", "historial"
    )
    database = _contains(text, "postgres", "database", "base de datos", "conexiones")
    tls = _contains(text, "tls", "ssl", "certificado", "certificate")
    auth = _contains(text, "login", "autentic", "ingresar", "cuenta", "account", "bloqueada")
    cosmetic = _contains(text, "color", "boton", "button", "ui")

    global_scope = _contains(
        text,
        "todos los comercios",
        "ningun comercio",
        "todos los usuarios",
        "todos los clientes",
        "a nuestros clientes",
        "indisponibilidad general",
        "caida total",
        "global outage",
    )
    outage = _contains(
        text,
        "caido",
        "caida",
        "indisponib",
        "sin servicio",
        "no pueden",
        "no funciona",
        "unavailable",
        "outage",
        "502",
        "bad gateway",
    )
    performance = _contains(
        text,
        "lent",
        "latencia",
        "latency",
        "slow",
        "demora",
        "tarda",
        "pensando",
        "timeout",
        "time out",
    ) or _latency_over_three_seconds(text)

    # 1) Exposición crítica (IDOR / cross-tenant) tiene precedencia.
    authorization_exposure = _contains(
        text,
        "idor",
        "cross-tenant",
        "cross tenant",
        "entre tenants",
        "otra organizacion",
        "otra empresa",
        "otro tenant",
        "another tenant",
        "company_id",
        "tenant_id",
    )
    exposure_evidence = _contains(
        text,
        "acced",
        "acceso",
        "visualiz",
        "facturas",
        "datos",
        "expos",
        "autorizacion",
        "authorization",
        "pertenecientes",
    )
    if authorization_exposure and exposure_evidence:
        return result(
            "P0",
            "reporting-api",
            "Security-IAM",
            "Exposición crítica de datos por autorización entre empresas o tenants.",
        )

    # 2) Pasarela de pagos con HTTP 502 (duplicados canónicos Spec 001).
    if payments and "502" in text:
        return result(
            "P0",
            "payments-gateway",
            "Backend-Core",
            "HTTP 502 en la pasarela de pagos con afectación a comercios/clientes.",
            "payments-gateway:http-502-outage",
        )

    # 3) Base de datos / pool de conexiones.
    if database or _connection_pressure(text):
        pressure = _connection_pressure(text)
        timeouts = _contains(text, "timeout", "time out", "tiempo de espera")
        if global_scope and outage:
            severity: SeverityLevel = "P0"
            rationale = "Indisponibilidad general asociada a la base de datos."
        elif pressure or timeouts:
            severity = "P1"
            rationale = (
                "Saturación de conexiones o timeouts de base de datos "
                "con degradación grave o riesgo inmediato."
            )
        elif performance:
            severity = "P2"
            rationale = "Base de datos operativa con degradación de rendimiento."
        else:
            severity = "P3"
            rationale = "Caso de base de datos con alcance limitado."
        return result(severity, "database-cluster", "Data-DBA", rationale)

    # 4) Certificados TLS / staging.
    if tls:
        preventive = _contains(
            text,
            "staging",
            "preventiv",
            "vencer",
            "vence",
            "expira",
            "rotacion",
            "renovacion",
        )
        if global_scope and outage:
            return result(
                "P0",
                "infra-certificates",
                "Platform-SRE",
                "Fallo TLS con indisponibilidad general.",
            )
        if preventive:
            return result(
                "P3",
                "infra-certificates",
                "Platform-SRE",
                "Mantenimiento preventivo de certificados o afectación de staging.",
            )
        return result(
            "P3",
            "infra-certificates",
            "Platform-SRE",
            "Revisión de certificados con alcance limitado.",
        )

    # 5) Autenticación / bloqueo de cuenta individual (Spec 001: P2; "hoy" no eleva a P0).
    if auth:
        if global_scope and outage:
            return result(
                "P0",
                "auth-identity",
                "Security-IAM",
                "Autenticación indisponible para todos los usuarios.",
            )
        return result(
            "P2",
            "auth-identity",
            "Security-IAM",
            "Incidencia de autenticación o bloqueo de cuenta individual.",
        )

    # 6) UX cosmética (antes de reportes: "exportar CSV" + color de botón no es P2).
    if cosmetic and not outage and not _large_dataset(text):
        return result(
            "P3",
            "frontend-ui",
            "Backend-Core",
            "Solicitud cosmética de interfaz sin impacto funcional.",
        )

    # 7) Reportes / exportación / listados.
    if reporting:
        if global_scope and outage:
            return result(
                "P0",
                "reporting-api",
                "Backend-Core",
                "Servicio de reportes con indisponibilidad general.",
            )
        if performance and _large_dataset(text):
            return result(
                "P2",
                "reporting-api",
                "Backend-Core",
                "Degradación de reportes con conjuntos grandes de datos.",
                "LARGE-DATASET-REPORT-PERFORMANCE",
            )
        if performance:
            return result(
                "P2",
                "reporting-api",
                "Backend-Core",
                "Reporte o exportación utilizable con degradación de rendimiento.",
            )
        return result(
            "P3",
            "reporting-api",
            "Backend-Core",
            "Incidencia de reportes con alcance limitado.",
        )

    # 8) Pagos sin 502 / plataforma genérica.
    if payments:
        severity = (
            "P0"
            if global_scope and outage
            else "P1"
            if outage
            else "P2"
            if performance
            else "P3"
        )
        return result(
            severity,
            "payments-gateway",
            "Platform-SRE",
            "Impacto en pagos evaluado por alcance, interrupción y degradación.",
        )

    return result(
        "P3",
        "frontend-ui",
        "Backend-Core",
        "Caso individual o cosmético según la evidencia disponible.",
    )


def _run_triage_audit() -> None:
    """Ejecuta el motor sobre los 10 incidentes de prueba."""
    incidents: List[Dict[str, str]] = json.loads(SAMPLE_DATA_PATH.read_text(encoding="utf-8"))

    print("=== Auditoría del Motor de Triaje (`src/domain/triage_rules.py`) ===")
    print(
        f"{'ID':<10} | {'Sev.':<5} | {'Team':<14} | {'Duplicate Key':<34} | {'Componente'}"
    )
    print("-" * 110)
    for item in incidents:
        triage = classify_incident_report(item["id"], item["raw_text"])
        print(
            f"{triage.incident_id:<10} | {triage.severity:<5} | "
            f"{triage.recommended_team:<14} | {triage.duplicate_group_key:<34} | "
            f"{triage.component}"
        )
    print("-" * 110)


if __name__ == "__main__":
    _run_triage_audit()
