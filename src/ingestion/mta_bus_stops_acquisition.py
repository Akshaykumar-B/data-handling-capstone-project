"""Acquire the active official MTA Bus Stops records for project routes.

This module is intentionally not invoked on import. It keeps physical stops
(``stop_id``) distinct from route-stop associations and retains records with
missing or invalid values so they can be reported rather than silently dropped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


API_BASE_URL = "https://data.ny.gov/resource"
DATASET_ID = "2ucp-7wg5"
ENDPOINT_URL = f"{API_BASE_URL}/{DATASET_ID}.json"
SOURCE_RECORD_COUNT = 3_166_924
EXPECTED_PROJECT_ROUTE_COUNT = 142

REQUIRED_COLUMNS = (
    "valid_from", "valid_to", "in_effect", "route_id", "route_short_name",
    "route_long_name", "route_description", "route_color", "stop_id", "stop_name",
    "direction_id", "direction", "revenue_stop", "timepoint", "boarding",
    "alighting", "is_cbd", "latitude", "longitude", "bundle", "georeference",
)
ASSOCIATION_KEY_COLUMNS = (
    "route_id", "route_short_name", "stop_id", "direction_id", "bundle",
)
ROUTE_COLUMNS = ("route_id", "route_short_name")

ROOT_DIR = Path(__file__).resolve().parents[2]
RIDERSHIP_PATH = ROOT_DIR / "data" / "raw" / "mta_ridership_dev.parquet"
ROUTES_PATH = ROOT_DIR / "data" / "raw" / "mta_bus_routes_valid.geojson"
DEFAULT_OUTPUT_PATH = ROOT_DIR / "data" / "raw" / "mta_bus_stops_project.parquet"
DEFAULT_SUMMARY_PATH = ROOT_DIR / "data" / "raw" / "mta_bus_stops_project_ingestion_summary.json"

DEFAULT_BATCH_SIZE = 25_000
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_RETRIES = 5
DEFAULT_BACKOFF_FACTOR = 1.0


@dataclass(frozen=True)
class IngestionConfig:
    endpoint_url: str
    batch_size: int
    timeout_seconds: int
    max_retries: int
    backoff_factor: float
    output_path: Path
    summary_path: Path


def _positive_int_from_env(name: str, default: int) -> int:
    value = os.getenv(name)
    try:
        return int(value) if value is not None and int(value) > 0 else default
    except ValueError:
        print(f"Invalid integer for {name}={value!r}; using default={default}.")
        return default


def _positive_float_from_env(name: str, default: float) -> float:
    value = os.getenv(name)
    try:
        return float(value) if value is not None and float(value) > 0 else default
    except ValueError:
        print(f"Invalid float for {name}={value!r}; using default={default}.")
        return default


def build_config(
    output_path: Path | None = None,
    summary_path: Path | None = None,
) -> IngestionConfig:
    return IngestionConfig(
        endpoint_url=ENDPOINT_URL,
        batch_size=_positive_int_from_env("MTA_BUS_STOPS_BATCH_SIZE", DEFAULT_BATCH_SIZE),
        timeout_seconds=_positive_int_from_env("MTA_REQUEST_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
        max_retries=_positive_int_from_env("MTA_MAX_RETRIES", DEFAULT_MAX_RETRIES),
        backoff_factor=_positive_float_from_env("MTA_BACKOFF_FACTOR", DEFAULT_BACKOFF_FACTOR),
        output_path=output_path or DEFAULT_OUTPUT_PATH,
        summary_path=summary_path or DEFAULT_SUMMARY_PATH,
    )


def create_retry_session(max_retries: int, backoff_factor: float) -> requests.Session:
    retry = Retry(
        total=max_retries,
        connect=max_retries,
        read=max_retries,
        status=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers["User-Agent"] = "public-transit-dashboard/1.0 (bus-stops-ingestion)"
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def normalize_route_identifier(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def normalize_identifier_set(values: pd.Series) -> set[str]:
    return {
        normalized
        for value in values
        if (normalized := normalize_route_identifier(value)) is not None
    }


def load_project_route_identifiers() -> tuple[set[str], set[str], dict[str, set[str]]]:
    """Return normalized ridership IDs and route-dataset aliases for those IDs."""
    ridership = pd.read_parquet(RIDERSHIP_PATH)
    if "bus_route" not in ridership.columns:
        raise ValueError(f"Ridership input has no bus_route column: {RIDERSHIP_PATH}")
    ridership_route_ids = normalize_identifier_set(ridership["bus_route"])
    if not ridership_route_ids:
        raise ValueError("Ridership input contains no usable bus_route values.")
    if len(ridership_route_ids) != EXPECTED_PROJECT_ROUTE_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_PROJECT_ROUTE_COUNT} unique ridership routes; found {len(ridership_route_ids)}."
        )

    routes = gpd.read_file(ROUTES_PATH)
    missing_columns = [column for column in ROUTE_COLUMNS if column not in routes.columns]
    if missing_columns:
        raise ValueError(f"Route geometry input is missing columns: {missing_columns}")

    aliases: set[str] = set()
    aliases_by_ridership_route = {route_id: {route_id} for route_id in ridership_route_ids}
    for _, route in routes[list(ROUTE_COLUMNS)].iterrows():
        route_id = normalize_route_identifier(route["route_id"])
        short_name = normalize_route_identifier(route["route_short_name"])
        route_values = {value for value in (route_id, short_name) if value}
        matching_ridership_routes = ridership_route_ids.intersection(route_values)
        if matching_ridership_routes:
            aliases.update(value for value in (route_id, short_name) if value)
            for ridership_route_id in matching_ridership_routes:
                aliases_by_ridership_route[ridership_route_id].update(route_values)

    # Preserve a direct ridership route match even if it has no corresponding route geometry alias.
    aliases.update(ridership_route_ids)
    return ridership_route_ids, aliases, aliases_by_ridership_route


def _socrata_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_where_clause(route_identifiers: set[str]) -> str:
    if not route_identifiers:
        raise ValueError("Cannot query Bus Stops without project route identifiers.")
    values = ", ".join(_socrata_string(value) for value in sorted(route_identifiers))
    return (
        "in_effect = 'true' AND "
        f"(upper(route_id) IN ({values}) OR upper(route_short_name) IN ({values}))"
    )


def build_query_params(
    config: IngestionConfig,
    where_clause: str,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    return {
        "$select": ", ".join(REQUIRED_COLUMNS),
        "$where": where_clause,
        "$order": "route_id, route_short_name, stop_id, direction_id, bundle, :id",
        "$limit": limit,
        "$offset": offset,
    }


def fetch_json(
    session: requests.Session,
    config: IngestionConfig,
    params: dict[str, Any],
    context: str,
) -> Any:
    try:
        response = session.get(config.endpoint_url, params=params, timeout=config.timeout_seconds)
    except requests.RequestException as exc:
        raise RuntimeError(f"Request failed ({context}): {exc}") from exc
    if response.status_code >= 400:
        raise RuntimeError(
            f"API returned HTTP {response.status_code} ({context}): {response.text[:500]}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"Invalid JSON response ({context}): {exc}") from exc


def fetch_count(
    session: requests.Session,
    config: IngestionConfig,
    where_clause: str | None,
) -> int:
    params: dict[str, Any] = {"$select": "count(*) as record_count"}
    if where_clause:
        params["$where"] = where_clause
    payload = fetch_json(session, config, params, "count query")
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise RuntimeError("Count query did not return exactly one object.")
    try:
        return int(payload[0]["record_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid count payload: {payload!r}") from exc


def validate_and_normalize_batch(
    payload: Any,
    batch_offset: int,
    validation_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise RuntimeError(f"Batch at offset {batch_offset:,} is not a JSON list.")
    normalized_records: list[dict[str, Any]] = []
    for row_offset, source_record in enumerate(payload):
        if not isinstance(source_record, dict):
            raise RuntimeError(
                f"Batch at offset {batch_offset:,} has a non-object record at index {row_offset}; no records accepted."
            )
        unexpected_columns = set(source_record).difference(REQUIRED_COLUMNS)
        if unexpected_columns:
            raise RuntimeError(
                f"Batch at offset {batch_offset:,} record {row_offset} has unexpected fields: {sorted(unexpected_columns)}"
            )
        record = {column: source_record.get(column) for column in REQUIRED_COLUMNS}
        issue_types: list[str] = []
        if not normalize_route_identifier(record["route_id"]) and not normalize_route_identifier(record["route_short_name"]):
            issue_types.append("missing_route_identifier")
        if not normalize_route_identifier(record["stop_id"]):
            issue_types.append("missing_stop_id")
        for coordinate_name, low, high in (("latitude", -90.0, 90.0), ("longitude", -180.0, 180.0)):
            value = pd.to_numeric(pd.Series([record[coordinate_name]]), errors="coerce").iloc[0]
            if pd.isna(value) or not low <= float(value) <= high:
                issue_types.append(f"invalid_{coordinate_name}")
        if issue_types:
            validation_issues.append({
                "source_offset": batch_offset + row_offset,
                "route_id": record["route_id"],
                "route_short_name": record["route_short_name"],
                "stop_id": record["stop_id"],
                "issues": issue_types,
            })
        normalized_records.append(record)
    return normalized_records


def validate_required_columns(df: pd.DataFrame) -> None:
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Required columns missing from normalized API response: {missing_columns}")


def download_project_records(config: IngestionConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ridership_routes, route_identifiers, aliases_by_ridership_route = load_project_route_identifiers()
    where_clause = build_where_clause(route_identifiers)
    session = create_retry_session(config.max_retries, config.backoff_factor)
    official_source_count = fetch_count(session, config, None)
    filtered_source_count = fetch_count(session, config, where_clause)

    records: list[dict[str, Any]] = []
    validation_issues: list[dict[str, Any]] = []
    offset = 0
    while offset < filtered_source_count:
        payload = fetch_json(
            session,
            config,
            build_query_params(config, where_clause, offset, config.batch_size),
            f"offset={offset:,}, limit={config.batch_size:,}",
        )
        batch = validate_and_normalize_batch(payload, offset, validation_issues)
        if not batch:
            raise RuntimeError(
                f"API ended at {offset:,} records; filtered source count is {filtered_source_count:,}."
            )
        if len(batch) > config.batch_size:
            raise RuntimeError(f"API returned more records than requested at offset {offset:,}.")
        records.extend(batch)
        offset += len(batch)
        print(f"Validated batch: {len(batch):,} records | Total: {offset:,}")
        if len(batch) < config.batch_size and offset != filtered_source_count:
            raise RuntimeError("Short non-final batch; refusing to write an incomplete extraction.")
    if len(records) != filtered_source_count:
        raise RuntimeError("Downloaded-record reconciliation failed; refusing to write output.")
    return records, {
        "official_source_record_count": official_source_count,
        "known_official_source_record_count": SOURCE_RECORD_COUNT,
        "filtered_source_record_count": filtered_source_count,
        "ridership_route_ids": sorted(ridership_routes),
        "api_route_identifiers": sorted(route_identifiers),
        "aliases_by_ridership_route": aliases_by_ridership_route,
        "validation_issues": validation_issues,
    }


def summarize_dataset(df: pd.DataFrame, context: dict[str, Any]) -> dict[str, Any]:
    route_id_values = normalize_identifier_set(df["route_id"])
    route_short_name_values = normalize_identifier_set(df["route_short_name"])
    downloaded_route_identifiers = route_id_values | route_short_name_values
    ridership_route_ids = set(context["ridership_route_ids"])
    matching_routes = {
        route_id
        for route_id, aliases in context["aliases_by_ridership_route"].items()
        if aliases.intersection(downloaded_route_identifiers)
    }
    missing_routes = ridership_route_ids.difference(matching_routes)
    invalid_coordinate_count = sum(
        any(issue in entry["issues"] for issue in ("invalid_latitude", "invalid_longitude"))
        for entry in context["validation_issues"]
    )
    duplicate_count = int(df.duplicated(subset=list(ASSOCIATION_KEY_COLUMNS)).sum())
    return {
        "dataset_id": DATASET_ID,
        "endpoint": ENDPOINT_URL,
        "source_record_count": context["official_source_record_count"],
        "known_source_record_count": context["known_official_source_record_count"],
        "filtered_source_record_count": context["filtered_source_record_count"],
        "downloaded_record_count": int(len(df)),
        "unique_physical_stops": int(df["stop_id"].nunique(dropna=True)),
        "unique_routes": int(len(downloaded_route_identifiers)),
        "unique_route_stop_associations": int(df[list(ASSOCIATION_KEY_COLUMNS)].drop_duplicates().shape[0]),
        "association_key_columns": list(ASSOCIATION_KEY_COLUMNS),
        "unique_directions": int(df["direction_id"].nunique(dropna=True)),
        "missing_values": {column: int(df[column].isna().sum()) for column in REQUIRED_COLUMNS},
        "missing_stop_id_count": int(df["stop_id"].isna().sum() + df["stop_id"].astype("string").str.strip().eq("").sum()),
        "missing_route_identifier_count": int(sum(
            not normalize_route_identifier(route_id) and not normalize_route_identifier(short_name)
            for route_id, short_name in zip(df["route_id"], df["route_short_name"])
        )),
        "invalid_coordinate_count": int(invalid_coordinate_count),
        "duplicate_association_count": duplicate_count,
        "route_coverage": {
            "ridership_route_count": len(ridership_route_ids),
            "matching_ridership_routes": len(matching_routes),
            "missing_ridership_routes": sorted(missing_routes),
            "coverage_percentage": round(100 * len(matching_routes) / len(ridership_route_ids), 2) if ridership_route_ids else 0.0,
        },
        "records_with_validation_issues": len(context["validation_issues"]),
        "validation_issues": context["validation_issues"],
    }


def temporary_path_for(path: Path) -> Path:
    return path.with_name(f"{path.stem}.tmp{path.suffix}")


def write_outputs(df: pd.DataFrame, summary: dict[str, Any], config: IngestionConfig) -> None:
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.summary_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = temporary_path_for(config.output_path)
    temporary_summary = temporary_path_for(config.summary_path)
    for temporary_path in (temporary_output, temporary_summary):
        if temporary_path.exists():
            raise RuntimeError(f"Temporary output already exists; inspect it before retrying: {temporary_path}")

    df.to_parquet(temporary_output, index=False)
    verified_df = pd.read_parquet(temporary_output)
    if len(verified_df) != len(df) or list(verified_df.columns) != list(REQUIRED_COLUMNS):
        raise RuntimeError("Temporary Parquet validation failed; final files were not changed.")
    temporary_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if json.loads(temporary_summary.read_text(encoding="utf-8")) != summary:
        raise RuntimeError("Temporary summary validation failed; final files were not changed.")
    try:
        os.replace(temporary_output, config.output_path)
    except PermissionError as exc:
        raise RuntimeError(
            "The final Parquet output is locked and was not overwritten. Validated temporary files were retained at "
            f"{temporary_output} and {temporary_summary}."
        ) from exc
    try:
        os.replace(temporary_summary, config.summary_path)
    except PermissionError as exc:
        raise RuntimeError(
            "The final summary is locked. The Parquet output was replaced successfully; "
            f"the validated temporary summary was retained at {temporary_summary}."
        ) from exc


def run_ingestion(
    output_path: Path | None = None,
    summary_path: Path | None = None,
) -> dict[str, Any]:
    config = build_config(output_path=output_path, summary_path=summary_path)
    records, context = download_project_records(config)
    df = pd.DataFrame.from_records(records, columns=REQUIRED_COLUMNS)
    validate_required_columns(df)
    summary = summarize_dataset(df, context)
    write_outputs(df, summary, config)
    print(json.dumps(summary, indent=2))
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--summary-path", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run_ingestion(output_path=args.output_path, summary_path=args.summary_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
