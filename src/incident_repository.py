"""Benchmark del listado activo sobre el adaptador SQLite outbound.

El esquema y la consulta viven en `SQLiteIncidentRepository`. Este módulo solo
siembra datos sintéticos y mide `list_active_incidents` más `evaluate_sla_status`.
"""

import argparse
from datetime import datetime
import time

from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.domain.sla_calculator import evaluate_sla_status


def _run_benchmark() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark del listado activo en SQLiteIncidentRepository"
    )
    parser.add_argument("--records", type=int, default=10000, help="Cantidad de registros a sembrar")
    parser.add_argument(
        "--iterations", type=int, default=20, help="Número de consultas consecutivas a medir"
    )
    args = parser.parse_args()

    repo = SQLiteIncidentRepository()
    print(f"Sembrando {args.records} incidentes en SQLite en memoria...")
    repo.seed_synthetic_incidents(total_records=args.records)

    ref_time = datetime(2026, 11, 20, 12, 0, 0)
    start = time.perf_counter()
    found_count = 0
    for _ in range(args.iterations):
        active = repo.list_active_incidents("payments-gateway")
        for incident in active:
            evaluate_sla_status(incident, reference_time=ref_time)
        found_count = len(active)
    elapsed_ms = (time.perf_counter() - start) * 1000

    print("=== Resultado del Benchmark ===")
    print(f"Incidentes activos encontrados para 'payments-gateway': {found_count}")
    print(f"Tiempo total ({args.iterations} ejecuciones sobre {args.records} filas): {elapsed_ms:.2f} ms")
    print(f"Promedio por consulta: {elapsed_ms / args.iterations:.2f} ms")
    print(
        "Diagnóstico: `list_active_incidents` lee los activos con un JOIN a sla_policies "
        "y el SLA se evalúa en el dominio sobre esas filas."
    )


if __name__ == "__main__":
    _run_benchmark()
