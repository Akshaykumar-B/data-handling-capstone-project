# Dashboard API

This FastAPI service is the only planned reader of the processed data for the
Phase 5 dashboard. The scaffold currently exposes health and processed-file
availability checks only.

## FastAPI backend

The backend exposes the read-only Phase 3 and Phase 4 data API. It reads the
runtime data directory through `TRANSIT_PROCESSED_DIR`; it never requires or
opens `routes_clean.geojson`.

## Requirements

- Python 3.11 or newer
- The existing backend dependencies from `requirements.txt`
- A mounted or copied read-only directory containing the required processed files

Install dependencies on the deployment host:

```bash
python -m pip install -r backend/requirements.txt
```

## Start command

Use this production ASGI command from the project root:

```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

On hosts that provide a `PORT` variable, Uvicorn binds to that port. The
application validates the runtime files during startup and fails clearly if any
required file is missing. Startup validation does not write or generate data.

## Environment variables

- `TRANSIT_PROCESSED_DIR`: absolute path to the deployed processed-data directory.
	If unset, local development uses `data/processed` in this project.
- `FRONTEND_ORIGIN`: the deployed Vercel frontend origin, for example
	`https://your-project.vercel.app`. Multiple comma-separated origins are
	accepted. If unset, local development allows `http://localhost:3000`.

## Required runtime files

The following 10 files must exist under `TRANSIT_PROCESSED_DIR`:

```text
processing_report.json
eda_report.json
ridership_clean.parquet
bus_stops_clean.parquet
customer_journey_clean.parquet
ridership_by_route.parquet
ridership_by_date.parquet
ridership_by_hour.parquet
cjtp_by_route.parquet
route_stop_relationships.parquet
```

The runtime bundle is approximately 4.30 MiB. Keep it outside Git and deploy it
as a versioned read-only artifact or mounted volume. Do not include the 2.3 GB
route GeoJSON.

## Verification endpoints

- `GET /api/v1/health` confirms the API process is responding.
- `GET /api/v1/data/status` reports the presence of all required runtime files.

The Vercel frontend must set `NEXT_PUBLIC_API_BASE_URL` to the public FastAPI
origin, and the backend must set `FRONTEND_ORIGIN` to that Vercel origin so the
browser requests pass CORS validation.

```powershell
python -m uvicorn backend.app.main:app --reload
```

The status endpoint checks the small JSON and Parquet inputs listed in
`backend/app/services/data_access.py`. It never opens `routes_clean.geojson`.