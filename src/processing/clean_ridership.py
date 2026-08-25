"""Clean the MTA ridership parquet (development sample).

Deterministic transforms only:
  * ``transit_timestamp`` parsed to datetime64[ns]
  * ``ridership`` / ``transfers`` coerced to numeric
  * ``bus_route`` normalized (trim + uppercase) and alias-canonicalized into
    ``route_id`` while the original value is preserved
  * derived calendar helpers (``service_date``, ``hour``, ``day_of_week``)

Nothing is dropped, imputed or fabricated. Missing/duplicate findings are
measured and reported so the known 140-of-142 route limitation stays visible.
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


def clean_ridership(
    reference: RouteReference,
    warnings: WarningCollector,
    *,
    source_path: Path = config.RIDERSHIP_RAW,
    output_path: Path = config.RIDERSHIP_CLEAN,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Clean the ridership dataset and write ``ridership_clean.parquet``."""
    print(f"[ridership] reading {source_path.name}")
    frame = pd.read_parquet(source_path)
    input_rows = len(frame)
    source_columns = [str(column) for column in frame.columns]

    expected = set(config.RIDERSHIP_COLUMNS)
    missing_columns = sorted(expected - set(source_columns))
    extra_columns = sorted(set(source_columns) - expected)
    if missing_columns:
        warnings.add(
            "ridership",
            f"expected column(s) absent from the raw parquet: {missing_columns}",
        )
    if extra_columns:
        warnings.add(
            "ridership",
            f"unexpected column(s) carried through unchanged: {extra_columns}",
        )

    # --- timestamps -------------------------------------------------------
    timestamp_unparsed = 0
    if "transit_timestamp" in frame.columns:
        original_missing = int(frame["transit_timestamp"].isna().sum())
        frame["transit_timestamp"] = pd.to_datetime(
            frame["transit_timestamp"], errors="coerce"
        )
        timestamp_unparsed = int(frame["transit_timestamp"].isna().sum()) - original_missing
        if timestamp_unparsed:
            warnings.add(
                "ridership",
                f"{timestamp_unparsed} transit_timestamp value(s) could not be parsed "
                "and are retained as NaT (rows kept)",
            )

    # --- numerics ---------------------------------------------------------
    numeric_coercions: dict[str, int] = {}
    for column in ("ridership", "transfers"):
        if column not in frame.columns:
            continue
        before = int(frame[column].isna().sum())
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        introduced = int(frame[column].isna().sum()) - before
        numeric_coercions[column] = introduced
        if introduced:
            warnings.add(
                "ridership",
                f"{introduced} non-numeric {column} value(s) coerced to NaN (rows kept)",
            )

    # --- route identifiers ------------------------------------------------
    raw_route_values: set[str] = set()
    alias_applied = 0
    if "bus_route" in frame.columns:
        frame["bus_route"] = frame["bus_route"].astype("string").str.strip().str.upper()
        frame["bus_route"] = frame["bus_route"].replace({"": pd.NA})
        raw_route_values = normalized_route_set(frame["bus_route"].dropna().unique())
        alias_series = frame["bus_route"].map(
            lambda value: reference.canonical(value) if pd.notna(value) else pd.NA
        )
        frame["route_id"] = alias_series.astype("string")
        alias_applied = int(
            (frame["bus_route"].notna() & (frame["route_id"] != frame["bus_route"])).sum()
        )
    else:
        frame["route_id"] = pd.Series(pd.NA, index=frame.index, dtype="string")

    # --- categorical tidying (values untouched, only whitespace trimmed) ---
    for column in ("payment_method", "fare_class_category"):
        if column in frame.columns:
            frame[column] = frame[column].astype("string").str.strip()

    # --- derived calendar helpers ----------------------------------------
    if "transit_timestamp" in frame.columns:
        timestamps = frame["transit_timestamp"]
        # strftime (not .dt.date) so NaT becomes NA rather than the string "NaT".
        frame["service_date"] = timestamps.dt.strftime("%Y-%m-%d").astype("string")
        frame["hour"] = timestamps.dt.hour.astype("Int16")
        frame["day_of_week"] = timestamps.dt.day_name().astype("string")
        weekend = timestamps.dt.dayofweek.isin((5, 6)).astype("boolean")
        weekend[timestamps.isna()] = pd.NA
        frame["is_weekend"] = weekend

    # --- duplicate accounting (measured, not removed) ---------------------
    duplicate_full_rows = int(frame.duplicated(keep="first").sum())
    duplicate_key_rows = 0
    key_columns = [
        column
        for column in ("transit_timestamp", "bus_route", "payment_method", "fare_class_category")
        if column in frame.columns
    ]
    if key_columns:
        duplicate_key_rows = int(frame.duplicated(subset=key_columns, keep="first").sum())
    if duplicate_full_rows:
        warnings.add(
            "ridership",
            f"{duplicate_full_rows} fully duplicated row(s) retained — the raw extract is "
            "event-level, so identical rows are legitimate repeated observations",
        )

    # --- deterministic ordering ------------------------------------------
    sort_columns = [
        column for column in ("transit_timestamp", "route_id", "payment_method", "fare_class_category")
        if column in frame.columns
    ]
    if sort_columns:
        frame = frame.sort_values(sort_columns, kind="mergesort", na_position="last")
    frame = frame.reset_index(drop=True)

    # --- coverage against the authoritative route reference ---------------
    observed_routes = normalized_route_set(frame["route_id"].dropna().unique())
    coverage = coverage_against_project(observed_routes, reference)
    if coverage["project_routes_missing_from_dataset"]:
        warnings.add(
            "ridership",
            "route(s) present in the project reference but absent from ridership: "
            f"{coverage['project_routes_missing_from_dataset']} — preserved as a known "
            "limitation, no rows fabricated",
        )

    # --- write ------------------------------------------------------------
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
    frame.to_parquet(temporary_path, index=False)
    verification = pd.read_parquet(temporary_path, columns=["route_id"])
    if len(verification) != len(frame):
        raise RuntimeError(
            f"ridership_clean verification failed: wrote {len(frame)} rows, "
            f"read back {len(verification)}"
        )
    replace_atomic(temporary_path, output_path)
    print(f"[ridership] wrote {output_path.name}: {len(frame)} rows")

    ridership_total = (
        float(frame["ridership"].sum()) if "ridership" in frame.columns else None
    )
    transfers_total = (
        float(frame["transfers"].sum()) if "transfers" in frame.columns else None
    )

    report: dict[str, Any] = {
        "source_file": source_path.name,
        "output_file": output_path.name,
        "input_row_count": input_rows,
        "output_row_count": len(frame),
        "rows_excluded": input_rows - len(frame),
        "expected_row_count": config.EXPECTED_RIDERSHIP_ROWS,
        "row_count_matches_expected": input_rows == config.EXPECTED_RIDERSHIP_ROWS,
        "source_columns": source_columns,
        "output_columns": [str(column) for column in frame.columns],
        "missing_expected_columns": missing_columns,
        "unexpected_columns": extra_columns,
        "timestamp_parse_failures": timestamp_unparsed,
        "numeric_coercions_introducing_nan": numeric_coercions,
        "missing_values_by_column": describe_missing(frame),
        "duplicate_full_rows_retained": duplicate_full_rows,
        "duplicate_rows_on_event_key_retained": duplicate_key_rows,
        "raw_route_identifier_count": len(raw_route_values),
        "canonical_route_identifier_count": len(observed_routes),
        "rows_with_alias_canonicalization_applied": alias_applied,
        "route_coverage_vs_project_reference": coverage,
        "total_ridership": ridership_total,
        "total_transfers": transfers_total,
        "date_range": {
            "min": None,
            "max": None,
        },
        "distinct_service_dates": None,
        "distinct_hours": None,
        "transformations_applied": [
            "transit_timestamp parsed with pd.to_datetime(errors='coerce')",
            "ridership and transfers coerced with pd.to_numeric(errors='coerce')",
            "bus_route trimmed and uppercased",
            "route_id derived from bus_route using the profiling report alias map",
            "derived service_date, hour, day_of_week, is_weekend",
            "deterministic sort by timestamp then route",
        ],
        "records_removed": "none — no rows were dropped, filtered or imputed",
    }

    if "transit_timestamp" in frame.columns and frame["transit_timestamp"].notna().any():
        report["date_range"] = {
            "min": frame["transit_timestamp"].min().isoformat(),
            "max": frame["transit_timestamp"].max().isoformat(),
        }
    if "service_date" in frame.columns:
        report["distinct_service_dates"] = int(frame["service_date"].nunique(dropna=True))
    if "hour" in frame.columns:
        distinct_hours = sorted(int(value) for value in frame["hour"].dropna().unique())
        report["distinct_hours"] = len(distinct_hours)
        report["observed_hour_values"] = distinct_hours

    return frame, report
