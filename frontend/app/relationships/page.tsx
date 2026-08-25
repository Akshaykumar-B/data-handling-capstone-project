"use client";

import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Cell, XAxis, YAxis } from "recharts";
import { PageHeader, Section } from "@/components/dashboard/page-header";
import { ApiState } from "@/components/dashboard/api-state";
import { CoverageNote } from "@/components/dashboard/coverage-note";
import { DataTable, type Column } from "@/components/dashboard/data-table";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { useRelationshipsSummary } from "@/lib/queries";
import { correlationDataset, type CorrelationBar } from "@/lib/analytics";
import { formatInt } from "@/lib/format";

const chartConfig: ChartConfig = { pearsonR: { label: "Pearson r", color: "var(--chart-1)" } };

const barColumns: Column<CorrelationBar>[] = [
  { header: "Pair", render: (row) => <span className="capitalize">{row.label}</span> },
  { header: "n", align: "right", render: (row) => formatInt(row.n) },
  { header: "Pearson r", align: "right", render: (row) => (row.pearsonR != null ? row.pearsonR.toFixed(3) : "—") },
  { header: "Spearman ρ", align: "right", render: (row) => (row.spearmanRho != null ? row.spearmanRho.toFixed(3) : "—") },
  { header: "Strength", render: (row) => row.strength },
];

function barColor(pearsonR: number | null): string {
  if (pearsonR === null) return "var(--muted-foreground)";
  return pearsonR >= 0 ? "var(--chart-1)" : "var(--destructive)";
}

export default function RelationshipsPage() {
  const relationships = useRelationshipsSummary();

  const recordLevel = relationships.data?.data.record_level ?? {};
  const routeLevel = relationships.data?.data.route_level ?? {};
  const bars = useMemo(() => correlationDataset(recordLevel, routeLevel), [recordLevel, routeLevel]);

  return (
    <div className="flex flex-col gap-10">
      <PageHeader
        eyebrow="Relationships"
        title="Measured relationships between variables"
        description="Pearson and Spearman coefficients from /relationships/summary. These are statistical associations only — correlation strength is reported alongside sample size and significance, never framed as causation. No record-level scatter plot is shown since the backend does not expose point-level sampling for this view."
      />

      <Section title="Correlation coefficients">
        <ApiState isLoading={relationships.isLoading} error={relationships.error} isEmpty={bars.length === 0} skeletonHeight="h-72">
          <ChartContainer config={chartConfig} className="aspect-auto h-72 w-full">
            <BarChart data={bars} layout="vertical" margin={{ left: 16, right: 16 }}>
              <CartesianGrid horizontal={false} strokeDasharray="3 3" />
              <XAxis type="number" domain={[-1, 1]} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="label" width={160} tickLine={false} axisLine={false} className="capitalize" />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="pearsonR" name="Pearson r" radius={[0, 4, 4, 0]}>
                {bars.map((bar) => (
                  <Cell key={bar.label} fill={barColor(bar.pearsonR)} />
                ))}
              </Bar>
            </BarChart>
          </ChartContainer>
        </ApiState>
      </Section>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        <Section title="Record-level pairs" description="Computed across individual observation records.">
          <ApiState isLoading={relationships.isLoading} error={relationships.error} isEmpty={Object.keys(recordLevel).length === 0}>
            <DataTable columns={barColumns} rows={correlationDataset(recordLevel, {})} getKey={(row) => row.label} />
          </ApiState>
        </Section>
        <Section title="Route-level pairs" description="Computed across route-aggregated totals.">
          <ApiState isLoading={relationships.isLoading} error={relationships.error} isEmpty={Object.keys(routeLevel).length === 0}>
            <DataTable columns={barColumns} rows={correlationDataset({}, routeLevel)} getKey={(row) => row.label} />
          </ApiState>
        </Section>
      </div>

      {relationships.data ? (
        <CoverageNote source={relationships.data.meta.source} limitations={relationships.data.meta.limitations} />
      ) : null}
    </div>
  );
}
