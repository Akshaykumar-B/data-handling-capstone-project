"""Static configuration for Phase 3 cleaning and preprocessing.

Every path is derived from the repository root so the pipeline is portable and
rerunnable regardless of the working directory it is launched from.
"""

from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"

# ---------------------------------------------------------------------------
# Raw inputs (read-only; Phase 3 must never write into data/raw/)
# ---------------------------------------------------------------------------
RIDERSHIP_RAW = RAW_DIR / "mta_ridership_dev.parquet"
ROUTES_RAW = RAW_DIR / "mta_bus_routes_valid.geojson"
STOPS_RAW = RAW_DIR / "mta_bus_stops_project.parquet"
CJTP_RAW = RAW_DIR / "MTA_Bus_Customer_Journey-Focused_Metrics__Beginning_2017_20260824.csv"

# Existing validated reference reports (read-only inputs).
PROFILING_REPORT = PROCESSED_DIR / "dataset_profiling_report.json"
ROUTES_VALID_REPORT = RAW_DIR / "mta_bus_routes_valid_report.json"
RIDERSHIP_INGESTION_SUMMARY = RAW_DIR / "mta_ridership_dev_ingestion_summary.json"
STOPS_INGESTION_SUMMARY = RAW_DIR / "mta_bus_stops_project_ingestion_summary.json"

RAW_INPUTS = (RIDERSHIP_RAW, ROUTES_RAW, STOPS_RAW, CJTP_RAW)

# ---------------------------------------------------------------------------
# Cleaned outputs
# ---------------------------------------------------------------------------
RIDERSHIP_CLEAN = PROCESSED_DIR / "ridership_clean.parquet"
ROUTES_CLEAN = PROCESSED_DIR / "routes_clean.geojson"
STOPS_CLEAN = PROCESSED_DIR / "bus_stops_clean.parquet"
CJTP_CLEAN = PROCESSED_DIR / "customer_journey_clean.parquet"

# Analysis-ready tables
RIDERSHIP_BY_ROUTE = PROCESSED_DIR / "ridership_by_route.parquet"
RIDERSHIP_BY_DATE = PROCESSED_DIR / "ridership_by_date.parquet"
RIDERSHIP_BY_HOUR = PROCESSED_DIR / "ridership_by_hour.parquet"
CJTP_BY_ROUTE = PROCESSED_DIR / "cjtp_by_route.parquet"
ROUTE_STOP_RELATIONSHIPS = PROCESSED_DIR / "route_stop_relationships.parquet"

PROCESSING_REPORT = PROCESSED_DIR / "processing_report.json"

OUTPUT_PATHS = (
    RIDERSHIP_CLEAN,
    ROUTES_CLEAN,
    STOPS_CLEAN,
    CJTP_CLEAN,
    RIDERSHIP_BY_ROUTE,
    RIDERSHIP_BY_DATE,
    RIDERSHIP_BY_HOUR,
    CJTP_BY_ROUTE,
    ROUTE_STOP_RELATIONSHIPS,
)

# ---------------------------------------------------------------------------
# Column contracts
# ---------------------------------------------------------------------------
RIDERSHIP_COLUMNS = (
    "transit_timestamp",
    "bus_route",
    "payment_method",
    "fare_class_category",
    "ridership",
    "transfers",
)

STOP_ASSOCIATION_COLUMNS = ("route_id", "route_short_name", "stop_id", "direction_id", "bundle")

CJTP_COLUMNS = (
    "month",
    "borough",
    "trip_type",
    "route_id",
    "period",
    "number_of_customers",
    "additional_bus_stop_time",
    "additional_travel_time",
    "customer_journey_time_performance",
)

CJTP_NUMERIC_COLUMNS = (
    "number_of_customers",
    "additional_bus_stop_time",
    "additional_travel_time",
)

# Route attribute columns carried through the routes GeoJSON, in source order.
ROUTE_PROPERTY_COLUMNS = (
    "valid_from",
    "valid_to",
    "in_effect",
    "route_id",
    "route_short_name",
    "route_long_name",
    "route_description",
    "trip_type",
    "route_type",
    "bundle",
    "route_color",
    "direction_id",
    "direction",
    "shape_id",
    "vertices",
    "shape_length",
    "min_longitude",
    "min_latitude",
    "max_longitude",
    "max_latitude",
    "_socrata_id",
)

# ---------------------------------------------------------------------------
# Expectations taken from the already-validated reference reports.
# These are cross-checked and reported, never used to alter or invent data.
# ---------------------------------------------------------------------------
EXPECTED_RIDERSHIP_ROWS = 200_000
EXPECTED_ROUTE_FEATURES = 206_338
EXPECTED_STOP_ROWS = 8_664
EXPECTED_PROJECT_ROUTE_COUNT = 142

# GeoJSON handling
GEOJSON_CRS_NAME = "urn:ogc:def:crs:OGC:1.3:CRS84"
ACCEPTED_CRS_EPSG = 4326
DEFAULT_GEOJSON_BATCH_SIZE = 5_000
MULTILINESTRING_TYPE_ID = 5

# Files larger than this are fingerprinted by size+mtime only (hashing 2.3 GB
# on every run would dominate runtime for no analytical benefit).
HASH_SIZE_LIMIT_BYTES = 128 * 1024 * 1024
