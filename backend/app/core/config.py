"""Environment-driven paths and local API settings."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = Path(os.getenv("TRANSIT_PROCESSED_DIR", PROJECT_ROOT / "data" / "processed"))


class Settings:
    """Environment-driven settings for local and hosted deployments."""

    cors_origins = [
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGIN", os.getenv("TRANSIT_CORS_ORIGINS", "http://localhost:3000")
        ).split(",")
        if origin.strip()
    ]


settings = Settings()