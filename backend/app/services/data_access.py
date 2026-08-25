"""Cached, read-only access to the Phase 3 and Phase 4 outputs."""

from __future__ import annotations

from pathlib import Path
import json
from functools import lru_cache
from typing import Any

import pandas as pd
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
    """Central repository for reports and dashboard-sized Parquet tables."""

    def __init__(self, processed_dir: Path) -> None:
        self.processed_dir = processed_dir

    @lru_cache(maxsize=None)
    def report(self, name: str) -> dict[str, Any]:
        with (self.processed_dir / name).open(encoding="utf-8") as handle:
            return json.load(handle)

    @lru_cache(maxsize=None)
    def table(self, name: str) -> pd.DataFrame:
        return pd.read_parquet(self.processed_dir / f"{name}.parquet")

    @property
    def eda(self) -> dict[str, Any]:
        return self.report("eda_report.json")

    @property
    def processing(self) -> dict[str, Any]:
        return self.report("processing_report.json")

    def coverage(self, dataset: str) -> dict[str, Any]:
        return self.eda["analyses"][dataset]["route_coverage"]

    def missing_runtime_files(self) -> list[str]:
        """Return missing inputs without reading or creating any dataset."""
        return [name for name in REQUIRED_FILES if not (self.processed_dir / name).is_file()]

    def status(self) -> dict[str, Any]:
        files = {name: (self.processed_dir / name).is_file() for name in REQUIRED_FILES}
        return {"status": "ready" if all(files.values()) else "incomplete", "required_files": files}


data_store = DataStore(PROCESSED_DIR)