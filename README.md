# Public Transit Dashboard - Phase 1 Data Ingestion

This repository currently implements only **Phase 1: Data Ingestion** for the academic capstone:

**Implementation of a Public Transit Ridership and Route Performance Visualization Dashboard**

## Scope in this phase

- Ingests MTA Bus Hourly Ridership data from the official NY Open Data SODA2 endpoint.
- Default configured date window:
  - Start: `2023-01-01T00:00:00`
  - End: `2023-02-28T23:00:00`
- Retrieves only required fields:
  - `transit_timestamp`
  - `bus_route`
  - `payment_method`
  - `fare_class_category`
  - `ridership`
  - `transfers`
- Supports two ingestion modes:
  - DEVELOPMENT DATA mode (default): deterministic date-stratified extraction capped to ~200,000 rows across the configured date range.
  - Full mode: ingests all rows in the configured date range.
- Downloads in paginated batches.
- Validates schema and performs data quality checks.
- Saves output to Parquet.

No frontend, backend, database, dashboard, ML, or later modules are included in this phase.

## Project structure

```text
public-transit-dashboard/
├── data/
│   ├── raw/
│   └── processed/
├── src/
│   └── ingestion/
│       └── mta_ridership_ingestion.py
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

## Setup

From the `public-transit-dashboard` folder:

```powershell
pip install -r requirements.txt
```

## Run ingestion

Default run (DEVELOPMENT DATA mode):

```powershell
python src/ingestion/mta_ridership_ingestion.py
```

Full extraction mode for a configured date range:

```powershell
python src/ingestion/mta_ridership_ingestion.py --mode full
```

Optional custom output/summary path and date range:

```powershell
python src/ingestion/mta_ridership_ingestion.py --mode full --date-start 2023-01-01T00:00:00 --date-end 2023-02-28T23:00:00 --output-path data/raw/mta_ridership_2023_jan_feb.parquet --summary-path data/raw/mta_ridership_2023_jan_feb_ingestion_summary.json
```

## Configuration

Runtime configuration can be set using environment variables (see `.env.example`):

- `MTA_INGESTION_MODE` (default: `development`)
- `MTA_DEVELOPMENT_ROW_LIMIT` (default: `200000`)
- `MTA_BATCH_SIZE` (default: `50000`)
- `MTA_REQUEST_TIMEOUT_SECONDS` (default: `30`)
- `MTA_MAX_RETRIES` (default: `5`)
- `MTA_BACKOFF_FACTOR` (default: `1.0`)

## Outputs

After a successful run, the script writes:

- Default DEVELOPMENT DATA outputs:
  - `data/raw/mta_ridership_dev.parquet`
  - `data/raw/mta_ridership_dev_ingestion_summary.json`
- Full mode defaults:
  - `data/raw/mta_ridership_2023_jan_feb.parquet`
  - `data/raw/mta_ridership_2023_jan_feb_ingestion_summary.json`

The summary includes:

- total rows
- unique source/business records
- actual minimum and maximum timestamp
- unique route count
- unique date count
- missing values by required column
- duplicate count based on source/business key (`transit_timestamp`, `bus_route`, `payment_method`, `fare_class_category`)
- conversion issues from type coercion
