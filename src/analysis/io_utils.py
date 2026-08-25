"""File I/O for the EDA.

This is the only analysis module that reads Parquet (needs pyarrow) or reads
the processing report, keeping the analysis modules pure and independently
testable. It performs no writes; figures are written by :mod:`figures` and the
report is written by :mod:`run_eda`. The 2.3 GB ``routes_clean.geojson`` is
never read here - route metadata comes from ``processing_report.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import eda_config as C


def load_processing_report() -> dict:
    """Read the Phase 3 ``processing_report.json`` (source of routes metadata)."""
    path = Path(C.PROCESSING_REPORT)
    if not path.exists():
        raise FileNotFoundError(f"processing report is required but missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def missing_inputs() -> list[str]:
    """Names of any required parquet inputs that are absent."""
    return [name for name, path in C.PARQUET_INPUTS.items() if not Path(path).exists()]


def load_datasets() -> dict[str, pd.DataFrame]:
    """Read every processed Parquet input into a DataFrame.

    ``routes_clean.geojson`` is intentionally excluded (2.3 GB; its metadata is
    read from the processing report instead).
    """
    frames: dict[str, pd.DataFrame] = {}
    for name, path in C.PARQUET_INPUTS.items():
        resolved = Path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"required processed input missing: {resolved}")
        frames[name] = pd.read_parquet(resolved)
    return frames
