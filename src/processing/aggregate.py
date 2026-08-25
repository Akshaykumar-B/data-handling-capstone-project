"""Deterministic analysis-ready aggregations built from the cleaned datasets.

Five tables are produced:
  1. ``ridership_by_route.parquet``       - one row per canonical route
  2. ``ridership_by_date.parquet``        - one row per service date
  3. ``ridership_by_hour.parquet``        - one row per hour-of-day bucket
  4. ``cjtp_by_route.parquet``            - one row per route, peak/off-peak kept
  5. ``route_stop_relationships.parquet`` - route <-> stop association table

Every aggregation is a pure groupby over already-cleaned inputs, sorted
deterministically, so repeated runs produce byte-comparable outputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from . import config
from .reference import RouteReference
from .utils import WarningCollector, replace_atomic


def _write_table(frame: pd.DataFrame, output_path: Path, label: str) -> dict[str, Any]:
    """Write a parquet table via temp file + read-back verification + atomic move."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
    frame.to_parquet(temporary_path, index=False)
    verification = pd.read_parquet(temporary_path)
    if len(verification) != len(frame):
        raise RuntimeError(
            f"{label} verification failed: wrote {len(frame)} rows, "
            f"read back {len(verification)}"
        )
    replace_atomic(temporary_path, output_path)
    print(f"[aggregate] wrote {output_path.name}: {len(frame)} rows")
    return {
        "output_file": output_path.name,
        "row_count": len(frame),
        "columns": [str(column) for column in frame.columns],
    }


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float | None:
    """Customer-weighted mean, ignoring rows where either side is missing."""
    usable = values.notna() & weights.notna() & (weights > 0)
    if not usable.any():
        return None
    weight_total = float(weights[usable].sum())
    if weight_total <= 0:
        return None
    return float((values[usable] * weights[usable]).sum() / weight_total)


# ---------------------------------------------------------------------------
# 1-3. Ridership aggregations
# ---------------------------------------------------------------------------

def aggregate_ridership(
    ridership: pd.DataFrame,
    warnings: WarningCollector,
) -> dict[str, Any]:
    """Build the three ridership aggregation tables."""
    has_transfers = "transfers" in ridership.columns
    reports: dict[str, Any] = {}

    # --- by route ---------------------------------------------------------
    by_route = (
        ridership.dropna(subset=["route_id"])
        .groupby("route_id", dropna=True, observed=True)
        .agg(
            record_count=("ridership", "size"),
            total_ridership=("ridership", "sum"),
            mean_ridership_per_record=("ridership", "mean"),
            max_ridership_per_record=("ridership", "max"),
            distinct_service_dates=("service_date", "nunique"),
            first_observed=("transit_timestamp", "min"),
            last_observed=("transit_timestamp", "max"),
        )
        .reset_index()
    )
    if has_transfers:
        transfers_by_route = (
            ridership.dropna(subset=["route_id"])
            .groupby("route_id", dropna=True, observed=True)["transfers"]
            .sum()
            .rename("total_transfers")
            .reset_index()
        )
        by_route = by_route.merge(transfers_by_route, on="route_id", how="left")

    by_route["mean_daily_ridership"] = (
        by_route["total_ridership"] / by_route["distinct_service_dates"].replace(0, pd.NA)
    )
    total_ridership_all = float(by_route["total_ridership"].sum())
    by_route["share_of_total_ridership_pct"] = (
        (by_route["total_ridership"] / total_ridership_all * 100).round(6)
        if total_ridership_all
        else pd.NA
    )
    by_route = by_route.sort_values("route_id", kind="mergesort").reset_index(drop=True)
    reports["ridership_by_route"] = _write_table(
        by_route, config.RIDERSHIP_BY_ROUTE, "ridership_by_route"
    )
    reports["ridership_by_route"]["distinct_routes"] = int(by_route["route_id"].nunique())
    reports["ridership_by_route"]["total_ridership"] = total_ridership_all

    # --- by date ----------------------------------------------------------
    by_date = (
        ridership.dropna(subset=["service_date"])
        .groupby("service_date", dropna=True, observed=True)
        .agg(
            record_count=("ridership", "size"),
            total_ridership=("ridership", "sum"),
            distinct_routes=("route_id", "nunique"),
        )
        .reset_index()
    )
    if has_transfers:
        transfers_by_date = (
            ridership.dropna(subset=["service_date"])
            .groupby("service_date", dropna=True, observed=True)["transfers"]
            .sum()
            .rename("total_transfers")
            .reset_index()
        )
        by_date = by_date.merge(transfers_by_date, on="service_date", how="left")

    # Attach calendar context deterministically from the date string itself.
    parsed_dates = pd.to_datetime(by_date["service_date"], errors="coerce")
    by_date["day_of_week"] = parsed_dates.dt.day_name().astype("string")
    by_date["is_weekend"] = parsed_dates.dt.dayofweek.isin((5, 6))
    by_date = by_date.sort_values("service_date", kind="mergesort").reset_index(drop=True)
    reports["ridership_by_date"] = _write_table(
        by_date, config.RIDERSHIP_BY_DATE, "ridership_by_date"
    )
    reports["ridership_by_date"]["date_range"] = {
        "min": str(by_date["service_date"].min()) if len(by_date) else None,
        "max": str(by_date["service_date"].max()) if len(by_date) else None,
    }

    # --- by hour ----------------------------------------------------------
    by_hour = (
        ridership.dropna(subset=["hour"])
        .groupby("hour", dropna=True, observed=True)
        .agg(
            record_count=("ridership", "size"),
            total_ridership=("ridership", "sum"),
            distinct_routes=("route_id", "nunique"),
            distinct_service_dates=("service_date", "nunique"),
        )
        .reset_index()
    )
    if has_transfers:
        transfers_by_hour = (
            ridership.dropna(subset=["hour"])
            .groupby("hour", dropna=True, observed=True)["transfers"]
            .sum()
            .rename("total_transfers")
            .reset_index()
        )
        by_hour = by_hour.merge(transfers_by_hour, on="hour", how="left")

    by_hour["mean_ridership_per_date"] = (
        by_hour["total_ridership"] / by_hour["distinct_service_dates"].replace(0, pd.NA)
    )
    by_hour = by_hour.sort_values("hour", kind="mergesort").reset_index(drop=True)
    reports["ridership_by_hour"] = _write_table(
        by_hour, config.RIDERSHIP_BY_HOUR, "ridership_by_hour"
    )
    observed_hours = [int(value) for value in by_hour["hour"].tolist()]
    reports["ridership_by_hour"]["observed_hour_values"] = observed_hours
    if len(observed_hours) <= 1:
        warnings.add(
            "aggregate",
            f"ridership_by_hour has only {len(observed_hours)} distinct hour bucket(s) "
            f"({observed_hours}) — the raw extract's timestamps carry limited hour "
            "resolution; preserved as-is rather than imputed",
        )

    return reports


# ---------------------------------------------------------------------------
# 4. CJTP by route
# ---------------------------------------------------------------------------

def aggregate_cjtp(cjtp: pd.DataFrame, warnings: WarningCollector) -> dict[str, Any]:
    """One row per canonical route, with the peak/off-peak split preserved."""
    frame = cjtp.dropna(subset=["route_id_canonical"]).copy()
    if frame.empty:
        warnings.add("aggregate", "no CJTP rows with a usable route id; table will be empty")

    rows: list[dict[str, Any]] = []
    for route_id, group in frame.groupby("route_id_canonical", dropna=True, observed=True):
        customers = group.get("number_of_customers", pd.Series(dtype="float64"))
        performance = group.get(
            "customer_journey_time_performance", pd.Series(dtype="float64")
        )
        # fillna(False) + bool cast: a nullable BooleanDtype mask containing NA
        # cannot be used for boolean indexing.
        if "period" in group.columns:
            folded = group["period"].str.casefold()
            peak_mask = (folded == "peak").fillna(False).astype(bool)
            off_peak_mask = (folded == "off-peak").fillna(False).astype(bool)
        else:
            peak_mask = pd.Series(False, index=group.index)
            off_peak_mask = pd.Series(False, index=group.index)

        record: dict[str, Any] = {
            "route_id": str(route_id),
            "record_count": int(len(group)),
            "months_observed": int(group["month"].nunique(dropna=True))
            if "month" in group.columns
            else None,
            "first_month": group["month"].min().isoformat()
            if "month" in group.columns and group["month"].notna().any()
            else None,
            "last_month": group["month"].max().isoformat()
            if "month" in group.columns and group["month"].notna().any()
            else None,
            "total_customers": float(customers.sum()) if len(customers) else None,
            "mean_cjtp_unweighted": float(performance.mean())
            if performance.notna().any()
            else None,
            "median_cjtp": float(performance.median())
            if performance.notna().any()
            else None,
            "min_cjtp": float(performance.min()) if performance.notna().any() else None,
            "max_cjtp": float(performance.max()) if performance.notna().any() else None,
            "customer_weighted_cjtp": _weighted_mean(performance, customers),
            "peak_record_count": int(peak_mask.sum()),
            "off_peak_record_count": int(off_peak_mask.sum()),
            "peak_customers": float(customers[peak_mask].sum())
            if peak_mask.any()
            else None,
            "off_peak_customers": float(customers[off_peak_mask].sum())
            if off_peak_mask.any()
            else None,
            "peak_customer_weighted_cjtp": _weighted_mean(
                performance[peak_mask], customers[peak_mask]
            )
            if peak_mask.any()
            else None,
            "off_peak_customer_weighted_cjtp": _weighted_mean(
                performance[off_peak_mask], customers[off_peak_mask]
            )
            if off_peak_mask.any()
            else None,
            "mean_additional_bus_stop_time": float(group["additional_bus_stop_time"].mean())
            if "additional_bus_stop_time" in group.columns
            and group["additional_bus_stop_time"].notna().any()
            else None,
            "mean_additional_travel_time": float(group["additional_travel_time"].mean())
            if "additional_travel_time" in group.columns
            and group["additional_travel_time"].notna().any()
            else None,
            "trip_types": "|".join(
                sorted(str(value) for value in group["trip_type"].dropna().unique())
            )
            if "trip_type" in group.columns
            else None,
            "boroughs": "|".join(
                sorted(str(value) for value in group["borough"].dropna().unique())
            )
            if "borough" in group.columns
            else None,
            "missing_cjtp_values": int(performance.isna().sum())
            if len(performance)
            else 0,
        }
        rows.append(record)

    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.sort_values("route_id", kind="mergesort").reset_index(drop=True)
        table["peak_minus_off_peak_cjtp"] = pd.to_numeric(
            table["peak_customer_weighted_cjtp"], errors="coerce"
        ) - pd.to_numeric(table["off_peak_customer_weighted_cjtp"], errors="coerce")

    report = _write_table(table, config.CJTP_BY_ROUTE, "cjtp_by_route")
    report["distinct_routes"] = int(table["route_id"].nunique()) if not table.empty else 0
    report["routes_with_missing_cjtp_values"] = (
        int((table["missing_cjtp_values"] > 0).sum()) if not table.empty else 0
    )
    report["bootstrap_resampling"] = "not performed in Phase 3"
    return report


# ---------------------------------------------------------------------------
# 5. Route <-> stop relationships
# ---------------------------------------------------------------------------

def aggregate_route_stops(
    stops: pd.DataFrame,
    ridership_routes: set[str],
    geometry_routes: set[str],
    reference: RouteReference,
    warnings: WarningCollector,
) -> dict[str, Any]:
    """Join-ready route/stop association table with cross-dataset presence flags."""
    preferred_columns = [
        "route_id_canonical",
        "route_id",
        "route_short_name",
        "route_long_name",
        "route_description",
        "direction_id",
        "direction",
        "stop_id",
        "stop_name",
        "latitude",
        "longitude",
        "is_cbd",
        "bundle",
        "in_effect",
    ]
    columns = [column for column in preferred_columns if column in stops.columns]
    table = stops[columns].copy()

    key_columns = [
        column
        for column in ("route_id_canonical", "route_id", "direction_id", "stop_id", "bundle")
        if column in table.columns
    ]
    duplicates_collapsed = 0
    if key_columns:
        before = len(table)
        table = table.drop_duplicates(subset=key_columns, keep="first")
        duplicates_collapsed = before - len(table)
        if duplicates_collapsed:
            warnings.add(
                "aggregate",
                f"{duplicates_collapsed} duplicate association(s) collapsed in "
                "route_stop_relationships (the cleaned stop dataset retains them all)",
            )

    if "route_id_canonical" in table.columns:
        table["has_ridership_data"] = table["route_id_canonical"].isin(ridership_routes)
        table["has_route_geometry"] = table["route_id_canonical"].isin(geometry_routes)
        table["is_project_route"] = table["route_id_canonical"].isin(
            reference.project_routes
        )
        stops_per_route = (
            table.groupby("route_id_canonical", dropna=True, observed=True)["stop_id"]
            .nunique()
            .rename("route_unique_stop_count")
            .reset_index()
        )
        table = table.merge(stops_per_route, on="route_id_canonical", how="left")

    sort_columns = [
        column
        for column in ("route_id_canonical", "direction_id", "stop_id")
        if column in table.columns
    ]
    if sort_columns:
        table = table.sort_values(sort_columns, kind="mergesort", na_position="last")
    table = table.reset_index(drop=True)

    report = _write_table(
        table, config.ROUTE_STOP_RELATIONSHIPS, "route_stop_relationships"
    )
    report["duplicate_associations_collapsed"] = duplicates_collapsed
    report["distinct_routes"] = (
        int(table["route_id_canonical"].nunique()) if "route_id_canonical" in table else 0
    )
    report["distinct_stops"] = (
        int(table["stop_id"].nunique()) if "stop_id" in table else 0
    )
    report["associations_with_ridership_data"] = (
        int(table["has_ridership_data"].sum()) if "has_ridership_data" in table else 0
    )
    report["associations_with_route_geometry"] = (
        int(table["has_route_geometry"].sum()) if "has_route_geometry" in table else 0
    )
    return report
