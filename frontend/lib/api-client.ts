/**
 * Typed client for the Phase 5 FastAPI dashboard endpoints (backend/app/api.py).
 *
 * The backend is read-only over Phase 3/4 processed outputs. Every response
 * carries a `meta` block with `source`, `coverage`, and `limitations` so the
 * UI can surface data provenance instead of fabricating anything the
 * pipeline did not produce.
 */

export type Meta = {
  source: string;
  coverage: unknown;
  limitations: string[];
};

export type Envelope<T> = { data: T; meta: Meta };

export type HealthResponse = { status: string; service: string };

export type DataStatusResponse = {
  status: "ready" | "incomplete";
  required_files: Record<string, boolean>;
};

export type RouteCoverage = {
  observed_route_count: number;
  project_route_count: number;
  matching_route_count: number;
  coverage_percentage: number;
  project_routes_missing_from_dataset: string[];
  dataset_routes_not_in_project_reference: string[];
};

export type OverviewData = {
  total_ridership: number;
  total_transfers: number;
  ridership_record_count: number;
  ridership_route_coverage: RouteCoverage;
  cjtp_weighted_average: number;
  cjtp_route_coverage: RouteCoverage;
  unique_stops: number;
  stop_associations: number;
  stop_route_coverage: RouteCoverage;
  route_geometry_feature_count: number;
  route_coverage: { project_route_count: number; routes_with_geometry: number; coverage_percentage: number; project_routes_missing_geometry: string[] };
  all_dataset_route_coverage: {
    project_route_count: number;
    in_ridership: number;
    in_stops: number;
    in_cjtp: number;
    in_all_three_datasets: number;
    in_all_three_pct: number;
    missing_from_every_dataset: string[];
    missing_from_ridership: string[];
    missing_from_stops: string[];
    missing_from_cjtp: string[];
  };
};

export type DescriptiveStats = {
  name: string;
  count: number;
  missing: number;
  mean: number;
  median: number;
  std: number;
  min: number;
  max: number;
  q1: number;
  q3: number;
  iqr: number;
  range: number;
  skew: number;
  unit?: string;
  record_count?: number;
  customer_weighted_mean?: number;
};

export type RidershipTotals = {
  total_ridership: number;
  total_transfers: number;
  record_count: number;
  distinct_routes_in_ridership?: number;
  distinct_routes?: number;
  distinct_service_dates: number;
  date_range?: { start: string; end: string };
  reconciles_with_by_route?: boolean;
};

export type RidershipByRouteRow = {
  route_id: string;
  record_count: number;
  total_ridership: number;
  mean_ridership_per_record: number;
  max_ridership_per_record: number;
  distinct_service_dates: number;
  first_observed: string;
  last_observed: string;
  total_transfers: number;
  mean_daily_ridership: number;
  share_of_total_ridership_pct: number;
};

export type RidershipByDateRow = {
  service_date: string;
  record_count: number;
  total_ridership: number;
  distinct_routes: number;
  total_transfers: number;
  day_of_week: string;
  is_weekend: boolean;
};

export type RidershipByHourRow = {
  hour: number;
  record_count: number;
  total_ridership: number;
  distinct_routes: number;
  distinct_service_dates?: number;
  total_transfers?: number;
  mean_ridership_per_date?: number;
};

export type CjtpGroupRow = {
  record_count: number;
  customer_weighted_cjtp: number | null;
  [key: string]: string | number | null;
};

export type CjtpOverallDistribution = DescriptiveStats & {
  record_count: number;
  customer_weighted_mean: number;
};

export type CjtpByRouteRow = {
  route_id: string;
  record_count: number;
  months_observed: number;
  first_month: string;
  last_month: string;
  total_customers: number;
  mean_cjtp_unweighted: number;
  median_cjtp: number;
  min_cjtp: number;
  max_cjtp: number;
  customer_weighted_cjtp: number;
  peak_record_count?: number;
  [key: string]: string | number | undefined;
};

export type StopsSummaryData = {
  physical_stop_inventory: {
    unique_physical_stops: number;
    total_route_stop_associations: number;
    note: string;
  };
  by_direction: Array<{ direction: string; associations: number; unique_stops: number; distinct_routes: number }>;
  by_direction_id: Array<{ direction_id: number; associations: number; unique_stops: number }>;
};

export type RouteStopRow = {
  route_id_canonical: string;
  route_id: string;
  route_short_name: string;
  route_long_name: string;
  route_description: string | null;
  direction_id: number | null;
  direction: string;
  stop_id: string;
  stop_name: string;
  latitude: number | null;
  longitude: number | null;
  is_cbd?: boolean;
  [key: string]: string | number | boolean | null | undefined;
};

export type StopPointFeature = {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: { route_id_canonical: string; stop_id: string; stop_name: string; direction: string };
};

export type StopPointsResponse = { type: "FeatureCollection"; features: StopPointFeature[]; meta: Meta };

export type RoutesSummaryData = {
  geometry_summary: {
    feature_count: number;
    unique_route_id_values: number;
    unique_route_short_name_values: number;
    geometry_type: string;
    output_size_gb: number;
    geometry_parsed: boolean;
  };
  project_route_coverage: {
    project_route_count: number;
    routes_with_geometry: number;
    coverage_percentage: number;
    project_routes_missing_geometry: string[];
  };
  service_categories: {
    basis: string;
    by_service_type: Array<{ category: string; route_count: number }>;
    by_borough_prefix: Array<{ borough: string; route_count: number }>;
  };
};

export type CorrelationPair = {
  x: string;
  y: string;
  n: number;
  pearson_r: number | null;
  spearman_rho: number | null;
  pearson_p_value: number | null;
  spearman_p_value: number | null;
  strength: string;
  note: string;
  p_value_note: string;
};

export type RelationshipsSummaryData = {
  record_level: Record<string, CorrelationPair>;
  route_level: Record<string, CorrelationPair>;
};

export type DataQualityData = {
  phase3: { status: string; validation: unknown };
  phase4: { status: string; validation: unknown };
  row_counts: Record<string, number | undefined>;
  route_coverage: Record<string, RouteCoverage>;
  missing_values: Record<string, Record<string, number>>;
  warnings: Array<{ scope: string; message: string }>;
  limitations: unknown;
  reports: {
    processing: { phase: string; started_utc: string; finished_utc: string };
    eda: { phase: string; started_utc: string; finished_utc: string };
  };
};

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export function isApiConfigured(): boolean {
  return apiBaseUrl.length > 0;
}

function toQuery(params?: Record<string, string | number | boolean | null | undefined>): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

async function get<T>(path: string, params?: Record<string, string | number | boolean | null | undefined>): Promise<T> {
  if (!apiBaseUrl) {
    throw new ApiError("NEXT_PUBLIC_API_BASE_URL is not configured");
  }
  // Requests are routed through the Next.js same-origin proxy (/api/proxy)
  // rather than fetched directly from the browser, because the FastAPI
  // backend does not send Access-Control-Allow-Origin and a direct
  // cross-origin fetch is blocked by the browser's CORS enforcement. The
  // proxy forwards the exact same path/query server-side; no request or
  // response data is altered.
  const proxiedPath = `/api/proxy${path}`;
  let response: Response;
  try {
    response = await fetch(`${proxiedPath}${toQuery(params)}`, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError("Unable to reach the transit dashboard API");
  }
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : "";
    } catch {
      // ignore body parse errors
    }
    throw new ApiError(detail || `API request failed: ${response.status}`, response.status);
  }
  return response.json() as Promise<T>;
}

export const apiClient = {
  health: () => get<HealthResponse>("/api/v1/health"),
  dataStatus: () => get<DataStatusResponse>("/api/v1/data/status"),

  overview: () => get<Envelope<OverviewData>>("/api/v1/overview"),

  ridershipSummary: (params?: { route?: string; start_date?: string; end_date?: string }) =>
    get<Envelope<RidershipTotals>>("/api/v1/ridership/summary", params),
  ridershipRoutes: (params?: { route?: string }) => get<Envelope<RidershipByRouteRow[]>>("/api/v1/ridership/routes", params),
  ridershipDaily: (params?: { route?: string; start_date?: string; end_date?: string; day_type?: "weekday" | "weekend"; day_of_week?: string }) =>
    get<Envelope<RidershipByDateRow[]>>("/api/v1/ridership/daily", params),
  ridershipHourly: (params?: { route?: string; hour?: number }) => get<Envelope<RidershipByHourRow[]>>("/api/v1/ridership/hourly", params),

  cjtpSummary: (params?: { route?: string }) => get<Envelope<CjtpOverallDistribution | CjtpGroupRow[]>>("/api/v1/cjtp/summary", params),
  cjtpMonthly: (params?: { route?: string; start_month?: string; end_month?: string }) =>
    get<Envelope<CjtpGroupRow[]>>("/api/v1/cjtp/monthly", params),
  cjtpYearly: (params?: { route?: string; year?: number }) => get<Envelope<CjtpGroupRow[]>>("/api/v1/cjtp/yearly", params),
  cjtpRoutes: (params?: { route?: string }) => get<Envelope<CjtpByRouteRow[]>>("/api/v1/cjtp/routes", params),
  cjtpByPeriod: (params?: { route?: string; period?: string }) => get<Envelope<CjtpGroupRow[]>>("/api/v1/cjtp/by-period", params),
  cjtpByTripType: (params?: { route?: string; trip_type?: string }) => get<Envelope<CjtpGroupRow[]>>("/api/v1/cjtp/by-trip-type", params),
  cjtpByBorough: (params?: { route?: string; borough?: string }) => get<Envelope<CjtpGroupRow[]>>("/api/v1/cjtp/by-borough", params),

  stopsSummary: () => get<Envelope<StopsSummaryData>>("/api/v1/stops/summary"),
  stopsRoutes: (params?: { route?: string }) => get<Envelope<RouteStopRow[]>>("/api/v1/stops/routes", params),
  stopsPoints: (params?: { route?: string; direction?: "N" | "S" | "E" | "W" }) => get<StopPointsResponse>("/api/v1/stops/points", params),

  routesSummary: () => get<Envelope<RoutesSummaryData>>("/api/v1/routes/summary"),

  relationshipsSummary: () => get<Envelope<RelationshipsSummaryData>>("/api/v1/relationships/summary"),
  relationshipsCorrelation: (params?: { pair?: string }) => get<Envelope<Record<string, CorrelationPair>>>("/api/v1/relationships/correlation", params),

  dataQuality: () => get<Envelope<DataQualityData>>("/api/v1/data/quality"),
};
