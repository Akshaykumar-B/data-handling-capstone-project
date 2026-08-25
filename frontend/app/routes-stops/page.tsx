"use client";

import { useMemo, useState } from "react";
import { PageHeader, Section } from "@/components/dashboard/page-header";
import { RouteSelect } from "@/components/dashboard/route-select";
import { ApiState } from "@/components/dashboard/api-state";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { CoverageNote } from "@/components/dashboard/coverage-note";
import { CoverageBar } from "@/components/dashboard/coverage-bar";
import { DataTable } from "@/components/dashboard/data-table";
import { StopMap } from "@/components/dashboard/stop-map";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatInt } from "@/lib/format";
import { useRoutesSummary, useStopsSummary, useStopsRoutes, useStopsPoints } from "@/lib/queries";

export default function RoutesStopsPage() {
  const [route, setRoute] = useState<string | null>(null);

  const routesSummary = useRoutesSummary();
  const stopsSummary = useStopsSummary();
  const stopsRoutes = useStopsRoutes(route ? { route } : undefined);
  const stopsPoints = useStopsPoints(route ? { route } : undefined);

  const stopRows = useMemo(() => stopsRoutes.data?.data ?? [], [stopsRoutes.data]);
  const serviceCategories = routesSummary.data?.data.service_categories;
  const projectCoverage = routesSummary.data?.data.project_route_coverage;

  return (
    <div className="flex flex-col gap-10">
      <PageHeader
        eyebrow="Routes & stops"
        title="Route geometry and stop associations"
        description="Physical stop inventory, direction breakdowns, and route-stop associations from the Phase 4 processed outputs. No route-line overlay is drawn on the map since the backend does not expose parsed route geometry."
        actions={<RouteSelect value={route} onChange={setRoute} />}
      />

      <Section title="Route coverage against the project reference list">
        <ApiState isLoading={routesSummary.isLoading} error={routesSummary.error} skeletonHeight="h-40">
          {projectCoverage ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <CoverageBar
                label="Routes with parsed geometry"
                matching={projectCoverage.routes_with_geometry}
                total={projectCoverage.project_route_count}
                percentage={projectCoverage.coverage_percentage}
                missing={projectCoverage.project_routes_missing_geometry}
              />
              <Card className="gap-3 py-5">
                <CardHeader className="gap-1 px-5">
                  <CardTitle className="text-sm font-medium">Geometry feature summary</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-1 px-5 text-sm text-muted-foreground">
                  <p>
                    {formatInt(routesSummary.data?.data.geometry_summary.feature_count)} geometry features &middot;{" "}
                    {routesSummary.data?.data.geometry_summary.unique_route_id_values} unique route IDs
                  </p>
                  <p>Geometry type: {routesSummary.data?.data.geometry_summary.geometry_type}</p>
                </CardContent>
              </Card>
            </div>
          ) : null}
        </ApiState>
      </Section>

      {serviceCategories ? (
        <Section title="Service categories" description="Route counts grouped by service type and borough prefix.">
          <div className="grid gap-4 sm:grid-cols-2">
            <Card className="py-5">
              <CardHeader className="px-5">
                <CardTitle className="text-sm font-medium">By service type</CardTitle>
              </CardHeader>
              <CardContent className="px-5">
                <DataTable
                  columns={[
                    { header: "Category", render: (r: { category: string; route_count: number }) => r.category },
                    { header: "Routes", align: "right", render: (r) => formatInt(r.route_count) },
                  ]}
                  rows={serviceCategories.by_service_type}
                  getKey={(r) => r.category}
                />
              </CardContent>
            </Card>
            <Card className="py-5">
              <CardHeader className="px-5">
                <CardTitle className="text-sm font-medium">By borough prefix</CardTitle>
              </CardHeader>
              <CardContent className="px-5">
                <DataTable
                  columns={[
                    { header: "Borough", render: (r: { borough: string; route_count: number }) => r.borough },
                    { header: "Routes", align: "right", render: (r) => formatInt(r.route_count) },
                  ]}
                  rows={serviceCategories.by_borough_prefix}
                  getKey={(r) => r.borough}
                />
              </CardContent>
            </Card>
          </div>
        </Section>
      ) : null}

      <Section title="Physical stop inventory">
        <ApiState isLoading={stopsSummary.isLoading} error={stopsSummary.error} skeletonHeight="h-32">
          {stopsSummary.data ? (
            <div className="grid gap-4 sm:grid-cols-3">
              <KpiCard
                label="Unique physical stops"
                value={formatInt(stopsSummary.data.data.physical_stop_inventory.unique_physical_stops)}
                accent="primary"
              />
              <KpiCard
                label="Route-stop associations"
                value={formatInt(stopsSummary.data.data.physical_stop_inventory.total_route_stop_associations)}
              />
              <KpiCard
                label="Directions observed"
                value={formatInt(stopsSummary.data.data.by_direction.length)}
                detail={stopsSummary.data.data.physical_stop_inventory.note}
              />
            </div>
          ) : null}
        </ApiState>
        {stopsSummary.data ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Card className="py-5">
              <CardHeader className="px-5">
                <CardTitle className="text-sm font-medium">By direction</CardTitle>
              </CardHeader>
              <CardContent className="px-5">
                <DataTable
                  columns={[
                    { header: "Direction", render: (r: { direction: string }) => r.direction },
                    { header: "Associations", align: "right", render: (r) => formatInt(r.associations) },
                    { header: "Unique stops", align: "right", render: (r) => formatInt(r.unique_stops) },
                    { header: "Routes", align: "right", render: (r) => formatInt(r.distinct_routes) },
                  ]}
                  rows={stopsSummary.data.data.by_direction}
                  getKey={(r) => r.direction}
                />
              </CardContent>
            </Card>
            <Card className="py-5">
              <CardHeader className="px-5">
                <CardTitle className="text-sm font-medium">By direction ID</CardTitle>
              </CardHeader>
              <CardContent className="px-5">
                <DataTable
                  columns={[
                    { header: "Direction ID", render: (r: { direction_id: number }) => String(r.direction_id) },
                    { header: "Associations", align: "right", render: (r) => formatInt(r.associations) },
                    { header: "Unique stops", align: "right", render: (r) => formatInt(r.unique_stops) },
                  ]}
                  rows={stopsSummary.data.data.by_direction_id}
                  getKey={(r) => String(r.direction_id)}
                />
              </CardContent>
            </Card>
          </div>
        ) : null}
        {stopsSummary.data ? <CoverageNote source={stopsSummary.data.meta.source} limitations={stopsSummary.data.meta.limitations} /> : null}
      </Section>

      <Section title="Stop map" description={route ? `Stops served by route ${route}.` : "All observed stop points."}>
        <ApiState isLoading={stopsPoints.isLoading} error={stopsPoints.error} isEmpty={(stopsPoints.data?.features.length ?? 0) === 0} skeletonHeight="h-[420px]">
          {stopsPoints.data ? <StopMap features={stopsPoints.data.features} /> : null}
        </ApiState>
        {stopsPoints.data ? <CoverageNote source={stopsPoints.data.meta.source} limitations={stopsPoints.data.meta.limitations} /> : null}
      </Section>

      <Section title="Route-stop associations" description={route ? `Stops for route ${route}.` : "Showing all routes — pick a route above to filter."}>
        <ApiState isLoading={stopsRoutes.isLoading} error={stopsRoutes.error} isEmpty={stopRows.length === 0} skeletonHeight="h-64">
          <DataTable
            columns={[
              { header: "Route", render: (r) => <span className="route-chip">{r.route_id_canonical}</span> },
              { header: "Direction", render: (r) => r.direction },
              { header: "Stop ID", render: (r) => r.stop_id },
              { header: "Stop name", render: (r) => r.stop_name },
              { header: "Lat", align: "right", render: (r) => (r.latitude != null ? r.latitude.toFixed(4) : "—") },
              { header: "Lon", align: "right", render: (r) => (r.longitude != null ? r.longitude.toFixed(4) : "—") },
            ]}
            rows={stopRows.slice(0, 200)}
            getKey={(r, i) => `${r.route_id_canonical}-${r.stop_id}-${r.direction}-${i}`}
          />
        </ApiState>
        {stopRows.length > 200 ? (
          <p className="text-xs text-muted-foreground">Showing the first 200 of {formatInt(stopRows.length)} associations returned by the API.</p>
        ) : null}
        {stopsRoutes.data ? <CoverageNote source={stopsRoutes.data.meta.source} limitations={stopsRoutes.data.meta.limitations} /> : null}
      </Section>
    </div>
  );
}
