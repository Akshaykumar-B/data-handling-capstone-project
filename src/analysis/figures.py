"""Matplotlib figures for the EDA.

Writes the ten recommended PNGs into ``data/processed/eda/`` using the Agg
backend (headless, deterministic). Each figure is wrapped so one failure cannot
abort the run; the runner's validation reports any figure that failed to render.

No 24-hour ridership-profile figure is produced: the ridership extract lacks the
temporal resolution to justify one (see eda_config.TEMPORAL_LIMITATION).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg")  # headless, deterministic; must precede pyplot import

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from . import eda_config as C  # noqa: E402
from . import stats_utils as S  # noqa: E402

_FIGSIZE = (10, 6)
_SOURCE = "Source: Phase 3 processed datasets"


def _finish(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=C.FIG_DPI, format=C.FIG_FORMAT)
    plt.close(fig)


def _project_ridership_routes(datasets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frame = datasets["ridership_by_route"].copy()
    frame["total_ridership"] = pd.to_numeric(frame["total_ridership"], errors="coerce")
    return frame.dropna(subset=["total_ridership"])


# --- individual figures -----------------------------------------------------
def _fig_ridership_by_route(datasets, merged, path):
    frame = _project_ridership_routes(datasets)
    top = frame.sort_values(
        ["total_ridership", "route_id"], ascending=[False, True], kind="mergesort"
    ).head(C.FIG_BAR_ROUTES)
    fig, ax = plt.subplots(figsize=_FIGSIZE)
    ax.barh(top["route_id"].astype(str), top["total_ridership"], color="#2a6f97")
    ax.invert_yaxis()
    ax.set_xlabel("Total ridership (records summed)")
    ax.set_ylabel("Route")
    ax.set_title(f"Top {C.FIG_BAR_ROUTES} routes by total ridership")
    ax.figure.text(0.99, 0.01, _SOURCE, ha="right", fontsize=7, color="#666")
    _finish(fig, path)


def _fig_ridership_daily(datasets, merged, path):
    frame = datasets["ridership_by_date"].copy()
    frame["service_date"] = pd.to_datetime(frame["service_date"], errors="coerce")
    frame = frame.sort_values("service_date", kind="mergesort")
    fig, ax = plt.subplots(figsize=_FIGSIZE)
    ax.plot(frame["service_date"], frame["total_ridership"], marker="o", ms=3, color="#2a6f97")
    ax.set_xlabel("Service date")
    ax.set_ylabel("Total daily ridership")
    ax.set_title("Daily ridership (2023-01-01 to 2023-02-28 dev subsample)")
    fig.autofmt_xdate()
    ax.figure.text(0.99, 0.01, _SOURCE, ha="right", fontsize=7, color="#666")
    _finish(fig, path)


def _fig_ridership_distribution(datasets, merged, path):
    values = pd.to_numeric(datasets["ridership_clean"]["ridership"], errors="coerce").dropna()
    fig, ax = plt.subplots(figsize=_FIGSIZE)
    ax.hist(values, bins=50, color="#2a6f97", edgecolor="white", linewidth=0.3)
    ax.set_yscale("log")
    ax.set_xlabel("Ridership per record")
    ax.set_ylabel("Frequency (log scale)")
    ax.set_title("Distribution of ridership per record (right-skewed)")
    ax.figure.text(0.99, 0.01, _SOURCE, ha="right", fontsize=7, color="#666")
    _finish(fig, path)


def _fig_cjtp_distribution(datasets, merged, path):
    values = pd.to_numeric(
        datasets["customer_journey_clean"][C.CJTP_METRIC], errors="coerce"
    ).dropna()
    fig, ax = plt.subplots(figsize=_FIGSIZE)
    ax.hist(values, bins=40, color="#468faf", edgecolor="white", linewidth=0.3)
    ax.set_xlabel("Customer Journey Time Performance (%)")
    ax.set_ylabel("Frequency")
    ax.set_title("Distribution of CJTP (higher = more on-time)")
    ax.figure.text(0.99, 0.01, _SOURCE, ha="right", fontsize=7, color="#666")
    _finish(fig, path)


def _weighted_by_category(clean: pd.DataFrame, column: str) -> pd.DataFrame:
    rows = []
    for key, group in clean.groupby(column, dropna=False, observed=True):
        rows.append(
            {
                "category": "UNKNOWN" if pd.isna(key) else str(key),
                "weighted_cjtp": S.weighted_mean(group[C.CJTP_METRIC], group["number_of_customers"]),
            }
        )
    frame = pd.DataFrame(rows).dropna(subset=["weighted_cjtp"])
    return frame.sort_values("category", kind="mergesort")


def _fig_cjtp_by_period(datasets, merged, path):
    frame = _weighted_by_category(datasets["customer_journey_clean"], "period")
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.bar(frame["category"], frame["weighted_cjtp"], color="#468faf", width=0.6)
    ax.set_ylabel("Customer-weighted CJTP (%)")
    ax.set_title("CJTP by period (customer-weighted)")
    for x, y in zip(frame["category"], frame["weighted_cjtp"]):
        ax.text(x, y, f"{y:.1f}", ha="center", va="bottom", fontsize=9)
    ax.figure.text(0.99, 0.01, _SOURCE, ha="right", fontsize=7, color="#666")
    _finish(fig, path)


def _fig_cjtp_by_trip_type(datasets, merged, path):
    frame = _weighted_by_category(datasets["customer_journey_clean"], "trip_type")
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.bar(frame["category"], frame["weighted_cjtp"], color="#468faf", width=0.6)
    ax.set_xlabel("Trip type")
    ax.set_ylabel("Customer-weighted CJTP (%)")
    ax.set_title("CJTP by trip type (customer-weighted)")
    for x, y in zip(frame["category"], frame["weighted_cjtp"]):
        ax.text(x, y, f"{y:.1f}", ha="center", va="bottom", fontsize=9)
    ax.figure.text(0.99, 0.01, _SOURCE, ha="right", fontsize=7, color="#666")
    _finish(fig, path)


def _fig_cjtp_top_bottom_routes(datasets, merged, path):
    cjtp = datasets["cjtp_by_route"].copy()
    cjtp["customer_weighted_cjtp"] = pd.to_numeric(
        cjtp["customer_weighted_cjtp"], errors="coerce"
    )
    cjtp = cjtp.dropna(subset=["customer_weighted_cjtp"])
    ordered = cjtp.sort_values(
        ["customer_weighted_cjtp", "route_id"], ascending=[False, True], kind="mergesort"
    )
    top = ordered.head(C.TOP_N)
    bottom = ordered.tail(C.TOP_N)
    combined = pd.concat([bottom.iloc[::-1], top.iloc[::-1]])
    colors = ["#b5384d"] * len(bottom) + ["#2a9d8f"] * len(top)
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.barh(combined["route_id"].astype(str), combined["customer_weighted_cjtp"], color=colors)
    ax.set_xlabel("Customer-weighted CJTP (%)")
    ax.set_ylabel("Route")
    ax.set_title(f"Best (green) and worst (red) {C.TOP_N} routes by CJTP")
    ax.figure.text(0.99, 0.01, _SOURCE, ha="right", fontsize=7, color="#666")
    _finish(fig, path)


def _fig_stops_by_route(datasets, merged, path):
    rel = datasets["route_stop_relationships"]
    per_route = (
        rel.groupby("route_id_canonical", observed=True)["stop_id"].nunique().rename("unique_stops").reset_index()
    )
    top = per_route.sort_values(
        ["unique_stops", "route_id_canonical"], ascending=[False, True], kind="mergesort"
    ).head(C.FIG_BAR_ROUTES)
    fig, ax = plt.subplots(figsize=_FIGSIZE)
    ax.barh(top["route_id_canonical"].astype(str), top["unique_stops"], color="#5f7470")
    ax.invert_yaxis()
    ax.set_xlabel("Unique physical stops")
    ax.set_ylabel("Route")
    ax.set_title(f"Top {C.FIG_BAR_ROUTES} routes by unique stop count")
    ax.figure.text(0.99, 0.01, _SOURCE, ha="right", fontsize=7, color="#666")
    _finish(fig, path)


def _scatter(merged, x_col, y_col, x_label, y_label, title, path):
    frame = merged[merged["is_project_route"]][[x_col, y_col]].copy()
    frame[x_col] = pd.to_numeric(frame[x_col], errors="coerce")
    frame[y_col] = pd.to_numeric(frame[y_col], errors="coerce")
    frame = frame.dropna()
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(frame[x_col], frame[y_col], s=22, alpha=0.6, color="#2a6f97", edgecolor="white", linewidth=0.3)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title)
    if len(frame) >= 3 and frame[x_col].nunique() > 1 and frame[y_col].nunique() > 1:
        r = frame[x_col].corr(frame[y_col])
        ax.text(
            0.03, 0.97, f"Pearson r = {r:.3f}  (n = {len(frame)})\nassociation, not causation",
            transform=ax.transAxes, va="top", fontsize=9,
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8, edgecolor="#ccc"),
        )
    ax.figure.text(0.99, 0.01, _SOURCE, ha="right", fontsize=7, color="#666")
    _finish(fig, path)


def _fig_ridership_vs_stops(datasets, merged, path):
    _scatter(
        merged, "unique_stops", "total_ridership",
        "Unique physical stops per route", "Total ridership per route",
        "Ridership vs number of stops (project routes)", path,
    )


def _fig_ridership_vs_cjtp(datasets, merged, path):
    _scatter(
        merged, "customer_weighted_cjtp", "total_ridership",
        "Customer-weighted CJTP (%)", "Total ridership per route",
        "Ridership vs CJTP (project routes)", path,
    )


_FIGURES: dict[str, Callable] = {
    "ridership_by_route.png": _fig_ridership_by_route,
    "ridership_daily.png": _fig_ridership_daily,
    "ridership_distribution.png": _fig_ridership_distribution,
    "cjtp_distribution.png": _fig_cjtp_distribution,
    "cjtp_by_period.png": _fig_cjtp_by_period,
    "cjtp_by_trip_type.png": _fig_cjtp_by_trip_type,
    "cjtp_top_bottom_routes.png": _fig_cjtp_top_bottom_routes,
    "stops_by_route.png": _fig_stops_by_route,
    "ridership_vs_stops.png": _fig_ridership_vs_stops,
    "ridership_vs_cjtp.png": _fig_ridership_vs_cjtp,
}


def render_all(
    datasets: dict[str, pd.DataFrame],
    merged: pd.DataFrame,
    output_dir: Path,
    warnings,
) -> list[dict[str, Any]]:
    """Render every figure into ``output_dir``; return per-figure status rows."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for filename, builder in _FIGURES.items():
        path = output_dir / filename
        entry: dict[str, Any] = {"filename": filename}
        try:
            builder(datasets, merged, path)
            entry["created"] = path.exists() and path.stat().st_size > 0
            entry["size_bytes"] = path.stat().st_size if path.exists() else 0
        except Exception as exc:  # noqa: BLE001 - one bad figure must not abort the run
            entry["created"] = False
            entry["error"] = f"{type(exc).__name__}: {exc}"
            warnings.add("figures", f"failed to render {filename}: {exc}")
        results.append(entry)
    return results
