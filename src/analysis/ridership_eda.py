"""Ridership EDA (pure).

Consumes the cleaned ridership table plus the ridership_by_route / _by_date /
_by_hour aggregations and returns a JSON-safe findings dict. No I/O.

Temporal honesty: the ridership extract is a 2-month development subsample with
hour buckets at even hours only, so this module reports hourly totals purely
descriptively and never asserts a 24-hour / diurnal pattern. Weekday-vs-weekend
comparison *is* supported (59 distinct dates spanning both) and is included.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from . import eda_config as C
from . import stats_utils as S
from ..processing.reference import RouteReference, coverage_against_project

_WEEKDAY_ORDER = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _weekday_key(value: Any) -> tuple[int, str]:
    text = str(value)
    return (_WEEKDAY_ORDER.get(text.strip().lower(), 99), text)


def analyze(
    datasets: dict[str, pd.DataFrame],
    reference: RouteReference,
    warnings,
) -> dict[str, Any]:
    clean = datasets["ridership_clean"]
    by_route = datasets["ridership_by_route"]
    by_date = datasets["ridership_by_date"]
    by_hour = datasets["ridership_by_hour"]

    ridership = pd.to_numeric(clean["ridership"], errors="coerce")
    transfers = pd.to_numeric(clean["transfers"], errors="coerce")
    total_ridership = float(ridership.sum())
    by_route_total = float(pd.to_numeric(by_route["total_ridership"], errors="coerce").sum())

    # --- headline totals ----------------------------------------------------
    service_dates = pd.to_datetime(by_date["service_date"], errors="coerce")
    totals = {
        "total_ridership": int(round(total_ridership)),
        "total_transfers": int(round(float(transfers.sum()))),
        "record_count": int(len(clean)),
        "distinct_routes_in_ridership": int(clean["route_id"].nunique()),
        "distinct_service_dates": int(by_date["service_date"].nunique()),
        "date_range": {
            "start": None if service_dates.isna().all() else str(service_dates.min().date()),
            "end": None if service_dates.isna().all() else str(service_dates.max().date()),
        },
        "reconciles_with_by_route": abs(total_ridership - by_route_total) < 1e-6,
    }

    # --- descriptive statistics (multiple grains) ---------------------------
    descriptive_statistics = {
        "per_record_ridership": S.describe_series(ridership, name="ridership_per_record"),
        "per_record_transfers": S.describe_series(transfers, name="transfers_per_record"),
        "per_route_total_ridership": S.describe_series(
            by_route["total_ridership"], name="total_ridership_per_route"
        ),
        "per_route_mean_daily_ridership": S.describe_series(
            by_route["mean_daily_ridership"], name="mean_daily_ridership_per_route"
        ),
        "daily_total_ridership": S.describe_series(
            by_date["total_ridership"], name="total_ridership_per_day"
        ),
    }

    # --- ridership by route: top / bottom + concentration -------------------
    ranked = S.top_bottom(
        by_route,
        "route_id",
        "total_ridership",
        n=C.TOP_N,
        extra_columns=("share_of_total_ridership_pct", "mean_daily_ridership"),
    )
    route_totals = pd.to_numeric(by_route["total_ridership"], errors="coerce")
    ordered_shares = pd.to_numeric(
        by_route["share_of_total_ridership_pct"], errors="coerce"
    ).sort_values(ascending=False, kind="mergesort")
    mean_route = float(route_totals.mean())
    std_route = float(route_totals.std(ddof=1)) if len(route_totals) > 1 else 0.0
    route_level_variation = {
        "route_count": int(len(by_route)),
        "mean_total_ridership_per_route": S._round(mean_route),
        "std_total_ridership_per_route": S._round(std_route),
        "coefficient_of_variation": S._round(std_route / mean_route) if mean_route else None,
        "max_over_min_ratio": S._round(
            float(route_totals.max()) / float(route_totals.min())
        ) if float(route_totals.min()) > 0 else None,
        "top_10_routes_share_pct": S._round(float(ordered_shares.head(10).sum())),
        "top_20_routes_share_pct": S._round(float(ordered_shares.head(20).sum())),
        "interpretation": (
            "higher coefficient of variation and top-10 share => ridership concentrated "
            "in a few routes"
        ),
    }

    # --- daily ridership: weekday vs weekend (supported) --------------------
    by_date_local = by_date.copy()
    by_date_local["is_weekend"] = by_date_local["is_weekend"].astype(bool)
    daily_total = pd.to_numeric(by_date_local["total_ridership"], errors="coerce")
    weekend_split = []
    for is_weekend, group in by_date_local.groupby("is_weekend", observed=True):
        metric = pd.to_numeric(group["total_ridership"], errors="coerce")
        weekend_split.append(
            {
                "day_type": "weekend" if is_weekend else "weekday",
                "distinct_dates": int(len(group)),
                "mean_daily_ridership": S._round(metric.mean()),
                "median_daily_ridership": S._round(metric.median()),
                "total_ridership": int(round(float(metric.sum()))),
            }
        )
    weekend_split.sort(key=lambda item: item["day_type"])

    by_dow = []
    for dow, group in by_date_local.groupby("day_of_week", observed=True):
        metric = pd.to_numeric(group["total_ridership"], errors="coerce")
        by_dow.append(
            {
                "day_of_week": str(dow),
                "distinct_dates": int(len(group)),
                "mean_daily_ridership": S._round(metric.mean()),
                "total_ridership": int(round(float(metric.sum()))),
            }
        )
    by_dow.sort(key=lambda item: _weekday_key(item["day_of_week"]))

    busiest_idx = daily_total.idxmax()
    quietest_idx = daily_total.idxmin()
    daily = {
        "weekday_vs_weekend": weekend_split,
        "by_day_of_week": by_dow,
        "busiest_date": {
            "service_date": str(pd.to_datetime(by_date_local.loc[busiest_idx, "service_date"]).date()),
            "total_ridership": int(round(float(daily_total.loc[busiest_idx]))),
        },
        "quietest_date": {
            "service_date": str(pd.to_datetime(by_date_local.loc[quietest_idx, "service_date"]).date()),
            "total_ridership": int(round(float(daily_total.loc[quietest_idx]))),
        },
    }

    # --- hourly (descriptive ONLY; no diurnal claims) -----------------------
    hour_rows = []
    for _, row in by_hour.sort_values("hour", kind="mergesort").iterrows():
        hour_rows.append(
            {
                "hour": int(row["hour"]),
                "total_ridership": int(round(float(row["total_ridership"]))),
                "record_count": int(row["record_count"]),
                "distinct_routes": int(row["distinct_routes"]),
            }
        )
    observed_hours = sorted(int(h) for h in by_hour["hour"].unique())
    hourly = {
        "observed_hour_buckets": observed_hours,
        "distinct_hour_buckets": len(observed_hours),
        "diurnal_analysis_supported": False,
        "buckets": hour_rows,
        "caveat": C.TEMPORAL_LIMITATION,
    }

    # --- outliers (reported, never removed) ---------------------------------
    outliers = {
        "per_route_total_ridership": S.iqr_outliers(
            by_route["total_ridership"].reset_index(drop=True),
            multiplier=C.IQR_MULTIPLIER,
            labels=by_route["route_id"].reset_index(drop=True),
            max_examples=C.MAX_OUTLIER_EXAMPLES,
        ),
        "daily_total_ridership": S.iqr_outliers(
            by_date_local["total_ridership"].reset_index(drop=True),
            multiplier=C.IQR_MULTIPLIER,
            labels=by_date_local["service_date"].astype(str).reset_index(drop=True),
            max_examples=C.MAX_OUTLIER_EXAMPLES,
        ),
        "per_record_ridership": S.iqr_outliers(
            ridership.reset_index(drop=True),
            multiplier=C.IQR_MULTIPLIER,
            labels=clean["route_id"].reset_index(drop=True),
            max_examples=C.MAX_OUTLIER_EXAMPLES,
        ),
    }

    # --- project-route coverage --------------------------------------------
    coverage = coverage_against_project(
        set(by_route["route_id"].dropna().unique()), reference, canonicalize=True
    )
    if coverage.get("project_routes_missing_from_dataset"):
        warnings.add(
            "ridership",
            "routes absent from ridership (no rows fabricated): "
            + ", ".join(coverage["project_routes_missing_from_dataset"]),
        )

    return {
        "dataset": "ridership_clean.parquet (+ ridership_by_route/_by_date/_by_hour)",
        "totals": totals,
        "descriptive_statistics": descriptive_statistics,
        "by_route": {
            "top_routes": ranked["top"],
            "bottom_routes": ranked["bottom"],
            "route_level_variation": route_level_variation,
        },
        "daily": daily,
        "hourly": hourly,
        "outliers": outliers,
        "route_coverage": coverage,
    }
