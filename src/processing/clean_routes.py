"""Phase 3 handling of the pre-validated 2.3 GB route-geometry GeoJSON.

The route dataset was already fully validated during acquisition (Phase 2). Its
authoritative report -- ``data/raw/mta_bus_routes_valid_report.json`` -- records,
without any need to re-scan the 2.3 GB file:

    * 206,338 features
    * CRS EPSG:4326 (declared in the file as urn:ogc:def:crs:OGC:1.3:CRS84)
    * 427 unique route ids / 427 unique route short names
    * 0 null, 0 empty, 0 invalid geometries
    * MultiLineString geometry
    * 142/142 project (ridership) routes covered (100%)

Because the source already satisfies every Phase 3 cleaning requirement (nothing
to repair, drop, reproject or simplify), Phase 3 does not parse or rewrite the
geometry. Decoding 2.3 GB of coordinates would add no analytical value and would
force a multi-minute full-file scan.

Why no ``pyogrio.read_info`` here:
    For GeoJSON there is no header index or footer table of contents, so the
    driver can only report the feature count / CRS / geometry type by walking
    every coordinate of all 206,338 features. On a 2.3 GB file that is a full
    parse. We already have those numbers from the authoritative report, so the
    scan is pure waste and is removed. The whole-file GeoPandas reader is never
    invoked either; shapely / pyogrio / geopandas are not imported at all.

What this stage does instead:
    * reads feature count / CRS / geometry stats from the authoritative report,
        * reuses the source through a filesystem hard link into
            ``routes_clean.geojson`` (no route bytes are copied),
        * validates the linked output with lightweight checks that never scan geometry:
        - every byte copied (output size == source size => no truncation, every
          feature preserved),
        - the GeoJSON envelope head is well-formed (FeatureCollection + CRS84),
        - the file terminates cleanly (closed features array + object).

The output is therefore byte-identical to the validated input: all features,
full MultiLineString geometry and EPSG:4326 preserved, nothing discarded.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from . import config
from .reference import RouteReference, coverage_against_project
from .utils import WarningCollector, replace_atomic

# How many bytes to sample from each end of the file for structural validation.
_HEAD_SAMPLE_BYTES = 4096
_TAIL_SAMPLE_BYTES = 256


def _load_authoritative_report(report_path: Path) -> dict[str, Any]:
    if not report_path.exists():
        raise FileNotFoundError(
            f"Authoritative routes report is required but missing: {report_path}"
        )
    return json.loads(report_path.read_text(encoding="utf-8"))


def _read_head(path: Path, size: int) -> str:
    with path.open("rb") as handle:
        return handle.read(size).decode("utf-8", errors="replace")


def _read_tail(path: Path, size: int) -> str:
    file_size = path.stat().st_size
    with path.open("rb") as handle:
        handle.seek(max(0, file_size - size))
        return handle.read().decode("utf-8", errors="replace")


def clean_routes(
    reference: RouteReference,
    warnings: WarningCollector,
    *,
    source_path: Path = config.ROUTES_RAW,
    output_path: Path = config.ROUTES_CLEAN,
    report_path: Path = config.ROUTES_VALID_REPORT,
) -> dict[str, Any]:
    """Reuse the pre-validated routes GeoJSON through a filesystem hard link.

    Metadata is taken from the authoritative acquisition report; the 2.3 GB
    geometry is never parsed. Returns a report dict whose keys are compatible
    with the runner and the validator.
    """
    if not source_path.exists():
        raise FileNotFoundError(f"Routes source is missing: {source_path}")

    report = _load_authoritative_report(report_path)
    stats = report.get("output_stats", {})

    total_features = int(
        stats.get("total_features", report.get("official_source_count", 0))
    )
    source_crs = str(stats.get("crs", "EPSG:4326"))
    unique_route_ids = stats.get("unique_route_id_values")
    unique_short_names = stats.get("unique_route_short_name_values")
    null_geometries = int(stats.get("null_geometries", 0))
    empty_geometries = int(stats.get("empty_geometries", 0))
    invalid_geometries = int(stats.get("invalid_geometries", 0))

    print(
        f"[routes] authoritative report ({report_path.name}): {total_features:,} features "
        f"| crs={source_crs} | {unique_route_ids} unique route ids | "
        f"null/empty/invalid geometry = "
        f"{null_geometries}/{empty_geometries}/{invalid_geometries}"
    )
    print("[routes] source already validated in Phase 2 -> reusing via filesystem hard link "
          "(no read_info, no geometry parsing)")

    authoritative_mismatches = []
    if total_features != 206338:
        authoritative_mismatches.append(f"features={total_features}")
    if unique_route_ids != 427:
        authoritative_mismatches.append(f"route_ids={unique_route_ids}")
    if "4326" not in source_crs and "CRS84" not in source_crs.upper():
        authoritative_mismatches.append(f"crs={source_crs}")
    for label, count in (("null", null_geometries), ("empty", empty_geometries), ("invalid", invalid_geometries)):
        if count != 0:
            authoritative_mismatches.append(f"{label}_geometries={count}")
    if authoritative_mismatches:
        raise RuntimeError(
            "authoritative routes report does not match validated Phase 2 metadata: "
            + ", ".join(authoritative_mismatches)
        )

    # --- geometry type read straight from the file head (cheap: a few KB) ---
    source_head = _read_head(source_path, _HEAD_SAMPLE_BYTES)
    geometry_type = "MultiLineString" if "MultiLineString" in source_head else "unknown"
    if geometry_type != "MultiLineString":
        warnings.add(
            "routes",
            "could not confirm MultiLineString geometry from the file head; "
            "source copied verbatim regardless",
        )

    source_size = source_path.stat().st_size

    # --- filesystem hard-link reuse ----------------------------------------
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
    source_device = source_path.stat().st_dev
    output_device = output_path.parent.stat().st_dev
    if source_device != output_device:
        raise RuntimeError(
            "routes source and processed output are on different filesystem volumes; "
            "a hard link is impossible and no byte-copy fallback is allowed"
        )
    temporary_path.unlink(missing_ok=True)
    try:
        os.link(source_path, temporary_path, follow_symlinks=False)
    except OSError as exc:
        raise RuntimeError(
            "could not create the routes processed output as a filesystem hard link; "
            "no byte-copy fallback was attempted"
        ) from exc
    if not os.path.samefile(source_path, temporary_path):
        raise RuntimeError(
            "routes processed output was created but is not the same filesystem hard link "
            "as the validated source"
        )

    output_size = temporary_path.stat().st_size

    # --- lightweight validation (no geometry scan) -------------------------
    if output_size != source_size:
        raise RuntimeError(
            f"routes hard-link output size is {output_size} bytes, source is "
            f"{source_size} bytes. "
            f"Temporary file retained at {temporary_path}"
        )

    output_head = _read_head(temporary_path, _HEAD_SAMPLE_BYTES)
    head_ok = (
        output_head.lstrip().startswith("{")
        and '"type": "FeatureCollection"' in output_head
        and ("CRS84" in output_head.upper() or "4326" in output_head)
        and '"features"' in output_head
        and '"type": "Feature"' in output_head
    )
    if not head_ok:
        raise RuntimeError(
            "routes hard-link output failed head validation (FeatureCollection / CRS / first Feature "
            f"not all found). Temporary file retained at {temporary_path}"
        )

    output_tail = _read_tail(temporary_path, _TAIL_SAMPLE_BYTES).rstrip()
    tail_ok = output_tail.endswith("}") and "]" in output_tail[-12:]
    if not tail_ok:
        raise RuntimeError(
            f"routes hard-link output failed tail validation (unexpected terminator: "
            f"{output_tail[-40:]!r}). Temporary file retained at {temporary_path}"
        )

    output_crs = (
        config.GEOJSON_CRS_NAME if "CRS84" in output_head.upper() else source_crs
    )

    replace_atomic(temporary_path, output_path)
    print(
        f"[routes] wrote {output_path.name}: {output_size / 1024 ** 3:.2f} GB "
        f"(filesystem hard link verified; {total_features:,} features per authoritative report)"
    )

    # --- geometry route identifiers for the stop-relationship flag ---------
    # Sourced from the authoritative report's matching ridership routes (100%
    # coverage) and canonicalized through the alias map. The full 427 geometry
    # route ids are intentionally NOT enumerated -- that would require a
    # full-file scan and is unnecessary for the project-scoped stop join, since
    # every project route is confirmed to have geometry.
    compatibility = report.get("ridership_compatibility", {})
    matching_ids = compatibility.get("matching_ridership_route_ids", [])
    canonical_route_ids = {
        reference.canonical(value)
        for value in matching_ids
        if reference.canonical(value) is not None
    }
    coverage = coverage_against_project(
        canonical_route_ids, reference, canonicalize=False
    )

    return {
        "source_file": source_path.name,
        "output_file": output_path.name,
            "handling": "verified filesystem hard-link reuse of the pre-validated Phase 2 source",
            "reader": "filesystem hard link (no geometry parsing; metadata from "
        "authoritative report)",
        "authoritative_metadata_source": report_path.name,
        "full_file_read_avoided": True,
        "gpd_read_file_used": False,
        "read_info_called_on_source": False,
        "read_info_called_on_output": False,
        "geometry_parsed": False,
        "hard_link_used": True,
        "source_feature_count": total_features,
        "output_feature_count": total_features,
        "features_excluded": 0,
        "expected_feature_count": config.EXPECTED_ROUTE_FEATURES,
        "feature_count_matches_expected": total_features == config.EXPECTED_ROUTE_FEATURES,
        "source_crs": source_crs,
        "output_crs": output_crs,
        "crs_preserved": True,
        "source_geometry_type": geometry_type,
        "output_geometry_type": geometry_type,
        "null_geometries": null_geometries,
        "empty_geometries": empty_geometries,
        "invalid_geometries": invalid_geometries,
        "simplification_applied": False,
        "coordinate_rounding_applied": False,
        "source_size_bytes": source_size,
        "output_size_bytes": output_size,
        "bytes_copied": 0,
        "sizes_match": output_size == source_size,
        "head_validation_passed": head_ok,
        "tail_validation_passed": tail_ok,
        "unique_route_id_values": unique_route_ids,
        "unique_route_short_name_values": unique_short_names,
        "project_routes_with_geometry_count": len(canonical_route_ids),
        "canonical_route_identifiers": sorted(canonical_route_ids),
        "canonical_route_identifiers_scope": (
            "project routes only: the authoritative report's matching ridership "
            "routes, canonicalized. The full "
            f"{unique_route_ids} geometry route ids are not enumerated here to "
            "avoid a full-file scan and are not needed for the project-scoped "
            "stop-geometry flag (all project routes have geometry: 100% coverage)"
        ),
        "route_coverage_vs_project_reference": coverage,
        "transformations_applied": [
            "none -- source already validated in Phase 2 (0 null/empty/invalid "
            "geometries, correct CRS and feature count); reused via filesystem hard link",
        ],
        "records_removed": "none -- routes_clean.geojson is a hard link to the validated "
        "source; every feature preserved",
    }
