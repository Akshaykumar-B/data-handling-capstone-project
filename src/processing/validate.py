"""Post-run validation for the Phase 3 outputs.

Checks are additive and non-destructive: every check records a pass/fail plus
enough detail to explain itself in ``processing_report.json``. Validation never
edits data. Raw-input immutability is proven by comparing fingerprints taken
before and after processing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from . import config
from .reference import RouteReference


class CheckList:
    """Collects named pass/fail checks."""

    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def record(self, name: str, passed: bool, detail: str, **extra: Any) -> bool:
        entry: dict[str, Any] = {"check": name, "passed": bool(passed), "detail": detail}
        entry.update(extra)
        self.checks.append(entry)
        marker = "PASS" if passed else "FAIL"
        print(f"  [{marker}] {name}: {detail}")
        return bool(passed)

    @property
    def failures(self) -> list[dict[str, Any]]:
        return [entry for entry in self.checks if not entry["passed"]]

    def summary(self) -> dict[str, Any]:
        return {
            "total_checks": len(self.checks),
            "passed": sum(1 for entry in self.checks if entry["passed"]),
            "failed": len(self.failures),
            "all_passed": not self.failures,
            "checks": self.checks,
            "failed_checks": [entry["check"] for entry in self.failures],
        }


def _row_count(path: Path) -> int:
    """Row count of a parquet file read via metadata only where possible."""
    try:
        import pyarrow.parquet as pq

        return int(pq.ParquetFile(path).metadata.num_rows)
    except Exception:  # pragma: no cover - fallback for unusual pyarrow builds
        return int(len(pd.read_parquet(path)))


def validate_outputs(
    reference: RouteReference,
    raw_fingerprints_before: dict[str, dict[str, Any]],
    dataset_reports: dict[str, Any],
    aggregation_reports: dict[str, Any],
) -> dict[str, Any]:
    """Run every Phase 3 validation check and return a structured summary."""
    from .utils import fingerprint_all

    checks = CheckList()

    # --- 1. every declared output exists and is non-empty ------------------
    for path in config.OUTPUT_PATHS:
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        checks.record(
            f"output_exists:{path.name}",
            exists and size > 0,
            f"{'present' if exists else 'MISSING'}, {size:,} bytes",
            size_bytes=size,
        )

    # --- 2. no stray temporary files left behind --------------------------
    leftovers = sorted(item.name for item in config.PROCESSED_DIR.glob("*.tmp.*"))
    checks.record(
        "no_temporary_files_left",
        not leftovers,
        "no .tmp outputs remain" if not leftovers else f"leftover temp files: {leftovers}",
        leftover_files=leftovers,
    )

    # --- 3. record counts preserved through cleaning -----------------------
    for label, key in (
        ("ridership", "ridership"),
        ("bus_stops", "bus_stops"),
        ("customer_journey", "customer_journey"),
    ):
        report = dataset_reports.get(key, {})
        input_rows = report.get("input_row_count")
        output_rows = report.get("output_row_count")
        checks.record(
            f"row_count_preserved:{label}",
            input_rows is not None and input_rows == output_rows,
            f"input {input_rows} -> output {output_rows} (excluded {report.get('rows_excluded')})",
            input_row_count=input_rows,
            output_row_count=output_rows,
        )

    # --- 4. cleaned parquet files match their reported counts -------------
    for path, key in (
        (config.RIDERSHIP_CLEAN, "ridership"),
        (config.STOPS_CLEAN, "bus_stops"),
        (config.CJTP_CLEAN, "customer_journey"),
    ):
        if not path.exists():
            continue
        on_disk = _row_count(path)
        reported = dataset_reports.get(key, {}).get("output_row_count")
        checks.record(
            f"on_disk_row_count:{path.name}",
            reported is not None and on_disk == reported,
            f"{on_disk} rows on disk vs {reported} reported",
            on_disk_row_count=on_disk,
        )

    # --- 5. routes GeoJSON: reused pre-validated source (NO geometry scan) --
    # Feature count / CRS / geometry type are taken from the authoritative Phase
    # 2 report (surfaced in routes_report), never from a fresh full-file scan.
    # pyogrio.read_info() on a 2.3 GB GeoJSON is a full parse, so it is not used
    # here. Completeness is proven cheaply via a byte-size comparison plus a few
    # KB read from each end of the file.
    if config.ROUTES_CLEAN.exists():
        routes_report = dataset_reports.get("routes", {})

        report_feature_count = routes_report.get("output_feature_count")
        checks.record(
            "routes_feature_count_preserved",
            report_feature_count == config.EXPECTED_ROUTE_FEATURES,
            f"{report_feature_count} features per authoritative report "
            f"(expected {config.EXPECTED_ROUTE_FEATURES:,}); not re-scanned",
            feature_count=report_feature_count,
        )
        crs_text = str(routes_report.get("output_crs"))
        checks.record(
            "routes_crs_is_wgs84",
            "4326" in crs_text or "CRS84" in crs_text.upper(),
            f"output CRS preserved as {crs_text}",
            crs=crs_text,
        )
        geometry_type = str(routes_report.get("output_geometry_type"))
        checks.record(
            "routes_geometry_type_multilinestring",
            "MULTILINESTRING" in geometry_type.upper(),
            f"geometry type reported as {geometry_type}",
            geometry_type=geometry_type,
        )
        checks.record(
            "routes_no_features_discarded",
            routes_report.get("features_excluded") == 0,
            f"{routes_report.get('features_excluded')} feature(s) excluded",
        )
        checks.record(
            "routes_no_simplification",
            routes_report.get("simplification_applied") is False
            and routes_report.get("coordinate_rounding_applied") is False,
            "no simplification or coordinate rounding was applied",
        )
        checks.record(
            "routes_full_file_read_avoided",
            routes_report.get("gpd_read_file_used") is False
            and routes_report.get("read_info_called_on_output") is False,
            f"reader used: {routes_report.get('reader')}",
        )

        # Completeness proof without a geometry scan: the hard-linked output
        # must have exactly the same size as the untouched validated source.
        if config.ROUTES_RAW.exists():
            source_size = config.ROUTES_RAW.stat().st_size
            output_size = config.ROUTES_CLEAN.stat().st_size
            checks.record(
                "routes_output_size_matches_source",
                source_size == output_size,
                f"output {output_size:,} bytes vs source {source_size:,} bytes",
                source_size_bytes=source_size,
                output_size_bytes=output_size,
            )

        # Cheap structural checks: a few KB from each end of the file only.
        with config.ROUTES_CLEAN.open("rb") as handle:
            head = handle.read(4096).decode("utf-8", errors="replace")
            file_size = config.ROUTES_CLEAN.stat().st_size
            handle.seek(max(0, file_size - 256))
            tail = handle.read().decode("utf-8", errors="replace").rstrip()
        head_ok = (
            head.lstrip().startswith("{")
            and '"type": "FeatureCollection"' in head
            and ("CRS84" in head.upper() or "4326" in head)
            and '"features"' in head
            and '"type": "Feature"' in head
        )
        tail_ok = tail.endswith("}") and "]" in tail[-12:]
        checks.record(
            "routes_geojson_envelope_wellformed",
            head_ok and tail_ok,
            "FeatureCollection header + CRS + first Feature present and file terminates "
            "cleanly"
            if head_ok and tail_ok
            else f"head_ok={head_ok} tail_ok={tail_ok}; tail={tail[-40:]!r}",
        )

    # --- 6. aggregation reconciliation ------------------------------------
    if config.RIDERSHIP_CLEAN.exists() and config.RIDERSHIP_BY_ROUTE.exists():
        clean_total = float(
            pd.read_parquet(config.RIDERSHIP_CLEAN, columns=["ridership"])["ridership"].sum()
        )
        by_route_total = float(
            pd.read_parquet(config.RIDERSHIP_BY_ROUTE, columns=["total_ridership"])[
                "total_ridership"
            ].sum()
        )
        by_date_total = float(
            pd.read_parquet(config.RIDERSHIP_BY_DATE, columns=["total_ridership"])[
                "total_ridership"
            ].sum()
        )
        by_hour_total = float(
            pd.read_parquet(config.RIDERSHIP_BY_HOUR, columns=["total_ridership"])[
                "total_ridership"
            ].sum()
        )
        tolerance = 1e-6
        checks.record(
            "ridership_totals_reconcile",
            abs(clean_total - by_route_total) < tolerance
            and abs(clean_total - by_date_total) < tolerance
            and abs(clean_total - by_hour_total) < tolerance,
            f"clean={clean_total} by_route={by_route_total} "
            f"by_date={by_date_total} by_hour={by_hour_total}",
            clean_total=clean_total,
            by_route_total=by_route_total,
            by_date_total=by_date_total,
            by_hour_total=by_hour_total,
        )

    # --- 7. no fabricated routes anywhere ---------------------------------
    for key, label in (
        ("ridership", "ridership"),
        ("bus_stops", "bus_stops"),
        ("customer_journey", "customer_journey"),
        ("routes", "routes"),
    ):
        coverage = dataset_reports.get(key, {}).get("route_coverage_vs_project_reference", {})
        matching = coverage.get("matching_route_count")
        project_total = coverage.get("project_route_count")
        checks.record(
            f"route_coverage_not_inflated:{label}",
            matching is not None
            and project_total is not None
            and matching <= project_total,
            f"{matching}/{project_total} project routes present "
            f"({coverage.get('coverage_percentage')}%)",
            missing_project_routes=coverage.get("project_routes_missing_from_dataset"),
        )

    # --- 8. alias map fully applied ---------------------------------------
    alias_sources = set(reference.alias_map)
    residual: dict[str, list[str]] = {}
    for path, column, label in (
        (config.RIDERSHIP_CLEAN, "route_id", "ridership"),
        (config.STOPS_CLEAN, "route_id_canonical", "bus_stops"),
        (config.CJTP_CLEAN, "route_id_canonical", "customer_journey"),
    ):
        if not path.exists():
            continue
        values = set(pd.read_parquet(path, columns=[column])[column].dropna().unique())
        leftover = sorted(str(value) for value in values & alias_sources)
        if leftover:
            residual[label] = leftover
    checks.record(
        "aliases_canonicalized_everywhere",
        not residual,
        "no un-canonicalized alias identifiers remain in the cleaned datasets"
        if not residual
        else f"alias identifiers still present: {residual}",
        residual_aliases=residual,
    )

    # --- 9. raw inputs untouched ------------------------------------------
    after = fingerprint_all(config.RAW_INPUTS, hash_limit_bytes=config.HASH_SIZE_LIMIT_BYTES)
    changed = [
        name
        for name, record in after.items()
        if raw_fingerprints_before.get(name) != record
    ]
    checks.record(
        "raw_inputs_unmodified",
        not changed,
        "all raw inputs match their pre-run fingerprints"
        if not changed
        else f"raw input(s) changed during processing: {changed}",
        changed_files=changed,
    )

    # --- 10. every aggregation table produced rows ------------------------
    for name, report in aggregation_reports.items():
        row_count = report.get("row_count", 0)
        checks.record(
            f"aggregation_non_empty:{name}",
            row_count > 0,
            f"{row_count} rows",
            row_count=row_count,
        )

    summary = checks.summary()
    summary["raw_input_fingerprints_after"] = after
    return summary
