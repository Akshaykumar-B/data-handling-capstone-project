# Dashboard API

This FastAPI service is the only planned reader of the processed data for the
Phase 5 dashboard. The scaffold currently exposes health and processed-file
availability checks only.

Run from the project root after installing the project-approved dependencies:

```powershell
python -m uvicorn backend.app.main:app --reload
```

The status endpoint checks the small JSON and Parquet inputs listed in
`backend/app/services/data_access.py`. It never opens `routes_clean.geojson`.