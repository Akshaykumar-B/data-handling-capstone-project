"use client";

import Link from "next/link";
import { ArrowRight, BarChart3, MapPinned, Search, ShieldCheck, Users } from "lucide-react";
import { useOverview } from "@/lib/queries";
import { ApiState } from "@/components/dashboard/api-state";
import { formatInt, formatPercent } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const areas = [
  { href: "/overview", title: "Overview", description: "System coverage and headline measures.", icon: BarChart3 },
  { href: "/ridership", title: "Ridership", description: "Daily, hourly, and route-level demand.", icon: Users },
  { href: "/cjtp", title: "CJTP", description: "Customer journey transfer performance.", icon: Search },
  { href: "/routes-stops", title: "Routes + Stops", description: "Route associations and stop geography.", icon: MapPinned },
  { href: "/relationships", title: "Relationships", description: "Measured associations between datasets.", icon: ShieldCheck },
  { href: "/data-quality", title: "Data quality", description: "Coverage, warnings, and provenance.", icon: ShieldCheck },
  { href: "/about", title: "About", description: "Sources, methods, and limitations.", icon: BarChart3 },
];

export default function HomePage() {
  const overview = useOverview();
  const data = overview.data?.data;

  return (
    <div className="flex flex-col gap-10">
      <section className="relative overflow-hidden rounded-lg border bg-primary px-6 py-10 text-primary-foreground shadow-sm md:px-10 md:py-14">
        <div className="relative z-10 flex max-w-3xl flex-col gap-6">
          <Badge variant="secondary" className="w-fit font-mono text-[10px] uppercase tracking-[0.16em]">Public transit intelligence</Badge>
          <h2 className="max-w-2xl text-4xl font-semibold tracking-tight text-balance md:text-6xl">See how the network moves.</h2>
          <p className="max-w-2xl text-base leading-7 text-primary-foreground/80 md:text-lg">A transparent way to explore ridership, customer journey transfer performance, routes, stops, and data quality from the processed transit datasets.</p>
          <div className="flex flex-wrap gap-3">
            <Button asChild variant="secondary"><Link href="/overview">Explore the dashboard <ArrowRight data-icon="inline-end" /></Link></Button>
            <Button asChild variant="outline" className="border-primary-foreground/30 bg-transparent text-primary-foreground hover:bg-primary-foreground/10 hover:text-primary-foreground"><Link href="/about">Read the methodology</Link></Button>
          </div>
        </div>
      </section>

      <ApiState isLoading={overview.isLoading} error={overview.error} isEmpty={!data} emptyLabel="The API returned no overview data.">
        {data && (
          <section aria-label="Live system snapshot" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Snapshot label="Ridership records" value={formatInt(data.ridership_record_count)} detail="records in the ridership extract" />
            <Snapshot label="Total transfers" value={formatInt(data.total_transfers)} detail="observed transfer count" />
            <Snapshot label="Unique stops" value={formatInt(data.unique_stops)} detail="physical stops represented" />
            <Snapshot label="Route coverage" value={formatPercent(data.ridership_route_coverage.coverage_percentage)} detail="project routes in ridership" />
          </section>
        )}
      </ApiState>

      <section className="flex flex-col gap-5">
        <div className="flex flex-col gap-2"><span className="font-mono text-[11px] uppercase tracking-[0.14em] text-primary">Start exploring</span><h2 className="text-2xl font-semibold tracking-tight">One network, several useful views.</h2><p className="max-w-2xl text-sm leading-6 text-muted-foreground">Choose a perspective that fits your question. Every view keeps its source, coverage, and limitations visible.</p></div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {areas.map(({ href, title, description, icon: Icon }) => <Link key={href} href={href} className="group"><Card className="h-full transition-colors group-hover:border-primary/50"><CardHeader className="flex flex-row items-start justify-between gap-4"><CardTitle className="text-base">{title}</CardTitle><Icon className="size-5 text-primary" aria-hidden="true" /></CardHeader><CardContent><p className="text-sm leading-6 text-muted-foreground">{description}</p><span className="mt-4 inline-flex items-center gap-1 font-mono text-[11px] uppercase tracking-wider text-primary">Open view <ArrowRight className="size-3 transition-transform group-hover:translate-x-1" /></span></CardContent></Card></Link>)}
        </div>
      </section>

      <section className="grid gap-4 border-t pt-6 md:grid-cols-3">
        <TrustNote title="Data-backed" text="Numbers are read from the existing FastAPI contract, not invented in the interface." />
        <TrustNote title="Transparent" text="Coverage and limitations travel with each API response and remain visible." />
        <TrustNote title="Explore freely" text="Use route filters and shareable URLs to return to the same question later." />
      </section>
    </div>
  );
}

function Snapshot({ label, value, detail }: { label: string; value: string; detail: string }) { return <Card><CardContent className="flex flex-col gap-2 p-5"><span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span><strong className="text-2xl tracking-tight">{value}</strong><span className="text-xs leading-5 text-muted-foreground">{detail}</span></CardContent></Card>; }
function TrustNote({ title, text }: { title: string; text: string }) { return <div className="flex flex-col gap-2"><span className="font-mono text-[11px] uppercase tracking-wider text-primary">{title}</span><p className="text-sm leading-6 text-muted-foreground">{text}</p></div>; }
