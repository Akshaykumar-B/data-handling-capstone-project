import { PageHeader, Section } from "@/components/dashboard/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const pipelinePhases = [
  { phase: "Phase 1–2", title: "Ingestion & cleaning", detail: "Raw MTA bus ridership, CJTP, and route/stop reference files are ingested and cleaned into a consistent schema." },
  { phase: "Phase 3", title: "Processing", detail: "Cleaned sources are aggregated into the ridership, CJTP, and route-stop tables this dashboard reads from, with a validation report covering row counts and route coverage." },
  { phase: "Phase 4", title: "Exploratory data analysis", detail: "Descriptive statistics, correlations, and coverage diagnostics are computed once and persisted to the EDA report." },
  { phase: "Phase 5", title: "Dashboard", detail: "This Next.js app and the FastAPI backend expose Phase 3/4 outputs read-only, through typed endpoints that always carry their source and limitations." },
];

export default function AboutPage() {
  return (
    <div className="flex flex-col gap-10">
      <PageHeader
        eyebrow="About"
        title="Project context and methodology"
        description="This dashboard is the Phase 5 presentation layer for a data-handling capstone project. It reads exclusively from files produced by the Phase 3 processing and Phase 4 EDA steps — it does not run its own analysis and does not fabricate figures the pipeline did not produce."
      />

      <Section title="Pipeline">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {pipelinePhases.map((step) => (
            <Card key={step.phase} className="py-5">
              <CardHeader className="gap-1 px-5">
                <span className="font-mono text-[11px] tracking-wide text-muted-foreground uppercase">{step.phase}</span>
                <CardTitle className="text-base font-semibold">{step.title}</CardTitle>
              </CardHeader>
              <CardContent className="px-5">
                <p className="text-sm leading-relaxed text-muted-foreground">{step.detail}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </Section>

      <Section title="Datasets" description="Three source datasets, joined only where a shared route identifier exists.">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Card className="py-5">
            <CardHeader className="px-5">
              <CardTitle className="text-sm font-medium">Ridership</CardTitle>
            </CardHeader>
            <CardContent className="px-5 text-sm leading-relaxed text-muted-foreground">
              Fare-tap ridership and transfer counts by route, service date, and hour bucket, from a development subsample.
            </CardContent>
          </Card>
          <Card className="py-5">
            <CardHeader className="px-5">
              <CardTitle className="text-sm font-medium">CJTP</CardTitle>
            </CardHeader>
            <CardContent className="px-5 text-sm leading-relaxed text-muted-foreground">
              Customer Journey Time Performance — monthly, customer-weighted travel time performance by route, period, trip type, and borough.
            </CardContent>
          </Card>
          <Card className="py-5">
            <CardHeader className="px-5">
              <CardTitle className="text-sm font-medium">Routes & stops</CardTitle>
            </CardHeader>
            <CardContent className="px-5 text-sm leading-relaxed text-muted-foreground">
              Route geometry and route-stop associations, including direction and physical stop coordinates.
            </CardContent>
          </Card>
        </div>
      </Section>

      <Section title="How to read this dashboard">
        <ul className="flex flex-col gap-2 text-sm leading-relaxed text-muted-foreground">
          <li>
            Every chart and table is backed by a live call to the FastAPI backend. If <code className="font-mono text-xs">NEXT_PUBLIC_API_BASE_URL</code> is unset or the
            backend is unreachable, the page shows an explicit &quot;API unavailable&quot; state rather than placeholder numbers.
          </li>
          <li>Route coverage is always reported against the canonical project route list — routes absent from a dataset are named, not hidden.</li>
          <li>Correlations on the Relationships page report Pearson and Spearman coefficients with sample size; they describe association, not causation.</li>
          <li>Views without a dedicated backend endpoint (weekday/weekend split, day-of-week breakdown, route concentration) are derived client-side from fields the API already returns, and are labeled as such.</li>
        </ul>
      </Section>
    </div>
  );
}
