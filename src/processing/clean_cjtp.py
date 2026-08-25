"""Clean the MTA Customer Journey-Focused Metrics (CJTP) CSV.

Source quirks handled deterministically:
  * ``month`` is a date string -> parsed to datetime64[ns]
  * ``number_of_customers`` carries thousands separators ("219,531.64")
  * ``customer_journey_time_performance`` is a percent string ("70.1999545%")
    -> parsed to a 0-100 numeric percentage plus a 0-1 ratio companion
  * ``route_id`` normalized (trim + uppercase) and alias-canonicalized

Analytical dimensions required downstream are preserved verbatim:
``number_of_customers``, ``period`` (Peak / Off-Peak) and ``trip_type``
(EXP, LCL/LTD, SBS). No bootstrap resampling happens here — that belongs to a
later phase.
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


def _parse_percentage(series: pd.Series) -> pd.Series:
    """Strip ``%`` and thousands separators, then coerce to numeric."""
    text = series.astype("string").str.strip()
    text = text.str.replace("%", "", regex=False).str.replace(",", "", regex=False)
    text = text.replace({"": pd.NA})
    return pd.to_numeric(text, errors="coerce")


def _parse_number(series: pd.Series) -> pd.Series:
    """Strip thousands separators and coerce to numeric."""
    text = series.astype("string").str.strip()
    text = text.str.replace(",", "", regex=False)
    text = text.replace({"": pd.NA})
    return pd.to_numeric(text, errors="coerce")


def clean_cjtp(
    reference: RouteReference,
    warnings: WarningCollector,
    *,
    source_path: Path = config.CJTP_RAW,
    output_path: Path = config.CJTP_CLEAN,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Clean the CJTP dataset and write ``customer_journey_clean.parquet``."""
    print(f"[cjtp] reading {source_path.name}")
    # Read everything as text first so pandas cannot silently guess dtypes for
    # the comma/percent formatted columns.
    frame = pd.read_csv(source_path, dtype=str, keep_default_na=True)
    input_rows = len(frame)
    source_columns = [str(column) for column in frame.columns]

    missing_columns = sorted(set(config.CJTP_COLUMNS) - set(source_columns))
    if missing_columns:
        warnings.add("cjtp", f"expected column(s) absent from the CSV: {missing_columns}")

    blank_counts_raw = {
        column: int(frame[column].isna().sum()) for column in frame.columns
    }

    # --- month ------------------------------------------------------------
    month_parse_failures = 0
    if "month" in frame.columns:
        before = int(frame["month"].isna().sum())
        frame["month"] = pd.to_datetime(frame["month"], errors="coerce")
        month_parse_failures = int(frame["month"].isna().sum()) - before
        if month_parse_failures:
            warnings.add(
                "cjtp",
                f"{month_parse_failures} month value(s) failed to parse and are NaT "
                "(rows kept)",
            )
        frame["year"] = frame["month"].dt.year.astype("Int16")
        frame["month_number"] = frame["month"].dt.month.astype("Int8")

    # --- numeric measures -------------------------------------------------
    numeric_nan_introduced: dict[str, int] = {}
    for column in config.CJTP_NUMERIC_COLUMNS:
        if column not in frame.columns:
            continue
        before = int(frame[column].isna().sum())
        frame[column] = _parse_number(frame[column])
        introduced = int(frame[column].isna().sum()) - before
        numeric_nan_introduced[column] = introduced
        if introduced:
            warnings.add(
                "cjtp",
                f"{introduced} non-numeric {column} value(s) coerced to NaN (rows kept)",
            )

    # --- percentage measure ----------------------------------------------
    if "customer_journey_time_performance" in frame.columns:
        before = int(frame["customer_journey_time_performance"].isna().sum())
        frame["customer_journey_time_performance"] = _parse_percentage(
            frame["customer_journey_time_performance"]
        )
        introduced = (
            int(frame["customer_journey_time_performance"].isna().sum()) - before
        )
        numeric_nan_introduced["customer_journey_time_performance"] = introduced
        if introduced:
            warnings.add(
                "cjtp",
                f"{introduced} customer_journey_time_performance value(s) could not be "
                "parsed as a percentage and are NaN (rows kept)",
            )
        frame["cjtp_ratio"] = frame["customer_journey_time_performance"] / 100.0

        out_of_bounds = int(
            (
                (frame["customer_journey_time_performance"] < 0)
                | (frame["customer_journey_time_performance"] > 100)
            )
            .fillna(False)
            .sum()
        )
        if out_of_bounds:
            warnings.add(
                "cjtp",
                f"{out_of_bounds} customer_journey_time_performance value(s) fall outside "
                "0-100% — flagged, rows retained",
            )
    else:
        out_of_bounds = 0

    # --- dimensions preserved verbatim (whitespace only) ------------------
    for column in ("borough", "trip_type", "period"):
        if column in frame.columns:
            frame[column] = frame[column].astype("string").str.strip()

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

    # --- duplicate accounting --------------------------------------------
    key_columns = [
        column
        for column in ("month", "route_id_canonical", "period", "trip_type", "borough")
        if column in frame.columns
    ]
    duplicate_rows = 0
    if key_columns:
        duplicate_rows = int(frame.duplicated(subset=key_columns, keep="first").sum())
        if duplicate_rows:
            warnings.add(
                "cjtp",
                f"{duplicate_rows} duplicate row(s) on key {key_columns} retained",
            )

    # --- deterministic ordering ------------------------------------------
    sort_columns = [
        column
        for column in ("month", "route_id_canonical", "period", "trip_type")
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
            "cjtp",
            "project route(s) with no CJTP records: "
            f"{coverage['project_routes_missing_from_dataset']} — preserved as the "
            "documented CJTP coverage limitation, no metrics fabricated",
        )

    missing_after = describe_missing(frame)
    total_missing_cells = sum(
        count for column, count in missing_after.items() if column in config.CJTP_COLUMNS
    )

    # --- write ------------------------------------------------------------
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
    frame.to_parquet(temporary_path, index=False)
    verification = pd.read_parquet(temporary_path, columns=["route_id_canonical"])
    if len(verification) != len(frame):
        raise RuntimeError(
            f"customer_journey_clean verification failed: wrote {len(frame)} rows, "
            f"read back {len(verification)}"
        )
    replace_atomic(temporary_path, output_path)
    print(f"[cjtp] wrote {output_path.name}: {len(frame)} rows")

    report: dict[str, Any] = {
        "source_file": source_path.name,
        "output_file": output_path.name,
        "input_row_count": input_rows,
        "output_row_count": len(frame),
        "rows_excluded": input_rows - len(frame),
        "source_columns": source_columns,
        "output_columns": [str(column) for column in frame.columns],
        "missing_expected_columns": missing_columns,
        "blank_cells_in_raw_csv": blank_counts_raw,
        "month_parse_failures": month_parse_failures,
        "numeric_coercions_introducing_nan": numeric_nan_introduced,
        "percentage_values_outside_0_100": out_of_bounds,
        "missing_values_by_column": missing_after,
        "missing_cells_across_source_columns": total_missing_cells,
        "duplicate_rows_retained": duplicate_rows,
        "canonical_route_identifier_count": len(observed_routes),
        "rows_with_alias_canonicalization_applied": alias_applied,
        "route_coverage_vs_project_reference": coverage,
        "preserved_dimensions": {
            "period_values": sorted(
                str(value) for value in frame["period"].dropna().unique()
            )
            if "period" in frame.columns
            else [],
            "trip_type_values": sorted(
                str(value) for value in frame["trip_type"].dropna().unique()
            )
            if "trip_type" in frame.columns
            else [],
            "borough_values": sorted(
                str(value) for value in frame["borough"].dropna().unique()
            )
            if "borough" in frame.columns
            else [],
        },
        "month_range": {"min": None, "max": None},
        "transformations_applied": [
            "CSV read with dtype=str to avoid dtype guessing on formatted columns",
            "month parsed with pd.to_datetime(errors='coerce'); year/month_number derived",
            "thousands separators stripped from number_of_customers before to_numeric",
            "percent sign stripped from customer_journey_time_performance; cjtp_ratio derived",
            "route_id trimmed/uppercased; route_id_canonical adds alias folding",
            "deterministic sort by month then route then period then trip type",
        ],
        "bootstrap_resampling": "not performed in Phase 3 (deferred to a later phase)",
        "records_removed": "none — no rows were dropped, filtered or imputed",
    }

    if "month" in frame.columns and frame["month"].notna().any():
        report["month_range"] = {
            "min": frame["month"].min().isoformat(),
            "max": frame["month"].max().isoformat(),
        }

    return frame, report
