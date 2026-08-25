"""Application entry point for the Phase 5 dashboard API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .services.data_access import data_store

app = FastAPI(title="Public Transit Dashboard API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """Report that the API process is responding."""
    return {"status": "ok", "service": "public-transit-dashboard-api"}


@app.get("/api/v1/data/status")
def data_status() -> dict[str, object]:
    """Report availability of the small, supported processed-data inputs."""
    return data_store.status()