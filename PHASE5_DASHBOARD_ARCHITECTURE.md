# Phase 5.1 — Dashboard Architecture Specification

**Project:** Implementation of a Public Transit Ridership and Route Performance Visualization Dashboard
**Phase:** 5.1 (design only — no implementation)
**Frontend stack (approved):** **Next.js + TypeScript** (presentation) over a **FastAPI (Python)** data API.
**Author of record:** produced from the actual Phase 3 processing outputs and the Phase 4 EDA report; no metrics invented, no documented limitation silently corrected.
**Status:** Specification. Defines *what* to build and *from which files/endpoints*. Contains **no dashboard code** and creates **no dashboard output, dataset, or server**.

> **Stack-change note (2026-08-25).** This document supersedes the earlier Streamlit-based Phase 5.1 draft. The approved Phase 5 frontend is now **Next.js + TypeScript**, served by a **FastAPI** backend. **Phase 3 (data processing) and Phase 4 (EDA) are unchanged** — the dashboard only *reads* their existing outputs. Every metric, data-source mapping, limitation, and insight below is identical to the verified values from Phase 4; only the technology, structure, API layer, performance model, responsive UI, validation, and implementation order are redesigned.

> **Scope guard for this phase.** Nothing here has been executed. No packages installed (Python or npm), nothing downloaded, no Node.js toolchain added, `data/raw` and `data/processed` untouched, the 2.3 GB route GeoJSON not opened, no server started, no `dashboard/` code created. Implementation is Phase 5.2.

---

## 0. Sources of truth (read once, cited everywhere below)

Every number in this spec traces to one of these files. The **FastAPI backend is the only component that reads them**; the Next.js frontend never touches the filesystem or the data directory.

| Source file | Role | Notes |
|---|---|---|
| `data/processed/eda_report.json` | **Primary Phase 4 source of truth** for statistics, distributions, correlations, outliers, coverage, limitations. | 3,842 lines; validated 6/6. Analytics live under `analyses.{ridership,cjtp,bus_stops,routes,cross_dataset}`. |
| `data/processed/processing_report.json` | **Authoritative route reference** (`route_reference.project_routes` = 142 canonical IDs) + Phase 3 geometry metadata. | Route membership comes only from here. |
| `data/processed/ridership_by_route.parquet` | Per-route ridership (140 rows). | Schema in §9. |
| `data/processed/ridership_by_date.parquet` | Per-service-date ridership (59 rows). | |
| `data/processed/ridership_by_hour.parquet` | Per-hour-bucket ridership (12 rows). | **12 even buckets only — §4/§8.** |
| `data/processed/cjtp_by_route.parquet` | Per-route CJTP (393 rows). | |
| `data/processed/route_stop_relationships.parquet` | Route↔stop associations (8,664) **with `latitude`/`longitude`**. | Enables the stop map with zero GeoJSON access. |
| `data/processed/bus_stops_clean.parquet` | Cleaned stops (8,664) with coordinates. | Alternate coordinate source. |
| `data/processed/customer_journey_clean.parquet` | Cleaned CJTP records (67,943). | Record-level; for sampled scatter only. |
| `data/processed/ridership_clean.parquet` | Cleaned ridership (200,000). | Record-level; aggregations preferred. |
| `data/processed/eda/*.png` | 10 pre-rendered Phase 4 figures. | Optional static "report view." |
| `data/processed/routes_clean.geojson` | 2.3 GB route geometry (206,338 features). | **Never read at request time / never sent to the browser.** §11. |

---

## 1. Technology

### 1.1 What already exists (inspected, not assumed)

`requirements.txt` pins **pandas, geopandas, requests, pyarrow, matplotlib** — a pure-Python data stack; the runtime `.venv` resolves pandas 3.0.5 / pyarrow 25.0.1 / matplotlib 3.11.1; **`scipy` is deliberately absent** (Phase 4 computes Spearman without it). **There is no web framework and no JavaScript/Node toolchain in the repo today.** Phase 3/4 conventions: pure functions, deterministic output, atomic writes, input immutability, and the routes GeoJSON handled by metadata only.

### 1.2 Approved three-tier architecture

```
┌─────────────────────────┐     HTTP / JSON      ┌──────────────────────────┐
│  Next.js + TypeScript    │  ───────────────▶   │  FastAPI (Python)         │
│  (App Router, React)     │  ◀───────────────   │  data API                 │
│  charts · maps · filters │   typed responses    │  reads processed files    │
└─────────────────────────┘                      └────────────┬─────────────┘
        browser                                                │ read-only
                                                   ┌───────────▼─────────────┐
                                                   │ data/processed/ (Phase   │
                                                   │ 3 & 4 outputs) UNCHANGED │
                                                   └──────────────────────────┘
```

- **Data tier (unchanged).** The Phase 3/4 outputs in §0. Treated as **read-only** by the dashboard. No pipeline file (`src/processing`, `src/analysis`) is modified, imported for mutation, or re-run by the dashboard.
- **Backend — FastAPI (Python).** Reuses the existing pandas/pyarrow stack to load the small processed tables and the two JSON reports **once at startup**, then serves a versioned JSON API. It is the single reader of the data directory and the **only** place the (small, derived) geometry is ever handled. It never reads the 2.3 GB GeoJSON at request time.
- **Frontend — Next.js + TypeScript.** App Router. React Server Components fetch initial data; Client Components handle interactive charts, filters, and the map. TypeScript types are generated from the backend's OpenAPI schema so the contract is enforced at compile time.

**Why this split.** It keeps the verified Python analytics logic on the Python side (no re-implementation of statistics in JS), gives the frontend a small, typed, cache-friendly JSON surface instead of raw files, and keeps the 2.3 GB GeoJSON entirely server-side. It is the conventional, well-documented FastAPI + Next.js pattern, so another developer can implement it without novel decisions.

### 1.3 Recommended libraries (chosen here so 5.2 has no open design decisions)

**Backend (Python, new in 5.2):** `fastapi`, `uvicorn[standard]` (ASGI server), `pydantic` v2 (response models), `orjson` (fast JSON). Reuses already-present `pandas` + `pyarrow`. Optional `pydantic-settings` for config.

**Frontend (Node/npm, entirely new to the repo, added in 5.2):**
- `next`, `react`, `react-dom`, `typescript` — framework + types.
- `@tanstack/react-query` — client-side fetching, caching, dedupe, background refetch.
- **`recharts`** — primary charting (declarative, React-native, TypeScript-typed, sufficient for bars/lines/scatter/histograms). *Alternative:* `echarts-for-react` if heavier interactivity is later needed.
- **`maplibre-gl`** + **`react-map-gl`** — open-source vector map (no API token) for the stop map and optional route lines. *Alternative for very large point layers:* `deck.gl`.
- `tailwindcss` + **shadcn/ui** (Radix primitives) — responsive layout and accessible components.
- `zod` — runtime validation of API responses; `openapi-typescript` — generate TS types from the FastAPI OpenAPI schema.
- Testing: `vitest` + `@testing-library/react` (unit), `@playwright/test` (e2e smoke).

> **Nothing is installed in this phase.** Phase 5.2 adds a `dashboard/backend/requirements.txt` (fastapi/uvicorn/pydantic/orjson) and a `dashboard/frontend/package.json` (the npm deps above). **Node.js ≥ 20 becomes a new prerequisite** for the frontend — it is not part of the current Python `.venv` and must be installed by the developer in 5.2, not now.

### 1.4 Repository layout (created in Phase 5.2, not now)

```
public-transit-dashboard/
├── src/                         # Phase 3 & 4 pipeline — UNCHANGED
├── data/                        # UNCHANGED; read-only to the dashboard
│   └── processed/               # parquet + eda_report.json + processing_report.json + eda/*.png
├── PHASE5_DASHBOARD_ARCHITECTURE.md   # this document
└── dashboard/                   # NEW in 5.2
    ├── backend/
    │   ├── app/
    │   │   ├── main.py                 # FastAPI app, CORS, startup data-load
    │   │   ├── core/config.py          # paths reuse ../../src/processing/config.py values
    │   │   ├── services/data_access.py # cached loaders for the 8 parquet + 2 JSON
    │   │   ├── services/reference.py   # authoritative 142-route set + canonicalization
    │   │   ├── services/selftest.py    # startup validation vs reports (§14)
    │   │   ├── models/schemas.py       # Pydantic response models
    │   │   └── api/routers/            # overview, ridership, cjtp, stops, relationships, data_quality, routes, meta
    │   ├── requirements.txt            # fastapi, uvicorn, pydantic, orjson
    │   └── tests/                      # pytest: totals/coverage/no-fabrication
    └── frontend/
        ├── app/(dashboard)/
        │   ├── layout.tsx              # shell: sidebar nav + global filter context
        │   ├── overview/page.tsx
        │   ├── ridership/page.tsx
        │   ├── customer-journey/page.tsx
        │   ├── routes-stops/page.tsx
        │   ├── relationships/page.tsx
        │   └── data-quality/page.tsx
        ├── components/                 # KPI cards, chart wrappers, RouteBullet, filters, map
        ├── lib/api-client.ts           # typed fetch wrapper
        ├── lib/types.ts                # generated from OpenAPI (openapi-typescript)
        ├── package.json
        └── tests/                      # vitest + playwright
```

---

## 2. Dashboard structure (pages, navigation)

Next.js **App Router** with a shared dashboard layout (persistent sidebar + top bar). Each section is its own route (own code-split bundle). Global scope filters live in a client context provider in `layout.tsx` and are reflected in the URL query string (shareable, back-button friendly).

**Route hierarchy**

1. `/overview` — KPI cards + coverage summary + headline insights.
2. `/ridership` — totals, transfers, top/bottom routes, daily, weekday vs weekend, concentration, hour buckets (caveated).
3. `/customer-journey` — overall CJTP, peak/off-peak, trip type, borough, monthly & yearly trend, project-route coverage.
4. `/routes-stops` — stop counts per route, coverage, stop-level map, route detail.
5. `/relationships` — CJTP vs travel time / bus-stop time / customers; Pearson + Spearman; outliers.
6. `/data-quality` — dedicated, prominent; every documented limitation verbatim.

**Navigation:** persistent left sidebar (collapsible to a drawer on mobile) listing the six sections, plus a top bar holding the global **"Project routes only"** toggle and scope filters. Active-route highlighting; deep links carry filter state via query params.

---

## 2b. API design (FastAPI)

Versioned under `/api/v1`. All responses are Pydantic-typed JSON; every field maps to a §0 source. Read-only `GET`s. Filters are query params; **no endpoint mutates any file**.

| Endpoint | Returns | Backed by |
|---|---|---|
| `GET /api/v1/overview` | All KPI scalars + per-dataset coverage summary | `eda_report.analyses.*` totals/coverage |
| `GET /api/v1/ridership/summary` | totals (ridership, transfers, records, routes, dates) | `analyses.ridership.totals` |
| `GET /api/v1/ridership/by-route?order=top\|bottom&limit=N` | ranked routes + share | `ridership_by_route.parquet` |
| `GET /api/v1/ridership/by-date?start=&end=` | daily series | `ridership_by_date.parquet` |
| `GET /api/v1/ridership/by-hour` | 12 bucket totals **+ `caveat` string** | `ridership_by_hour.parquet` + `analyses.ridership.hourly` |
| `GET /api/v1/ridership/weekday-weekend` | weekday/weekend means + day-of-week | `analyses.ridership.daily` |
| `GET /api/v1/ridership/concentration` | CV, top-10/20 share, Lorenz points | `analyses.ridership.by_route.route_level_variation` (+ `ridership_by_route` for the curve) |
| `GET /api/v1/cjtp/overview` | distribution + customer-weighted mean | `analyses.cjtp.overall_distribution` |
| `GET /api/v1/cjtp/by-period` · `/by-trip-type` · `/by-borough` | category splits (weighted) | `analyses.cjtp.by_*` |
| `GET /api/v1/cjtp/by-month` · `/by-year` | trends | `analyses.cjtp.by_month` / `by_year` |
| `GET /api/v1/cjtp/by-route?scope=project\|all&order=&limit=` | ranked route CJTP | `cjtp_by_route.parquet` filtered to the 142 reference when `scope=project` |
| `GET /api/v1/cjtp/coverage` | 120/142 + missing list | `analyses.cjtp.route_coverage` |
| `GET /api/v1/stops/summary` | inventory + stops-per-route stats | `analyses.bus_stops.physical_stop_inventory` / `stops_by_route` |
| `GET /api/v1/stops/by-route` | per-route stop counts | `route_stop_relationships.parquet` |
| `GET /api/v1/stops/points?route=&direction=` | **GeoJSON FeatureCollection of stop points** | `route_stop_relationships.parquet` `latitude/longitude` |
| `GET /api/v1/stops/missing` | 13 routes without stops | `analyses.bus_stops.routes_missing_stop_associations` |
| `GET /api/v1/relationships` | all Pearson/Spearman + n + strength + association note | `analyses.cjtp.relationships`, `analyses.cross_dataset` |
| `GET /api/v1/relationships/scatter?pair=&max=5000` | **server-sampled** points for a scatter | `customer_journey_clean.parquet` (record-level) or route-level frames |
| `GET /api/v1/data-quality` | limitations (verbatim), coverage table, outliers | `eda_report.limitations`, `*.route_coverage`, `*.outliers` |
| `GET /api/v1/routes/reference` | authoritative 142 canonical IDs | `processing_report.route_reference.project_routes` |
| `GET /api/v1/routes/geometry?route=` | **small pre-simplified** route line(s); `404`/`501` if extraction not yet run | derived `dashboard` artifact (§11), never the 2.3 GB file |
| `GET /api/v1/meta/health` · `/meta/validation` | health + self-test results | `services/selftest.py` |

Response conventions: numeric fields carry the report's precision; every coverage response includes `covered`, `total=142`, `pct`, and `missing[]`; every correlation includes `pearson_r`, `spearman_rho`, `n`, `strength`, and the fixed `note: "association only; correlation does not imply causation"`.

---

## 3. Overview page

**KPI cards** (values verified against `eda_report.json`; each card shows its scope caption and links to `/data-quality` when caveated). Served by `GET /api/v1/overview`.

| KPI | Value | Source key | Required caption |
|---|---|---|---|
| Total ridership | **1,207,832** | `analyses.ridership.totals.total_ridership` | "Dev subsample · 2023-01-01 → 2023-02-28" |
| Total transfers | **213,004** | `analyses.ridership.totals.total_transfers` | same subsample |
| Ridership records | **200,000** | `analyses.ridership.totals.record_count` | dev subsample |
| Routes seen in ridership | **140 / 142** (98.59%) | `analyses.ridership.route_coverage` | missing J90, J99 |
| Overall CJTP (customer-weighted) | **69.58%** | `analyses.cjtp.overall_distribution.customer_weighted_mean` | "2017-08 → 2026-06" |
| CJTP project-route coverage | **120 / 142** (84.51%) | `analyses.cjtp.route_coverage` | 22 project routes absent |
| Unique physical stops | **6,281** | `analyses.bus_stops.physical_stop_inventory.unique_physical_stops` | 8,664 associations |
| Stop coverage | **129 / 142** (90.85%) | `analyses.bus_stops.route_coverage` | 13 routes without stops |
| Route geometries | **206,338 features · 142/142 routes** | `analyses.routes.geometry_summary` + `project_route_coverage` | geometry not parsed |
| Routes in all 3 datasets | **119 / 142** (83.80%) | `analyses.cross_dataset.coverage_overlap.in_all_three_datasets` | in all three |

**Summary visualizations:** dataset-coverage bar (ridership 140 / stops 129 / CJTP 120 / geometry 142 vs 142); top-10 routes by ridership mini bar; CJTP monthly trend sparkline; and a headline-insight panel rendering the 5–8 items of §15 (each framed as an association; ridership as a dev subsample).

---

## 4. Ridership Analysis page

**Endpoints:** `/ridership/summary`, `/by-route`, `/by-date`, `/by-hour`, `/weekday-weekend`, `/concentration`. **KPIs:** total 1,207,832 · transfers 213,004 · records 200,000 · routes 140 · dates 59.

**Visualizations**

1. **Top-N routes by total ridership** (bar, default N=10): B6 44,390 (3.675%), B35 33,612, BX19 29,493, B38 29,261, B41 29,007, B1 28,985, B82 26,303, BX12-SBS 26,250, B46-SBS 25,557, B8 25,212. Source: `ridership_by_route.parquet` (`total_ridership`, `share_of_total_ridership_pct`).
2. **Bottom / zero-ridership routes** (table): F1, D99, D90, BX99, BX95, BX92, BX90, B99, B98V, B98. Framed *"not observed in this subsample,"* not "no service."
3. **Daily ridership series** (line, 59 dates): busiest 2023-02-15 (31,720), quietest 2023-01-01 (8,931), mean 20,471.7. Source: `ridership_by_date.parquet`.
4. **Weekday vs weekend** (bar of mean daily): weekday **23,717.05** (42 dates, total 996,116) vs weekend **12,453.88** (17 dates, total 211,716). Source: `analyses.ridership.daily.weekday_vs_weekend`.
5. **By day of week** (bar): Mon 22,545.78 · Tue 24,210.67 · Wed 25,667.38 · Thu 23,891.13 · Fri 22,355.00 · Sat 13,705.88 · Sun 11,341.00. Source: `analyses.ridership.daily.by_day_of_week`.
6. **Route concentration** (Lorenz curve + callouts): top-10 share **24.68%**, top-20 **42.84%**, CV **1.039**. Source: `analyses.ridership.by_route.route_level_variation`.
7. **Ridership by hour bucket** (bar) — **with the mandatory caveat banner below.**

**Filters:** route multiselect (from the 142 reference) · date range (bounded 2023-01-01 … 2023-02-28) · day type · day of week · top-N slider · hour bucket (values 0,2,…,22 only). All applied as API query params; the backend slices cached frames.

> **⚠ MANDATORY LIMITATION — hourly data (preserve verbatim intent).** The ridership extract carries only **12 distinct hour buckets: 0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22** (`analyses.ridership.hourly.observed_hour_buckets`; `diurnal_analysis_supported=false`). The dashboard must **not** present this as a complete 24-hour or diurnal pattern, must **not** interpolate odd hours, and must render the hour chart only alongside a visible caveat (the backend returns the `caveat` string with the data). Odd hours are absent in the data, not zero.

---

## 5. Customer Journey Performance (CJTP) page

**Endpoints:** `/cjtp/overview`, `/by-period`, `/by-trip-type`, `/by-borough`, `/by-month`, `/by-year`, `/by-route`, `/coverage`. **Headline metric is customer-weighted CJTP** (weight = `number_of_customers`). **KPIs:** weighted **69.58%** · unweighted 67.31% · median 69.16% · records 67,943 (1 missing) · coverage **120/142 (84.51%)**.

**Visualizations**

1. **Overall distribution** (histogram/box): mean 67.31, median 69.16, std 13.69, q1 61.21, q3 76.23. Source: `analyses.cjtp.overall_distribution`.
2. **Peak vs Off-Peak** (bar, weighted): Off-Peak **69.72%**, Peak **69.39%**. Source: `analyses.cjtp.by_period`.
3. **By trip type** (bar, weighted): **EXP 58.84%**, LCL/LTD 69.37%, **SBS 73.13%**. Source: `analyses.cjtp.by_trip_type`.
4. **By borough** (bar, weighted): Manhattan **75.24%**, Queens 69.34%, Bronx 68.57%, Staten Island 68.39%, Brooklyn **67.38%**; UNKNOWN (1 record, null — annotate/exclude). Source: `analyses.cjtp.by_borough`.
5. **Monthly trend** (line, weighted): **102 monthly observations** spanning 2017-08 → 2026-06 (calendar span ~107 months; ~5 have no data — do not interpolate gaps). Source: `analyses.cjtp.by_month`.
6. **Yearly trend** (bar/line): 2017–2026. Source: `analyses.cjtp.by_year`.
7. **Top / bottom project routes** (weighted, project-scoped): top BX46 86.54, B42 82.31, B2 82.16, B31 81.21, BX29 81.07; bottom BM2 26.72, BM5 36.74, BXM3 39.15, BXM8 40.15, BM1 41.28. Source: `cjtp_by_route.parquet` filtered to the 142 reference.

**Filters:** route (project-scoped default) · period · trip type · borough · month range (bounded 2017-08 … 2026-06) · year · **"project routes only" toggle (default ON)**.

> **⚠ MANDATORY LIMITATION — CJTP coverage (preserve verbatim).** CJTP covers **120 of 142 project routes = 84.51%**; **22 project routes have no CJTP data** and the CJTP dataset also contains **273 routes outside the project reference** (M/Q/QM/S/SIM/X/T-prefixed). Project-scoped views (`scope=project`) include **only** the 142 reference routes; the 273 out-of-scope routes appear only in an explicitly labeled "full dataset" view. Never rescale coverage toward 100%.

---

## 6. Route & Stop Analysis page

**Endpoints:** `/stops/summary`, `/stops/by-route`, `/stops/points`, `/stops/missing`. **KPIs:** unique stops **6,281** · associations **8,664** · routes with stops **129/142 (90.85%)** · stops-per-route mean 66.98 / median 65.

**Visualizations**

1. **Stops per route** (sorted bar / distribution): highest B6 155, B8 151, B15 143, B82 143, B44 137; lowest B106 6, B39 7, BX95 8, BX92 8, B94 11. Source: `route_stop_relationships.parquet` (`route_unique_stop_count`) / `analyses.bus_stops.stops_by_route`.
2. **Stop-level map** (see §11): points from `latitude`/`longitude` (6,281 stops) served as GeoJSON by `/stops/points`, rendered with MapLibre. Filterable by route/direction. **Zero raw-GeoJSON access.**
3. **Stops by direction** (bar): N 2,387 assoc · S 2,350 · E 1,968 · W 1,959; by `direction_id` 0 → 4,355, 1 → 4,309. Source: `analyses.bus_stops.stops_by_direction` / `stops_by_direction_id`.
4. **Route detail drill-down** (table + map filter): selected route's stops, direction split, and flags (`has_ridership_data`, `has_route_geometry`, `is_project_route`).
5. **Routes missing stop associations** (table of 13): B101, B91, B91A, B92, B98, B98V, BX18, BX90, BX99, D90, D99, F1, J99. Source: `analyses.bus_stops.routes_missing_stop_associations`.

**Filters:** route · direction (N/S/E/W) · direction_id (0/1) · project-only toggle.

> **⚠ MANDATORY LIMITATION — stop coverage (preserve).** Stop associations exist for **129 of 142 routes = 90.85%**; **13 project routes have no stop associations** (listed above). Do not imply every project route has mapped stops.

---

## 7. Relationship Analysis page

**Endpoints:** `/relationships` (coefficients), `/relationships/scatter?pair=` (server-sampled points, ≤5,000). **Every correlation is labeled an association, with n shown and a "correlation does not imply causation" note. p-values are intentionally absent (scipy not installed); n is reported instead.**

**Record-level correlations (n = 67,942):**

| Relationship | Pearson r | Spearman ρ | Strength |
|---|---|---|---|
| CJTP vs additional travel time | **−0.7770** | −0.7806 | very strong (−) |
| CJTP vs additional bus-stop time | **−0.5153** | −0.6415 | strong (−) |
| CJTP vs number of customers | **0.1540** | 0.1379 | weak (+) |

**Route-level correlations (`analyses.cross_dataset`):**

| Relationship | Pearson r | Spearman ρ | n | Strength |
|---|---|---|---|---|
| Ridership vs stop count | **0.5842** | 0.6204 | 128 | strong (+) |
| Ridership vs CJTP | 0.2843 | 0.3141 | 120 | weak (+) |
| Stops vs CJTP | **−0.0062** | −0.0060 | 119 | negligible |
| CJTP vs mean additional travel time | −0.6067 | −0.6502 | 392 | strong (−) |
| CJTP vs mean additional bus-stop time | −0.2187 | −0.6353 | 392 | weak Pearson / strong rank |

**Visualizations:** scatter + fit line per pair (record-level trio via sampled endpoint; route-level via cross-dataset frames), r/ρ/n annotated; a correlation heatmap; and an outlier panel.

**Outliers (Tukey IQR k=1.5, reported not removed):** CJTP 3,145 (4.63%); additional travel time 9,260 (13.63%); additional bus-stop time 4,083 (6.01%); per-route ridership 2 upper (B6, B35); per-record ridership 43,881 (21.94%, an artifact of zero-ridership fare-split rows — annotate, do not "fix"). Source: `analyses.*.outliers`.

**Filters:** relationship/metric selector · project-only toggle · show/hide flagged outliers (visual only — never deletes source rows).

> **⚠ MANDATORY FRAMING.** These are statistical associations only. The strong negative CJTP↔travel-time relationship is the headline pattern, **not** a demonstrated cause. No copy may phrase a correlation as "X causes Y."

---

## 8. Data Quality & Limitations page (dedicated, prominent)

Served by `GET /api/v1/data-quality`, which returns `eda_report.limitations` **verbatim** plus coverage/outlier facts. Contents:

- **Route coverage by dataset** vs 142: geometry 142/142 (100%), ridership 140/142 (98.59%, missing J90/J99), stops 129/142 (90.85%, 13 missing), CJTP 120/142 (84.51%, 22 missing). In **all three** analytic datasets: 119/142 (83.80%). Absent from every dataset beyond geometry: J99.
- **Missing project routes** — explicit per-dataset lists (not summarized away).
- **Missing CJTP value** — 1 of 67,943 records; overall n = 67,942.
- **Outliers** — the six findings above, reported-not-removed.
- **Ridership dev-sample limitation (verbatim intent):** 200,000-row development subsample; **2023-01-01 → 2023-02-28** (59 dates); only **12 even hour buckets (0,2,…,22)**; **no diurnal/24-hour analysis supported**; weekday-vs-weekend **is** supported.
- **Dataset date-range differences:** ridership Jan–Feb 2023; CJTP 2017-08 → 2026-06 — windows do not overlap, so cross-dataset comparisons are structural, not temporal. State explicitly.
- **Coverage differences** — why totals differ across pages (different denominators/routes).
- **Geometry not parsed** — per-feature characteristics `computed=false`; route-line rendering depends on the deferred extraction in §11.
- **Service categories are a naming heuristic** (SBS/Express/Local from route-id patterns), **not** GTFS `route_type`.

Every caveated KPI links here.

---

## 9. Data-source mapping (per visualization)

Exact file/columns and API endpoint for every element. `eda_report.json` keys are verified against the actual report.

> **Canonical JSON paths.** All analytics live under top-level **`analyses`** (`analyses.ridership`, `.cjtp`, `.bus_stops`, `.routes`, `.cross_dataset`). Coverage blocks (`analyses.<ds>.route_coverage`) use `observed_route_count, project_route_count, matching_route_count, coverage_percentage, project_routes_missing_from_dataset, dataset_routes_not_in_project_reference`. Concentration is under `analyses.ridership.by_route.route_level_variation`. Stop inventory is under `analyses.bus_stops.physical_stop_inventory`. The all-three key is `analyses.cross_dataset.coverage_overlap.in_all_three_datasets` (`in_all_three_pct = 83.802817`).

**Overview**

| Element | Endpoint | File | Columns / key |
|---|---|---|---|
| Ridership/transfers/records KPIs | `/overview` | `eda_report.json` | `analyses.ridership.totals.{total_ridership,total_transfers,record_count}` |
| Ridership coverage KPI | `/overview` | `eda_report.json` | `analyses.ridership.route_coverage` |
| Overall CJTP KPI | `/overview` | `eda_report.json` | `analyses.cjtp.overall_distribution.customer_weighted_mean` |
| CJTP coverage KPI | `/overview` | `eda_report.json` | `analyses.cjtp.route_coverage` |
| Stops/coverage KPIs | `/overview` | `eda_report.json` | `analyses.bus_stops.physical_stop_inventory`, `analyses.bus_stops.route_coverage` |
| Geometry KPI | `/overview` | `processing_report.json` + `eda_report.json` | `analyses.routes.geometry_summary`, `analyses.routes.project_route_coverage` |
| All-three coverage KPI | `/overview` | `eda_report.json` | `analyses.cross_dataset.coverage_overlap.in_all_three_datasets` |
| Coverage bar | `/overview` | `eda_report.json` | the four `*.route_coverage` blocks |
| Top-10 mini bar | `/ridership/by-route` | `ridership_by_route.parquet` | `route_id,total_ridership` |
| CJTP monthly sparkline | `/cjtp/by-month` | `eda_report.json` | `analyses.cjtp.by_month[].customer_weighted_cjtp` |

**Ridership**

| Element | Endpoint | File | Columns / key |
|---|---|---|---|
| Top/bottom routes | `/ridership/by-route` | `ridership_by_route.parquet` | `route_id,total_ridership,share_of_total_ridership_pct,mean_daily_ridership` |
| Daily series | `/ridership/by-date` | `ridership_by_date.parquet` | `service_date,total_ridership,day_of_week,is_weekend` |
| Weekday vs weekend / DOW | `/ridership/weekday-weekend` | `eda_report.json` | `analyses.ridership.daily.{weekday_vs_weekend,by_day_of_week}` |
| Concentration/CV | `/ridership/concentration` | `eda_report.json` (+ `ridership_by_route.parquet` for curve) | `analyses.ridership.by_route.route_level_variation` |
| Hour buckets (caveated) | `/ridership/by-hour` | `ridership_by_hour.parquet` | `hour,total_ridership` + `analyses.ridership.hourly.{observed_hour_buckets,caveat}` |

**Customer Journey**

| Element | Endpoint | File | Columns / key |
|---|---|---|---|
| Distribution | `/cjtp/overview` | `eda_report.json` | `analyses.cjtp.overall_distribution` |
| Peak/Off-Peak · Trip type · Borough | `/cjtp/by-period` · `/by-trip-type` · `/by-borough` | `eda_report.json` | `analyses.cjtp.{by_period,by_trip_type,by_borough}` |
| Monthly / yearly | `/cjtp/by-month` · `/by-year` | `eda_report.json` | `analyses.cjtp.{by_month,by_year}` |
| Top/bottom routes | `/cjtp/by-route?scope=project` | `cjtp_by_route.parquet` | `route_id,customer_weighted_cjtp,total_customers` (filtered to 142) |

**Routes & Stops**

| Element | Endpoint | File | Columns / key |
|---|---|---|---|
| Stops per route | `/stops/by-route` | `route_stop_relationships.parquet` | `route_id_canonical,route_unique_stop_count` |
| Stop map | `/stops/points` | `route_stop_relationships.parquet` | `latitude,longitude,stop_name,route_id_canonical,direction` |
| Direction splits | `/stops/summary` | `eda_report.json` | `analyses.bus_stops.{stops_by_direction,stops_by_direction_id}` |
| Missing-stop routes | `/stops/missing` | `eda_report.json` | `analyses.bus_stops.routes_missing_stop_associations` |

**Relationships**

| Element | Endpoint | File | Columns / key |
|---|---|---|---|
| Record-level correlations | `/relationships` | `eda_report.json` | `analyses.cjtp.relationships.*` |
| Scatter points (sampled) | `/relationships/scatter` | `customer_journey_clean.parquet` | `customer_journey_time_performance,additional_travel_time,additional_bus_stop_time,number_of_customers` |
| Route-level correlations | `/relationships` | `eda_report.json` | `analyses.cross_dataset.*` |
| Outliers | `/relationships` · `/data-quality` | `eda_report.json` | `analyses.ridership.outliers.*`, `analyses.cjtp.outliers.*` |

**Data Quality / Reference**

| Element | Endpoint | File | Key |
|---|---|---|---|
| Limitations (verbatim) | `/data-quality` | `eda_report.json` | `limitations[]` |
| Coverage tables | `/data-quality` | `eda_report.json` + `processing_report.json` | `analyses.*.route_coverage`, `route_reference.project_routes` |
| Authoritative 142 | `/routes/reference` | `processing_report.json` | `route_reference.project_routes` |

**Aggregation table schemas (for the developer):**

- `ridership_by_route` (140): `route_id, record_count, total_ridership, mean_ridership_per_record, max_ridership_per_record, distinct_service_dates, first_observed, last_observed, total_transfers, mean_daily_ridership, share_of_total_ridership_pct`
- `ridership_by_date` (59): `service_date, record_count, total_ridership, distinct_routes, total_transfers, day_of_week, is_weekend`
- `ridership_by_hour` (12): `hour, record_count, total_ridership, distinct_routes, distinct_service_dates, total_transfers, mean_ridership_per_date`
- `cjtp_by_route` (393): `route_id, record_count, months_observed, first_month, last_month, total_customers, mean_cjtp_unweighted, median_cjtp, min_cjtp, max_cjtp, customer_weighted_cjtp, peak_record_count, off_peak_record_count, peak_customers, off_peak_customers, peak_customer_weighted_cjtp, off_peak_customer_weighted_cjtp, mean_additional_bus_stop_time, mean_additional_travel_time, trip_types, boroughs, missing_cjtp_values, peak_minus_off_peak_cjtp`
- `route_stop_relationships` (8,664): `route_id_canonical, route_id, route_short_name, route_long_name, route_description, direction_id, direction, stop_id, stop_name, latitude, longitude, is_cbd, bundle, in_effect, has_ridership_data, has_route_geometry, is_project_route, route_unique_stop_count`

---

## 10. Authoritative route reference

Project-route membership (the 142 routes) is read **only** from `processing_report.json → route_reference.project_routes` (canonical spelling, e.g. `B44-SBS`, `BX12-SBS`), exposed by the backend as a cached set (`services/reference.py`) and via `GET /api/v1/routes/reference`. Every "project routes only" filter and every coverage denominator uses it.

**Rules:**
- Never derive membership from a dataset's observed routes (each is a biased subset — 140/129/120).
- Canonicalize incoming ids to this spelling before filtering (21 alias pairs reconciled in Phase 3, e.g. `B44+` → `B44-SBS`); use `route_id_canonical` where provided.
- Coverage denominators are always **142** — never the count of routes that happen to appear in a table. The frontend receives coverage already computed by the backend and does not recompute denominators.

---

## 11. Route GeoJSON strategy (2.3 GB — performance-safe)

**Hard rule: `routes_clean.geojson` (2.3 GB, 206,338 MultiLineString features) is never opened at request time and never sent to the browser.** Only the FastAPI backend ever touches route geometry, and only via small derived artifacts.

**Primary map = stop-level points, zero GeoJSON.** The backend builds a small **GeoJSON FeatureCollection of stop points** from the parquet `latitude`/`longitude` (6,281 stops; 8,664 associations) and serves it via `GET /api/v1/stops/points` (filterable by route/direction). The Next.js client renders it with **MapLibre GL**. Payload is well under ~1 MB. **This fully satisfies the map requirement without touching the GeoJSON.**

**Optional route-line overlay = deferred, offline, one-time pre-simplification (Phase 5.2).** If polylines are wanted:
1. A **one-time offline script** (run once on Windows, outside the app) reads the 2.3 GB file with a **bounded streaming reader** (batched `pyogrio`/`fiona`, batch size already configured as `DEFAULT_GEOJSON_BATCH_SIZE=5000`, or an `ijson` feature stream) — **never** a whole-file load and **never** `pyogrio.read_info()` (which forces a multi-minute full-coordinate scan, per the Phase 3 finding).
2. It keeps **only the 142 project routes**, simplifies geometry (Douglas–Peucker / `shapely.simplify`), and writes a **new small artifact** (target < 5–10 MB), e.g. `data/processed/dashboard/route_lines_simplified.geojson`, or converts to **PMTiles/vector tiles** for tiled delivery.
3. The backend serves only that small file via `GET /api/v1/routes/geometry`; until it exists the endpoint returns `501/404` and the map simply omits the line layer. Per-feature `shape_length`, `vertices`, and bbox already exist in the source **properties**, so route bounding boxes/centroids can be extracted in the same pass without decoding full coordinates.

This pass **reads** the raw file and **writes a new file**; it never modifies, simplifies, or deletes the 2.3 GB source. **It is not executed in Phase 5.1**, and because it would create a processed artifact, it is explicitly a Phase 5.2 step under the same immutability discipline as Phase 3.

---

## 12. Performance strategy

**Backend (FastAPI):**
- **Load once.** On startup, load the 8 small parquet tables + both JSON reports into module-level singletons (`functools.lru_cache` / a `DataStore` object). Tables are tiny (140/59/12/393/8,664 rows); reports ~100 KB — memory is negligible.
- **Cheap slices.** Endpoints return pre-aggregated data or thin filtered slices of cached frames; no re-aggregation of the 200,000/67,943-row cleaned files at request time (record-level files are read only for the sampled scatter, column-pruned).
- **Bounded payloads.** Ranked endpoints take `limit`/`order`; the scatter endpoint returns a **server-side sample (≤5,000 points)** so the browser never receives 67,942 rows.
- **HTTP caching.** `Cache-Control` + `ETag` on every response (data is static between pipeline runs); `orjson` for fast serialization; gzip/brotli compression via the ASGI server/reverse proxy.
- **GeoJSON never at runtime** (§11); the stop-points GeoJSON is generated from cached parquet and cached.

**Frontend (Next.js):**
- **RSC first paint.** Server Components fetch the initial payload for each route so the first render is fast and SEO-safe; Client Components hydrate for interactivity.
- **Per-route code splitting.** Each page is its own bundle; the **map and heavy charts are dynamically imported (`ssr:false` for MapLibre)** so they don't block initial load.
- **TanStack Query** caches API responses client-side, dedupes, and serves cached data instantly on filter/back navigation; stale-while-revalidate keeps it responsive.
- **Static where static.** The `/data-quality` limitations content can be statically generated / ISR-cached (it doesn't change between pipeline runs).
- **Perceived speed.** Skeleton loaders on cards/charts; virtualized long tables; memoized selectors; images (pre-rendered PNGs, if used) via `next/image`.

---

## 13. Responsive UI & design direction

### 13.1 Layout & breakpoints (Tailwind)

- **Desktop (≥1024px):** persistent left sidebar nav + top filter bar; KPI cards in a CSS grid (`repeat(auto-fit, minmax(220px, 1fr))`, ~4–5 across); charts two-up; map + detail table side by side.
- **Tablet (768–1023px):** sidebar collapses to an icon rail or drawer; KPI grid 2–3 across; charts stack to one-up.
- **Mobile (<768px):** sidebar becomes a slide-in drawer (hamburger); single-column stack; full-width map; tables horizontally scrollable. Charts use responsive containers (`ResponsiveContainer`) and drop to top-N defaults for legibility.
- **Quality floor:** visible keyboard focus, `prefers-reduced-motion` respected, semantic landmarks, sufficient contrast (WCAG AA), sticky section header.

### 13.2 Design direction — "Wayfinding" (grounded in the transit subject, not a generic dashboard)

The dashboard reads like a **transit information system**, not a template admin panel:

- **Palette (functional, not decorative):** a cool paper base `#F5F6F7` with near-black ink `#141719` for text; a systemic transit-blue accent `#1B57C4` for interactive/primary; a signal-amber `#E8A400` and signal-red `#C8102E` reserved strictly for performance thresholds (CJTP bands) and missing-data warnings; a neutral rail-gray `#5A6470` for secondary. Categorical encodings (borough, trip type) use a fixed, colorblind-safe scale defined once and reused everywhere so a color always means the same thing.
- **Typography:** **Inter** (UI/body — engineered, high legibility) + **IBM Plex Mono** (route codes, KPI figures, schedule-board feel) + a condensed grotesque such as **Archivo** for section headers (signage lineage). Deliberately *not* the default high-contrast-serif look.
- **Signature element:** a reusable **RouteBullet** chip — the circular/diamond route marker used consistently to identify every route across KPIs, charts, tables, and the map legend. It encodes route family via color and is the one memorable, subject-true device; everything around it stays quiet and systematic.
- **Structure:** hairline dividers and small uppercase eyebrow labels used as *structure* (section identity), not decoration; KPI cards styled like a departure board.
- **Motion (restrained, one orchestrated moment):** a brief count-up on KPI figures at first load and smooth transitions when filters change; skeletons during fetch; nothing gratuitous, reduced-motion honored.

---

## 14. Validation strategy (two-tier)

**Backend (data correctness — the source of truth for numbers):**
- **Startup self-test** (`services/selftest.py`, exposed at `GET /api/v1/meta/validation`, mirrored as `pytest` in `dashboard/backend/tests/`) asserting the API reflects the reports without inflation/fabrication:
  1. Totals match `eda_report.json`: ridership 1,207,832; transfers 213,004; records 200,000; CJTP records 67,943 (n=67,942).
  2. Reconciliation: Σ `ridership_by_route.total_ridership` == totals; by-date and by-hour totals each == 1,207,832.
  3. Coverage not inflated: every denominator == 142; covered == {geometry 142, ridership 140, stops 129, CJTP 120}; all-three == 119; no route set exceeds 142.
  4. Reference integrity: project-route set size == 142, loaded from `processing_report.route_reference.project_routes`.
  5. No fabrication: missing routes/values surfaced as missing (J90/J99; 22 CJTP; 13 stops; 1 CJTP value); hour buckets remain the 12 observed values (never zero-filled/interpolated).
  6. Scope correctness: `scope=project` responses contain only the 142; the 273 out-of-scope CJTP routes never enter project metrics.

**Contract (frontend/back agreement):**
- FastAPI's OpenAPI schema generates the TypeScript types (`openapi-typescript` → `lib/types.ts`); `zod` validates responses at runtime. A CI check regenerates types and fails on drift.

**Frontend (display correctness):**
- No metric is hardcoded in the UI (only labels/captions); all numbers come from the API.
- Filters send query params and **never** mutate cached data (unit test asserts the query cache object is unchanged aside from the new keyed entry).
- Component unit tests (vitest) render API fixtures and assert displayed values equal the fixture.
- A **Playwright e2e smoke test** loads `/overview` and asserts the rendered KPIs equal `GET /api/v1/overview` (and that displayed totals equal the report values).

---

## 15. Capstone presentation — the 5–8 headline insights

Prominent on `/overview`, echoed on their home pages. Each is an **association / observed pattern**, grounded only in Phase 4 findings.

1. **On-time performance is tied most strongly to added travel time.** CJTP vs additional travel time is a **very strong negative association** (Pearson −0.777, Spearman −0.781, n=67,942). *Association, not cause.*
2. **Ridership is highly concentrated.** Top-10 routes = **24.68%**, top-20 = **42.84%** of observed rides; CV **1.04**. **B6** leads (44,390; also a statistical upper outlier).
3. **Weekdays carry ~1.9× weekend ridership.** Mean daily **23,717** vs **12,454**; Wednesday highest, Sunday lowest. *(Weekday/weekend supported; hour-of-day is not.)*
4. **Express/commuter routes lag on CJTP.** Weighted by trip type: **EXP 58.8%** < LCL/LTD 69.4% < **SBS 73.1%**; the ten worst project routes are all BM/BXM/QM express (e.g., **BM2 26.7%**).
5. **Borough gap in CJTP.** Manhattan best (**75.2%**), Brooklyn lowest (**67.4%**), customer-weighted.
6. **More stops, more ridership.** Route-level ridership vs stop count is a **strong positive association** (r=0.584, n=128).
7. **Stop count doesn't explain punctuality.** Stops-per-route vs CJTP is **negligible** (r≈−0.006, n=119).
8. **Coverage is uneven and must be read honestly.** Only **119/142 (83.8%)** project routes appear in all three analytic datasets (CJTP 120, stops 129, ridership 140, geometry 142); ridership is a **Jan–Feb 2023 dev subsample** with 12 hour buckets only.

---

## 16. Final deliverable summary (for Phase 5.2 hand-off)

**Proposed technology.** Three-tier: **Next.js + TypeScript** frontend (App Router, RSC + client components) ↔ **FastAPI** backend (reuses pandas/pyarrow to read the processed files) ↔ **unchanged Phase 3/4 data tier**. Frontend libs: TanStack Query, Recharts (charts), MapLibre GL + react-map-gl (maps), Tailwind + shadcn/ui, zod, openapi-typescript. Backend libs: fastapi, uvicorn, pydantic v2, orjson. **New prerequisite: Node.js ≥ 20.** Nothing installed in this phase.

**Page/section hierarchy.** `/overview` → `/ridership` → `/customer-journey` → `/routes-stops` → `/relationships` → `/data-quality`; shared layout with sidebar nav + top filter bar; filter state in the URL. Backend API under `/api/v1` (§2b).

**Visualization list.** Coverage bar; top-N & zero-ridership route views; daily line; weekday/weekend & day-of-week bars; concentration (Lorenz) curve; hour-bucket bar (caveated); CJTP distribution, peak/off-peak, trip-type, borough, monthly, yearly, top/bottom-route charts; stops-per-route bar; stop-level MapLibre map; direction splits; route detail & missing-stop tables; correlation scatters (record + route level, sampled) + heatmap; outlier panels.

**KPI list.** Total ridership 1,207,832; transfers 213,004; records 200,000; ridership routes 140/142; overall CJTP (weighted) 69.58%; CJTP coverage 120/142; unique stops 6,281; associations 8,664; stop coverage 129/142; geometry 206,338 features / 142 routes; all-three coverage 119/142.

**Filter list.** Global "project routes only" (default ON) + route multiselect; ridership date range (2023-01-01…02-28), day-type, day-of-week, hour bucket, top-N; CJTP period, trip type, borough, month range (2017-08…2026-06), year; stop direction & direction_id; relationship metric selector, outlier show/hide. All are API query params operating on cached copies; none mutate source data.

**Data-source mapping.** Complete per-visualization file + column + **API endpoint** table in §9; aggregation schemas listed; verified `analyses.*` JSON paths; `eda_report.json` / `processing_report.json` are the validation sources.

**Performance strategy.** Backend: load-once singletons, cheap slices, bounded payloads (top-N + ≤5,000-point sampled scatter), ETag/Cache-Control + orjson + gzip, GeoJSON never at runtime. Frontend: RSC first paint, per-route code splitting, dynamic-import map/heavy charts, TanStack Query caching, static/ISR for the limitations page, skeletons + virtualized tables. (§12)

**Validation strategy.** Backend startup self-test + pytest (totals/reconciliation/coverage/reference-integrity/no-fabrication/scope); OpenAPI→TS type contract + zod runtime checks; frontend unit tests + Playwright e2e asserting rendered KPIs equal `/overview` and the reports. (§14)

**Known limitations (preserved verbatim).** Ridership dev subsample, Jan–Feb 2023, **12 hour buckets (0,2,…,22), no diurnal claim**; **CJTP 120/142 = 84.51%** (22 missing, 273 out-of-scope excluded); **stops 129/142 = 90.85%** (13 missing); ridership 140/142; geometry parsed=false; correlations are associations (no p-values, scipy absent); outliers reported not removed; dataset date ranges don't overlap; service categories are a naming heuristic. (§8)

**Implementation order for Phase 5.2.**
1. Scaffold `dashboard/backend` (FastAPI app, CORS, `core/config.py` reusing `src/processing/config.py` paths); add `dashboard/backend/requirements.txt`.
2. Backend `services/data_access.py` — startup loaders for the 8 parquet + 2 JSON reports (cached singletons).
3. Backend `services/reference.py` — authoritative 142-route set + canonicalization; `GET /routes/reference`.
4. Backend `services/selftest.py` + `tests/` — validation vs reports; `GET /meta/validation`.
5. Backend routers: overview → ridership → cjtp → stops → relationships → data-quality; Pydantic response models; ETag/orjson/compression.
6. Generate OpenAPI; scaffold `dashboard/frontend` (Next.js + TS + Tailwind + shadcn/ui); `openapi-typescript` → `lib/types.ts`; `lib/api-client.ts`; TanStack Query provider.
7. Frontend shell: layout, sidebar nav, global filter context (URL-synced), RouteBullet component, KPI card, chart wrappers.
8. Overview page (KPIs + coverage + insights).
9. Ridership page (+ filters + **mandatory hour caveat banner**).
10. Customer Journey page (+ filters + **120/142 coverage banner**).
11. Routes & Stops page (+ MapLibre stop map from `/stops/points` + **129/142 banner**).
12. Relationship Analysis page (correlations + sampled scatter + outliers, association labels).
13. Data Quality & Limitations page (verbatim limitations).
14. *(Optional)* offline bounded-streaming route-line extraction → small simplified GeoJSON/PMTiles; serve via `/routes/geometry`; add the map line layer.
15. Responsive polish + design-direction pass; e2e/unit tests; final number-for-number QA of every displayed value against `eda_report.json` / `processing_report.json`.

---

*End of Phase 5.1 architecture specification (Next.js + TypeScript + FastAPI). No implementation, dataset change, download, install, Node/npm setup, GeoJSON access, or server start was performed in producing this document. Phase 3 and Phase 4 remain unchanged.*
