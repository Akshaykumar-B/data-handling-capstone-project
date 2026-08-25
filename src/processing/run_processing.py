"""Phase 3 orchestrator: clean four raw datasets, build five analysis-ready
tables, validate everything, and emit ``processing_report.json``.

Run from the Windows project environment (the .venv holds the geo stack):

    cd "C:\\Users\\aksha\\Downloads\\datahandling capstone\\public-transit-dashboard"
    "C:\\Users\\aksha\\Downloads\\datahandling capstone\\.venv\\Scripts\\python.exe" -m src.processing.run_processing

The runner is deterministic and rerunnable: it only reads from ``data/raw``
and writes to ``data/processed`` via temp-file + atomic replacement. It never
modifies the raw inputs, downloads anything, or touches the ingestion scripts.
"""

from __future__ import annotations

import platform
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any

from . import config
from .aggregate import (
    aggregate_cjtp,
    aggregate_ridership,
    aggregate_route_stops,
)
from .clean_cjtp import clean_cjtp
from .clean_ridership import clean_ridership
from .clean_routes import clean_routes
from .clean_stops import clean_stops
from .reference import load_route_reference
from .utils import (
    WarningCollector,
    fingerprint_all,
    json_safe,
    normalized_route_set,
    write_json_atomic,
)
from .validate import validate_outputs


def _environment() -> dict[str, Any]:
    versions: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
    for module_name in ("pandas", "numpy", "pyarrow", "geopandas", "pyogrio", "shapely"):
        try:
            module = __import__(module_name)
            versions[module_name] = getattr(module, "__version__", "unknown")
        except Exception:  # noqa: BLE001 - report absence rather than crash
            versions[module_name] = "not available"
    return versions


def _limitations(dataset_reports: dict[str, Any], project_route_count: int) -> dict[str, Any]:
    """Restate the documented coverage limitations against what was measured.

    The documented figures come from the Phase 1/2 reports. Nothing here alters
    data - it exists so a shrinking (or silently growing) route coverage is
    visible in the report rather than discovered later.
    """
    documented = {
        "ridership": 140,
        "bus_stops": 129,
        "customer_journey": 120,
    }
    entries: dict[str, Any] = {}
    for key, documented_count in documented.items():
        coverage = dataset_reports.get(key, {}).get(
            "route_coverage_vs_project_reference", {}
        )
        measured = coverage.get("matching_route_count")
        entries[key] = {
            "documented_route_coverage": f"{documented_count}/{project_route_count}",
            "measured_route_coverage": (
                f"{measured}/{project_route_count}" if measured is not None else None
            ),
            "matches_documented": measured == documented_count,
            "coverage_percentage": coverage.get("coverage_percentage"),
            "project_routes_absent": coverage.get("project_routes_missing_from_dataset"),
            "handling": "absent routes are left absent — no rows or metrics were fabricated",
        }
    routes_coverage = dataset_reports.get("routes", {}).get(
        "route_coverage_vs_project_reference", {}
    )
    entries["routes_geometry"] = {
        "documented_route_coverage": f"{project_route_count}/{project_route_count}",
        "measured_route_coverage": (
            f"{routes_coverage.get('matching_route_count')}/{project_route_count}"
        ),
        "coverage_percentage": routes_coverage.get("coverage_percentage"),
        "project_routes_absent": routes_coverage.get("project_routes_missing_from_dataset"),
        "handling": "every source feature preserved; geometry untouched",
    }
    return entries


def main() -> int:
    started_at = time.perf_counter()
    start_wall = datetime.now(timezone.utc)
    print("=" * 72)
    print("Phase 3 - Data Cleaning & Preprocessing")
    print(f"Started: {start_wall.isoformat()}")
    print("=" * 72)

    warnings = WarningCollector()

    # Verify raw inputs exist before doing anything.
    missing_inputs = [path.name for path in config.RAW_INPUTS if not path.exists()]
    if missing_inputs:
        print(f"ERROR: required raw input(s) missing: {missing_inputs}")
        return 2

    # Fingerprint raw inputs up front to prove immutability afterwards.
    print("\n[setup] fingerprinting raw inputs")
    raw_before = fingerprint_all(
        config.RAW_INPUTS, hash_limit_bytes=config.HASH_SIZE_LIMIT_BYTES
    )

    print("[setup] loading authoritative route reference")
    reference, profile = load_route_reference(
        config.PROFILING_REPORT, config.ROUTES_VALID_REPORT
    )
    print(
        f"[setup] {len(reference.project_routes)} project routes, "
        f"{len(reference.alias_pairs)} known aliases"
    )
    for note in reference.source_notes:
        print(f"        - {note}")

    dataset_reports: dict[str, Any] = {}
    aggregation_reports: dict[str, Any] = {}
    stage_timings: dict[str, float] = {}

    try:
        # --- clean the three tabular datasets -----------------------------
        stage_start = time.perf_counter()
        print("\n--- Cleaning ridership ---")
        ridership_clean, dataset_reports["ridership"] = clean_ridership(reference, warnings)
        stage_timings["clean_ridership"] = time.perf_counter() - stage_start

        stage_start = time.perf_counter()
        print("\n--- Cleaning bus stops ---")
        stops_clean, dataset_reports["bus_stops"] = clean_stops(reference, warnings)
        stage_timings["clean_stops"] = time.perf_counter() - stage_start

        stage_start = time.perf_counter()
        print("\n--- Cleaning customer journey metrics ---")
        cjtp_clean, dataset_reports["customer_journey"] = clean_cjtp(reference, warnings)
        stage_timings["clean_cjtp"] = time.perf_counter() - stage_start

        # --- reuse the large routes GeoJSON without copying ----------------
        stage_start = time.perf_counter()
        print("\n--- Reusing validated route geometries (hard link) ---")
        dataset_reports["routes"] = clean_routes(reference, warnings)
        stage_timings["clean_routes"] = time.perf_counter() - stage_start

        # --- aggregations -------------------------------------------------
        stage_start = time.perf_counter()
        print("\n--- Building ridership aggregations ---")
        aggregation_reports.update(aggregate_ridership(ridership_clean, warnings))

        print("\n--- Building CJTP aggregation ---")
        aggregation_reports["cjtp_by_route"] = aggregate_cjtp(cjtp_clean, warnings)

        print("\n--- Building route/stop relationships ---")
        ridership_routes = normalized_route_set(
            ridership_clean["route_id"].dropna().unique()
        )
        geometry_routes = set(dataset_reports["routes"].get("canonical_route_identifiers", []))
        aggregation_reports["route_stop_relationships"] = aggregate_route_stops(
            stops_clean, ridership_routes, geometry_routes, reference, warnings
        )
        stage_timings["aggregations"] = time.perf_counter() - stage_start

        # The canonical route list was only needed to build the relationship
        # table; keep it out of the persisted report to avoid bloat.
        dataset_reports["routes"].pop("canonical_route_identifiers", None)

        # --- validation ---------------------------------------------------
        stage_start = time.perf_counter()
        print("\n--- Validating outputs ---")
        validation = validate_outputs(
            reference, raw_before, dataset_reports, aggregation_reports
        )
        stage_timings["validation"] = time.perf_counter() - stage_start

    except Exception as exc:  # noqa: BLE001 - capture into the report, then re-raise cleanly
        elapsed = time.perf_counter() - started_at
        print("\nERROR during processing:")
        traceback.print_exc()
        failure_report = {
            "phase": "Phase 3 - Data Cleaning & Preprocessing",
            "status": "failed",
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "traceback": traceback.format_exc(),
            "started_utc": start_wall.isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            "stage_timings_seconds": {k: round(v, 2) for k, v in stage_timings.items()},
            "dataset_reports": json_safe(dataset_reports),
            "aggregation_reports": json_safe(aggregation_reports),
            "warnings": warnings.to_list(),
        }
        try:
            write_json_atomic(failure_report, config.PROCESSING_REPORT)
            print(f"Failure report written to {config.PROCESSING_REPORT}")
        except Exception:  # noqa: BLE001
            print("Could not write failure report.")
        return 1

    elapsed = time.perf_counter() - started_at

    report = {
        "phase": "Phase 3 - Data Cleaning & Preprocessing",
        "status": "completed" if validation["all_passed"] else "completed_with_failures",
        "started_utc": start_wall.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "stage_timings_seconds": {k: round(v, 2) for k, v in stage_timings.items()},
        "environment": _environment(),
        "route_reference": {
            "project_route_count": len(reference.project_routes),
            "project_routes": sorted(reference.project_routes),
            "raw_project_route_count": len(reference.raw_project_routes),
            "raw_project_routes": sorted(reference.raw_project_routes),
            "known_alias_count": len(reference.alias_pairs),
            "known_aliases": [
                {"from": source, "to": target} for source, target in reference.alias_pairs
            ],
            "source_notes": list(reference.source_notes),
        },
        "raw_inputs": {
            "fingerprints_before": raw_before,
            "fingerprints_after": validation.get("raw_input_fingerprints_after"),
            "note": "raw inputs are read-only in Phase 3; matching fingerprints prove immutability",
        },
        "outputs_created": [path.name for path in config.OUTPUT_PATHS if path.exists()],
        "documented_limitations": _limitations(
            dataset_reports, len(reference.project_routes)
        ),
        "dataset_reports": json_safe(dataset_reports),
        "aggregation_reports": json_safe(aggregation_reports),
        "validation": json_safe(validation),
        "warnings": warnings.to_list(),
        "warning_count": len(warnings.to_list()),
        "constraints_observed": [
            "raw datasets never modified (proven by fingerprints)",
            "no data downloaded",
            "ingestion scripts not run or modified",
            "2.3GB routes GeoJSON reused through a filesystem hard link (metadata from the "
            "authoritative Phase 2 report); never fully parsed, never scanned with read_info()",
            "all route geometry preserved (no simplification, no feature loss)",
            "EPSG:4326 / CRS84 preserved",
            "missing routes preserved as documented limitations, none fabricated",
            "CJTP bootstrap resampling deferred to a later phase",
        ],
    }

    write_json_atomic(report, config.PROCESSING_REPORT)

    print("\n" + "=" * 72)
    print(f"Phase 3 {report['status'].upper()} in {elapsed:.1f}s")
    print(f"Outputs created: {len(report['outputs_created'])}/{len(config.OUTPUT_PATHS)}")
    print(
        f"Validation: {validation['passed']}/{validation['total_checks']} checks passed, "
        f"{validation['failed']} failed"
    )
    if validation["failed"]:
        print(f"Failed checks: {validation['failed_checks']}")
    print(f"Warnings: {len(warnings.to_list())}")
    print(f"Report: {config.PROCESSING_REPORT}")
    print("=" * 72)

    return 0 if validation["all_passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
