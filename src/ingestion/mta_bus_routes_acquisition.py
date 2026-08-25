"""Acquire and validate the official MTA Bus Routes Socrata dataset."""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from shapely.geometry import shape
from urllib3.util.retry import Retry

SOCRATA_DOMAIN = "https://data.ny.gov"
DATASET_ID = "bzwk-3hb4"
METADATA_URL = f"{SOCRATA_DOMAIN}/api/views/{DATASET_ID}"
GEOJSON_URL = f"{SOCRATA_DOMAIN}/resource/{DATASET_ID}.geojson"
ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_PATH = ROOT_DIR / "data" / "raw" / "mta_bus_routes_valid.geojson"
DEFAULT_REPORT_PATH = ROOT_DIR / "data" / "raw" / "mta_bus_routes_valid_report.json"
RIDERSHIP_PATH = ROOT_DIR / "data" / "raw" / "mta_ridership_dev.parquet"
DATA_COLUMNS = ("valid_from", "valid_to", "in_effect", "route_id", "route_short_name", "route_long_name", "route_description", "trip_type", "route_type", "bundle", "route_color", "direction_id", "direction", "shape_id", "vertices", "shape_length", "min_longitude", "min_latitude", "max_longitude", "max_latitude", "geometry")
REQUIRED_ATTRIBUTES = ("route_id", "route_short_name", "shape_id", "direction_id")

@dataclass(frozen=True)
class Config:
    batch_size: int; timeout_seconds: int; max_retries: int; backoff_factor: float
    output_path: Path; report_path: Path

def retry_session(retries: int, backoff: float) -> requests.Session:
    policy = Retry(total=retries, connect=retries, read=retries, status=retries, backoff_factor=backoff, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset(("GET",)), raise_on_status=False)
    session = requests.Session()
    session.headers["User-Agent"] = "public-transit-dashboard/1.0 (official-data-acquisition)"
    session.mount("https://", HTTPAdapter(max_retries=policy))
    return session

def get_json(session: requests.Session, url: str, *, params: dict[str, Any] | None, timeout: int) -> Any:
    try:
        response = session.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"Official API request failed: {url}; params={params}; error={exc}") from exc

def inspect_metadata(session: requests.Session, config: Config) -> dict[str, Any]:
    metadata = get_json(session, METADATA_URL, params=None, timeout=config.timeout_seconds)
    fields = {column.get("fieldName") for column in metadata.get("columns", [])}
    missing = set(DATA_COLUMNS) - fields
    if missing: raise RuntimeError(f"Official metadata lacks expected fields: {sorted(missing)}")
    return {"id": metadata.get("id"), "name": metadata.get("name"), "rows_updated_at": metadata.get("rowsUpdatedAt"), "publication_date": metadata.get("publicationDate"), "metadata_updated_at": metadata.get("metadataUpdatedAt"), "declared_column_count": len(metadata.get("columns", []))}

def source_count(session: requests.Session, config: Config) -> int:
    payload = get_json(session, GEOJSON_URL, params={"$select": "count(*) as record_count"}, timeout=config.timeout_seconds)
    features = payload.get("features", []) if isinstance(payload, dict) else []
    if len(features) != 1: raise RuntimeError(f"Could not determine official source count: {payload!r}")
    try: return int(features[0]["properties"]["record_count"])
    except (KeyError, TypeError, ValueError) as exc: raise RuntimeError("Invalid official source count") from exc

def fetch_and_validate_batch(session: requests.Session, config: Config, offset: int) -> list[dict[str, Any]]:
    params = {"$select": ", ".join((*DATA_COLUMNS, ":id")), "$order": ":id", "$limit": config.batch_size, "$offset": offset}
    payload = get_json(session, GEOJSON_URL, params=params, timeout=config.timeout_seconds)
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection": raise RuntimeError(f"Batch {offset} is not a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or len(features) > config.batch_size: raise RuntimeError(f"Batch {offset} has an invalid feature list")
    seen: set[str] = set()
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature" or not isinstance(feature.get("properties"), dict): raise RuntimeError(f"Batch {offset}: feature {index} is structurally invalid")
        source_id = feature["properties"].get(":id")
        if source_id is None: raise RuntimeError(f"Batch {offset}: feature {index} lacks Socrata :id")
        source_id_text = str(source_id)
        if source_id_text in seen: raise RuntimeError(f"Batch {offset}: duplicate Socrata :id {source_id_text}")
        seen.add(source_id_text)
        if not source_id_text.strip(): raise RuntimeError(f"Batch {offset}: blank Socrata :id")
    return features

def feature_to_row(feature: dict[str, Any], source_index: int, issues: list[dict[str, Any]]) -> tuple[dict[str, Any], Any]:
    properties = feature["properties"]
    row = {column: properties.get(column) for column in DATA_COLUMNS if column != "geometry"}
    row["_socrata_id"] = properties[":id"]
    record_issues = [f"missing_attribute:{field}" for field in REQUIRED_ATTRIBUTES if row.get(field) is None]
    geometry_payload = feature.get("geometry"); geometry = None
    if geometry_payload is None: record_issues.append("null_geometry")
    elif not isinstance(geometry_payload, dict): record_issues.append(f"geometry_not_object:{type(geometry_payload).__name__}")
    else:
        try:
            geometry = shape(geometry_payload)
            if geometry.is_empty: record_issues.append("empty_geometry")
            elif not geometry.is_valid: record_issues.append("invalid_geometry")
        except Exception as exc: record_issues.append(f"geometry_parse_error:{exc}")
    if record_issues: issues.append({"source_index": source_index, "socrata_id": row["_socrata_id"], "route_id": row.get("route_id"), "shape_id": row.get("shape_id"), "issues": record_issues})
    return row, geometry

def normalize_ids(series: pd.Series) -> set[str]:
    values = series.dropna().astype(str).str.strip().str.upper()
    return set(values[values.ne("")])

def stats(gdf: gpd.GeoDataFrame) -> dict[str, Any]:
    geometry = gdf.geometry; present = geometry.notna()
    return {"total_features": len(gdf), "unique_route_id_values": int(gdf.route_id.nunique(dropna=True)), "unique_route_short_name_values": int(gdf.route_short_name.nunique(dropna=True)), "crs": str(gdf.crs), "null_geometries": int(geometry.isna().sum()), "empty_geometries": int(geometry[present].is_empty.sum()), "invalid_geometries": int((~geometry[present & ~geometry.is_empty].is_valid).sum())}

def compatibility(gdf: gpd.GeoDataFrame) -> dict[str, Any]:
    ridership = pd.read_parquet(RIDERSHIP_PATH)
    ridership_ids = normalize_ids(ridership["bus_route"]); official_ids = normalize_ids(gdf.route_id) | normalize_ids(gdf.route_short_name)
    matching = ridership_ids & official_ids; missing = ridership_ids - official_ids
    return {"ridership_unique_routes": len(ridership_ids), "matching_ridership_routes": len(matching), "missing_ridership_routes": len(missing), "coverage_percentage": round(100 * len(matching) / len(ridership_ids), 2) if ridership_ids else 0.0, "matching_ridership_route_ids": sorted(matching), "missing_ridership_route_ids": sorted(missing)}

def acquire(config: Config) -> dict[str, Any]:
    session = retry_session(config.max_retries, config.backoff_factor)
    metadata = inspect_metadata(session, config); expected = source_count(session, config)
    print(json.dumps({"official_metadata": metadata, "official_source_count": expected}, indent=2))
    rows: list[dict[str, Any]] = []; geometries: list[Any] = []; issues: list[dict[str, Any]] = []; seen: set[str] = set(); offset = 0
    while offset < expected:
        batch = fetch_and_validate_batch(session, config, offset)
        if not batch: raise RuntimeError(f"Official API ended early at {offset:,}; expected {expected:,}")
        for local_index, feature in enumerate(batch):
            source_id = str(feature["properties"][":id"])
            if source_id in seen: raise RuntimeError(f"Duplicate Socrata :id across batches: {source_id}")
            seen.add(source_id); row, geometry = feature_to_row(feature, offset + local_index, issues); rows.append(row); geometries.append(geometry)
        offset += len(batch); print(f"Validated API batch: offset={offset - len(batch):,}, size={len(batch):,}, total={offset:,}")
        if len(batch) < config.batch_size and offset != expected: raise RuntimeError(f"Short API batch ended at {offset:,}; metadata count is {expected:,}")
    if len(rows) != expected or len(seen) != expected: raise RuntimeError("Record-count reconciliation failed; refusing to write incomplete dataset")
    gdf = gpd.GeoDataFrame(pd.DataFrame(rows), geometry=geometries, crs="EPSG:4326")
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config.output_path.with_name(f"{config.output_path.stem}.tmp{config.output_path.suffix}")
    if temporary_path.exists():
        raise RuntimeError(f"Temporary output already exists; inspect or remove it before retrying: {temporary_path}")
    gdf.to_file(temporary_path, driver="GeoJSON")
    # Deliberately use the normal reader before allowing the final-file rename.
    verified = gpd.read_file(temporary_path)
    if len(verified) != expected: raise RuntimeError(f"Normal read_file count mismatch: {len(verified):,} != {expected:,}")
    try:
        os.replace(temporary_path, config.output_path)
    except PermissionError as exc:
        raise RuntimeError(
            f"Final output is locked and was not overwritten: {config.output_path}. "
            f"Validated temporary file retained at: {temporary_path}"
        ) from exc
    report = {"official_metadata": metadata, "official_source_count": expected, "normal_read_file_succeeded": True, "output_stats": stats(verified), "ridership_compatibility": compatibility(verified), "source_records_with_issues": len(issues), "source_record_issues": issues}
    config.report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=5000); parser.add_argument("--timeout-seconds", type=int, default=60); parser.add_argument("--max-retries", type=int, default=5); parser.add_argument("--backoff-factor", type=float, default=1.0); parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH); parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 50000: raise ValueError("batch-size must be between 1 and 50,000")
    print(json.dumps(acquire(Config(args.batch_size, args.timeout_seconds, args.max_retries, args.backoff_factor, args.output_path, args.report_path)), indent=2))
    return 0

if __name__ == "__main__": raise SystemExit(main())
