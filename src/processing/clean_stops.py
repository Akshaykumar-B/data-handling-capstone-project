"""Clean the MTA bus-stops parquet (route/stop associations).

The raw table is one row per (route, stop, direction) association. Cleaning is
deterministic and non-destructive:
  * coordinate columns coerced to numeric and range-checked (never dropped)
  * route identifiers normalized + alias-canonicalized while originals persist
  * whitespace trimmed on text columns
  * duplicate associations measured on the documented key, not removed

The known 129-of-142 ridership coverage is measured and reported; no stop rows
are fabricated for the routes that legitimately have no stop associations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from . import config
from .reference import RouteReference, coverage_against_project
from .utils import (
    WarningCollector,
    describe_missing,
    normalized_route_set,
    replace_atomic,
)

# New-York-City bounding box used only to *flag* out-of-range coordinates.
_LAT_MIN, _LAT_MAX = 40.3, 41.1
_LON_MIN, _LON_MAX = -74.3, -73.6


def clean_stops(
    reference: RouteReference,
    warnings: WarningCollector,
    *,
    source_path: Path = config.STOPS_RAW,
    output_path: Path = config.STOPS_CLEAN,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Clean the bus-stops dataset and write ``bus_stops_clean.parquet``."""
    print(f"[stops] reading {source_path.name}")
    frame = pd.read_parquet(source_path)
    input_rows = len(frame)
    source_columns = [str(column) for column in frame.columns]

    # --- coordinates ------------------------------------------------------
    coordinate_issues = 0
    for column in ("latitude", "longitude"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    if {"latitude", "longitude"}.issubset(frame.columns):
        out_of_range = (
            (frame["latitude"] < _LAT_MIN)
            | (frame["latitude"] > _LAT_MAX)
            | (frame["longitude"] < _LON_MIN)
            | (frame["longitude"] > _LON_MAX)
        )
        coordinate_issues = int(out_of_range.fillna(False).sum())
        if coordinate_issues:
            warnings.add(
                "stops",
                f"{coordinate_issues} stop(s) fall outside the NYC bounding box — "
                "flagged for review, rows retained unchanged",
            )

    # --- route identifiers ------------------------------------------------
    alias_applied = 0
    if "route_id" in frame.columns:
        frame["route_id"] = frame["route_id"].astype("string").str.strip().str.upper()
        frame["route_id"] = frame["route_id"].replace({"": pd.NA})
        canonical = frame["route_id"].map(
            lambda value: reference.canonical(value) if pd.notna(value) else pd.NA
        )
        alias_applied = int((frame["route_id"].notna() & (canonical != frame["route_id"])).sum())
        frame["route_id_canonical"] = canonical.astype("string")
    else:
        frame["route_id_canonical"] = pd.Series(pd.NA, index=frame.index, dtype="string")

    if "route_short_name" in frame.columns:
        frame["route_short_name"] = (
            frame["route_short_name"].astype("string").str.strip().str.upper()
        )

    # --- whitespace tidy on remaining text columns ------------------------
    text_columns = [
        "route_long_name",
        "route_description",
        "stop_name",
        "direction",
        "bundle",
        "in_effect",
        "revenue_stop",
        "timepoint",
    ]
    for column in text_columns:
        if column in frame.columns:
            frame[column] = frame[column].astype("string").str.strip()

    # --- typed identifiers ------------------------------------------------
    if "stop_id" in frame.columns:
        frame["stop_id"] = frame["stop_id"].astype("string").str.strip()
    if "direction_id" in frame.columns:
        frame["direction_id"] = pd.to_numeric(frame["direction_id"], errors="coerce").astype(
            "Int8"
        )

    # --- duplicate accounting (measured, not removed) ---------------------
    key_columns = [
        column for column in config.STOP_ASSOCIATION_COLUMNS if column in frame.columns
    ]
    duplicate_associations = 0
    if key_columns:
        duplicate_associations = int(frame.duplicated(subset=key_columns, keep="first").sum())
        if duplicate_associations:
            warnings.add(
                "stops",
                f"{duplicate_associations} duplicate route/stop association(s) retained "
                f"on key {key_columns}",
            )

    # --- deterministic ordering ------------------------------------------
    sort_columns = [
        column
        for column in ("route_id_canonical", "route_id", "direction_id", "stop_id")
        if column in frame.columns
    ]
    if sort_columns:
        frame = frame.sort_values(sort_columns, kind="mergesort", na_position="last")
    frame = frame.reset_index(drop=True)

    # --- coverage vs. the authoritative reference -------------------------
    observed_routes = normalized_route_set(frame["route_id_canonical"].dropna().unique())
    coverage = coverage_against_project(observed_routes, reference)
    if coverage["project_routes_missing_from_dataset"]:
        warnings.add(
            "stops",
            "project route(s) with no stop associations: "
            f"{coverage['project_routes_missing_from_dataset']} — preserved as the "
            "documented 129/142 limitation, no stops fabricated",
        )

    physical_stops = (
        int(frame["stop_id"].nunique(dropna=True)) if "stop_id" in frame.columns else None
    )

    # --- write ------------------------------------------------------------
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
    frame.to_parquet(temporary_path, index=False)
    verification = pd.read_parquet(temporary_path, columns=["route_id_canonical"])
    if len(verification) != len(frame):
        raise RuntimeError(
            f"bus_stops_clean verification failed: wrote {len(frame)} rows, "
            f"read back {len(verification)}"
        )
    replace_atomic(temporary_path, output_path)
    print(f"[stops] wrote {output_path.name}: {len(frame)} rows")

    report: dict[str, Any] = {
        "source_file": source_path.name,
        "output_file": output_path.name,
        "input_row_count": input_rows,
        "output_row_count": len(frame),
        "rows_excluded": input_rows - len(frame),
        "expected_row_count": config.EXPECTED_STOP_ROWS,
        "row_count_matches_expected": input_rows == config.EXPECTED_STOP_ROWS,
        "source_columns": source_columns,
        "output_columns": [str(column) for column in frame.columns],
        "unique_physical_stops": physical_stops,
        "coordinate_out_of_range_flags": coordinate_issues,
        "missing_values_by_column": describe_missing(frame),
        "duplicate_associations_retained": duplicate_associations,
        "canonical_route_identifier_count": len(observed_routes),
        "rows_with_alias_canonicalization_applied": alias_applied,
        "route_coverage_vs_project_reference": coverage,
        "transformations_applied": [
            "latitude/longitude coerced with pd.to_numeric(errors='coerce')",
            "coordinates range-checked against the NYC bounding box (flag only)",
            "route_id trimmed/uppercased; route_id_canonical adds alias folding",
            "text columns whitespace-trimmed",
            "direction_id coerced to nullable Int8",
            "deterministic sort by canonical route then direction then stop",
        ],
        "records_removed": "none — no associations were dropped or imputed",
    }
    return frame, report
