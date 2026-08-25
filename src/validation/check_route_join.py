from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    import geopandas as gpd
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "GeoPandas is required for this script. Install it in your environment "
        "before running: pip install geopandas"
    ) from exc


def load_geojson_resilient(geojson_path: Path) -> gpd.GeoDataFrame:
    try:
        return gpd.read_file(geojson_path)
    except Exception as exc:
        print(
            "GeoPandas direct read failed. Attempting resilient fallback parse "
            "(first valid GeoJSON document only)."
        )
        print(f"  Original error: {exc}")

    raw_text = geojson_path.read_text(encoding="utf-8", errors="replace")
    decoder = json.JSONDecoder()

    try:
        first_obj, _end_index = decoder.raw_decode(raw_text.lstrip())
        if isinstance(first_obj, dict) and first_obj.get("type") == "FeatureCollection":
            features = first_obj.get("features")
            if isinstance(features, list):
                return gpd.GeoDataFrame.from_features(features)
    except json.JSONDecodeError:
        pass

    print("Primary fallback parse failed. Attempting line-by-line feature recovery.")
    recovered_features: list[dict[str, object]] = []
    skipped_feature_lines = 0

    with geojson_path.open("r", encoding="utf-8", errors="replace") as geo_file:
        for line in geo_file:
            candidate = line.strip()
            if not candidate:
                continue
            if not candidate.startswith('{"type":"Feature"'):
                continue

            if candidate.endswith(","):
                candidate = candidate[:-1]

            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                skipped_feature_lines += 1
                continue

            if isinstance(parsed, dict) and parsed.get("type") == "Feature":
                recovered_features.append(parsed)

    if not recovered_features:
        raise RuntimeError(
            "Failed to recover any valid feature records from GeoJSON. "
            "The file appears corrupted."
        )

    print(
        "Recovered features from malformed GeoJSON: "
        f"{len(recovered_features):,} parsed, {skipped_feature_lines:,} skipped malformed feature lines."
    )
    return gpd.GeoDataFrame.from_features(recovered_features)


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_RIDERSHIP_PATH = ROOT_DIR / "data" / "raw" / "mta_ridership_dev.parquet"
DEFAULT_GEOJSON_PATH = ROOT_DIR / "data" / "raw" / "mta_bus_routes.geojson"
RIDERSHIP_ROUTE_COLUMN = "bus_route"
GEO_ROUTE_CANDIDATES = (
    "route_short_name",
    "route_id",
    "bus_route",
    "route",
    "route_name",
)


def normalize_route_values(values: Iterable[object]) -> set[str]:
    series = pd.Series(list(values), dtype="object")
    normalized = (
        series.dropna()
        .astype(str)
        .str.strip()
        .str.upper()
    )
    normalized = normalized[normalized != ""]
    return set(normalized.tolist())


def detect_geo_route_column(gdf: gpd.GeoDataFrame, ridership_routes: set[str]) -> str:
    available_candidates = [column for column in GEO_ROUTE_CANDIDATES if column in gdf.columns]
    if not available_candidates:
        raise ValueError(
            "Could not find a route ID column in GeoJSON. "
            f"Checked candidates: {list(GEO_ROUTE_CANDIDATES)}"
        )

    best_column = available_candidates[0]
    best_overlap_count = -1

    print("\nGeoJSON route column candidate overlap:")
    for column in available_candidates:
        geo_routes = normalize_route_values(gdf[column].unique())
        overlap_count = len(ridership_routes.intersection(geo_routes))
        print(
            f"  - {column}: overlap={overlap_count:,} / "
            f"ridership_routes={len(ridership_routes):,}"
        )

        if overlap_count > best_overlap_count:
            best_overlap_count = overlap_count
            best_column = column

    return best_column


def summarize_route_overlap(ridership_df: pd.DataFrame, geo_df: gpd.GeoDataFrame) -> None:
    if RIDERSHIP_ROUTE_COLUMN not in ridership_df.columns:
        raise ValueError(
            f"Required ridership route column '{RIDERSHIP_ROUTE_COLUMN}' was not found."
        )

    ridership_routes = normalize_route_values(ridership_df[RIDERSHIP_ROUTE_COLUMN].unique())
    geo_route_column = detect_geo_route_column(geo_df, ridership_routes)
    geo_routes = normalize_route_values(geo_df[geo_route_column].unique())

    matching_routes = ridership_routes.intersection(geo_routes)
    ridership_missing_from_geo = ridership_routes.difference(geo_routes)
    geo_missing_from_ridership = geo_routes.difference(ridership_routes)

    match_percentage = (
        (len(matching_routes) / len(ridership_routes)) * 100.0
        if ridership_routes
        else 0.0
    )

    print("\nRoute Join Inspection")
    print(f"  Ridership route column: {RIDERSHIP_ROUTE_COLUMN}")
    print(f"  GeoJSON route column: {geo_route_column}")
    print(f"  Unique ridership routes: {len(ridership_routes):,}")
    print(f"  Unique GeoJSON routes: {len(geo_routes):,}")
    print(f"  Matching routes: {len(matching_routes):,}")
    print(f"  Ridership routes missing from GeoJSON: {len(ridership_missing_from_geo):,}")
    print(f"  GeoJSON routes missing from ridership: {len(geo_missing_from_ridership):,}")
    print(f"  Match percentage (ridership covered by GeoJSON): {match_percentage:.2f}%")

    matched_preview = sorted(matching_routes)[:10]
    ridership_missing_preview = sorted(ridership_missing_from_geo)[:10]
    geo_missing_preview = sorted(geo_missing_from_ridership)[:10]

    print("\nSample route IDs")
    print(f"  Matched (up to 10): {matched_preview}")
    print(f"  Ridership missing in GeoJSON (up to 10): {ridership_missing_preview}")
    print(f"  GeoJSON missing in ridership (up to 10): {geo_missing_preview}")

    can_join_fully = len(ridership_missing_from_geo) == 0
    print("\nJoin Conclusion")
    if can_join_fully:
        print(
            "  The datasets can be joined directly for ridership coverage using "
            f"ridership.{RIDERSHIP_ROUTE_COLUMN} -> geojson.{geo_route_column} "
            "(recommended with uppercase/trim normalization)."
        )
    else:
        print(
            "  The datasets can be joined, but not fully directly for all ridership routes. "
            f"Use ridership.{RIDERSHIP_ROUTE_COLUMN} -> geojson.{geo_route_column} "
            "(recommended with uppercase/trim normalization), and review missing route IDs."
        )


def summarize_geometry(geo_df: gpd.GeoDataFrame) -> None:
    geometry = geo_df.geometry
    null_geometries = int(geometry.isna().sum())
    empty_geometries = int(geometry.is_empty.sum())

    non_null_mask = geometry.notna()
    invalid_non_null = int((~geometry[non_null_mask].is_valid).sum())

    print("\nGeoJSON Geometry Inspection")
    print(f"  CRS: {geo_df.crs}")
    print(f"  Total features: {len(geo_df):,}")
    print(f"  Null geometries: {null_geometries:,}")
    print(f"  Empty geometries: {empty_geometries:,}")
    print(f"  Invalid non-null geometries: {invalid_non_null:,}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only inspection for joining ridership routes with GeoJSON routes."
    )
    parser.add_argument(
        "--ridership-path",
        type=Path,
        default=DEFAULT_RIDERSHIP_PATH,
        help="Path to mta_ridership_dev.parquet",
    )
    parser.add_argument(
        "--geojson-path",
        type=Path,
        default=DEFAULT_GEOJSON_PATH,
        help="Path to mta_bus_routes.geojson",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    ridership_path = args.ridership_path
    geojson_path = args.geojson_path

    print("Loading datasets (read-only)...")
    ridership_df = pd.read_parquet(ridership_path)
    geo_df = load_geojson_resilient(geojson_path)

    print("\nRidership columns:")
    print(list(ridership_df.columns))

    print("\nGeoJSON columns:")
    print(list(geo_df.columns))

    summarize_route_overlap(ridership_df=ridership_df, geo_df=geo_df)
    summarize_geometry(geo_df=geo_df)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
