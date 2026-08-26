"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { StopPointFeature } from "@/lib/api-client";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

const NYC_BOUNDS: [number, number, number, number] = [-74.35, 40.45, -73.6, 40.95];

export function StopMap({ features }: { features: StopPointFeature[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [search, setSearch] = useState("");
  const [direction, setDirection] = useState("all");
  const [selected, setSelected] = useState<StopPointFeature | null>(null);
  const filtered = useMemo(() => features.filter((feature) => {
    const props = feature.properties;
    const matchesSearch = `${props.stop_name} ${props.stop_id} ${props.route_id_canonical}`.toLowerCase().includes(search.toLowerCase());
    return matchesSearch && (direction === "all" || props.direction === direction);
  }), [features, search, direction]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({ container: containerRef.current, style: { version: 8, sources: { basemap: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap contributors" } }, layers: [{ id: "basemap", type: "raster", source: "basemap" }] }, bounds: NYC_BOUNDS, attributionControl: false });
    map.addControl(new maplibregl.AttributionControl({ compact: true }));
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const applySource = () => {
      const geojson = { type: "FeatureCollection" as const, features: filtered };
      const source = map.getSource("stops") as maplibregl.GeoJSONSource | undefined;
      if (source) source.setData(geojson);
      else {
        map.addSource("stops", { type: "geojson", data: geojson });
        map.addLayer({ id: "stops-layer", type: "circle", source: "stops", paint: { "circle-radius": 4, "circle-color": "#1b4fd6", "circle-stroke-width": 1, "circle-stroke-color": "#ffffff", "circle-opacity": 0.85 } });
        map.on("click", "stops-layer", (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const props = feature.properties as StopPointFeature["properties"];
          setSelected(filtered.find((item) => item.properties.stop_id === props.stop_id && item.properties.direction === props.direction) ?? null);
        });
        map.on("mouseenter", "stops-layer", () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", "stops-layer", () => { map.getCanvas().style.cursor = ""; });
      }
      if (filtered.length > 0) { const lons = filtered.map((f) => f.geometry.coordinates[0]); const lats = filtered.map((f) => f.geometry.coordinates[1]); map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 32, maxZoom: 15, duration: 300 }); }
    };
    if (map.isStyleLoaded()) applySource(); else map.once("load", applySource);
  }, [filtered]);

  return <div className="flex flex-col gap-3"><div className="grid gap-3 sm:grid-cols-[1fr_180px]"><label className="flex flex-col gap-2 text-xs font-medium">Search stops<Input aria-label="Search stops" placeholder="Stop name, ID, or route" value={search} onChange={(event) => setSearch(event.target.value)} /></label><label className="flex flex-col gap-2 text-xs font-medium">Direction<Select value={direction} onValueChange={setDirection}><SelectTrigger aria-label="Filter stops by direction"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All directions</SelectItem>{["N", "S", "E", "W"].map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select></label></div><div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><Badge variant="outline" className="gap-1"><span className="size-2 rounded-full bg-primary" aria-hidden="true" /> Stop point</Badge><span>{filtered.length.toLocaleString()} of {features.length.toLocaleString()} points shown</span></div><div ref={containerRef} className="h-[420px] w-full overflow-hidden rounded-md border" role="img" aria-label="Interactive map of transit stops. Use the accessible stop table below for the same filtered information." />{selected && <Card className="border-primary/30"><CardContent className="flex flex-wrap items-start justify-between gap-4 p-4"><div><p className="font-semibold">{selected.properties.stop_name}</p><p className="mt-1 text-sm text-muted-foreground">Stop ID {selected.properties.stop_id} · route {selected.properties.route_id_canonical} · direction {selected.properties.direction}</p></div><button className="text-xs text-primary underline" onClick={() => setSelected(null)}>Clear selection</button></CardContent></Card>}<div className="max-h-56 overflow-auto rounded-md border"><table className="w-full text-left text-xs"><caption className="sr-only">Accessible table of filtered transit stops</caption><thead className="sticky top-0 bg-muted"><tr><th className="p-2 font-medium">Stop</th><th className="p-2 font-medium">Route</th><th className="p-2 font-medium">Direction</th><th className="p-2 font-medium">Coordinates</th></tr></thead><tbody>{filtered.slice(0, 100).map((feature) => <tr key={`${feature.properties.stop_id}-${feature.properties.direction}`} className="border-t"><td className="p-2">{feature.properties.stop_name} <span className="text-muted-foreground">({feature.properties.stop_id})</span></td><td className="p-2">{feature.properties.route_id_canonical}</td><td className="p-2">{feature.properties.direction}</td><td className="p-2 font-mono">{feature.geometry.coordinates[1].toFixed(4)}, {feature.geometry.coordinates[0].toFixed(4)}</td></tr>)}</tbody></table></div></div>;
}
