"use client";

import { useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { PageHeader, Section } from "@/components/dashboard/page-header";
import { ApiState } from "@/components/dashboard/api-state";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { CoverageNote } from "@/components/dashboard/coverage-note";
import { RouteSelect } from "@/components/dashboard/route-select";
import { DataTable, type Column } from "@/components/dashboard/data-table";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { useRidershipDaily, useRidershipHourly, useRidershipRoutes, useRidershipSummary } from "@/lib/queries";
import { byDayOfWeek, weekdayVsWeekend } from "@/lib/analytics";
import { formatCompact, formatDate, formatInt, formatPercent } from "@/lib/format";
import type { RidershipByRouteRow } from "@/lib/api-client";

const dailyChartConfig: ChartConfig = { totalRidership: { label: "Total ridership", color: "var(--chart-1)" } };
const weekdayChartConfig: ChartConfig = { totalRidership: { label: "Total ridership", color: "var(--chart-2)" } };
const hourlyChartConfig: ChartConfig = { totalRidership: { label: "Total ridership", color: "var(--chart-1)" } };

const routeColumns: Column<RidershipByRouteRow>[] = [
  { header: "Route", render: (row) => <span className="route-chip">{row.route_id}</span> },
  { header: "Total ridership", align: "right", render: (row) => formatCompact(row.total_ridership) },
  { header: "Share of total", align: "right", render: (row) => formatPercent(row.share_of_total_ridership_pct) },
  { header: "Mean daily", align: "right", render: (row) => formatInt(row.mean_daily_ridership) },
  { header: "Records", align: "right", render: (row) => formatInt(row.record_count) },
];

export default function RidershipPage() {
  const [route, setRoute] = useState<string | null>(null);

  const summary = useRidershipSummary({ route: route ?? undefined });
  const daily = useRidershipDaily({ route: route ?? undefined });
  const hourly = useRidershipHourly({ route: route ?? undefined });
  const routes = useRidershipRoutes({ route: route ?? undefined });

  const dailyRows = daily.data?.data ?? [];
  const weekdayWeekend = useMemo(() => weekdayVsWeekend(dailyRows), [dailyRows]);
  const dayOfWeek = useMemo(() => byDayOfWeek(dailyRows), [dailyRows]);

  const topRoutes = useMemo(() => [...(routes.data?.data ?? [])].sort((a, b) => b.total_ridership - a.total_ridership).slice(0, 12), [routes.data]);

  return (
    <div className="flex flex-col gap-10">
      <PageHeader
        eyebrow="Ridership"
        title="Ridership"
        description="Fare-tap ridership and transfers from the development subsample: 200,000 records across 59 service dates (Jan 1 – Feb 28, 2023)."
        actions={<RouteSelect value={route} onChange={setRoute} />}
      />

      <Section>
        <ApiState isLoading={summary.isLoading} error={summary.error} skeletonHeight="h-32">
          {summary.data ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <KpiCard accent="primary" label="Total ridership" value={formatCompact(summary.data.data.total_ridership)} />
              <KpiCard accent="primary" label="Total transfers" value={formatCompact(summary.data.data.total_transfers)} />
              <KpiCard label="Records" value={formatInt(summary.data.data.record_count)} />
              <KpiCard label="Distinct service dates" value={formatInt(summary.data.data.distinct_service_dates)} />
            </div>
          ) : null}
        </ApiState>
      </Section>

      <Section title="Daily ridership trend" description={route ? `Route ${route} only` : "All project routes, aggregated by service date"}>
        <ApiState isLoading={daily.isLoading} error={daily.error} isEmpty={dailyRows.length === 0}>
          <ChartContainer config={dailyChartConfig} className="aspect-auto h-72 w-full">
            <AreaChart data={dailyRows} margin={{ left: 8, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="service_date" tickFormatter={(value) => formatDate(value)} tickLine={false} axisLine={false} minTickGap={32} />
              <YAxis tickFormatter={(value) => formatCompact(value)} tickLine={false} axisLine={false} width={48} />
              <ChartTooltip content={<ChartTooltipContent labelFormatter={(value) => formatDate(String(value))} />} />
              <Area dataKey="total_ridership" type="monotone" fill="var(--color-totalRidership)" fillOpacity={0.18} stroke="var(--color-totalRidership)" strokeWidth={2} />
            </AreaChart>
          </ChartContainer>
        </ApiState>
      </Section>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        <Section title="Weekday vs. weekend" description="Derived client-side from /ridership/daily — no dedicated endpoint exists.">
          <ApiState isLoading={daily.isLoading} error={daily.error} isEmpty={weekdayWeekend.every((point) => point.distinctDates === 0)} skeletonHeight="h-56">
            <ChartContainer config={weekdayChartConfig} className="aspect-auto h-56 w-full">
              <BarChart data={weekdayWeekend} margin={{ left: 8, right: 8 }}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="dayType" tickLine={false} axisLine={false} />
                <YAxis tickFormatter={(value) => formatCompact(value)} tickLine={false} axisLine={false} width={48} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="meanDailyRidership" name="Mean daily ridership" fill="var(--color-totalRidership)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ChartContainer>
          </ApiState>
        </Section>

        <Section title="By day of week" description="Mean daily ridership per weekday, derived client-side.">
          <ApiState isLoading={daily.isLoading} error={daily.error} isEmpty={dayOfWeek.length === 0} skeletonHeight="h-56">
            <ChartContainer config={weekdayChartConfig} className="aspect-auto h-56 w-full">
              <BarChart data={dayOfWeek} margin={{ left: 8, right: 8 }}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="dayOfWeek" tickFormatter={(value) => String(value).slice(0, 3)} tickLine={false} axisLine={false} />
                <YAxis tickFormatter={(value) => formatCompact(value)} tickLine={false} axisLine={false} width={48} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="meanDailyRidership" name="Mean daily ridership" fill="var(--color-totalRidership)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ChartContainer>
          </ApiState>
        </Section>
      </div>

      <Section title="Hourly buckets" description="Only 12 even-hour buckets (0, 2, 4 … 22) were observed. This is descriptive only and does not support a continuous diurnal pattern claim.">
        <ApiState isLoading={hourly.isLoading} error={hourly.error} isEmpty={(hourly.data?.data.length ?? 0) === 0} skeletonHeight="h-56">
          <ChartContainer config={hourlyChartConfig} className="aspect-auto h-56 w-full">
            <BarChart data={hourly.data?.data ?? []} margin={{ left: 8, right: 8 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="hour" tickFormatter={(value) => `${value}:00`} tickLine={false} axisLine={false} />
              <YAxis tickFormatter={(value) => formatCompact(value)} tickLine={false} axisLine={false} width={48} />
              <ChartTooltip content={<ChartTooltipContent labelFormatter={(value) => `${value}:00`} />} />
              <Bar dataKey="total_ridership" name="Total ridership" fill="var(--color-totalRidership)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ChartContainer>
        </ApiState>
        {hourly.data ? <CoverageNote source={hourly.data.meta.source} limitations={hourly.data.meta.limitations} className="mt-3" /> : null}
      </Section>

      <Section title="Top routes by total ridership" description={route ? "Filtered to the selected route" : "Top 12 of 140 observed routes"}>
        <ApiState isLoading={routes.isLoading} error={routes.error} isEmpty={topRoutes.length === 0}>
          <DataTable columns={routeColumns} rows={topRoutes} getKey={(row) => row.route_id} />
        </ApiState>
      </Section>

      {summary.data ? <CoverageNote source={summary.data.meta.source} coverage={summary.data.meta.coverage as never} limitations={summary.data.meta.limitations} /> : null}
    </div>
  );
}
