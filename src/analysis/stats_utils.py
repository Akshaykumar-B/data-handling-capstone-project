"""Deterministic descriptive statistics, IQR outlier detection and correlation
helpers shared across the EDA modules.

Every function is pure: a pandas Series / arrays go in, a plain JSON-safe dict
comes out. No file I/O, no randomness, no global state. scipy is optional and
used only to attach p-values when it happens to be installed; the correlation
coefficients themselves come from pandas so the pipeline has no hard scipy
dependency.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

try:  # optional - only for p-values
    from scipy import stats as _scipy_stats

    _HAVE_SCIPY = True
except Exception:  # noqa: BLE001 - scipy is genuinely optional
    _scipy_stats = None
    _HAVE_SCIPY = False

ROUND = 6


def have_scipy() -> bool:
    return _HAVE_SCIPY


def _round(value: Any) -> float | None:
    """Round to a stable precision; map NaN/inf/non-numeric to None."""
    if value is None:
        return None
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(as_float) or math.isinf(as_float):
        return None
    return round(as_float, ROUND)


def describe_series(series: pd.Series, *, name: str | None = None) -> dict[str, Any]:
    """count / mean / median / std / min / max / quartiles / IQR (+skew, missing).

    Non-numeric entries are coerced to NaN and excluded from the statistics but
    counted under ``missing``.
    """
    numeric = pd.to_numeric(series, errors="coerce")
    non_null = numeric.dropna()
    count = int(non_null.shape[0])
    resolved_name = name if name is not None else getattr(series, "name", None)
    result: dict[str, Any] = {
        "name": resolved_name,
        "count": count,
        "missing": int(numeric.isna().sum()),
        "mean": None,
        "median": None,
        "std": None,
        "min": None,
        "max": None,
        "q1": None,
        "q3": None,
        "iqr": None,
        "range": None,
        "skew": None,
    }
    if count == 0:
        return result
    q1 = float(non_null.quantile(0.25))
    q3 = float(non_null.quantile(0.75))
    minimum = float(non_null.min())
    maximum = float(non_null.max())
    result.update(
        {
            "mean": _round(non_null.mean()),
            "median": _round(non_null.median()),
            "std": _round(non_null.std(ddof=1)) if count > 1 else 0.0,
            "min": _round(minimum),
            "max": _round(maximum),
            "q1": _round(q1),
            "q3": _round(q3),
            "iqr": _round(q3 - q1),
            "range": _round(maximum - minimum),
            "skew": _round(non_null.skew()) if count > 2 else None,
        }
    )
    return result


def iqr_outliers(
    series: pd.Series,
    *,
    multiplier: float = 1.5,
    labels: pd.Series | None = None,
    max_examples: int = 25,
) -> dict[str, Any]:
    """Tukey IQR fences (Q1 - k*IQR, Q3 + k*IQR).

    Outliers are reported, never removed. ``examples`` lists the most extreme
    values (largest distance beyond the nearest fence first) with an optional
    label taken from the index-aligned ``labels`` series.
    """
    numeric = pd.to_numeric(series, errors="coerce")
    non_null = numeric.dropna()
    n = int(non_null.shape[0])
    result: dict[str, Any] = {
        "method": f"Tukey IQR (k={multiplier})",
        "count_evaluated": n,
        "q1": None,
        "q3": None,
        "iqr": None,
        "lower_fence": None,
        "upper_fence": None,
        "outlier_count": 0,
        "lower_outlier_count": 0,
        "upper_outlier_count": 0,
        "outlier_percentage": 0.0,
        "examples": [],
        "action": "reported only - not removed",
    }
    if n < 4:
        result["note"] = "too few non-null values for a meaningful IQR"
        return result

    q1 = float(non_null.quantile(0.25))
    q3 = float(non_null.quantile(0.75))
    iqr = q3 - q1
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    below = non_null < lower
    above = non_null > upper
    mask = below | above
    result.update(
        {
            "q1": _round(q1),
            "q3": _round(q3),
            "iqr": _round(iqr),
            "lower_fence": _round(lower),
            "upper_fence": _round(upper),
            "outlier_count": int(mask.sum()),
            "lower_outlier_count": int(below.sum()),
            "upper_outlier_count": int(above.sum()),
            "outlier_percentage": _round(100.0 * int(mask.sum()) / n),
        }
    )
    if int(mask.sum()):
        outliers = non_null[mask]
        distance = pd.Series(
            np.where(outliers < lower, lower - outliers, outliers - upper),
            index=outliers.index,
        )
        order = distance.sort_values(ascending=False, kind="mergesort").index[:max_examples]
        examples = []
        for idx in order:
            example: dict[str, Any] = {"value": _round(float(non_null.loc[idx]))}
            if labels is not None:
                try:
                    example["label"] = str(labels.loc[idx])
                except Exception:  # noqa: BLE001 - label is best-effort
                    pass
            examples.append(example)
        result["examples"] = examples
    return result


def _strength_label(r: float | None) -> str | None:
    if r is None:
        return None
    magnitude = abs(r)
    if magnitude < 0.1:
        return "negligible"
    if magnitude < 0.3:
        return "weak"
    if magnitude < 0.5:
        return "moderate"
    if magnitude < 0.7:
        return "strong"
    return "very strong"


def correlations(
    x: pd.Series,
    y: pd.Series,
    *,
    x_name: str | None = None,
    y_name: str | None = None,
) -> dict[str, Any]:
    """Pearson + Spearman between two series (pairwise-complete rows only).

    Coefficients come from pandas. p-values are attached only when scipy is
    installed; otherwise ``n`` is reported so significance can still be judged.
    Always framed as association, never causation.
    """
    frame = pd.DataFrame(
        {"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}
    ).dropna()
    n = int(len(frame))
    result: dict[str, Any] = {
        "x": x_name,
        "y": y_name,
        "n": n,
        "pearson_r": None,
        "spearman_rho": None,
        "pearson_p_value": None,
        "spearman_p_value": None,
        "strength": None,
        "note": "association only; correlation does not imply causation",
    }
    if n < 3 or frame["x"].nunique() < 2 or frame["y"].nunique() < 2:
        result["insufficient_data"] = True
        return result

    pearson = frame["x"].corr(frame["y"], method="pearson")
    # Spearman = Pearson correlation of average ranks. Computed explicitly so we
    # never touch scipy (pandas' method="spearman" imports scipy.stats internally).
    spearman = frame["x"].rank(method="average").corr(
        frame["y"].rank(method="average"), method="pearson"
    )
    result["pearson_r"] = _round(pearson)
    result["spearman_rho"] = _round(spearman)
    result["strength"] = _strength_label(result["pearson_r"])

    if _HAVE_SCIPY:
        try:
            pearson_test = _scipy_stats.pearsonr(frame["x"].to_numpy(), frame["y"].to_numpy())
            spearman_test = _scipy_stats.spearmanr(frame["x"].to_numpy(), frame["y"].to_numpy())
            result["pearson_p_value"] = _round(float(pearson_test[1]))
            spearman_p = getattr(spearman_test, "pvalue", None)
            result["spearman_p_value"] = _round(
                float(spearman_p if spearman_p is not None else spearman_test[1])
            )
        except Exception:  # noqa: BLE001 - p-values are best-effort
            pass
    else:
        result["p_value_note"] = (
            "scipy not installed; p-values omitted (n reported so significance can be judged)"
        )
    return result


def weighted_mean(values: pd.Series, weights: pd.Series) -> float | None:
    """Weighted mean ignoring NaN values, NaN weights and non-positive weights."""
    v = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce")
    mask = v.notna() & w.notna() & (w > 0)
    if not bool(mask.any()):
        return None
    total_weight = float(w[mask].sum())
    if total_weight <= 0:
        return None
    return float((v[mask] * w[mask]).sum() / total_weight)


def category_summary(
    frame: pd.DataFrame,
    group_column: str,
    value_column: str,
    *,
    weight_column: str | None = None,
) -> list[dict[str, Any]]:
    """Per-category count / simple mean / (optional) weighted mean of a metric.

    Rows are returned sorted by category name for deterministic output.
    """
    rows: list[dict[str, Any]] = []
    for key, group in frame.groupby(group_column, dropna=False, observed=True):
        metric = pd.to_numeric(group[value_column], errors="coerce")
        entry: dict[str, Any] = {
            "category": None if (isinstance(key, float) and math.isnan(key)) else str(key),
            "record_count": int(len(group)),
            "non_null_count": int(metric.notna().sum()),
            "mean": _round(metric.mean()),
            "median": _round(metric.median()),
        }
        if weight_column is not None:
            entry["weighted_mean"] = _round(weighted_mean(metric, group[weight_column]))
            entry["total_weight"] = _round(
                pd.to_numeric(group[weight_column], errors="coerce").sum()
            )
        rows.append(entry)
    rows.sort(key=lambda item: (item["category"] is None, item["category"] or ""))
    return rows


def top_bottom(
    frame: pd.DataFrame,
    label_column: str,
    value_column: str,
    *,
    n: int = 10,
    extra_columns: tuple[str, ...] = (),
) -> dict[str, list[dict[str, Any]]]:
    """Top-n and bottom-n rows by ``value_column`` (deterministic tie-breaking).

    Sort is by value then label so equal values order stably by label name.
    """
    working = frame[[label_column, value_column, *extra_columns]].copy()
    working[value_column] = pd.to_numeric(working[value_column], errors="coerce")
    working = working.dropna(subset=[value_column])
    ordered = working.sort_values(
        by=[value_column, label_column], ascending=[False, True], kind="mergesort"
    )

    def _rows(subset: pd.DataFrame) -> list[dict[str, Any]]:
        records = []
        for _, row in subset.iterrows():
            record = {
                "label": str(row[label_column]),
                "value": _round(row[value_column]),
            }
            for column in extra_columns:
                record[column] = _round(row[column]) if isinstance(
                    row[column], (int, float, np.floating, np.integer)
                ) else (None if pd.isna(row[column]) else str(row[column]))
            records.append(record)
        return records

    return {
        "top": _rows(ordered.head(n)),
        "bottom": _rows(ordered.tail(n).iloc[::-1]),
    }
