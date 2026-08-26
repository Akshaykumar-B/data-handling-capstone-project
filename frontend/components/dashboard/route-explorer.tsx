"use client";

import { useMemo, useState } from "react";
import { Download, GitCompareArrows, Search, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCjtpRoutes, useKnownRoutes, useRidershipRoutes, useStopsRoutes } from "@/lib/queries";
import { isApiConfigured } from "@/lib/api-client";
import { formatInt, formatPercent } from "@/lib/format";
import { ApiState } from "./api-state";
import { RouteSelect } from "./route-select";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

function csvCell(value: unknown) { return `"${String(value ?? "").replaceAll('"', '""')}"`; }
function downloadCsv(filename: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return;
  const keys = Object.keys(rows[0]);
  const body = [keys, ...rows.map((row) => keys.map((key) => row[key]))].map((row) => row.map(csvCell).join(",")).join("\n");
  const blob = new Blob([body], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url);
}

export function RouteExplorer() {
  const router = useRouter();
  const { routes, isLoading: routesLoading } = useKnownRoutes();
  const initialQuery = typeof window === "undefined" ? new URLSearchParams() : new URLSearchParams(window.location.search);
  const initial = initialQuery.get("route") ?? "";
  const initialCompare = initialQuery.get("compare") ?? "";
  const [route, setRoute] = useState(initial);
  const [compare, setCompare] = useState(initialCompare);
  const [search, setSearch] = useState("");
  const ridership = useRidershipRoutes({ route: route || undefined });
  const cjtp = useCjtpRoutes({ route: route || undefined });
  const stops = useStopsRoutes({ route: route || undefined });
  const compareRidership = useRidershipRoutes({ route: compare || undefined });
  const filteredRoutes = useMemo(() => routes.filter((item) => item.toLowerCase().includes(search.toLowerCase())).slice(0, 60), [routes, search]);
  const rows = useMemo(() => {
    const ridershipRows = ridership.data?.data ?? [];
    const cjtpRows = cjtp.data?.data ?? [];
    const stopRows = stops.data?.data ?? [];
    return ridershipRows.map((r) => {
      const c = cjtpRows.find((item) => item.route_id === r.route_id);
      return { route_id: r.route_id, total_ridership: r.total_ridership, share_of_total_ridership_pct: r.share_of_total_ridership_pct, cjtp_customer_weighted: c?.customer_weighted_cjtp ?? "", stop_associations: stopRows.filter((s) => s.route_id_canonical === r.route_id).length };
    });
  }, [ridership.data, cjtp.data, stops.data]);
  const comparisonRows = compareRidership.data?.data ?? [];
  const updateRoute = (next: string | null) => { setRoute(next ?? ""); const query = new URLSearchParams(typeof window === "undefined" ? "" : window.location.search); next ? query.set("route", next) : query.delete("route"); router.replace(`/routes-stops?${query.toString()}`, { scroll: false }); };
  const updateCompare = (next: string | null) => { setCompare(next ?? ""); const query = new URLSearchParams(typeof window === "undefined" ? "" : window.location.search); next ? query.set("compare", next) : query.delete("compare"); router.replace(`/routes-stops?${query.toString()}`, { scroll: false }); };
  const clear = () => { setRoute(""); setCompare(""); router.replace("/routes-stops", { scroll: false }); };

  return <Card className="border-primary/20"><CardHeader className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between"><div><div className="mb-2 flex items-center gap-2"><GitCompareArrows className="size-4 text-primary" aria-hidden="true" /><span className="font-mono text-[10px] uppercase tracking-wider text-primary">Route explorer</span></div><CardTitle className="text-xl">Compare real route context</CardTitle><p className="mt-1 max-w-xl text-sm leading-6 text-muted-foreground">Search the observed route union, then compare ridership with available CJTP and stop associations.</p></div><Button variant="outline" size="sm" onClick={() => downloadCsv(`route-explorer-${route || "all"}.csv`, rows)} disabled={!rows.length}><Download data-icon="inline-start" /> Export CSV</Button></CardHeader><CardContent className="flex flex-col gap-5">
    <div className="grid gap-3 md:grid-cols-3"><label className="flex flex-col gap-2 text-xs font-medium">Search routes<Input aria-label="Search routes" placeholder="e.g. M15" value={search} onChange={(event) => setSearch(event.target.value)} /></label><div className="flex flex-col gap-2"><span className="text-xs font-medium">Primary route</span><RouteSelect value={route} routes={filteredRoutes} onChange={updateRoute} /></div><div className="flex flex-col gap-2"><span className="text-xs font-medium">Compare with</span><RouteSelect value={compare} routes={filteredRoutes.filter((item) => item !== route)} onChange={updateCompare} /></div></div>
    {(route || compare) && <div className="flex flex-wrap items-center gap-2"><span className="text-xs text-muted-foreground">Active filters:</span>{route && <Badge variant="secondary">Route {route}<button className="ml-1" aria-label={`Clear route ${route}`} onClick={() => updateRoute("")}><X className="size-3" /></button></Badge>}{compare && <Badge variant="secondary">Compare {compare}<button className="ml-1" aria-label={`Clear comparison ${compare}`} onClick={() => updateCompare("")}><X className="size-3" /></button></Badge>}<Button variant="ghost" size="sm" onClick={clear}>Reset all</Button></div>}
    {!isApiConfigured() || routesLoading ? <ApiState isLoading={routesLoading} error={undefined} isEmpty={!isApiConfigured()} emptyLabel="Connect the API to search observed routes.">{null}</ApiState> : <div className="grid gap-3 md:grid-cols-2">{rows.map((row) => <div key={row.route_id} className="rounded-md border bg-muted/20 p-4"><div className="flex items-center justify-between gap-3"><span className="route-chip">{row.route_id}</span><span className="font-mono text-xs text-muted-foreground">{formatPercent(row.share_of_total_ridership_pct)} share</span></div><div className="mt-4 grid grid-cols-3 gap-3 text-sm"><Metric label="Ridership" value={formatInt(row.total_ridership)} /><Metric label="CJTP" value={typeof row.cjtp_customer_weighted === "number" ? row.cjtp_customer_weighted.toFixed(2) : "—"} /><Metric label="Stops" value={formatInt(row.stop_associations)} /></div></div>)}{compare && comparisonRows.length > 0 && <div className="rounded-md border border-dashed p-4"><span className="route-chip">{compare}</span><div className="mt-4 text-sm text-muted-foreground">Total ridership {formatInt(comparisonRows[0].total_ridership)} across {formatInt(comparisonRows[0].record_count)} records.</div></div>}</div>}
    {isApiConfigured() && !routesLoading && !rows.length && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Search className="size-4" />No route-level rows were returned for this selection.</div>}
  </CardContent></Card>;
}
function Metric({ label, value }: { label: string; value: string }) { return <div className="flex flex-col gap-1"><span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span><strong>{value}</strong></div>; }
