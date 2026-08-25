"""Read-only access to the small processed dashboard inputs.

The first scaffold exposes file availability only. Future analytics services can
add cached JSON/Parquet loaders here without making the frontend access files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.config import PROCESSED_DIR


REQUIRED_FILES = (
    "processing_report.json",
    "eda_report.json",
    "ridership_clean.parquet",
    "bus_stops_clean.parquet",
    "customer_journey_clean.parquet",
    "ridership_by_route.parquet",
    "ridership_by_date.parquet",
    "ridership_by_hour.parquet",
    "cjtp_by_route.parquet",
    "route_stop_relationships.parquet",
)


class DataStore:
    """Central read-only boundary for processed data."""

    def __init__(self, processed_dir: Path) -> None:
        self.processed_dir = processed_dir

    def status(self) -> dict[str, Any]:
        files = {
            name: {
                "path": f"data/processed/{name}",
                "exists": (self.processed_dir / name).is_file(),
            }
            for name in REQUIRED_FILES
        }
        return {
            "status": "ready" if all(item["exists"] for item in files.values()) else "incomplete",
            "processed_directory": str(self.processed_dir),
            "required_files": files,
        }


data_store = DataStore(PROCESSED_DIR)