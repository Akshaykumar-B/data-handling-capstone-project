"""Static configuration for the Phase 4 exploratory data analysis (EDA).

Input locations are imported from the Phase 3 processing config so there is a
single source of truth; Phase 4 adds only two output targets:

  * ``data/processed/eda/``            - analysis figures (PNG)
  * ``data/processed/eda_report.json`` - machine-readable EDA report

Nothing here reads or writes data; it only declares locations and constants so
the pipeline is portable and rerunnable from any working directory.
"""

from __future__ import annotations

from ..processing import config as _pc

# --- read-only processed inputs (authoritative Phase 3 locations) ----------
ROOT_DIR = _pc.ROOT_DIR
PROCESSED_DIR = _pc.PROCESSED_DIR
RAW_DIR = _pc.RAW_DIR

RIDERSHIP_CLEAN = _pc.RIDERSHIP_CLEAN
STOPS_CLEAN = _pc.STOPS_CLEAN
CJTP_CLEAN = _pc.CJTP_CLEAN
ROUTES_CLEAN = _pc.ROUTES_CLEAN  # metadata only - never parsed (2.3 GB)

RIDERSHIP_BY_ROUTE = _pc.RIDERSHIP_BY_ROUTE
RIDERSHIP_BY_DATE = _pc.RIDERSHIP_BY_DATE
RIDERSHIP_BY_HOUR = _pc.RIDERSHIP_BY_HOUR
CJTP_BY_ROUTE = _pc.CJTP_BY_ROUTE
ROUTE_STOP_RELATIONSHIPS = _pc.ROUTE_STOP_RELATIONSHIPS

PROCESSING_REPORT = _pc.PROCESSING_REPORT
PROFILING_REPORT = _pc.PROFILING_REPORT
ROUTES_VALID_REPORT = _pc.ROUTES_VALID_REPORT

EXPECTED_PROJECT_ROUTE_COUNT = _pc.EXPECTED_PROJECT_ROUTE_COUNT
EXPECTED_ROUTE_FEATURES = _pc.EXPECTED_ROUTE_FEATURES

# Parquet inputs the EDA actually reads (routes geometry is excluded on purpose).
PARQUET_INPUTS = {
    "ridership_clean": RIDERSHIP_CLEAN,
    "bus_stops_clean": STOPS_CLEAN,
    "customer_journey_clean": CJTP_CLEAN,
    "ridership_by_route": RIDERSHIP_BY_ROUTE,
    "ridership_by_date": RIDERSHIP_BY_DATE,
    "ridership_by_hour": RIDERSHIP_BY_HOUR,
    "cjtp_by_route": CJTP_BY_ROUTE,
    "route_stop_relationships": ROUTE_STOP_RELATIONSHIPS,
}

# Every input whose immutability we prove (parquet inputs + reports + geometry).
IMMUTABLE_INPUTS = tuple(PARQUET_INPUTS.values()) + (
    ROUTES_CLEAN,
    PROCESSING_REPORT,
    PROFILING_REPORT,
    ROUTES_VALID_REPORT,
)

# --- Phase 4 outputs --------------------------------------------------------
EDA_DIR = PROCESSED_DIR / "eda"
EDA_REPORT = PROCESSED_DIR / "eda_report.json"

# --- analysis constants -----------------------------------------------------
IQR_MULTIPLIER = 1.5
TOP_N = 10
MAX_OUTLIER_EXAMPLES = 25
ROUND = 6

# CJTP performance metric: percentage in [0, 100]; higher = more on-time.
CJTP_METRIC = "customer_journey_time_performance"

# --- figure settings --------------------------------------------------------
FIG_DPI = 120
FIG_FORMAT = "png"
FIG_BAR_ROUTES = 15  # how many routes to show in "top routes" bar charts

FIGURES = (
    "ridership_by_route.png",
    "ridership_daily.png",
    "ridership_distribution.png",
    "cjtp_distribution.png",
    "cjtp_by_period.png",
    "cjtp_by_trip_type.png",
    "cjtp_top_bottom_routes.png",
    "stops_by_route.png",
    "ridership_vs_stops.png",
    "ridership_vs_cjtp.png",
)

# --- known data limitations (surfaced verbatim in the report) ---------------
TEMPORAL_LIMITATION = (
    "The processed ridership extract (mta_ridership_dev.parquet) is a development "
    "subsample: 200,000 records spanning only 2023-01-01 to 2023-02-28 (59 distinct "
    "service dates) with timestamps bucketed to 12 even hours (0,2,...,22). It does "
    "NOT support meaningful 24-hour / diurnal ridership pattern claims; hourly totals "
    "are reported descriptively only, and no continuous hourly-profile figure is drawn."
)
