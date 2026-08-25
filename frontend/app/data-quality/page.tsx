"use client";

import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { PageHeader, Section } from "@/components/dashboard/page-header";
import { ApiState } from "@/components/dashboard/api-state";
import { CoverageBar } from "@/components/dashboard/coverage-bar";
import { DataTable, type Column } from "@/components/dashboard/data-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { useDataQuality, useDataStatus } from "@/lib/queries";
import { formatInt } from "@/lib/format";
import type { RouteCoverage } from "@/lib/api-client";

type MissingRow = { dataset: string; column: string; missing: number };
type RowCountRow = { dataset: string; count: number };

const missingColumns: Column<MissingRow>[] = [
  { header: "Dataset", render: (row) => row.dataset },
  { header: "Column", render: (row) => <span className="font-mono text-xs">{row.column}</span> },
  { header: "Missing values", align: "right", render: (row) => formatInt(row.missing) },
];

const rowCountColumns: Column<RowCountRow>[] = [
  { header: "Dataset", render: (row) => row.dataset },
  { header: "Rows", align: "right", render: (row) => formatInt(row.count) },
];

export default function DataQualityPage() {
  const status = useDataStatus();
  const quality = useDataQuality();

  const missingRows: MissingRow[] = Object.entries(quality.data?.data.missing_values ?? {}).flatMap(([dataset, columns]) =>
    Object.entries(columns)
      .filter(([, missing]) => missing > 0)
      .map(([column, missing]) => ({ dataset, column, missing })),
  );

  const rowCountRows: RowCountRow[] = Object.entries(quality.data?.data.row_counts ?? {})
    .filter(([, count]) => count !== undefined)
    .map(([dataset, count]) => ({ dataset, count: count as number }));

  const routeCoverageEntries = Object.entries(quality.data?.data.route_coverage ?? {}) as Array<[string, RouteCoverage]>;
  const warnings = quality.data?.data.warnings ?? [];

  return (
    <div className="flex flex-col gap-10">
      <PageHeader
        eyebrow="Data quality"
        title="Coverage, limitations, and source readiness"
        description="Everything on this page is read directly from the Phase 3/4 validation reports and the live /api/v1/data/quality and /api/v1/data/status endpoints — nothing here is estimated or fabricated."
      />

      <Section title="Backend data readiness">
        <ApiState isLoading={status.isLoading} error={status.error} skeletonHeight="h-24">
          {status.data ? (
            <Card className="py-5">
              <CardHeader className="px-5">
                <CardTitle className="flex items-center gap-2 text-sm font-medium">
                  {status.data.status === "ready" ? (
                    <Badge variant="secondary" className="gap-1">
                      <CheckCircle2 className="size-3" /> Ready
                    </Badge>
                  ) : (
                    <Badge variant="destructive" className="gap-1">
                      <AlertTriangle className="size-3" /> Incomplete
                    </Badge>
                  )}
                  Required processed files
                </CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-2 gap-2 px-5 sm:grid-cols-3">
                {Object.entries(status.data.required_files).map(([file, present]) => (
                  <div key={file} className="flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-xs">
                    <span className="truncate font-mono">{file}</span>
                    <Badge variant={present ? "secondary" : "destructive"}>{present ? "present" : "missing"}</Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </ApiState>
      </Section>

      <Section title="Route coverage against the project reference list" description="Each dataset's coverage of the canonical route list, straight from the validation report.">
        <ApiState isLoading={quality.isLoading} error={quality.error} isEmpty={routeCoverageEntries.length === 0} skeletonHeight="h-40">
          <div className="grid gap-4 sm:grid-cols-2">
            {routeCoverageEntries.map(([dataset, coverage]) => (
              <CoverageBar
                key={dataset}
                label={dataset}
                matching={coverage.matching_route_count}
                total={coverage.project_route_count}
                percentage={coverage.coverage_percentage}
                missing={coverage.project_routes_missing_from_dataset}
              />
            ))}
          </div>
        </ApiState>
      </Section>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        <Section title="Row counts by dataset">
          <ApiState isLoading={quality.isLoading} error={quality.error} isEmpty={rowCountRows.length === 0}>
            <DataTable columns={rowCountColumns} rows={rowCountRows} getKey={(row) => row.dataset} />
          </ApiState>
        </Section>

        <Section title="Missing values" description="Only columns with at least one missing value are listed.">
          <ApiState isLoading={quality.isLoading} error={quality.error} isEmpty={missingRows.length === 0} emptyLabel="No missing values were reported.">
            <DataTable columns={missingColumns} rows={missingRows} getKey={(row) => `${row.dataset}-${row.column}`} />
          </ApiState>
        </Section>
      </div>

      <Section title="Warnings" description="Verbatim limitations surfaced by the Phase 3/4 pipeline.">
        <ApiState isLoading={quality.isLoading} error={quality.error} isEmpty={warnings.length === 0} emptyLabel="No warnings were reported." skeletonHeight="h-24">
          <div className="flex flex-col gap-3">
            {warnings.map((warning, index) => (
              <Alert key={`${warning.scope}-${index}`}>
                <AlertTriangle />
                <AlertTitle className="capitalize">{warning.scope}</AlertTitle>
                <AlertDescription>{warning.message}</AlertDescription>
              </Alert>
            ))}
          </div>
        </ApiState>
      </Section>

      {quality.data ? (
        <div className="flex flex-col gap-1 border-t border-dashed pt-4 text-xs text-muted-foreground">
          <p>Phase 3 processing: {quality.data.data.reports.processing.started_utc} → {quality.data.data.reports.processing.finished_utc}</p>
          <p>Phase 4 EDA: {quality.data.data.reports.eda.started_utc} → {quality.data.data.reports.eda.finished_utc}</p>
        </div>
      ) : null}
    </div>
  );
}
