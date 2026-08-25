"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient, isApiConfigured } from "@/lib/api-client";

/**
 * Every hook here is disabled when NEXT_PUBLIC_API_BASE_URL isn't set, so
 * pages can render a consistent "API unavailable" state instead of throwing
 * on mount.
 */

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: apiClient.health, enabled: isApiConfigured() });
}

export function useDataStatus() {
  return useQuery({ queryKey: ["data-status"], queryFn: apiClient.dataStatus, enabled: isApiConfigured() });
}

export function useOverview() {
  return useQuery({ queryKey: ["overview"], queryFn: apiClient.overview, enabled: isApiConfigured() });
}

export function useRidershipSummary(params?: { route?: string; start_date?: string; end_date?: string }) {
  return useQuery({
    queryKey: ["ridership-summary", params],
    queryFn: () => apiClient.ridershipSummary(params),
    enabled: isApiConfigured(),
  });
}

export function useRidershipRoutes(params?: { route?: string }) {
  return useQuery({
    queryKey: ["ridership-routes", params],
    queryFn: () => apiClient.ridershipRoutes(params),
    enabled: isApiConfigured(),
  });
}

export function useRidershipDaily(params?: { route?: string; start_date?: string; end_date?: string; day_type?: "weekday" | "weekend"; day_of_week?: string }) {
  return useQuery({
    queryKey: ["ridership-daily", params],
    queryFn: () => apiClient.ridershipDaily(params),
    enabled: isApiConfigured(),
  });
}

export function useRidershipHourly(params?: { route?: string; hour?: number }) {
  return useQuery({
    queryKey: ["ridership-hourly", params],
    queryFn: () => apiClient.ridershipHourly(params),
    enabled: isApiConfigured(),
  });
}

export function useCjtpSummary(params?: { route?: string }) {
  return useQuery({ queryKey: ["cjtp-summary", params], queryFn: () => apiClient.cjtpSummary(params), enabled: isApiConfigured() });
}

export function useCjtpMonthly(params?: { route?: string; start_month?: string; end_month?: string }) {
  return useQuery({ queryKey: ["cjtp-monthly", params], queryFn: () => apiClient.cjtpMonthly(params), enabled: isApiConfigured() });
}

export function useCjtpYearly(params?: { route?: string; year?: number }) {
  return useQuery({ queryKey: ["cjtp-yearly", params], queryFn: () => apiClient.cjtpYearly(params), enabled: isApiConfigured() });
}

export function useCjtpRoutes(params?: { route?: string }) {
  return useQuery({ queryKey: ["cjtp-routes", params], queryFn: () => apiClient.cjtpRoutes(params), enabled: isApiConfigured() });
}

export function useCjtpByPeriod(params?: { route?: string; period?: string }) {
  return useQuery({ queryKey: ["cjtp-by-period", params], queryFn: () => apiClient.cjtpByPeriod(params), enabled: isApiConfigured() });
}

export function useCjtpByTripType(params?: { route?: string; trip_type?: string }) {
  return useQuery({ queryKey: ["cjtp-by-trip-type", params], queryFn: () => apiClient.cjtpByTripType(params), enabled: isApiConfigured() });
}

export function useCjtpByBorough(params?: { route?: string; borough?: string }) {
  return useQuery({ queryKey: ["cjtp-by-borough", params], queryFn: () => apiClient.cjtpByBorough(params), enabled: isApiConfigured() });
}

export function useStopsSummary() {
  return useQuery({ queryKey: ["stops-summary"], queryFn: apiClient.stopsSummary, enabled: isApiConfigured() });
}

export function useStopsRoutes(params?: { route?: string }) {
  return useQuery({ queryKey: ["stops-routes", params], queryFn: () => apiClient.stopsRoutes(params), enabled: isApiConfigured() });
}

export function useStopsPoints(params?: { route?: string; direction?: "N" | "S" | "E" | "W" }) {
  return useQuery({ queryKey: ["stops-points", params], queryFn: () => apiClient.stopsPoints(params), enabled: isApiConfigured() });
}

export function useRoutesSummary() {
  return useQuery({ queryKey: ["routes-summary"], queryFn: apiClient.routesSummary, enabled: isApiConfigured() });
}

export function useRelationshipsSummary() {
  return useQuery({ queryKey: ["relationships-summary"], queryFn: apiClient.relationshipsSummary, enabled: isApiConfigured() });
}

export function useDataQuality() {
  return useQuery({ queryKey: ["data-quality"], queryFn: apiClient.dataQuality, enabled: isApiConfigured() });
}

/** Union of route IDs actually observed across the ridership, CJTP, and stop-association endpoints. */
export function useKnownRoutes() {
  const ridership = useRidershipRoutes();
  const cjtp = useCjtpRoutes();
  const stops = useStopsRoutes();

  const routes = new Set<string>();
  ridership.data?.data.forEach((row) => routes.add(row.route_id));
  cjtp.data?.data.forEach((row) => routes.add(row.route_id));
  stops.data?.data.forEach((row) => routes.add(row.route_id_canonical));

  return {
    routes: Array.from(routes).sort(),
    isLoading: ridership.isLoading || cjtp.isLoading || stops.isLoading,
  };
}
