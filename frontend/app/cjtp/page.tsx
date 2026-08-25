"use client";

import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { PageHeader, Section } from "@/components/dashboard/page-header";
import { ApiState } from "@/components/dashboard/api-state";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { CoverageNote } from "@/components/dashboard/coverage-note";
import { RouteSelect } from "@/components/dashboard/route-select";
import { DataTable, type Column } from "@/components/dashboard/data-table";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { useCjtpByBorough, useCjtpByPeriod, useCjtpByTripType, useCjtpMonthly, useCjtpRoutes, useCjtpSummary } from "@/lib/queries";
import { formatInt, formatPercent } from "@/lib/format";
import type { CjtpByRouteRow, CjtpOverallDistribution } from "@/lib/api-client";

const monthlyChartConfig: ChartConfig = { customer_weighted_cjtp: { label: "Customer-weighted CJTP", color: "var(--chart-1)" } };
const groupChartConfig: ChartConfig = { customer_weighted_cjtp: { label: "Customer-weighted CJTP", color: "var(--chart-2)" } };

const routeColumns: Column<CjtpByRouteRow>[] = [
  { header: "Route", render: (row) => <span className="route-chip">{row.route_id}</span> },
  { header: "Customer-weighted CJTP", align: "right", render: (row) => formatPercent(row.customer_weighted_cjtp) },
  { header: "Median CJTP", align: "right", render: (row) => formatPercent(row.median_cjtp) },
  { header: "Months observed", align: "right", render: (row) => formatInt(row.months_observed) },
  { header: "Records", align: "right", render: (row) => formatInt(row.record_count) },
];

function isOverallDistribution(value: unknown): value is CjtpOverallDistribution {
  return typeof value === "object" && value !== null && "customer_weighted_mean" in value;
}

export default function CjtpPage() {
  const [route, setRoute] = useState<string | null>(null);

  const summary = useCjtpSummary({ route: route ?? undefined });
  const monthly = useCjtpMonthly({ route: route ?? undefined });
  const byPeriod = useCjtpByPeriod({ route: route ?? undefined });
  const byTripType = useCjtpByTripType({ route: route ?? undefined });
  const byBorough = useCjtpByBorough({ route: route ?? undefined });
  const routes = useCjtpRoutes({ route: route ?? undefined });

  const overall = summary.data && isOverallDistribution(summary.data.data) ? summary.data.data : null;

  const topRoutes = useMemo(
    () => [...(routes.data?.data ?? [])].sort((a, b) => b.customer_weighted_cjtp - a.customer_weighted_cjtp).slice(0, 12),
    [routes.data],
  );

  const monthlyRows = monthly.data?.data ?? [];

  return (
    <div className="flex flex-col gap-10">
      <PageHeader
        eyebrow="Customer journey time performance"
        title="CJTP"
        description="Customer journey time performance (0–100%, higher = more on-time). Covers 120 of 142 project routes — routes without CJTP data show no fabricated metric."
        actions={<RouteSelect value={route} onChange={setRoute} />}
      />

      <Section>
        <ApiState isLoading={summary.isLoading} error={summary.error} skeletonHeight="h-32">
          {overall ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <KpiCard accent="accent" label="Customer-weighted mean" value={formatPercent(overall.customer_weighted_mean)} />
              <KpiCard label="Unweighted mean" value={formatPercent(overall.mean)} />
              <KpiCard label="Median" value={formatPercent(overall.median)} />
              <KpiCard label="Records" value={formatInt(overall.record_count)} detail={overall.missing ? `${overall.missing} missing value(s) excluded, not imputed` : undefined} />
            </div>
          ) : !summary.isLoading ? (
            <p className="text-sm text-muted-foreground">Route-scoped summary is grouped by year — see the monthly trend below.</p>
          ) : null}
        </ApiState>
      </Section>

      <Section title="Monthly trend" description={route ? `Route ${route} only` : "All routes with CJTP coverage, by calendar month"}>
        <ApiState isLoading={monthly.isLoading} error={monthly.error} isEmpty={monthlyRows.length === 0}>
          <ChartContainer config={monthlyChartConfig} className="aspect-auto h-72 w-full">
            <LineChart data={monthlyRows} margin={{ left: 8, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="month" tickLine={false} axisLine={false} minTickGap={24} />
              <YAxis domain={[0, 100]} tickFormatter={(value) => `${value}%`} tickLine={false} axisLine={false} width={44} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Line dataKey="customer_weighted_cjtp" name="Customer-weighted CJTP" type="monotone" stroke="var(--color-customer_weighted_cjtp)" strokeWidth={2} dot={false} />
            </LineChart>
          </ChartContainer>
        </ApiState>
      </Section>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <Section title="By trip period" description="Peak vs. off-peak">
          <ApiState isLoading={byPeriod.isLoading} error={byPeriod.error} isEmpty={(byPeriod.data?.data.length ?? 0) === 0} skeletonHeight="h-56">
            <ChartContainer config={groupChartConfig} className="aspect-auto h-56 w-full">
              <BarChart data={byPeriod.data?.data ?? []} margin={{ left: 8, right: 8 }}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="period" tickLine={false} axisLine={false} />
                <YAxis domain={[0, 100]} tickFormatter={(value) => `${value}%`} tickLine={false} axisLine={false} width={40} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="customer_weighted_cjtp" name="Customer-weighted CJTP" fill="var(--color-customer_weighted_cjtp)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ChartContainer>
          </ApiState>
        </Section>

        <Section title="By trip type" description="Local vs. express">
          <ApiState isLoading={byTripType.isLoading} error={byTripType.error} isEmpty={(byTripType.data?.data.length ?? 0) === 0} skeletonHeight="h-56">
            <ChartContainer config={groupChartConfig} className="aspect-auto h-56 w-full">
              <BarChart data={byTripType.data?.data ?? []} margin={{ left: 8, right: 8 }}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="trip_type" tickLine={false} axisLine={false} />
                <YAxis domain={[0, 100]} tickFormatter={(value) => `${value}%`} tickLine={false} axisLine={false} width={40} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="customer_weighted_cjtp" name="Customer-weighted CJTP" fill="var(--color-customer_weighted_cjtp)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ChartContainer>
          </ApiState>
        </Section>

        <Section title="By borough" description="Includes an 'UNKNOWN' category — reported, not dropped">
          <ApiState isLoading={byBorough.isLoading} error={byBorough.error} isEmpty={(byBorough.data?.data.length ?? 0) === 0} skeletonHeight="h-56">
            <ChartContainer config={groupChartConfig} className="aspect-auto h-56 w-full">
              <BarChart data={byBorough.data?.data ?? []} margin={{ left: 8, right: 8 }}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="borough" tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 100]} tickFormatter={(value) => `${value}%`} tickLine={false} axisLine={false} width={40} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="customer_weighted_cjtp" name="Customer-weighted CJTP" fill="var(--color-customer_weighted_cjtp)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ChartContainer>
          </ApiState>
        </Section>
      </div>

      <Section title="Top performing routes" description="Ranked by customer-weighted CJTP, among project routes with CJTP coverage">
        <ApiState isLoading={routes.isLoading} error={routes.error} isEmpty={topRoutes.length === 0}>
          <DataTable columns={routeColumns} rows={topRoutes} getKey={(row) => row.route_id} />
        </ApiState>
      </Section>

      {summary.data ? <CoverageNote source={summary.data.meta.source} limitations={summary.data.meta.limitations} /> : null}
    </div>
  );
}
