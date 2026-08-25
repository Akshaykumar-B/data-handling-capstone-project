"""Phase 4 orchestrator: run the EDA over the Phase 3 processed datasets, render
figures into ``data/processed/eda/`` and emit ``data/processed/eda_report.json``.

Run from the Windows project environment (the .venv holds pandas/pyarrow; add
matplotlib once with ``pip install matplotlib``):

    cd "C:\\Users\\aksha\\Downloads\\datahandling capstone\\public-transit-dashboard"
    "C:\\Users\\aksha\\Downloads\\datahandling capstone\\.venv\\Scripts\\python.exe" -m src.analysis.run_eda

The runner is deterministic and rerunnable: it only READS processed inputs and
WRITES to ``data/processed/eda/`` + ``eda_report.json``. It never modifies the
processed datasets (proven by before/after fingerprints), never touches
``data/raw``, never downloads anything, and never parses the 2.3 GB
``routes_clean.geojson`` (its metadata comes from ``processing_report.json``).
"""

from __future__ import annotations

import platform
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any

from . import cjtp_eda, cross_dataset, eda_config as C, io_utils, ridership_eda, routes_eda, stops_eda
from . import stats_utils as S
from ..processing.reference import load_route_reference
from ..processing.utils import WarningCollector, fingerprint_all, json_safe, write_json_atomic

_HASH_LIMIT = 128 * 1024 * 1024  # never hash the 2.3 GB geojson; size+mtime only


def _environment() -> dict[str, Any]:
    versions: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
    for module_name in ("pandas", "numpy", "matplotlib", "scipy", "pyarrow"):
        try:
            module = __import__(module_name)
            versions[module_name] = getattr(module, "__version__", "unknown")
        except Exception:  # noqa: BLE001
            versions[module_name] = "not available"
    return versions


def _safe(value: Any, default: Any = None) -> Any:
    return default if value is None else value


def _major_findings(sections: dict[str, Any]) -> list[str]:
    """Human-readable headline findings, generated from the computed numbers."""
    ride = sections["ridership"]
    cj = sections["cjtp"]
    stops = sections["bus_stops"]
    routes = sections["routes"]
    cross = sections["cross_dataset"]
    findings: list[str] = []

    totals = ride["totals"]
    findings.append(
        f"Ridership dev subsample: {totals['total_ridership']:,} total rides across "
        f"{totals['record_count']:,} records, {totals['distinct_routes_in_ridership']} routes and "
        f"{totals['distinct_service_dates']} dates "
        f"({totals['date_range']['start']} to {totals['date_range']['end']})."
    )
    variation = ride["by_route"]["route_level_variation"]
    findings.append(
        f"Ridership is concentrated: the top 10 routes account for "
        f"{variation['top_10_routes_share_pct']}% of total ridership "
        f"(coefficient of variation {variation['coefficient_of_variation']})."
    )
    weekend = {row["day_type"]: row for row in ride["daily"]["weekday_vs_weekend"]}
    if "weekday" in weekend and "weekend" in weekend:
        findings.append(
            f"Mean daily ridership is higher on weekdays "
            f"({weekend['weekday']['mean_daily_ridership']:,}) than weekends "
            f"({weekend['weekend']['mean_daily_ridership']:,})."
        )

    overall = cj["overall_distribution"]
    findings.append(
        f"CJTP (customer-weighted) averages {overall['customer_weighted_mean']}% across "
        f"{overall['record_count']:,} records spanning "
        f"{cj['month_range']['start']} to {cj['month_range']['end']}."
    )
    periods = {row["category"]: row for row in cj["by_period"]}
    if "Peak" in periods and "Off-Peak" in periods:
        findings.append(
            f"Peak CJTP ({periods['Peak']['weighted_mean']}%) is lower than Off-Peak "
            f"({periods['Off-Peak']['weighted_mean']}%), i.e. journeys run less on-time at peak."
        )
    travel_corr = cj["relationships"]["cjtp_vs_additional_travel_time"]
    findings.append(
        f"CJTP falls as additional travel time rises (Pearson r = {travel_corr['pearson_r']}, "
        f"n = {travel_corr['n']}; association, not causation)."
    )

    findings.append(
        f"Stop network: {stops['physical_stop_inventory']['unique_physical_stops']:,} unique physical "
        f"stops across {stops['physical_stop_inventory']['total_route_stop_associations']:,} "
        f"route-stop associations."
    )
    missing_stops = stops["routes_missing_stop_associations"]["count"]
    if missing_stops:
        findings.append(
            f"{missing_stops} project route(s) have no stop associations in the cleaned data "
            "(left absent, not fabricated)."
        )

    findings.append(
        f"Route geometry: {routes['geometry_summary']['feature_count']:,} features covering "
        f"{routes['project_route_coverage']['routes_with_geometry']}/"
        f"{routes['project_route_coverage']['project_route_count']} project routes "
        f"({routes['project_route_coverage']['coverage_percentage']}%)."
    )

    rvs = cross["relationships"]["ridership_vs_stops"]
    findings.append(
        f"Across project routes, ridership vs stop count shows Pearson r = {rvs['pearson_r']} "
        f"(n = {rvs['n']}); association only."
    )
    overlap = cross["coverage_overlap"]
    findings.append(
        f"{overlap['in_all_three_datasets']}/{overlap['project_route_count']} project routes "
        f"({overlap['in_all_three_pct']}%) appear in all three of ridership, stops and CJTP."
    )
    return findings


def _limitations(sections: dict[str, Any]) -> list[str]:
    cj_cov = sections["cjtp"]["route_coverage"]
    ride_cov = sections["ridership"]["route_coverage"]
    stop_cov = sections["bus_stops"]["route_coverage"]
    limitations = [
        C.TEMPORAL_LIMITATION,
        "No 24-hour / diurnal ridership pattern is claimed; hourly totals are descriptive only "
        "(12 even-hour buckets).",
        f"Ridership covers {ride_cov.get('matching_route_count')}/{ride_cov.get('project_route_count')} "
        f"project routes; absent routes ({', '.join(ride_cov.get('project_routes_missing_from_dataset', []) or ['none'])}) "
        "carry no fabricated rows.",
        f"CJTP covers {cj_cov.get('matching_route_count')}/{cj_cov.get('project_route_count')} project "
        f"routes and has {sections['cjtp']['missing_cjtp_values']} missing CJTP value(s), excluded (not imputed).",
        f"Bus-stop associations cover {stop_cov.get('matching_route_count')}/"
        f"{stop_cov.get('project_route_count')} project routes.",
        "Route geometry is analyzed from processing_report.json metadata only; the 2.3 GB GeoJSON is "
        "not parsed, so per-feature geometry characteristics (length, vertices, bbox) are not computed.",
        "CJTP spans monthly aggregates 2017-2026 while ridership is a Jan-Feb 2023 subsample; the "
        "route-level ridership-vs-CJTP association therefore compares different time windows.",
        "All correlations are measures of association and do not imply causation.",
    ]
    if not S.have_scipy():
        limitations.append(
            "scipy is not installed, so correlation p-values are omitted; each correlation reports its "
            "sample size n so significance can still be judged."
        )
    return limitations


def _consolidated_correlations(sections: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for label, corr in (
        ("cjtp_vs_number_of_customers", sections["cjtp"]["relationships"]["cjtp_vs_number_of_customers"]),
        ("cjtp_vs_additional_travel_time", sections["cjtp"]["relationships"]["cjtp_vs_additional_travel_time"]),
        ("cjtp_vs_additional_bus_stop_time", sections["cjtp"]["relationships"]["cjtp_vs_additional_bus_stop_time"]),
        ("ridership_vs_stops", sections["cross_dataset"]["relationships"]["ridership_vs_stops"]),
        ("ridership_vs_cjtp", sections["cross_dataset"]["relationships"]["ridership_vs_cjtp"]),
        ("stops_vs_cjtp", sections["cross_dataset"]["relationships"]["stops_vs_cjtp"]),
    ):
        entry = dict(corr)
        entry["relationship"] = label
        out.append(entry)
    return out


def _outliers_summary(sections: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    catalogue = {
        "ridership": sections["ridership"]["outliers"],
        "cjtp": sections["cjtp"]["outliers"],
    }
    for group, metrics in catalogue.items():
        for metric_name, detail in metrics.items():
            rows.append(
                {
                    "group": group,
                    "metric": metric_name,
                    "method": detail.get("method"),
                    "count_evaluated": detail.get("count_evaluated"),
                    "outlier_count": detail.get("outlier_count"),
                    "outlier_percentage": detail.get("outlier_percentage"),
                    "lower_fence": detail.get("lower_fence"),
                    "upper_fence": detail.get("upper_fence"),
                }
            )
    return rows


def _validate(sections, figures, fingerprints_before, processing_report) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")

    # 1. inputs unmodified (fingerprints before vs after)
    after = fingerprint_all(list(C.IMMUTABLE_INPUTS), hash_limit_bytes=_HASH_LIMIT)
    changed = [name for name, record_ in after.items() if fingerprints_before.get(name) != record_]
    record(
        "processed_inputs_unmodified",
        not changed,
        "all inputs match pre-run fingerprints" if not changed else f"CHANGED: {changed}",
    )

    # 2. every figure rendered
    made = [fig["filename"] for fig in figures if fig.get("created")]
    record(
        "all_figures_rendered",
        len(made) == len(C.FIGURES),
        f"{len(made)}/{len(C.FIGURES)} figures created",
    )

    # 3. ridership totals reconcile with the processing report
    reported_total = (
        processing_report.get("aggregation_reports", {})
        .get("ridership_by_route", {})
        .get("total_ridership")
    )
    computed_total = sections["ridership"]["totals"]["total_ridership"]
    record(
        "ridership_total_matches_processing_report",
        reported_total is None or int(reported_total) == int(computed_total),
        f"EDA total={computed_total:,}; report total={reported_total}",
    )

    # 4. ridership internal reconciliation (clean vs by_route)
    record(
        "ridership_clean_reconciles_with_by_route",
        sections["ridership"]["totals"]["reconciles_with_by_route"],
        "clean ridership sum equals ridership_by_route sum",
    )

    # 5. coverage not inflated beyond the 142 project routes
    inflated = []
    for name in ("ridership", "cjtp", "bus_stops"):
        cov = sections[name]["route_coverage"]
        matching = _safe(cov.get("matching_route_count"), 0)
        project = _safe(cov.get("project_route_count"), C.EXPECTED_PROJECT_ROUTE_COUNT)
        if matching > project:
            inflated.append(f"{name}:{matching}/{project}")
    record(
        "route_coverage_not_inflated",
        not inflated,
        "coverage within project bounds" if not inflated else f"INFLATED: {inflated}",
    )

    # 6. route geometry not parsed
    record(
        "routes_geometry_not_parsed",
        sections["routes"]["geometry_summary"].get("geometry_parsed") is False,
        "route metadata sourced from processing_report.json; 2.3 GB GeoJSON not parsed",
    )

    passed = sum(1 for check in checks if check["passed"])
    return {
        "total_checks": len(checks),
        "passed": passed,
        "failed": len(checks) - passed,
        "all_passed": passed == len(checks),
        "checks": checks,
        "fingerprints_after": after,
    }


def build_report(datasets, reference, processing_report, warnings, fingerprints_before) -> dict[str, Any]:
    """Assemble every analysis section plus figures and the consolidated report."""
    sections: dict[str, Any] = {}
    sections["ridership"] = ridership_eda.analyze(datasets, reference, warnings)
    sections["cjtp"] = cjtp_eda.analyze(datasets, reference, warnings)
    sections["bus_stops"] = stops_eda.analyze(datasets, reference, warnings)
    sections["routes"] = routes_eda.analyze(processing_report, reference, warnings)
    sections["cross_dataset"] = cross_dataset.analyze(datasets, reference, warnings)

    merged = sections["cross_dataset"].pop("_merged")

    # figures (lazy import so a missing matplotlib gives a clean message)
    from . import figures as figures_module

    figure_results = figures_module.render_all(datasets, merged, C.EDA_DIR, warnings)

    validation = _validate(sections, figure_results, fingerprints_before, processing_report)

    descriptive = {
        "ridership_per_record": sections["ridership"]["descriptive_statistics"]["per_record_ridership"],
        "total_ridership_per_route": sections["ridership"]["descriptive_statistics"]["per_route_total_ridership"],
        "daily_total_ridership": sections["ridership"]["descriptive_statistics"]["daily_total_ridership"],
        "cjtp_overall": sections["cjtp"]["overall_distribution"],
        "additional_travel_time": sections["cjtp"]["additional_travel_time"],
        "additional_bus_stop_time": sections["cjtp"]["additional_bus_stop_time"],
        "unique_stops_per_route": sections["bus_stops"]["stops_by_route"]["unique_stops_per_route"],
    }

    route_coverage = {
        "project_route_count": C.EXPECTED_PROJECT_ROUTE_COUNT,
        "ridership": sections["ridership"]["route_coverage"],
        "cjtp": sections["cjtp"]["route_coverage"],
        "bus_stops": sections["bus_stops"]["route_coverage"],
        "routes_geometry": sections["routes"]["project_route_coverage"],
        "overlap_across_datasets": sections["cross_dataset"]["coverage_overlap"],
    }

    source_datasets_used = [
        {"name": name, "path": str(path), "row_count": int(len(datasets[name]))}
        for name, path in C.PARQUET_INPUTS.items()
    ]
    source_datasets_used.append(
        {"name": "routes_clean.geojson", "path": str(C.ROUTES_CLEAN),
         "usage": "metadata only (feature count/CRS/coverage from processing_report.json); not parsed"}
    )
    source_datasets_used.append(
        {"name": "processing_report.json", "path": str(C.PROCESSING_REPORT),
         "usage": "route geometry metadata + reconciliation"}
    )

    return {
        "analyses": sections,
        "descriptive_statistics": descriptive,
        "major_findings": _major_findings(sections),
        "outliers_summary": _outliers_summary(sections),
        "route_coverage": route_coverage,
        "important_correlations": _consolidated_correlations(sections),
        "figures": figure_results,
        "limitations": _limitations(sections),
        "source_datasets_used": source_datasets_used,
        "validation": validation,
    }


def main() -> int:
    started = time.perf_counter()
    start_wall = datetime.now(timezone.utc)
    print("=" * 72)
    print("Phase 4 - Exploratory Data Analysis (EDA)")
    print(f"Started: {start_wall.isoformat()}")
    print("=" * 72)

    absent = io_utils.missing_inputs()
    if absent:
        print(f"ERROR: required processed input(s) missing: {absent}")
        return 2

    warnings = WarningCollector()

    print("\n[setup] fingerprinting processed inputs (proves they are not modified)")
    fingerprints_before = fingerprint_all(
        list(C.IMMUTABLE_INPUTS), hash_limit_bytes=_HASH_LIMIT
    )

    print("[setup] loading route reference + processing report")
    reference, _profile = load_route_reference(C.PROFILING_REPORT, C.ROUTES_VALID_REPORT)
    processing_report = io_utils.load_processing_report()

    print("[setup] loading processed datasets (parquet)")
    try:
        datasets = io_utils.load_datasets()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR loading datasets: {exc}")
        traceback.print_exc()
        return 2

    try:
        report_body = build_report(datasets, reference, processing_report, warnings, fingerprints_before)
    except ImportError as exc:
        print(
            "\nERROR: matplotlib is required for Phase 4 figures but is not installed.\n"
            "Install it into the project environment and rerun:\n"
            '    "C:\\Users\\aksha\\Downloads\\datahandling capstone\\.venv\\Scripts\\python.exe" '
            "-m pip install matplotlib\n"
            f"(import error: {exc})"
        )
        return 2
    except Exception as exc:  # noqa: BLE001
        print("\nERROR during analysis:")
        traceback.print_exc()
        failure = {
            "phase": "Phase 4 - Exploratory Data Analysis (EDA)",
            "status": "failed",
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "traceback": traceback.format_exc(),
            "started_utc": start_wall.isoformat(),
            "warnings": warnings.to_list(),
        }
        try:
            write_json_atomic(json_safe(failure), C.EDA_REPORT)
        except Exception:  # noqa: BLE001
            print("Could not write failure report.")
        return 1

    elapsed = time.perf_counter() - started
    validation = report_body["validation"]
    report = {
        "phase": "Phase 4 - Exploratory Data Analysis (EDA)",
        "status": "completed" if validation["all_passed"] else "completed_with_failures",
        "started_utc": start_wall.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "environment": _environment(),
        "reproducibility": {
            "deterministic": True,
            "randomness_used": False,
            "inputs_read_only": True,
            "outputs": ["data/processed/eda/*.png", "data/processed/eda_report.json"],
            "note": (
                "stats/figures are deterministic across runs on the same input + library versions; "
                "only the wall-clock timestamps in this report vary between runs"
            ),
        },
        "warnings": warnings.to_list(),
        "warning_count": len(warnings.to_list()),
        "constraints_observed": [
            "only Phase 3 processed datasets were read",
            "nothing downloaded; data/raw untouched; Phase 3 pipeline unmodified",
            "processed datasets not modified (proven by before/after fingerprints)",
            "2.3 GB routes_clean.geojson never parsed (metadata from processing_report.json)",
            "no fabricated or imputed data; missing routes/values left absent",
            "no 24-hour ridership pattern claimed; bootstrap analysis deferred to a later phase",
            "dashboard (Phase 5) not started",
        ],
    }
    report.update(report_body)

    write_json_atomic(json_safe(report), C.EDA_REPORT)

    figures_made = sum(1 for fig in report_body["figures"] if fig.get("created"))
    print("\n" + "=" * 72)
    print(f"Phase 4 {report['status'].upper()} in {elapsed:.1f}s")
    print(f"Figures: {figures_made}/{len(C.FIGURES)} in {C.EDA_DIR}")
    print(f"Validation: {validation['passed']}/{validation['total_checks']} checks passed")
    if validation["failed"]:
        print(f"Failed checks: {[c['check'] for c in validation['checks'] if not c['passed']]}")
    print(f"Warnings: {len(warnings.to_list())}")
    print(f"Report: {C.EDA_REPORT}")
    print("=" * 72)
    return 0 if validation["all_passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
