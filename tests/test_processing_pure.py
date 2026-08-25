"""Unit tests for the pure, dependency-light Phase 3 logic.

These run under the Linux sandbox's Python (pandas + numpy present; geopandas /
pyogrio / shapely absent), so they deliberately avoid importing the geometry
cleaner. They exercise route normalisation, alias canonicalisation, the route
reference loader against the *real* profiling report, CJTP percent/comma
parsing, JSON coercion, and the aggregation weighted mean.

Run:  python3 -m pytest tests/test_processing_pure.py    (or run this file directly)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROFILING_REPORT = ROOT / "data" / "processed" / "dataset_profiling_report.json"
ROUTES_REPORT = ROOT / "data" / "raw" / "mta_bus_routes_valid_report.json"


def _load_module(name: str):
    """Import a single processing module without importing the whole package.

    Importing ``src.processing`` as a package would pull in the geometry cleaner
    (which needs shapely). We load the leaf modules we need directly, wiring a
    minimal package entry so their ``from . import`` statements resolve.
    """
    import types

    pkg_name = "src.processing"
    if "src" not in sys.modules:
        src_pkg = types.ModuleType("src")
        src_pkg.__path__ = [str(SRC)]
        sys.modules["src"] = src_pkg
    if pkg_name not in sys.modules:
        proc_pkg = types.ModuleType(pkg_name)
        proc_pkg.__path__ = [str(SRC / "processing")]
        sys.modules[pkg_name] = proc_pkg
    full = f"{pkg_name}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, SRC / "processing" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


utils = _load_module("utils")
reference_mod = _load_module("reference")


# ---------------------------------------------------------------------------
# normalize_route
# ---------------------------------------------------------------------------

def test_normalize_route_trims_and_uppercases():
    assert utils.normalize_route("  b44  ") == "B44"
    assert utils.normalize_route("bx12+") == "BX12+"


def test_normalize_route_handles_missing():
    assert utils.normalize_route(None) is None
    assert utils.normalize_route(float("nan")) is None
    assert utils.normalize_route("") is None
    assert utils.normalize_route("   ") is None
    assert utils.normalize_route("nan") is None
    assert utils.normalize_route("<NA>") is None


def test_normalized_route_set_drops_blanks():
    result = utils.normalized_route_set(["b1", " B1 ", None, "", "b2"])
    assert result == {"B1", "B2"}


# ---------------------------------------------------------------------------
# json_safe
# ---------------------------------------------------------------------------

def test_json_safe_coerces_numpy_and_nan():
    import numpy as np

    payload = {
        "int": np.int64(5),
        "float": np.float64(1.5),
        "nan": float("nan"),
        "nested": {"vals": [np.int32(1), np.int32(2)]},
        "set": {3, 1, 2},
    }
    safe = utils.json_safe(payload)
    assert safe["int"] == 5 and isinstance(safe["int"], int)
    assert safe["float"] == 1.5
    assert safe["nan"] is None
    assert safe["nested"]["vals"] == [1, 2]
    assert safe["set"] == [1, 2, 3]  # sets are sorted for determinism


def test_json_safe_timestamp_isoformat():
    stamp = pd.Timestamp("2023-01-15 06:00:00")
    assert utils.json_safe(stamp) == stamp.isoformat()


# ---------------------------------------------------------------------------
# route reference against the REAL profiling report
# ---------------------------------------------------------------------------

def test_route_reference_loads_real_report():
    ref, profile = reference_mod.load_route_reference(PROFILING_REPORT, ROUTES_REPORT)
    # 142 ridership routes documented in the report.
    assert len(ref.raw_project_routes) == 142
    # 21 known aliases, none inventing a new mapping.
    assert len(ref.alias_pairs) == 21
    assert ref.alias_map["B44+"] == "B44-SBS"
    assert ref.alias_map["Q70+"] == "Q70-SBS"


def test_reference_canonicalizes_aliases():
    ref, _ = reference_mod.load_route_reference(PROFILING_REPORT, ROUTES_REPORT)
    assert ref.canonical("b44+") == "B44-SBS"
    assert ref.canonical("  B46+ ") == "B46-SBS"
    # A plain route with no alias is returned unchanged.
    assert ref.canonical("B1") == "B1"
    assert ref.canonical(None) is None


def test_reference_project_routes_are_canonical():
    ref, _ = reference_mod.load_route_reference(PROFILING_REPORT, ROUTES_REPORT)
    # After canonicalization the SBS spelling is what downstream datasets carry,
    # so B44-SBS must be *in* the project set while B44+ must not.
    assert "B44-SBS" in ref.project_routes
    assert "B44+" not in ref.project_routes
    # Raw set keeps the original ridership spelling.
    assert "B44+" in ref.raw_project_routes
    # Canonicalization must not silently shrink the project scope.
    assert len(ref.project_routes) == len(ref.raw_project_routes)


def test_coverage_against_project_reports_both_directions():
    ref, _ = reference_mod.load_route_reference(PROFILING_REPORT, ROUTES_REPORT)
    # Observe every project route except two, plus one stranger.
    observed = set(ref.project_routes)
    dropped = sorted(observed)[:2]
    observed.discard(dropped[0])
    observed.discard(dropped[1])
    observed.add("ZZ99")
    cov = reference_mod.coverage_against_project(observed, ref, canonicalize=False)
    assert cov["project_route_count"] == len(ref.project_routes)
    assert cov["matching_route_count"] == len(ref.project_routes) - 2
    assert set(cov["project_routes_missing_from_dataset"]) == set(dropped)
    assert cov["dataset_routes_not_in_project_reference"] == ["ZZ99"]


def test_coverage_canonicalizes_alias_spelling():
    ref, _ = reference_mod.load_route_reference(PROFILING_REPORT, ROUTES_REPORT)
    # Feeding the ridership spelling ("B44+") with canonicalize=True must count
    # against the canonical project route ("B44-SBS").
    cov = reference_mod.coverage_against_project({"B44+"}, ref, canonicalize=True)
    assert cov["matching_route_count"] == 1
    assert "B44-SBS" not in cov["project_routes_missing_from_dataset"]


# ---------------------------------------------------------------------------
# CJTP parsing helpers (percent / comma stripping)
# ---------------------------------------------------------------------------

def test_cjtp_number_parsing_strips_thousands():
    cjtp = _load_module("clean_cjtp")
    series = pd.Series(["219,531.64", "1,000", "42", "", None])
    parsed = cjtp._parse_number(series)
    assert parsed.iloc[0] == 219531.64
    assert parsed.iloc[1] == 1000.0
    assert parsed.iloc[2] == 42.0
    assert pd.isna(parsed.iloc[3])
    assert pd.isna(parsed.iloc[4])


def test_cjtp_percentage_parsing_strips_percent():
    cjtp = _load_module("clean_cjtp")
    series = pd.Series(["70.1999545%", "100%", "0%", "", None])
    parsed = cjtp._parse_percentage(series)
    # Full precision must survive — no rounding is applied during parsing.
    assert parsed.iloc[0] == 70.1999545
    assert parsed.iloc[1] == 100.0
    assert parsed.iloc[2] == 0.0
    assert pd.isna(parsed.iloc[3])
    assert pd.isna(parsed.iloc[4])


# ---------------------------------------------------------------------------
# aggregation weighted mean
# ---------------------------------------------------------------------------

def test_weighted_mean_ignores_missing_and_zero_weight():
    aggregate = _load_module("aggregate")
    values = pd.Series([80.0, 90.0, None, 50.0])
    weights = pd.Series([100.0, 300.0, 500.0, 0.0])
    # (80*100 + 90*300) / (100 + 300) = 35000 / 400 = 87.5
    assert aggregate._weighted_mean(values, weights) == 87.5


def test_weighted_mean_all_missing_returns_none():
    aggregate = _load_module("aggregate")
    values = pd.Series([None, None], dtype="float64")
    weights = pd.Series([10.0, 20.0])
    assert aggregate._weighted_mean(values, weights) is None


# ---------------------------------------------------------------------------
# WarningCollector
# ---------------------------------------------------------------------------

def test_warning_collector_accumulates():
    collector = utils.WarningCollector()
    collector.add("scope", "message one")
    collector.add("scope", "message two")
    items = collector.to_list()
    assert len(items) == 2
    assert items[0] == {"scope": "scope", "message": "message one"}


def _run_all() -> int:
    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    failures = 0
    for name, test in tests:
        try:
            test()
            print(f"  PASS {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
