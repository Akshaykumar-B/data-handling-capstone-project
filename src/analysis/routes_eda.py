"""Route EDA (pure, metadata-only).

The 2.3 GB ``routes_clean.geojson`` is NEVER parsed here (consistent with the
Phase 3 strategy). Every figure below is read from the Phase 3
``processing_report.json`` (feature count, CRS, geometry type, coverage) and the
route reference (project routes, aliases). Per-feature geometry characteristics
(shape_length, vertex counts, bounding boxes) exist as properties inside the
GeoJSON but are intentionally not scanned; computing them would require a full-
file parse and adds no value to the project-scoped analysis.

Service categories are derived from the route-id NAMING CONVENTION (a heuristic,
clearly labelled) plus the CJTP trip_type dimension, since the authoritative
route_type property lives only in the unparsed geometry file.
"""

from __future__ import annotations

import re
from typing import Any

from . import eda_config as C
from . import stats_utils as S
from ..processing.reference import RouteReference

_EXPRESS_PREFIX = re.compile(r"^(BM|BXM|QM|SIM|X)\d")


def _service_category(route_id: str) -> str:
    upper = route_id.upper()
    if "SBS" in upper or upper.endswith("+"):
        return "Select Bus Service (SBS)"
    if _EXPRESS_PREFIX.match(upper):
        return "Express / Commuter"
    return "Local / Limited"


def _borough_prefix(route_id: str) -> str:
    upper = route_id.upper()
    for prefix, name in (
        ("BX", "Bronx"), ("BM", "Brooklyn (express)"), ("B", "Brooklyn"),
        ("M", "Manhattan"), ("QM", "Queens (express)"), ("Q", "Queens"),
        ("SIM", "Staten Island (express)"), ("S", "Staten Island"),
    ):
        if upper.startswith(prefix):
            return name
    return "Other"


def analyze(
    processing_report: dict,
    reference: RouteReference,
    warnings,
) -> dict[str, Any]:
    routes_report = processing_report.get("dataset_reports", {}).get("routes", {})
    ref_report = processing_report.get("route_reference", {})

    feature_count = routes_report.get("output_feature_count")
    if feature_count != C.EXPECTED_ROUTE_FEATURES:
        warnings.add(
            "routes",
            f"routes feature count in report ({feature_count}) != expected "
            f"{C.EXPECTED_ROUTE_FEATURES}",
        )

    output_size = routes_report.get("output_size_bytes")
    geometry_summary = {
        "feature_count": feature_count,
        "unique_route_id_values": routes_report.get("unique_route_id_values"),
        "unique_route_short_name_values": routes_report.get("unique_route_short_name_values"),
        "geometry_type": routes_report.get("output_geometry_type"),
        "crs": routes_report.get("output_crs"),
        "output_size_bytes": output_size,
        "output_size_gb": S._round(output_size / 1024 ** 3) if output_size else None,
        "reader": routes_report.get("reader"),
        "geometry_parsed": routes_report.get("geometry_parsed", False),
        "source": "processing_report.json (authoritative Phase 2/3 metadata; file not re-scanned)",
    }

    geometry_characteristics = {
        "computed": False,
        "reason": (
            "per-feature geometry metrics (shape_length, vertex counts, bounding boxes) "
            "require a full parse of the 2.3 GB GeoJSON; skipped by design (Phase 3 reuses "
            "the file via a filesystem hard link and never decodes geometry)"
        ),
        "available_in_source_properties": [
            "shape_length", "vertices", "min_longitude", "min_latitude",
            "max_longitude", "max_latitude",
        ],
        "recommendation": (
            "if geometry metrics become necessary later, extract them with a bounded "
            "streaming reader over selected features rather than a whole-file load"
        ),
    }

    coverage = routes_report.get("route_coverage_vs_project_reference", {})

    # --- service categories (derived from naming convention) ---------------
    project_routes = sorted(reference.project_routes)
    category_counts: dict[str, int] = {}
    borough_counts: dict[str, int] = {}
    for route in project_routes:
        category_counts[_service_category(route)] = category_counts.get(_service_category(route), 0) + 1
        borough_counts[_borough_prefix(route)] = borough_counts.get(_borough_prefix(route), 0) + 1
    service_categories = {
        "basis": "derived from route-id naming convention (heuristic) - NOT the geometry route_type property",
        "by_service_type": [
            {"category": name, "route_count": count}
            for name, count in sorted(category_counts.items())
        ],
        "by_borough_prefix": [
            {"borough": name, "route_count": count}
            for name, count in sorted(borough_counts.items())
        ],
    }

    aliases = ref_report.get("known_aliases", [])

    return {
        "dataset": "routes_clean.geojson (metadata only; never parsed)",
        "geometry_summary": geometry_summary,
        "geometry_characteristics": geometry_characteristics,
        "project_route_coverage": {
            "project_route_count": ref_report.get("project_route_count"),
            "routes_with_geometry": coverage.get("matching_route_count"),
            "coverage_percentage": coverage.get("coverage_percentage"),
            "project_routes_missing_geometry": coverage.get("project_routes_missing_from_dataset", []),
        },
        "route_aliases": {
            "count": ref_report.get("known_alias_count"),
            "pairs": aliases,
            "note": "aliases were canonicalized during Phase 3 (e.g. B44+ -> B44-SBS)",
        },
        "service_categories": service_categories,
    }
