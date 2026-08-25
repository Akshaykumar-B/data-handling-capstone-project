"""CJTP (Customer Journey Time Performance) EDA (pure).

Consumes the cleaned customer-journey table and the cjtp_by_route aggregation.
CJTP is a percentage in [0, 100] where higher = a larger share of customers
completed their journey within the scheduled time (more on-time). Customer-
weighted means are the headline metric because routes/segments carry very
different customer volumes; simple means are reported alongside for context.

All relationships are reported as association only, never causation.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from . import eda_config as C
from . import stats_utils as S
from ..processing.reference import RouteReference, coverage_against_project

_METRIC = C.CJTP_METRIC


def _monthly_series(clean: pd.DataFrame) -> list[dict[str, Any]]:
    """Customer-weighted CJTP per calendar month, ordered chronologically."""
    frame = clean.copy()
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
    frame["month_number"] = pd.to_numeric(frame["month_number"], errors="coerce")
    rows: list[dict[str, Any]] = []
    for (year, month_number), group in frame.groupby(["year", "month_number"], observed=True):
        if pd.isna(year) or pd.isna(month_number):
            continue
        metric = pd.to_numeric(group[_METRIC], errors="coerce")
        rows.append(
            {
                "month": f"{int(year):04d}-{int(month_number):02d}",
                "record_count": int(len(group)),
                "total_customers": int(
                    round(float(pd.to_numeric(group["number_of_customers"], errors="coerce").sum()))
                ),
                "mean_cjtp": S._round(metric.mean()),
                "customer_weighted_cjtp": S._round(
                    S.weighted_mean(metric, group["number_of_customers"])
                ),
            }
        )
    rows.sort(key=lambda item: item["month"])
    return rows


def _yearly_series(clean: pd.DataFrame) -> list[dict[str, Any]]:
    frame = clean.copy()
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
    rows: list[dict[str, Any]] = []
    for year, group in frame.groupby("year", observed=True):
        if pd.isna(year):
            continue
        metric = pd.to_numeric(group[_METRIC], errors="coerce")
        rows.append(
            {
                "year": int(year),
                "record_count": int(len(group)),
                "distinct_routes": int(group["route_id_canonical"].nunique()),
                "mean_cjtp": S._round(metric.mean()),
                "customer_weighted_cjtp": S._round(
                    S.weighted_mean(metric, group["number_of_customers"])
                ),
            }
        )
    rows.sort(key=lambda item: item["year"])
    return rows


def analyze(
    datasets: dict[str, pd.DataFrame],
    reference: RouteReference,
    warnings,
) -> dict[str, Any]:
    clean = datasets["customer_journey_clean"]
    by_route = datasets["cjtp_by_route"]

    metric = pd.to_numeric(clean[_METRIC], errors="coerce")
    customers = pd.to_numeric(clean["number_of_customers"], errors="coerce")
    add_travel = pd.to_numeric(clean["additional_travel_time"], errors="coerce")
    add_stop = pd.to_numeric(clean["additional_bus_stop_time"], errors="coerce")

    missing_cjtp = int(metric.isna().sum())
    if missing_cjtp:
        warnings.add(
            "cjtp",
            f"{missing_cjtp} record(s) have a missing CJTP value; excluded from CJTP "
            "statistics (not imputed)",
        )

    # --- overall distribution ----------------------------------------------
    overall = S.describe_series(clean[_METRIC], name="customer_journey_time_performance_pct")
    overall["unit"] = "percent (0-100; higher = more on-time)"
    overall["record_count"] = int(len(clean))
    overall["customer_weighted_mean"] = S._round(S.weighted_mean(metric, customers))

    month_ts = pd.to_datetime(clean["month"], errors="coerce")

    # --- by route (project-scoped headline + all-route context) ------------
    project_mask = by_route["route_id"].isin(set(reference.project_routes))
    project_routes = by_route[project_mask].copy()
    ranked = S.top_bottom(
        project_routes.dropna(subset=["customer_weighted_cjtp"]),
        "route_id",
        "customer_weighted_cjtp",
        n=C.TOP_N,
        extra_columns=("record_count", "total_customers", "mean_cjtp_unweighted"),
    )
    by_route_section = {
        "project_route_count": int(len(project_routes)),
        "all_route_count": int(len(by_route)),
        "project_customer_weighted_cjtp": S.describe_series(
            project_routes["customer_weighted_cjtp"], name="customer_weighted_cjtp_project_routes"
        ),
        "all_routes_customer_weighted_cjtp": S.describe_series(
            by_route["customer_weighted_cjtp"], name="customer_weighted_cjtp_all_routes"
        ),
        "top_performing_routes": ranked["top"],
        "bottom_performing_routes": ranked["bottom"],
        "metric_note": (
            "ranked by customer_weighted_cjtp among the project routes present in the CJTP "
            "dataset; higher = more on-time"
        ),
    }

    # --- dimensional breakdowns (customer-weighted) ------------------------
    by_period = S.category_summary(clean, "period", _METRIC, weight_column="number_of_customers")
    by_trip_type = S.category_summary(clean, "trip_type", _METRIC, weight_column="number_of_customers")
    by_borough = S.category_summary(clean, "borough", _METRIC, weight_column="number_of_customers")
    if any(row["category"] in (None, "UNKNOWN") for row in by_borough):
        warnings.add(
            "cjtp",
            "some CJTP records have borough 'UNKNOWN'; reported as its own category, not dropped",
        )

    # --- additional time metrics -------------------------------------------
    additional_travel_time = S.describe_series(add_travel, name="additional_travel_time")
    additional_bus_stop_time = S.describe_series(add_stop, name="additional_bus_stop_time")

    # --- relationships (row-level; association only) -----------------------
    relationships = {
        "cjtp_vs_number_of_customers": S.correlations(
            metric, customers, x_name="customer_journey_time_performance", y_name="number_of_customers"
        ),
        "cjtp_vs_additional_travel_time": S.correlations(
            metric, add_travel, x_name="customer_journey_time_performance", y_name="additional_travel_time"
        ),
        "cjtp_vs_additional_bus_stop_time": S.correlations(
            metric, add_stop, x_name="customer_journey_time_performance", y_name="additional_bus_stop_time"
        ),
    }

    # --- outliers (reported, never removed) ---------------------------------
    outliers = {
        "cjtp": S.iqr_outliers(
            metric.reset_index(drop=True),
            multiplier=C.IQR_MULTIPLIER,
            labels=clean["route_id_canonical"].reset_index(drop=True),
            max_examples=C.MAX_OUTLIER_EXAMPLES,
        ),
        "additional_travel_time": S.iqr_outliers(
            add_travel.reset_index(drop=True),
            multiplier=C.IQR_MULTIPLIER,
            labels=clean["route_id_canonical"].reset_index(drop=True),
            max_examples=C.MAX_OUTLIER_EXAMPLES,
        ),
        "additional_bus_stop_time": S.iqr_outliers(
            add_stop.reset_index(drop=True),
            multiplier=C.IQR_MULTIPLIER,
            labels=clean["route_id_canonical"].reset_index(drop=True),
            max_examples=C.MAX_OUTLIER_EXAMPLES,
        ),
    }

    # --- coverage -----------------------------------------------------------
    coverage = coverage_against_project(
        set(by_route["route_id"].dropna().unique()), reference, canonicalize=True
    )
    if coverage.get("project_routes_missing_from_dataset"):
        warnings.add(
            "cjtp",
            f"{len(coverage['project_routes_missing_from_dataset'])} project route(s) absent "
            "from CJTP data (no metrics fabricated)",
        )

    return {
        "dataset": "customer_journey_clean.parquet (+ cjtp_by_route)",
        "metric": _METRIC,
        "overall_distribution": overall,
        "missing_cjtp_values": missing_cjtp,
        "by_route": by_route_section,
        "by_month": _monthly_series(clean),
        "by_year": _yearly_series(clean),
        "month_range": {
            "start": None if month_ts.isna().all() else str(month_ts.min().date()),
            "end": None if month_ts.isna().all() else str(month_ts.max().date()),
        },
        "by_period": by_period,
        "by_trip_type": by_trip_type,
        "by_borough": by_borough,
        "additional_travel_time": additional_travel_time,
        "additional_bus_stop_time": additional_bus_stop_time,
        "relationships": relationships,
        "outliers": outliers,
        "route_coverage": coverage,
    }
