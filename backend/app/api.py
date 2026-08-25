"""Versioned read-only dashboard endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from .services.data_access import data_store

router = APIRouter(prefix="/api/v1")


def meta(source: str, coverage: Any = None, limitations: list[str] | None = None) -> dict[str, Any]:
    return {"source": source, "coverage": coverage, "limitations": limitations or []}


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    def clean(value: Any) -> Any:
        if value is None or value is pd.NA or (isinstance(value, float) and pd.isna(value)):
            return None
        if isinstance(value, (pd.Timestamp, date)):
            return value.isoformat()
        return value.item() if hasattr(value, "item") else value

    return [{key: clean(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]


def project_route(route: str | None) -> str | None:
    if route is None:
        return None
    value = route.strip().upper()
    if value not in set(data_store.processing["route_reference"]["project_routes"]):
        raise HTTPException(400, f"Unknown project route: {route}")
    return value


def date_slice(frame: pd.DataFrame, column: str, start: str | None, end: str | None) -> pd.DataFrame:
    try:
        if start:
            frame = frame[frame[column].astype(str) >= pd.Timestamp(start).date().isoformat()]
        if end:
            frame = frame[frame[column].astype(str) <= pd.Timestamp(end).date().isoformat()]
    except (TypeError, ValueError):
        raise HTTPException(400, "Invalid date filter") from None
    return frame


def ridership_frame(route: str | None = None) -> pd.DataFrame:
    frame = data_store.table("ridership_clean")
    if route:
        frame = frame[frame["route_id"].astype(str).str.upper() == route]
    return frame


def cjtp_frame(route: str | None = None) -> pd.DataFrame:
    frame = data_store.table("customer_journey_clean")
    if route:
        frame = frame[frame["route_id_canonical"].astype(str).str.upper() == route]
    return frame


def grouped_cjtp(frame: pd.DataFrame, column: str) -> list[dict[str, Any]]:
    valid = frame[frame["customer_journey_time_performance"].notna()]
    output = []
    for key, group in valid.groupby(column, dropna=False):
        weight = group["number_of_customers"]
        output.append({column: None if pd.isna(key) else key, "record_count": len(group), "customer_weighted_cjtp": float((group["customer_journey_time_performance"] * weight).sum() / weight.sum()) if weight.sum() else None})
    return output


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "public-transit-dashboard-api"}


@router.get("/data/status")
def data_status() -> dict[str, Any]:
    return data_store.status()


@router.get("/overview")
def overview() -> dict[str, Any]:
    a = data_store.eda["analyses"]
    return {"data": {"total_ridership": a["ridership"]["totals"]["total_ridership"], "total_transfers": a["ridership"]["totals"]["total_transfers"], "ridership_record_count": a["ridership"]["totals"]["record_count"], "ridership_route_coverage": a["ridership"]["route_coverage"], "cjtp_weighted_average": a["cjtp"]["overall_distribution"]["customer_weighted_mean"], "cjtp_route_coverage": a["cjtp"]["route_coverage"], "unique_stops": a["bus_stops"]["physical_stop_inventory"]["unique_physical_stops"], "stop_associations": a["bus_stops"]["physical_stop_inventory"]["total_route_stop_associations"], "stop_route_coverage": a["bus_stops"]["route_coverage"], "route_geometry_feature_count": a["routes"]["geometry_summary"]["feature_count"], "route_coverage": a["routes"]["project_route_coverage"], "all_dataset_route_coverage": a["cross_dataset"]["coverage_overlap"]}, "meta": meta("data/processed/eda_report.json and processing_report.json")}


@router.get("/ridership/summary")
def ridership_summary(route: str | None = None, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    selected = project_route(route)
    if not any((selected, start_date, end_date)):
        data = data_store.eda["analyses"]["ridership"]["totals"]
    else:
        frame = date_slice(ridership_frame(selected), "service_date", start_date, end_date)
        data = {"total_ridership": int(frame["ridership"].sum()), "total_transfers": int(frame["transfers"].sum()), "record_count": len(frame), "distinct_routes": int(frame["route_id"].nunique()), "distinct_service_dates": int(frame["service_date"].nunique())}
    return {"data": data, "meta": meta("data/processed/ridership_clean.parquet", data_store.coverage("ridership"), ["Development subsample; hourly data contains 12 even-hour buckets only."])}


@router.get("/ridership/routes")
def ridership_routes(route: str | None = None) -> dict[str, Any]:
    selected = project_route(route)
    frame = data_store.table("ridership_by_route")
    if selected:
        frame = frame[frame["route_id"].astype(str).str.upper() == selected]
    return {"data": records(frame), "meta": meta("data/processed/ridership_by_route.parquet", data_store.coverage("ridership"))}


@router.get("/ridership/daily")
def ridership_daily(route: str | None = None, start_date: str | None = None, end_date: str | None = None, day_type: str | None = None, day_of_week: str | None = None) -> dict[str, Any]:
    selected = project_route(route)
    if selected:
        frame = ridership_frame(selected).groupby(["service_date", "day_of_week", "is_weekend"], as_index=False).agg(record_count=("ridership", "size"), total_ridership=("ridership", "sum"), total_transfers=("transfers", "sum"), distinct_routes=("route_id", "nunique"))
    else:
        frame = data_store.table("ridership_by_date")
    frame = date_slice(frame, "service_date", start_date, end_date)
    if day_type:
        value = day_type.strip().lower()
        if value not in {"weekday", "weekend"}:
            raise HTTPException(400, "day_type must be weekday or weekend")
        frame = frame[frame["is_weekend"] == (value == "weekend")]
    if day_of_week:
        frame = frame[frame["day_of_week"].astype(str).str.lower() == day_of_week.strip().lower()]
    return {"data": records(frame), "meta": meta("data/processed/ridership_by_date.parquet", data_store.coverage("ridership"))}


@router.get("/ridership/hourly")
def ridership_hourly(route: str | None = None, hour: int | None = Query(None, ge=0, le=23)) -> dict[str, Any]:
    selected = project_route(route)
    frame = data_store.table("ridership_by_hour") if not selected else ridership_frame(selected).groupby("hour", as_index=False).agg(record_count=("ridership", "size"), total_ridership=("ridership", "sum"), total_transfers=("transfers", "sum"))
    if hour is not None:
        if hour % 2:
            raise HTTPException(400, "Only observed even hour buckets are valid")
        frame = frame[frame["hour"] == hour]
    caveat = data_store.eda["analyses"]["ridership"]["hourly"]["caveat"]
    return {"data": records(frame), "meta": meta("data/processed/ridership_by_hour.parquet", data_store.coverage("ridership"), [caveat])}


@router.get("/cjtp/summary")
def cjtp_summary(route: str | None = None) -> dict[str, Any]:
    selected = project_route(route)
    data = data_store.eda["analyses"]["cjtp"]["overall_distribution"] if not selected else grouped_cjtp(cjtp_frame(selected), "year")
    return {"data": data, "meta": meta("data/processed/eda_report.json", data_store.coverage("cjtp"), ["CJTP covers 120 of 142 project routes; missing metrics are not fabricated."])}


@router.get("/cjtp/monthly")
def cjtp_monthly(route: str | None = None, start_month: str | None = None, end_month: str | None = None) -> dict[str, Any]:
    selected = project_route(route)
    if selected:
        frame = cjtp_frame(selected)
        if start_month: frame = frame[frame["month"].astype(str) >= start_month]
        if end_month: frame = frame[frame["month"].astype(str) <= end_month]
        data = grouped_cjtp(frame, "month")
    else:
        data = data_store.eda["analyses"]["cjtp"]["by_month"]
        data = [row for row in data if (not start_month or row["month"] >= start_month) and (not end_month or row["month"] <= end_month)]
    return {"data": data, "meta": meta("data/processed/eda_report.json", data_store.coverage("cjtp"))}


@router.get("/cjtp/yearly")
def cjtp_yearly(route: str | None = None, year: int | None = None) -> dict[str, Any]:
    data = grouped_cjtp(cjtp_frame(project_route(route)), "year") if route else data_store.eda["analyses"]["cjtp"]["by_year"]
    if year is not None: data = [row for row in data if row["year"] == year]
    return {"data": data, "meta": meta("data/processed/eda_report.json", data_store.coverage("cjtp"))}


@router.get("/cjtp/routes")
def cjtp_routes(route: str | None = None) -> dict[str, Any]:
    selected = project_route(route)
    frame = data_store.table("cjtp_by_route")
    project = set(data_store.processing["route_reference"]["project_routes"])
    frame = frame[frame["route_id"].astype(str).str.upper().isin({selected} if selected else project)]
    return {"data": records(frame), "meta": meta("data/processed/cjtp_by_route.parquet", data_store.coverage("cjtp"))}


@router.get("/cjtp/by-period")
def cjtp_period(route: str | None = None, period: str | None = None) -> dict[str, Any]:
    data = grouped_cjtp(cjtp_frame(project_route(route)), "period")
    if period: data = [row for row in data if str(row["period"]).lower() == period.strip().lower()]
    return {"data": data, "meta": meta("data/processed/customer_journey_clean.parquet", data_store.coverage("cjtp"))}


@router.get("/cjtp/by-trip-type")
def cjtp_trip_type(route: str | None = None, trip_type: str | None = None) -> dict[str, Any]:
    data = grouped_cjtp(cjtp_frame(project_route(route)), "trip_type")
    if trip_type: data = [row for row in data if str(row["trip_type"]).upper() == trip_type.strip().upper()]
    return {"data": data, "meta": meta("data/processed/customer_journey_clean.parquet", data_store.coverage("cjtp"))}


@router.get("/cjtp/by-borough")
def cjtp_borough(route: str | None = None, borough: str | None = None) -> dict[str, Any]:
    data = grouped_cjtp(cjtp_frame(project_route(route)), "borough")
    if borough: data = [row for row in data if str(row["borough"]).upper() == borough.strip().upper()]
    return {"data": data, "meta": meta("data/processed/customer_journey_clean.parquet", data_store.coverage("cjtp"))}


@router.get("/stops/summary")
def stops_summary() -> dict[str, Any]:
    a = data_store.eda["analyses"]["bus_stops"]
    return {"data": {"physical_stop_inventory": a["physical_stop_inventory"], "by_direction": a["stops_by_direction"], "by_direction_id": a["stops_by_direction_id"]}, "meta": meta("data/processed/eda_report.json", a["route_coverage"])}


@router.get("/stops/routes")
def stops_routes(route: str | None = None) -> dict[str, Any]:
    selected = project_route(route)
    frame = data_store.table("route_stop_relationships")
    if selected: frame = frame[frame["route_id_canonical"].astype(str).str.upper() == selected]
    return {"data": records(frame), "meta": meta("data/processed/route_stop_relationships.parquet", data_store.coverage("bus_stops"))}


@router.get("/stops/points")
def stops_points(route: str | None = None, direction: str | None = None) -> dict[str, Any]:
    selected = project_route(route)
    frame = data_store.table("route_stop_relationships")
    if selected: frame = frame[frame["route_id_canonical"].astype(str).str.upper() == selected]
    if direction:
        value = direction.strip().upper()
        if value not in {"N", "S", "E", "W"}: raise HTTPException(400, "direction must be N, S, E, or W")
        frame = frame[frame["direction"].astype(str).str.upper() == value]
    features = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]}, "properties": {key: row[key] for key in ("route_id_canonical", "stop_id", "stop_name", "direction")}} for row in records(frame) if row.get("latitude") is not None and row.get("longitude") is not None]
    return {"type": "FeatureCollection", "features": features, "meta": meta("data/processed/route_stop_relationships.parquet", data_store.coverage("bus_stops"))}


@router.get("/routes/summary")
def routes_summary() -> dict[str, Any]:
    a = data_store.eda["analyses"]["routes"]
    return {"data": {"geometry_summary": a["geometry_summary"], "project_route_coverage": a["project_route_coverage"], "service_categories": a["service_categories"]}, "meta": meta("data/processed/eda_report.json and processing_report.json")}


@router.get("/relationships/summary")
def relationships_summary() -> dict[str, Any]:
    a = data_store.eda["analyses"]
    return {"data": {"record_level": a["cjtp"]["relationships"], "route_level": a["cross_dataset"]["relationships"]}, "meta": meta("data/processed/eda_report.json", limitations=["All values are statistical associations; correlation does not imply causation."])}


@router.get("/relationships/correlation")
def relationships_correlation(pair: str | None = None) -> dict[str, Any]:
    a = data_store.eda["analyses"]
    available = {**a["cjtp"]["relationships"], **a["cross_dataset"]["relationships"]}
    if pair:
        if pair not in available: raise HTTPException(400, f"Unknown relationship: {pair}")
        available = {pair: available[pair]}
    return {"data": available, "meta": meta("data/processed/eda_report.json", limitations=["Association only; correlation does not imply causation."])}


@router.get("/data/quality")
def data_quality() -> dict[str, Any]:
    eda, processing = data_store.eda, data_store.processing
    return {"data": {"phase3": {"status": processing["status"], "validation": processing["validation"]}, "phase4": {"status": eda["status"], "validation": eda["validation"]}, "row_counts": {key: value.get("output_row_count") for key, value in processing["dataset_reports"].items()}, "route_coverage": {key: value["route_coverage"] for key, value in eda["analyses"].items() if "route_coverage" in value}, "missing_values": {key: value.get("missing_values_by_column", {}) for key, value in processing["dataset_reports"].items()}, "warnings": eda["warnings"], "limitations": eda["limitations"], "reports": {"processing": {"phase": processing["phase"], "started_utc": processing["started_utc"], "finished_utc": processing["finished_utc"]}, "eda": {"phase": eda["phase"], "started_utc": eda["started_utc"], "finished_utc": eda["finished_utc"]}}}, "meta": meta("data/processed/eda_report.json and processing_report.json")}
