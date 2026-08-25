from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


API_BASE_URL = "https://data.ny.gov/resource"
DATASET_ID = "kv7t-n8in"
ENDPOINT_URL = f"{API_BASE_URL}/{DATASET_ID}.json"

DATE_START = "2023-01-01T00:00:00"
DATE_END = "2023-02-28T23:00:00"

REQUIRED_COLUMNS = (
    "transit_timestamp",
    "bus_route",
    "payment_method",
    "fare_class_category",
    "ridership",
    "transfers",
)

BUSINESS_KEY_COLUMNS = (
    "transit_timestamp",
    "bus_route",
    "payment_method",
    "fare_class_category",
)

DEFAULT_BATCH_SIZE = 50_000
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 5
DEFAULT_BACKOFF_FACTOR = 1.0
DEFAULT_INGESTION_MODE = "development"
DEFAULT_DEVELOPMENT_ROW_LIMIT = 200_000
DEVELOPMENT_MIN_ROUTE_COVERAGE = 0.95

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DEVELOPMENT_OUTPUT_PATH = ROOT_DIR / "data" / "raw" / "mta_ridership_dev.parquet"
DEFAULT_DEVELOPMENT_SUMMARY_PATH = ROOT_DIR / "data" / "raw" / "mta_ridership_dev_ingestion_summary.json"
DEFAULT_FULL_OUTPUT_PATH = ROOT_DIR / "data" / "raw" / "mta_ridership_2023_jan_feb.parquet"
DEFAULT_FULL_SUMMARY_PATH = ROOT_DIR / "data" / "raw" / "mta_ridership_2023_jan_feb_ingestion_summary.json"

PROJECT_ROUTE_CANDIDATE_PATHS = (
    ROOT_DIR / "data" / "processed" / "dataset_profiling_report.json",
    ROOT_DIR / "data" / "raw" / "mta_bus_routes_valid_report.json",
    ROOT_DIR / "data" / "raw" / "mta_ridership_2023_jan_feb.parquet",
)


@dataclass(frozen=True)
class IngestionConfig:
    endpoint_url: str
    date_start: str
    date_end: str
    required_columns: tuple[str, ...]
    ingestion_mode: str
    development_row_limit: int
    batch_size: int
    timeout_seconds: int
    max_retries: int
    backoff_factor: float
    output_path: Path
    summary_path: Path


def _int_from_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except ValueError:
        print(f"Invalid integer for {name}={value!r}; using default={default}.")
        return default


def _float_from_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = float(value)
        return parsed if parsed > 0 else default
    except ValueError:
        print(f"Invalid float for {name}={value!r}; using default={default}.")
        return default


def _resolve_mode(mode: str | None) -> str:
    resolved = mode or os.getenv("MTA_INGESTION_MODE", DEFAULT_INGESTION_MODE)
    normalized = resolved.strip().lower()
    if normalized not in {"development", "full"}:
        print(
            f"Invalid ingestion mode {resolved!r}; defaulting to {DEFAULT_INGESTION_MODE!r}."
        )
        return DEFAULT_INGESTION_MODE
    return normalized


def build_config(
    mode: str | None = None,
    output_path: Path | None = None,
    summary_path: Path | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    development_row_limit: int | None = None,
) -> IngestionConfig:
    resolved_mode = _resolve_mode(mode)
    resolved_row_limit = development_row_limit or _int_from_env(
        "MTA_DEVELOPMENT_ROW_LIMIT", DEFAULT_DEVELOPMENT_ROW_LIMIT
    )
    if resolved_row_limit <= 0:
        resolved_row_limit = DEFAULT_DEVELOPMENT_ROW_LIMIT

    default_output = (
        DEFAULT_DEVELOPMENT_OUTPUT_PATH
        if resolved_mode == "development"
        else DEFAULT_FULL_OUTPUT_PATH
    )
    default_summary = (
        DEFAULT_DEVELOPMENT_SUMMARY_PATH
        if resolved_mode == "development"
        else DEFAULT_FULL_SUMMARY_PATH
    )

    return IngestionConfig(
        endpoint_url=ENDPOINT_URL,
        date_start=date_start or DATE_START,
        date_end=date_end or DATE_END,
        required_columns=REQUIRED_COLUMNS,
        ingestion_mode=resolved_mode,
        development_row_limit=resolved_row_limit,
        batch_size=_int_from_env("MTA_BATCH_SIZE", DEFAULT_BATCH_SIZE),
        timeout_seconds=_int_from_env("MTA_REQUEST_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
        max_retries=_int_from_env("MTA_MAX_RETRIES", DEFAULT_MAX_RETRIES),
        backoff_factor=_float_from_env("MTA_BACKOFF_FACTOR", DEFAULT_BACKOFF_FACTOR),
        output_path=output_path or default_output,
        summary_path=summary_path or default_summary,
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
    adapter = HTTPAdapter(max_retries=retry)

    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def build_query_params(config: IngestionConfig, offset: int, limit: int) -> dict[str, Any]:
    selected_columns = ", ".join(config.required_columns)
    where_clause = (
        f"transit_timestamp between '{config.date_start}' and '{config.date_end}'"
    )
    return {
        "$select": selected_columns,
        "$where": where_clause,
        "$order": "transit_timestamp, bus_route, payment_method, fare_class_category",
        "$limit": limit,
        "$offset": offset,
    }


def _normalize_route_id(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def _load_project_route_ids() -> list[str]:
    """Load the authoritative project route set from persisted profiling outputs, never from the dev parquet."""
    for candidate_path in PROJECT_ROUTE_CANDIDATE_PATHS:
        if not candidate_path.exists():
            continue

        try:
            if candidate_path.suffix == ".parquet":
                df = pd.read_parquet(candidate_path)
                if "bus_route" not in df.columns:
                    continue
                routes = {
                    normalized
                    for value in df["bus_route"]
                    if (normalized := _normalize_route_id(value)) is not None
                }
                if routes:
                    return sorted(routes)
            elif candidate_path.suffix == ".json":
                payload = json.loads(candidate_path.read_text(encoding="utf-8"))
                routes: set[str] = set()

                if candidate_path.name == "dataset_profiling_report.json":
                    ridership_by_route = payload.get("aggregations", {}).get("ridership_by_route")
                    if isinstance(ridership_by_route, dict):
                        for route_name in ridership_by_route:
                            normalized = _normalize_route_id(route_name)
                            if normalized is not None:
                                routes.add(normalized)
                else:
                    for route_key in (
                        "matching_ridership_route_ids",
                        "ridership_route_ids",
                        "project_route_ids",
                        "route_ids",
                    ):
                        values = payload.get(route_key)
                        if isinstance(values, list):
                            for value in values:
                                normalized = _normalize_route_id(value)
                                if normalized is not None:
                                    routes.add(normalized)

                if routes:
                    return sorted(routes)
        except Exception:
            continue

    raise ValueError(
        "Could not find the authoritative 142-route project set in persisted project artifacts. "
        "Use the original profiling report or the official route compatibility report, not the biased development parquet."
    )


def _route_balanced_subset(project_routes: list[str], stratum_index: int, row_limit: int) -> list[str]:
    if not project_routes:
        return []

    ordered_routes = sorted(
        project_routes,
        key=lambda route: (
            hashlib.sha256(f"{stratum_index}|{route}".encode("utf-8")).hexdigest(),
            route,
        ),
    )

    if len(ordered_routes) <= 12:
        return ordered_routes

    route_count = max(12, min(len(ordered_routes), row_limit // 20))
    route_count = min(route_count, len(ordered_routes))
    selected = ordered_routes[:route_count]
    return selected


def build_development_query_params(
    config: IngestionConfig,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    limit: int,
    offset: int = 0,
    route_subset: list[str] | None = None,
) -> dict[str, Any]:
    selected_columns = ", ".join(config.required_columns)
    window_start_str = window_start.strftime("%Y-%m-%dT%H:%M:%S")
    window_end_str = window_end.strftime("%Y-%m-%dT%H:%M:%S")
    criteria: list[str] = [
        f"transit_timestamp between '{window_start_str}' and '{window_end_str}'"
    ]
    if route_subset:
        route_values_sql = ", ".join(f"'{route}'" for route in route_subset)
        criteria.append(f"upper(bus_route) in ({route_values_sql})")
    where_clause = " AND ".join(criteria)

    return {
        "$select": selected_columns,
        "$where": where_clause,
        "$order": "transit_timestamp, bus_route, payment_method, fare_class_category",
        "$limit": limit,
        "$offset": offset,
    }


def fetch_batch(
    session: requests.Session,
    config: IngestionConfig,
    params: dict[str, Any],
    context_label: str,
) -> list[dict[str, Any]]:
    try:
        response = session.get(config.endpoint_url, params=params, timeout=config.timeout_seconds)
    except requests.RequestException as exc:
        raise RuntimeError(f"Request failed ({context_label}): {exc}") from exc

    if response.status_code >= 400:
        snippet = response.text[:500]
        raise RuntimeError(
            "API returned HTTP error "
            f"{response.status_code} ({context_label}). Response snippet: {snippet}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Failed to decode JSON ({context_label}): {exc}") from exc

    if not isinstance(payload, list):
        raise RuntimeError(
            f"Unexpected API payload ({context_label}). Expected list, got {type(payload).__name__}."
        )

    return payload


def validate_required_columns(df: pd.DataFrame, required_columns: tuple[str, ...]) -> None:
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Required columns missing from API response: {missing_columns}")


def convert_column_types(df: pd.DataFrame) -> dict[str, int]:
    conversion_issues: dict[str, int] = {}

    ts_before_non_null = df["transit_timestamp"].notna().sum()
    df["transit_timestamp"] = pd.to_datetime(df["transit_timestamp"], errors="coerce")
    ts_after_non_null = df["transit_timestamp"].notna().sum()
    conversion_issues["transit_timestamp_coerced_to_null"] = int(ts_before_non_null - ts_after_non_null)

    for numeric_column in ("ridership", "transfers"):
        before_non_null = df[numeric_column].notna().sum()
        df[numeric_column] = pd.to_numeric(df[numeric_column], errors="coerce")
        after_non_null = df[numeric_column].notna().sum()
        conversion_issues[f"{numeric_column}_coerced_to_null"] = int(before_non_null - after_non_null)

    return conversion_issues


def summarize_dataset(df: pd.DataFrame, config: IngestionConfig) -> dict[str, Any]:
    missing_values_by_column = {
        column: int(df[column].isna().sum()) for column in config.required_columns
    }
    duplicate_count = int(df.duplicated(subset=list(BUSINESS_KEY_COLUMNS)).sum())

    timestamp_series = df["transit_timestamp"].dropna()
    observed_start = timestamp_series.min().isoformat() if not timestamp_series.empty else None
    observed_end = timestamp_series.max().isoformat() if not timestamp_series.empty else None
    unique_dates = int(timestamp_series.dt.date.nunique()) if not timestamp_series.empty else 0
    rows_by_hour = (
        timestamp_series.dt.hour.value_counts().sort_index().astype(int).to_dict()
        if not timestamp_series.empty
        else {}
    )
    unique_source_records = int(df[list(BUSINESS_KEY_COLUMNS)].drop_duplicates().shape[0])
    routes = df["bus_route"].dropna()
    rows_by_route = (
        routes.astype(str).str.upper().value_counts().sort_index().to_dict()
        if not routes.empty
        else {}
    )

    summary = {
        "rows_downloaded": int(len(df)),
        "total_rows": int(len(df)),
        "unique_source_business_records": unique_source_records,
        "ingestion_mode": config.ingestion_mode,
        "development_data": bool(config.ingestion_mode == "development"),
        "development_row_limit": int(config.development_row_limit),
        "configured_date_range": {
            "start": config.date_start,
            "end": config.date_end,
        },
        "actual_min_timestamp": observed_start,
        "actual_max_timestamp": observed_end,
        "observed_date_range": {"start": observed_start, "end": observed_end},
        "unique_routes": int(routes.nunique(dropna=True)),
        "unique_dates": unique_dates,
        "unique_hours": len(rows_by_hour),
        "rows_by_hour": rows_by_hour,
        "rows_by_route": rows_by_route,
        "missing_values": missing_values_by_column,
        "duplicate_count": duplicate_count,
        "duplicate_count_business_key": duplicate_count,
        "business_key_columns": list(BUSINESS_KEY_COLUMNS),
    }
    return summary


def _build_development_strata(
    date_start: str,
    date_end: str,
    target_rows: int,
) -> list[tuple[pd.Timestamp, pd.Timestamp, int]]:
    start_ts = pd.to_datetime(date_start)
    end_ts = pd.to_datetime(date_end)
    if pd.isna(start_ts) or pd.isna(end_ts):
        raise ValueError("Invalid date_start/date_end provided.")
    if start_ts > end_ts:
        raise ValueError("date_start cannot be later than date_end.")

    day_starts = pd.date_range(start=start_ts.normalize(), end=end_ts.normalize(), freq="D")
    strata_count = len(day_starts) * 12
    if strata_count == 0:
        return []

    base_rows = target_rows // strata_count
    remainder_rows = target_rows % strata_count
    strata: list[tuple[pd.Timestamp, pd.Timestamp, int]] = []
    for day_index, day_start in enumerate(day_starts):
        for band_index in range(12):
            hour_start = day_start + timedelta(hours=band_index * 2)
            hour_end = hour_start + timedelta(hours=2) - timedelta(seconds=1)
            window_start = max(hour_start, start_ts)
            window_end = min(hour_end, end_ts)
            stratum_index = day_index * 12 + band_index
            rows_for_stratum = base_rows + (stratum_index < remainder_rows)
            strata.append((window_start, window_end, rows_for_stratum))
    return strata


def _sample_development_data(df: pd.DataFrame, target_rows: int) -> pd.DataFrame:
    if len(df) <= target_rows:
        return df.copy()

    sampled = df.sort_values(
        list(REQUIRED_COLUMNS), kind="mergesort", na_position="last"
    ).reset_index(drop=True)
    sampled["_sample_date"] = sampled["transit_timestamp"].dt.date
    sampled["_sample_hour"] = sampled["transit_timestamp"].dt.hour
    sampled["_sample_route"] = sampled["bus_route"].fillna("<MISSING_ROUTE>")

    hour_groups = sampled.groupby(
        ["_sample_date", "_sample_hour"], sort=True, dropna=False
    ).indices
    selected: list[int] = []
    selected_set: set[int] = set()
    for positions in hour_groups.values():
        position = int(positions[0])
        selected.append(position)
        selected_set.add(position)
        if len(selected) == target_rows:
            break

    if len(selected) < target_rows:
        strata_groups = sampled.groupby(
            ["_sample_date", "_sample_hour", "_sample_route"],
            sort=True,
            dropna=False,
        ).indices
        remaining_groups = [
            [int(position) for position in positions if int(position) not in selected_set]
            for positions in strata_groups.values()
        ]
        round_index = 0
        while len(selected) < target_rows and remaining_groups:
            next_groups: list[list[int]] = []
            for positions in remaining_groups:
                if round_index < len(positions):
                    position = positions[round_index]
                    selected.append(position)
                    if len(selected) == target_rows:
                        break
                if round_index + 1 < len(positions):
                    next_groups.append(positions)
            remaining_groups = next_groups
            round_index += 1

    sampled = sampled.iloc[sorted(selected)].drop(
        columns=["_sample_date", "_sample_hour", "_sample_route"]
    )
    return sampled.reset_index(drop=True)


def download_all_records(config: IngestionConfig) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    development_request_count = 0

    session = create_retry_session(
        max_retries=config.max_retries,
        backoff_factor=config.backoff_factor,
    )

    print("Starting ingestion for MTA bus ridership dataset.")
    print(
        f"Mode={config.ingestion_mode} | batch_size={config.batch_size} | "
        f"timeout={config.timeout_seconds}s | retries={config.max_retries}"
    )
    if config.ingestion_mode == "development":
        print(
            "DEVELOPMENT DATA mode enabled: "
            f"deterministic date-stratified extraction capped at approximately {config.development_row_limit:,} rows."
        )

    if config.ingestion_mode == "development":
        project_routes = _load_project_route_ids()
        development_strata = _build_development_strata(
            date_start=config.date_start,
            date_end=config.date_end,
            target_rows=config.development_row_limit,
        )
        print(
            f"Using {len(development_strata)} date/two-hour API strata from "
            f"{config.date_start} to {config.date_end}."
        )
        if project_routes:
            print(
                f"Deterministic route-aware development sampling enabled for "
                f"{len(project_routes)} project routes."
            )

        for stratum_index, (window_start, window_end, row_limit) in enumerate(
            development_strata, start=1
        ):
            if row_limit <= 0:
                continue
            route_subset = _route_balanced_subset(project_routes, stratum_index, row_limit)
            params = build_development_query_params(
                config=config,
                window_start=window_start,
                window_end=window_end,
                limit=row_limit,
                route_subset=route_subset,
            )
            label = (
                f"development stratum {stratum_index}/{len(development_strata)} "
                f"[{window_start.strftime('%Y-%m-%dT%H:%M:%S')} to "
                f"{window_end.strftime('%Y-%m-%dT%H:%M:%S')}]"
            )
            batch = fetch_batch(
                session=session,
                config=config,
                params=params,
                context_label=label,
            )
            development_request_count += 1
            records.extend(batch)
            print(
                f"API request {development_request_count}/{len(development_strata)}: "
                f"downloaded {len(batch):,} rows | Total API rows downloaded: "
                f"{len(records):,} | routes={len(route_subset)} | {label}"
            )
    else:
        offset = 0
        while True:
            params = build_query_params(config=config, offset=offset, limit=config.batch_size)
            batch = fetch_batch(
                session=session,
                config=config,
                params=params,
                context_label=f"full mode offset={offset}, limit={config.batch_size}",
            )

            if not batch:
                print("No more records returned by API. Ingestion complete.")
                break

            records.extend(batch)
            offset += len(batch)

            print(
                f"Batch downloaded: {len(batch):,} rows | "
                f"Total rows downloaded: {len(records):,} | Next offset: {offset:,}"
            )

            if len(batch) < config.batch_size:
                print("Final partial batch received. Ingestion complete.")
                break

    if config.ingestion_mode == "development":
        print(
            f"Development API requests: {development_request_count} | "
            f"Total API rows downloaded: {len(records):,}"
        )
    return records


def save_outputs(df: pd.DataFrame, summary: dict[str, Any], config: IngestionConfig) -> None:
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.summary_path.parent.mkdir(parents=True, exist_ok=True)

    if config.output_path.exists():
        print(f"Existing output found. Overwriting: {config.output_path}")

    df.to_parquet(config.output_path, index=False)

    with config.summary_path.open("w", encoding="utf-8") as summary_file:
        json.dump(summary, summary_file, indent=2)


def run_ingestion(
    mode: str | None = None,
    output_path: Path | None = None,
    summary_path: Path | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    development_row_limit: int | None = None,
) -> dict[str, Any]:
    config = build_config(
        mode=mode,
        output_path=output_path,
        summary_path=summary_path,
        date_start=date_start,
        date_end=date_end,
        development_row_limit=development_row_limit,
    )

    records = download_all_records(config=config)
    if not records:
        raise RuntimeError("No rows returned by API for the configured date range.")

    df = pd.DataFrame.from_records(records)
    validate_required_columns(df=df, required_columns=config.required_columns)

    # Preserve only requested columns from the source payload.
    df = df[list(config.required_columns)].copy()

    conversion_issues = convert_column_types(df)
    rows_downloaded = len(df)
    if config.ingestion_mode == "development":
        df = _sample_development_data(
            df=df,
            target_rows=config.development_row_limit,
        )
        print(
            f"Final rows sampled: {len(df):,} (from {rows_downloaded:,} rows downloaded)"
        )

    summary = summarize_dataset(df=df, config=config)
    summary["rows_downloaded"] = rows_downloaded
    summary["rows_sampled"] = int(len(df))
    summary["conversion_issues"] = conversion_issues

    if config.ingestion_mode == "development":
        authoritative_project_routes = _load_project_route_ids()
        summary["authoritative_project_route_count"] = len(authoritative_project_routes)
        route_set = {
            _normalize_route_id(value) for value in df["bus_route"].dropna().astype(str)
        }
        route_set = {route for route in route_set if route is not None}
        missing_project_routes = sorted(set(authoritative_project_routes) - route_set)
        route_coverage_percentage = (
            round(100.0 * len(route_set.intersection(authoritative_project_routes)) / len(authoritative_project_routes), 2)
            if authoritative_project_routes
            else 0.0
        )
        summary["final_unique_route_count"] = int(len(route_set))
        summary["unique_routes"] = int(len(route_set))
        summary["missing_project_routes"] = missing_project_routes
        summary["route_coverage_percentage"] = route_coverage_percentage
        summary["rows_by_route"] = {
            str(route): int(count)
            for route, count in df["bus_route"].astype(str).str.upper().value_counts().sort_index().items()
        }
        summary["unique_dates"] = int(df["transit_timestamp"].dt.date.nunique())
        summary["unique_hours"] = int(df["transit_timestamp"].dt.hour.nunique())
        summary["rows_by_hour"] = (
            df["transit_timestamp"].dt.hour.value_counts().sort_index().astype(int).to_dict()
        )
        if route_coverage_percentage < DEVELOPMENT_MIN_ROUTE_COVERAGE * 100:
            raise ValueError(
                "Development sample validation failed: route coverage is unexpectedly low "
                f"({route_coverage_percentage}%, missing routes={missing_project_routes[:20]})."
            )

    if config.ingestion_mode == "development" and summary["unique_hours"] <= 1:
        raise ValueError(
            "Development sample validation failed: source data contains only one hour."
        )

    save_outputs(df=df, summary=summary, config=config)

    print("Ingestion summary:")
    print(json.dumps(summary, indent=2))
    print(
        f"Unique dates: {summary['unique_dates']} | "
        f"Unique hours: {summary['unique_hours']} | "
        f"Rows by hour: {summary['rows_by_hour']}"
    )
    print(f"Parquet saved to: {config.output_path}")
    print(f"Summary saved to: {config.summary_path}")

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest MTA bus hourly ridership data into Parquet."
    )
    parser.add_argument(
        "--mode",
        choices=["development", "full"],
        default=DEFAULT_INGESTION_MODE,
        help=(
            "Ingestion mode. 'development' caps extraction to a deterministic sample "
            "(~200k rows by default). 'full' ingests all rows in the configured date range."
        ),
    )
    parser.add_argument(
        "--date-start",
        default=DATE_START,
        help="Inclusive start timestamp (ISO-like format expected by SODA2).",
    )
    parser.add_argument(
        "--date-end",
        default=DATE_END,
        help="Inclusive end timestamp (ISO-like format expected by SODA2).",
    )
    parser.add_argument(
        "--development-row-limit",
        type=int,
        default=DEFAULT_DEVELOPMENT_ROW_LIMIT,
        help="Maximum rows to ingest in development mode.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Path to output Parquet file.",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=None,
        help="Path to output ingestion summary JSON file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        run_ingestion(
            mode=args.mode,
            output_path=args.output_path,
            summary_path=args.summary_path,
            date_start=args.date_start,
            date_end=args.date_end,
            development_row_limit=args.development_row_limit,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
