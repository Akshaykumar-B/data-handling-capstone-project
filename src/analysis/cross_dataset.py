"""Cross-dataset EDA (pure).

Builds a route-level frame keyed on the canonical route id, joining:
  * total ridership + mean daily ridership (ridership_by_route)
  * unique physical stops (route_stop_relationships)
  * customer-weighted CJTP + additional-time metrics (cjtp_by_route)

and reports pairwise associations between them. Also reports how project-route
coverage overlaps across the three datasets. Every relationship is association
only - never causation - and each correlation reports its pairwise-complete n.

The merged route frame is returned under ``_merged`` (leading underscore) so the
runner can hand it to the figure module without re-joining; it is dropped before
the report is serialized.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from . import eda_config as C
from . import stats_utils as S
from ..processing.reference import RouteReference


def _unique_stops_by_route(relationships: pd.DataFrame) -> pd.DataFrame:
    grouped = relationships.groupby("route_id_canonical", observed=True)["stop_id"].nunique()
    return grouped.rename("unique_stops").reset_index().rename(
        columns={"route_id_canonical": "route_id"}
    )


def build_route_frame(
    datasets: dict[str, pd.DataFrame],
    reference: RouteReference,
) -> pd.DataFrame:
    """Route-level join across ridership, stops and CJTP (outer, canonical id)."""
    by_route = datasets["ridership_by_route"][
        ["route_id", "total_ridership", "mean_daily_ridership"]
    ].copy()
    by_route["route_id"] = by_route["route_id"].map(
        lambda value: reference.canonical(value) or value
    )

    stops = _unique_stops_by_route(datasets["route_stop_relationships"])
    stops["route_id"] = stops["route_id"].map(lambda value: reference.canonical(value) or value)

    cjtp = datasets["cjtp_by_route"][
        [
            "route_id", "customer_weighted_cjtp", "mean_cjtp_unweighted",
            "total_customers", "mean_additional_travel_time", "mean_additional_bus_stop_time",
        ]
    ].copy()
    cjtp["route_id"] = cjtp["route_id"].map(lambda value: reference.canonical(value) or value)

    merged = by_route.merge(stops, on="route_id", how="outer").merge(
        cjtp, on="route_id", how="outer"
    )
    merged["is_project_route"] = merged["route_id"].isin(set(reference.project_routes))
    return merged.sort_values("route_id", kind="mergesort").reset_index(drop=True)


def analyze(
    datasets: dict[str, pd.DataFrame],
    reference: RouteReference,
    warnings,
) -> dict[str, Any]:
    merged = build_route_frame(datasets, reference)

    # --- route-level relationships -----------------------------------------
    ridership_vs_stops = S.correlations(
        merged["unique_stops"], merged["total_ridership"],
        x_name="unique_stops_per_route", y_name="total_ridership_per_route",
    )
    ridership_vs_cjtp = S.correlations(
        merged["customer_weighted_cjtp"], merged["total_ridership"],
        x_name="customer_weighted_cjtp", y_name="total_ridership_per_route",
    )
    stops_vs_cjtp = S.correlations(
        merged["unique_stops"], merged["customer_weighted_cjtp"],
        x_name="unique_stops_per_route", y_name="customer_weighted_cjtp",
    )

    # --- CJTP vs additional-time metrics (route-level aggregates) ----------
    cjtp_by_route = datasets["cjtp_by_route"]
    cjtp_vs_travel = S.correlations(
        cjtp_by_route["mean_additional_travel_time"], cjtp_by_route["customer_weighted_cjtp"],
        x_name="mean_additional_travel_time", y_name="customer_weighted_cjtp",
    )
    cjtp_vs_stop_time = S.correlations(
        cjtp_by_route["mean_additional_bus_stop_time"], cjtp_by_route["customer_weighted_cjtp"],
        x_name="mean_additional_bus_stop_time", y_name="customer_weighted_cjtp",
    )

    # --- coverage overlap across datasets ----------------------------------
    project = set(reference.project_routes)

    def _canon_set(frame: pd.DataFrame, column: str) -> set[str]:
        values = {reference.canonical(v) or v for v in frame[column].dropna().unique()}
        return {v for v in values if v in project}

    ridership_routes = _canon_set(datasets["ridership_by_route"], "route_id")
    stop_routes = _canon_set(datasets["route_stop_relationships"], "route_id_canonical")
    cjtp_routes = _canon_set(datasets["cjtp_by_route"], "route_id")
    in_all_three = ridership_routes & stop_routes & cjtp_routes
    in_none = project - (ridership_routes | stop_routes | cjtp_routes)

    coverage_overlap = {
        "project_route_count": len(project),
        "in_ridership": len(ridership_routes),
        "in_stops": len(stop_routes),
        "in_cjtp": len(cjtp_routes),
        "in_all_three_datasets": len(in_all_three),
        "in_all_three_pct": S._round(100.0 * len(in_all_three) / len(project)) if project else None,
        "missing_from_every_dataset": sorted(in_none),
        "missing_from_ridership": sorted(project - ridership_routes),
        "missing_from_stops": sorted(project - stop_routes),
        "missing_from_cjtp": sorted(project - cjtp_routes),
    }

    return {
        "description": (
            "route-level associations across datasets; all figures are association only and "
            "do not imply causation"
        ),
        "route_frame_row_count": int(len(merged)),
        "relationships": {
            "ridership_vs_stops": ridership_vs_stops,
            "ridership_vs_cjtp": ridership_vs_cjtp,
            "stops_vs_cjtp": stops_vs_cjtp,
            "cjtp_vs_additional_travel_time": cjtp_vs_travel,
            "cjtp_vs_additional_bus_stop_time": cjtp_vs_stop_time,
        },
        "coverage_overlap": coverage_overlap,
        "_merged": merged,  # dropped before serialization; used for figures
    }
