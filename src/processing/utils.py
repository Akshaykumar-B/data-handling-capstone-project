"""Shared helpers for Phase 3 processing.

Contains route-identifier normalization, deterministic JSON coercion, atomic
file replacement and a small warning collector. Everything here is pure and
side-effect free apart from the explicit file helpers.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

# ---------------------------------------------------------------------------
# Route identifier normalization
# ---------------------------------------------------------------------------

def normalize_route(value: object) -> str | None:
    """Uppercase and trim a route identifier.

    Mirrors the normalization already used by the Phase 2 profiling and
    validation scripts so route sets stay comparable across phases. Returns
    ``None`` for missing/blank values instead of inventing a placeholder.
    """
    if value is None:
        return None
    # Avoid importing pandas here; treat NaN via the self-inequality trick.
    if isinstance(value, float) and value != value:
        return None
    text = str(value).strip().upper()
    if not text or text in {"NAN", "NONE", "<NA>"}:
        return None
    return text


def normalized_route_set(values: Iterable[object]) -> set[str]:
    """Normalize an iterable of route identifiers into a set, dropping blanks."""
    result: set[str] = set()
    for value in values:
        normalized = normalize_route(value)
        if normalized is not None:
            result.add(normalized)
    return result


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def json_safe(value: Any) -> Any:
    """Coerce numpy/pandas scalars and containers into JSON-serializable values."""
    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return None if value != value else value
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        iterable = sorted(value) if isinstance(value, set) else value
        return [json_safe(item) for item in iterable]
    # numpy / pandas scalars expose .item(); pandas.Timestamp exposes isoformat().
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return isoformat()
        except Exception:  # pragma: no cover - defensive
            return str(value)
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return json_safe(item())
        except Exception:  # pragma: no cover - defensive
            return str(value)
    return str(value)


def write_json_atomic(payload: dict[str, Any], path: Path) -> None:
    """Write JSON via a temporary file, verify it parses, then atomically replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.stem}.tmp{path.suffix}")
    temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    json.loads(temporary_path.read_text(encoding="utf-8"))  # fail fast on bad JSON
    replace_atomic(temporary_path, path)


def replace_atomic(temporary_path: Path, final_path: Path) -> None:
    """Atomically move ``temporary_path`` onto ``final_path``.

    A PermissionError normally means the destination is open in another program
    (Excel, QGIS, a notebook). The validated temporary file is retained so no
    work is lost.
    """
    try:
        os.replace(temporary_path, final_path)
    except PermissionError as exc:  # pragma: no cover - environment specific
        raise RuntimeError(
            f"Output is locked and was not overwritten: {final_path}. "
            f"Validated temporary file retained at: {temporary_path}"
        ) from exc


# ---------------------------------------------------------------------------
# File fingerprinting (used to prove data/raw/ was not modified)
# ---------------------------------------------------------------------------

def fingerprint(path: Path, *, hash_limit_bytes: int) -> dict[str, Any]:
    """Return a size/mtime fingerprint, adding a sha256 for smaller files."""
    stat = path.stat()
    record: dict[str, Any] = {
        "path": path.name,
        "size_bytes": stat.st_size,
        "modified_time_ns": stat.st_mtime_ns,
        "sha256": None,
    }
    if stat.st_size <= hash_limit_bytes:
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        record["sha256"] = digest.hexdigest()
    return record


def fingerprint_all(paths: Sequence[Path], *, hash_limit_bytes: int) -> dict[str, dict[str, Any]]:
    return {path.name: fingerprint(path, hash_limit_bytes=hash_limit_bytes) for path in paths}


# ---------------------------------------------------------------------------
# Warning collection
# ---------------------------------------------------------------------------

@dataclass
class WarningCollector:
    """Accumulates non-fatal findings surfaced in the processing report."""

    items: list[dict[str, str]] = field(default_factory=list)

    def add(self, scope: str, message: str) -> None:
        self.items.append({"scope": scope, "message": message})
        print(f"  [warning:{scope}] {message}")

    def to_list(self) -> list[dict[str, str]]:
        return list(self.items)


def describe_missing(frame: Any) -> dict[str, int]:
    """Missing-value counts per column for a pandas DataFrame."""
    return {str(column): int(frame[column].isna().sum()) for column in frame.columns}
