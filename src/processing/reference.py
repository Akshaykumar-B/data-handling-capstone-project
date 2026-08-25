"""Authoritative route reference derived from the Phase 2 profiling report.

``data/processed/dataset_profiling_report.json`` is the single source of truth
for (a) the canonical project route list and (b) the known route-id aliases
such as ``B44+`` -> ``B44-SBS``. Nothing in this module invents identifiers: it
only reads, normalizes and indexes what the profiling report already recorded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .utils import normalize_route, normalized_route_set


@dataclass(frozen=True)
class RouteReference:
    """Canonical project routes plus the alias map used to unify identifiers."""

    project_routes: frozenset[str]
    raw_project_routes: frozenset[str]
    alias_map: dict[str, str]
    alias_pairs: tuple[tuple[str, str], ...]
    geometry_route_identifiers: frozenset[str]
    source_notes: tuple[str, ...]

    def canonical(self, value: object) -> str | None:
        """Normalize a route identifier and fold known aliases onto one form."""
        normalized = normalize_route(value)
        if normalized is None:
            return None
        return self.alias_map.get(normalized, normalized)

    def is_project_route(self, value: object) -> bool:
        """True when the (canonicalized or raw-normalized) route is in scope."""
        normalized = normalize_route(value)
        if normalized is None:
            return False
        if normalized in self.project_routes:
            return True
        return self.alias_map.get(normalized, normalized) in self.project_routes


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required reference report is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_route_reference(
    profiling_report_path: Path,
    routes_valid_report_path: Path | None = None,
) -> tuple[RouteReference, dict[str, Any]]:
    """Build the route reference and return it with the raw profiling payload."""
    profile = _load_json(profiling_report_path)
    notes: list[str] = [f"project routes and aliases sourced from {profiling_report_path.name}"]

    # --- Canonical project route list -------------------------------------
    aggregations = profile.get("aggregations", {})
    ridership_by_route = aggregations.get("ridership_by_route", {})
    project_routes = normalized_route_set(ridership_by_route.keys())

    # Cross-check against the routes acquisition report when available. The
    # larger of the two lists wins so a truncated aggregation cannot silently
    # shrink the project scope.
    if routes_valid_report_path is not None and routes_valid_report_path.exists():
        routes_report = _load_json(routes_valid_report_path)
        compatibility = routes_report.get("ridership_compatibility", {})
        listed = normalized_route_set(compatibility.get("matching_ridership_route_ids", []))
        if listed:
            notes.append(
                f"cross-checked against {routes_valid_report_path.name} "
                f"({len(listed)} matching ridership route ids)"
            )
            if len(listed) > len(project_routes):
                project_routes = project_routes | listed

    if not project_routes:
        raise ValueError(
            "Could not derive any project routes from the profiling report; "
            "refusing to continue with an empty route reference."
        )

    # --- Known aliases ----------------------------------------------------
    relationships = profile.get("relationships", {})
    alias_map: dict[str, str] = {}
    alias_pairs: list[tuple[str, str]] = []
    for entry in relationships.get("possible_route_id_aliases", []):
        source = normalize_route(entry.get("route_id"))
        target = normalize_route(entry.get("route_short_name"))
        if source is None or target is None or source == target:
            continue
        alias_map[source] = target
        alias_pairs.append((source, target))
    alias_pairs.sort()
    notes.append(f"{len(alias_pairs)} known route aliases loaded (no new aliases inferred)")

    # The project list is stated in ridership spelling (e.g. "B44+"), while the
    # geometry/stop datasets use the SBS spelling ("B44-SBS"). Canonicalizing
    # the project list through the same alias map is what makes coverage
    # comparisons meaningful in both directions.
    raw_project_routes = frozenset(project_routes)
    canonical_project_routes = {alias_map.get(route, route) for route in project_routes}
    aliased_project_routes = sorted(route for route in project_routes if route in alias_map)
    if aliased_project_routes:
        notes.append(
            f"{len(aliased_project_routes)} project route(s) canonicalized via the alias "
            f"map for coverage comparison: {aliased_project_routes}"
        )
    if len(canonical_project_routes) != len(raw_project_routes):
        notes.append(
            "warning: alias canonicalization collapsed "
            f"{len(raw_project_routes) - len(canonical_project_routes)} project route(s) "
            "onto an existing identifier"
        )

    # --- Route identifiers that have geometry -----------------------------
    routes_profile = profile.get("routes", {})
    coverage = routes_profile.get("route_geometry_coverage_against_ridership", {})
    geometry_identifiers = normalized_route_set(coverage.get("unmatched_right_route_ids", []))
    # Everything the ridership side matched also has geometry.
    matched_left = raw_project_routes - normalized_route_set(
        coverage.get("unmatched_left_route_ids", [])
    )
    geometry_identifiers |= {alias_map.get(route, route) for route in matched_left}

    reference = RouteReference(
        project_routes=frozenset(canonical_project_routes),
        raw_project_routes=raw_project_routes,
        alias_map=alias_map,
        alias_pairs=tuple(alias_pairs),
        geometry_route_identifiers=frozenset(geometry_identifiers),
        source_notes=tuple(notes),
    )
    return reference, profile


def coverage_against_project(
    observed: set[str],
    reference: RouteReference,
    *,
    canonicalize: bool = True,
) -> dict[str, Any]:
    """Compare an observed route set against the authoritative project routes.

    Reports both directions so missing routes are visible without ever being
    back-filled into the data.
    """
    if canonicalize:
        resolved = {reference.canonical(value) for value in observed}
        resolved.discard(None)
        observed_set: set[str] = {value for value in resolved if value is not None}
    else:
        observed_set = set(observed)

    project = set(reference.project_routes)
    matching = observed_set & project
    return {
        "observed_route_count": len(observed_set),
        "project_route_count": len(project),
        "matching_route_count": len(matching),
        "coverage_percentage": round(100 * len(matching) / len(project), 2) if project else 0.0,
        "project_routes_missing_from_dataset": sorted(project - observed_set),
        "dataset_routes_not_in_project_reference": sorted(observed_set - project),
    }
