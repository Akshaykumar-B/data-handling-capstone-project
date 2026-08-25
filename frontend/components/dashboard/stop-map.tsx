"use client";

import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { StopPointFeature } from "@/lib/api-client";

const NYC_BOUNDS: [number, number, number, number] = [-74.35, 40.45, -73.6, 40.95];

/** MapLibre point map of bus stops from /stops/points. No route-line overlay is drawn since /routes/geometry doesn't exist on the backend. */
export function StopMap({ features }: { features: StopPointFeature[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          basemap: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [{ id: "basemap", type: "raster", source: "basemap" }],
      },
      bounds: NYC_BOUNDS,
      attributionControl: false,
    });
    map.addControl(new maplibregl.AttributionControl({ compact: true }));
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const applySource = () => {
      const geojson = { type: "FeatureCollection" as const, features };
      const source = map.getSource("stops") as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(geojson);
      } else {
        map.addSource("stops", { type: "geojson", data: geojson });
        map.addLayer({
          id: "stops-layer",
          type: "circle",
          source: "stops",
          paint: {
            "circle-radius": 3.5,
            "circle-color": "#1b4fd6",
            "circle-stroke-width": 1,
            "circle-stroke-color": "#ffffff",
            "circle-opacity": 0.85,
          },
        });
        map.on("click", "stops-layer", (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const props = feature.properties as StopPointFeature["properties"];
          new maplibregl.Popup()
            .setLngLat(event.lngLat)
            .setHTML(`<div style="font-family: ui-sans-serif; font-size: 12px;"><strong>${props.stop_name}</strong><br/>${props.route_id_canonical} · dir ${props.direction}</div>`)
            .addTo(map);
        });
        map.on("mouseenter", "stops-layer", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "stops-layer", () => {
          map.getCanvas().style.cursor = "";
        });
      }

      if (features.length > 0) {
        const lons = features.map((f) => f.geometry.coordinates[0]);
        const lats = features.map((f) => f.geometry.coordinates[1]);
        map.fitBounds(
          [
            [Math.min(...lons), Math.min(...lats)],
            [Math.max(...lons), Math.max(...lats)],
          ],
          { padding: 32, maxZoom: 15, duration: 400 },
        );
      }
    };

    if (map.isStyleLoaded()) {
      applySource();
    } else {
      map.once("load", applySource);
    }
  }, [features]);

  return <div ref={containerRef} className="h-[420px] w-full overflow-hidden rounded-md border" />;
}
