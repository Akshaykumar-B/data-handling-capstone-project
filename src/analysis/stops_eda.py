"""Bus-stop EDA (pure).

Consumes the cleaned bus-stops table and the route_stop_relationships
aggregation. Reports the physical stop inventory, per-route and per-direction
stop counts, association counts, coverage extremes, and which project routes
have no stop associations at all. No I/O.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from . import eda_config as C
from . import stats_utils as S
from ..processing.reference import RouteReference, coverage_against_project


def _per_route_table(relationships: pd.DataFrame) -> pd.DataFrame:
    """One row per route: unique physical stops + association count + flags."""
    grouped = relationships.groupby("route_id_canonical", observed=True)
    table = grouped.agg(
        unique_stops=("stop_id", "nunique"),
        associations=("stop_id", "size"),
        is_project_route=("is_project_route", "max"),
        has_ridership_data=("has_ridership_data", "max"),
        has_route_geometry=("has_route_geometry", "max"),
    ).reset_index()
    return table


def analyze(
    datasets: dict[str, pd.DataFrame],
    reference: RouteReference,
    warnings,
) -> dict[str, Any]:
    stops = datasets["bus_stops_clean"]
    relationships = datasets["route_stop_relationships"]

    # --- physical stop inventory -------------------------------------------
    unique_physical_stops = int(stops["stop_id"].nunique())
    inventory = {
        "unique_physical_stops": unique_physical_stops,
        "total_route_stop_associations": int(len(stops)),
        "note": (
            "a physical stop can serve several routes/directions, so associations "
            "(route x direction x stop rows) exceed the count of distinct physical stops"
        ),
    }

    per_route = _per_route_table(relationships)

    # --- stops by route -----------------------------------------------------
    stops_by_route = {
        "route_count_with_stops": int(len(per_route)),
        "unique_stops_per_route": S.describe_series(
            per_route["unique_stops"], name="unique_stops_per_route"
        ),
        "associations_per_route": S.describe_series(
            per_route["associations"], name="associations_per_route"
        ),
    }
    coverage_ranked = S.top_bottom(
        per_route, "route_id_canonical", "unique_stops", n=C.TOP_N,
        extra_columns=("associations",),
    )
    stops_by_route["highest_stop_coverage"] = coverage_ranked["top"]
    stops_by_route["lowest_stop_coverage"] = coverage_ranked["bottom"]

    # --- stops by direction -------------------------------------------------
    by_direction = []
    for direction, group in relationships.groupby("direction", dropna=False, observed=True):
        by_direction.append(
            {
                "direction": None if pd.isna(direction) else str(direction),
                "associations": int(len(group)),
                "unique_stops": int(group["stop_id"].nunique()),
                "distinct_routes": int(group["route_id_canonical"].nunique()),
            }
        )
    by_direction.sort(key=lambda item: (item["direction"] is None, item["direction"] or ""))

    by_direction_id = []
    for direction_id, group in relationships.groupby("direction_id", dropna=False, observed=True):
        by_direction_id.append(
            {
                "direction_id": None if pd.isna(direction_id) else int(direction_id),
                "associations": int(len(group)),
                "unique_stops": int(group["stop_id"].nunique()),
            }
        )
    by_direction_id.sort(key=lambda item: (item["direction_id"] is None, item["direction_id"] or -1))

    # --- flags summary ------------------------------------------------------
    flags = {
        "associations_with_ridership_data": int(relationships["has_ridership_data"].astype(bool).sum()),
        "associations_with_route_geometry": int(relationships["has_route_geometry"].astype(bool).sum()),
        "associations_on_project_routes": int(relationships["is_project_route"].astype(bool).sum()),
        "routes_flagged_project": int(per_route["is_project_route"].astype(bool).sum()),
    }

    # --- coverage + routes missing stop associations -----------------------
    coverage = coverage_against_project(
        set(relationships["route_id_canonical"].dropna().unique()), reference, canonicalize=True
    )
    missing = coverage.get("project_routes_missing_from_dataset", [])
    if missing:
        warnings.add(
            "bus_stops",
            f"{len(missing)} project route(s) have NO stop associations (not fabricated): "
            + ", ".join(missing),
        )

    return {
        "dataset": "bus_stops_clean.parquet (+ route_stop_relationships)",
        "physical_stop_inventory": inventory,
        "stops_by_route": stops_by_route,
        "stops_by_direction": by_direction,
        "stops_by_direction_id": by_direction_id,
        "association_flags": flags,
        "routes_missing_stop_associations": {
            "count": len(missing),
            "route_ids": missing,
        },
        "route_coverage": coverage,
    }
