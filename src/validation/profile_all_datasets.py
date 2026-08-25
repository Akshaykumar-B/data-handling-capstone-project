"""Read-only profiling for the three prepared MTA datasets."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable

import geopandas as gpd
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_RIDERSHIP_PATH = ROOT_DIR / "data" / "raw" / "mta_ridership_dev.parquet"
DEFAULT_ROUTES_PATH = ROOT_DIR / "data" / "raw" / "mta_bus_routes_valid.geojson"
DEFAULT_STOPS_PATH = ROOT_DIR / "data" / "raw" / "mta_bus_stops_project.parquet"
DEFAULT_REPORT_PATH = ROOT_DIR / "data" / "processed" / "dataset_profiling_report.json"

RIDERSHIP_ROUTE_COLUMN = "bus_route"
RIDERSHIP_TIME_COLUMN = "transit_timestamp"
STOP_ASSOCIATION_COLUMNS = ("route_id", "route_short_name", "stop_id", "direction_id", "bundle")


def normalize_route(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def normalized_set(values: Iterable[object]) -> set[str]:
    return {normalized for value in values if (normalized := normalize_route(value)) is not None}


def route_identifiers(df: pd.DataFrame) -> set[str]:
    identifiers: set[str] = set()
    for column in ("route_id", "route_short_name"):
        if column in df.columns:
            identifiers.update(normalized_set(df[column]))
    return identifiers


def dtypes(df: pd.DataFrame) -> dict[str, str]:
    return {column: str(dtype) for column, dtype in df.dtypes.items()}


def json_scalar(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def coverage(left: set[str], right: set[str]) -> dict[str, Any]:
    matching = left.intersection(right)
    unmatched = left.difference(right)
    return {
        "left_count": len(left),
        "right_count": len(right),
        "matching_count": len(matching),
        "coverage_percentage": round(100 * len(matching) / len(left), 2) if left else 0.0,
        "unmatched_left_route_ids": sorted(unmatched),
        "unmatched_right_route_ids": sorted(right.difference(left)),
    }


def profile_ridership(df: pd.DataFrame) -> tuple[dict[str, Any], set[str], dict[str, Any]]:
    if RIDERSHIP_TIME_COLUMN not in df or RIDERSHIP_ROUTE_COLUMN not in df:
        raise ValueError("Ridership input lacks transit_timestamp or bus_route.")
    timestamps = pd.to_datetime(df[RIDERSHIP_TIME_COLUMN], errors="coerce")
    ridership_values = pd.to_numeric(df.get("ridership"), errors="coerce")
    routes = normalized_set(df[RIDERSHIP_ROUTE_COLUMN])
    hourly = timestamps.dt.hour
    aggregations = {
        "ridership_by_route": {
            str(route): json_scalar(value)
            for route, value in df.assign(_ridership=ridership_values).groupby(RIDERSHIP_ROUTE_COLUMN, dropna=False)["_ridership"].sum(min_count=1).sort_index().items()
        },
        "ridership_by_date": {
            str(date): json_scalar(value)
            for date, value in df.assign(_date=timestamps.dt.date, _ridership=ridership_values).groupby("_date", dropna=False)["_ridership"].sum(min_count=1).sort_index().items()
        },
        "ridership_by_hour": {
            str(hour): json_scalar(value)
            for hour, value in df.assign(_hour=hourly, _ridership=ridership_values).groupby("_hour", dropna=False)["_ridership"].sum(min_count=1).sort_index().items()
        },
        "ridership_by_route_and_hour": [
            {"bus_route": str(route), "hour": json_scalar(hour), "ridership": json_scalar(value)}
            for (route, hour), value in df.assign(_hour=hourly, _ridership=ridership_values).groupby([RIDERSHIP_ROUTE_COLUMN, "_hour"], dropna=False)["_ridership"].sum(min_count=1).sort_index().items()
        ],
    }
    return {
        "row_count": int(len(df)),
        "columns_and_dtypes": dtypes(df),
        "date_range": {"min": json_scalar(timestamps.min()), "max": json_scalar(timestamps.max())},
        "unique_routes": len(routes),
        "unique_days": int(timestamps.dt.date.nunique()),
        "hourly_range": {"min": json_scalar(hourly.min()), "max": json_scalar(hourly.max())},
        "total_ridership": json_scalar(ridership_values.sum(min_count=1)),
        "ridership_statistics": {key: json_scalar(value) for key, value in ridership_values.describe().items()},
        "missing_values": {column: int(df[column].isna().sum()) for column in df.columns},
        "duplicate_rows": int(df.duplicated().sum()),
    }, routes, aggregations


def profile_routes(gdf: gpd.GeoDataFrame, ridership_routes: set[str]) -> tuple[dict[str, Any], set[str], list[dict[str, str]]]:
    geometry = gdf.geometry
    present = geometry.notna()
    route_ids = normalized_set(gdf["route_id"])
    short_names = normalized_set(gdf["route_short_name"])
    aliases = sorted({
        (normalize_route(row.route_id), normalize_route(row.route_short_name))
        for row in gdf[["route_id", "route_short_name"]].itertuples(index=False)
        if normalize_route(row.route_id) and normalize_route(row.route_short_name) and normalize_route(row.route_id) != normalize_route(row.route_short_name)
    })
    return {
        "feature_count": int(len(gdf)),
        "columns_and_dtypes": dtypes(gdf.drop(columns=gdf.geometry.name)),
        "unique_route_id": len(route_ids),
        "unique_route_short_name": len(short_names),
        "crs": str(gdf.crs),
        "geometry_types": {str(key): int(value) for key, value in geometry.geom_type.value_counts(dropna=False).items()},
        "null_geometries": int(geometry.isna().sum()),
        "empty_geometries": int(geometry[present].is_empty.sum()),
        "invalid_geometries": int((~geometry[present & ~geometry.is_empty].is_valid).sum()),
        "route_geometry_coverage_against_ridership": coverage(ridership_routes, route_ids | short_names),
    }, route_ids | short_names, [{"route_id": route_id, "route_short_name": short_name} for route_id, short_name in aliases]


def profile_stops(df: pd.DataFrame, ridership_routes: set[str]) -> tuple[dict[str, Any], set[str]]:
    missing = [column for column in STOP_ASSOCIATION_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Bus Stops input lacks association columns: {missing}")
    timestamps = pd.to_datetime(df.get("valid_from"), errors="coerce")
    latitude = pd.to_numeric(df.get("latitude"), errors="coerce")
    longitude = pd.to_numeric(df.get("longitude"), errors="coerce")
    invalid_coordinates = latitude.isna() | longitude.isna() | ~latitude.between(-90, 90) | ~longitude.between(-180, 180)
    routes = route_identifiers(df)
    return {
        "row_count": int(len(df)),
        "columns_and_dtypes": dtypes(df),
        "date_range": {"min_valid_from": json_scalar(timestamps.min()), "max_valid_from": json_scalar(timestamps.max())},
        "unique_physical_stops": int(df["stop_id"].nunique(dropna=True)),
        "unique_routes": len(routes),
        "unique_route_stop_direction_bundle_associations": int(df[list(STOP_ASSOCIATION_COLUMNS)].drop_duplicates().shape[0]),
        "missing_values": {column: int(df[column].isna().sum()) for column in df.columns},
        "invalid_coordinates": int(invalid_coordinates.sum()),
        "duplicate_associations": int(df.duplicated(subset=list(STOP_ASSOCIATION_COLUMNS)).sum()),
        "route_coverage_against_ridership": coverage(ridership_routes, routes),
    }, routes


def build_report(ridership: pd.DataFrame, routes: gpd.GeoDataFrame, stops: pd.DataFrame) -> dict[str, Any]:
    ridership_profile, ridership_routes, aggregations = profile_ridership(ridership)
    routes_profile, route_identifiers_set, aliases = profile_routes(routes, ridership_routes)
    stops_profile, stop_route_identifiers = profile_stops(stops, ridership_routes)
    return {
        "ridership": ridership_profile,
        "routes": routes_profile,
        "bus_stops": stops_profile,
        "relationships": {
            "ridership_route_to_route_geometry_match": coverage(ridership_routes, route_identifiers_set),
            "ridership_route_to_bus_stop_match": coverage(ridership_routes, stop_route_identifiers),
            "route_geometry_to_bus_stop_route_match": coverage(route_identifiers_set, stop_route_identifiers),
            "all_unmatched_route_ids": {
                "ridership_missing_from_routes": sorted(ridership_routes - route_identifiers_set),
                "ridership_missing_from_stops": sorted(ridership_routes - stop_route_identifiers),
                "route_geometry_missing_from_stops": sorted(route_identifiers_set - stop_route_identifiers),
            },
            "possible_route_id_aliases": aliases,
        },
        "aggregations": aggregations,
    }


def write_report(report: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = report_path.with_name(f"{report_path.stem}.tmp{report_path.suffix}")
    if temporary_path.exists():
        raise RuntimeError(f"Temporary report already exists: {temporary_path}")
    temporary_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    json.loads(temporary_path.read_text(encoding="utf-8"))
    try:
        os.replace(temporary_path, report_path)
    except PermissionError as exc:
        raise RuntimeError(f"Report is locked; validated temporary report retained at {temporary_path}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ridership-path", type=Path, default=DEFAULT_RIDERSHIP_PATH)
    parser.add_argument("--routes-path", type=Path, default=DEFAULT_ROUTES_PATH)
    parser.add_argument("--stops-path", type=Path, default=DEFAULT_STOPS_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        pd.read_parquet(args.ridership_path),
        gpd.read_file(args.routes_path),
        pd.read_parquet(args.stops_path),
    )
    write_report(report, args.report_path)
    print(f"Profiling report saved to: {args.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
