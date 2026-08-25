"use client";

import { PageHeader, Section } from "@/components/dashboard/page-header";
import { ApiState } from "@/components/dashboard/api-state";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { CoverageBar } from "@/components/dashboard/coverage-bar";
import { CoverageNote } from "@/components/dashboard/coverage-note";
import { useOverview } from "@/lib/queries";
import { formatCompact, formatInt, formatPercent } from "@/lib/format";

export default function OverviewPage() {
  const overview = useOverview();
  const data = overview.data?.data;

  return (
    <div className="flex flex-col gap-10">
      <PageHeader
        eyebrow="Overview"
        title="Route coverage and performance at a glance"
        description="Assembled from the Phase 3/4 processed data pipeline. Every figure below traces to a specific parquet or JSON output — nothing here is estimated."
      />

      <ApiState isLoading={overview.isLoading} error={overview.error} skeletonHeight="h-96">
        {data ? (
          <div className="flex flex-col gap-10">
            <Section>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <KpiCard accent="primary" label="Total ridership" value={formatCompact(data.total_ridership)} detail={`${formatInt(data.ridership_record_count)} records, Jan–Feb 2023 subsample`} />
                <KpiCard accent="primary" label="Total transfers" value={formatCompact(data.total_transfers)} />
                <KpiCard accent="accent" label="CJTP weighted average" value={formatPercent(data.cjtp_weighted_average)} detail="Customer-weighted, on-time journeys" />
                <KpiCard label="Unique stops" value={formatInt(data.unique_stops)} detail={`${formatInt(data.stop_associations)} route × direction × stop associations`} />
              </div>
            </Section>

            <Section title="Route coverage by dataset" description="How many of the 142 project routes each processed dataset actually contains.">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <CoverageBar
                  label="Ridership"
                  matching={data.ridership_route_coverage.matching_route_count}
                  total={data.ridership_route_coverage.project_route_count}
                  percentage={data.ridership_route_coverage.coverage_percentage}
                  missing={data.ridership_route_coverage.project_routes_missing_from_dataset}
                />
                <CoverageBar
                  label="Customer journey (CJTP)"
                  matching={data.cjtp_route_coverage.matching_route_count}
                  total={data.cjtp_route_coverage.project_route_count}
                  percentage={data.cjtp_route_coverage.coverage_percentage}
                  missing={data.cjtp_route_coverage.project_routes_missing_from_dataset}
                />
                <CoverageBar
                  label="Bus stops"
                  matching={data.stop_route_coverage.matching_route_count}
                  total={data.stop_route_coverage.project_route_count}
                  percentage={data.stop_route_coverage.coverage_percentage}
                  missing={data.stop_route_coverage.project_routes_missing_from_dataset}
                />
                <CoverageBar
                  label="Route geometry"
                  matching={data.route_coverage.routes_with_geometry}
                  total={data.route_coverage.project_route_count}
                  percentage={data.route_coverage.coverage_percentage}
                  missing={data.route_coverage.project_routes_missing_geometry}
                />
              </div>
            </Section>

            <Section title="Cross-dataset overlap" description="Project routes with data in all three core datasets simultaneously.">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <KpiCard label="In all 3 datasets" value={`${formatInt(data.all_dataset_route_coverage.in_all_three_datasets)}/${formatInt(data.all_dataset_route_coverage.project_route_count)}`} detail={formatPercent(data.all_dataset_route_coverage.in_all_three_pct)} />
                <KpiCard label="Route geometry features" value={formatCompact(data.route_geometry_feature_count)} detail="MultiLineString features across all NYC bus service, metadata only — never parsed" />
                <KpiCard
                  label="Missing everywhere"
                  value={String(data.all_dataset_route_coverage.missing_from_every_dataset.length)}
                  detail={data.all_dataset_route_coverage.missing_from_every_dataset.join(", ") || "none"}
                />
              </div>
            </Section>

            <CoverageNote source={overview.data!.meta.source} limitations={overview.data!.meta.limitations} />
          </div>
        ) : null}
      </ApiState>
    </div>
  );
}
