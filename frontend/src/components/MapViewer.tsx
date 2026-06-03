import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";

export interface MapViewerItem {
  id: string;
  bbox: [number, number, number, number]; // [minLon, minLat, maxLon, maxLat]
  severity: string | null;
  status: string;
}

interface Props {
  aoi?: GeoJSON.Geometry | null;
  items?: MapViewerItem[];
  onItemClick?: (id: string) => void;
  className?: string;
  rasterUrl?: string | null;     // XYZ template, e.g. /titiler/cog/tiles/{z}/{x}/{y}.png?url=...
  rasterOpacity?: number;        // 0..1, default 0.75
  fitToAoiOnly?: boolean;        // ignore item bboxes when fitting bounds (item detail page)
}

const RASTER_SOURCE_ID = "cog-overlay";
const RASTER_LAYER_ID = "cog-overlay-layer";

const SEVERITY_COLORS: Record<string, string> = {
  green: "#22c55e",
  yellow: "#eab308",
  red: "#ef4444",
};

function bboxToPolygon(bbox: [number, number, number, number]): GeoJSON.Polygon {
  const [w, s, e, n] = bbox;
  return {
    type: "Polygon",
    coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
  };
}

export default function MapViewer({
  aoi,
  items = [],
  onItemClick,
  className = "",
  rasterUrl = null,
  rasterOpacity = 0.75,
  fitToAoiOnly = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);
  const fittedRef = useRef(false);
  const pendingOpsRef = useRef<Array<() => void>>([]);

  function runOrDefer(fn: () => void) {
    if (loadedRef.current) {
      fn();
    } else {
      pendingOpsRef.current.push(fn);
    }
  }

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          "osm-tiles": {
            type: "raster",
            tiles: [
              "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
              "https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
              "https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
              "https://d.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
            ],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors © CARTO",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm-tiles" }],
      },
      center: [78.96, 20.59],
      zoom: 2,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl(), "top-right");

    map.on("load", () => {
      map.addSource("aoi", {
        type: "geojson",
        data: aoi
          ? { type: "Feature", geometry: aoi, properties: {} }
          : { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "aoi-fill",
        type: "fill",
        source: "aoi",
        paint: { "fill-color": "#3b82f6", "fill-opacity": 0.15 },
      });
      map.addLayer({
        id: "aoi-line",
        type: "line",
        source: "aoi",
        paint: { "line-color": "#3b82f6", "line-width": 2 },
      });

      const itemFeatures: GeoJSON.Feature[] = items.map((item) => ({
        type: "Feature",
        geometry: bboxToPolygon(item.bbox),
        properties: { id: item.id, severity: item.severity, status: item.status },
      }));

      map.addSource("items", {
        type: "geojson",
        data: { type: "FeatureCollection", features: itemFeatures },
      });
      map.addLayer({
        id: "items-fill",
        type: "fill",
        source: "items",
        paint: {
          "fill-color": [
            "match", ["get", "severity"],
            "green", SEVERITY_COLORS.green,
            "yellow", SEVERITY_COLORS.yellow,
            "red", SEVERITY_COLORS.red,
            "#6b7280",
          ],
          "fill-opacity": 0.25,
        },
      });
      map.addLayer({
        id: "items-line",
        type: "line",
        source: "items",
        paint: {
          "line-color": [
            "match", ["get", "severity"],
            "green", SEVERITY_COLORS.green,
            "yellow", SEVERITY_COLORS.yellow,
            "red", SEVERITY_COLORS.red,
            "#6b7280",
          ],
          "line-width": 1.5,
        },
      });

      if (onItemClick) {
        map.on("click", "items-fill", (e) => {
          const id = e.features?.[0]?.properties?.id;
          if (id) onItemClick(id);
        });
        map.on("mouseenter", "items-fill", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "items-fill", () => {
          map.getCanvas().style.cursor = "";
        });
      }

      if (aoi || items.length > 0) {
        fitBounds(map, aoi, items, fitToAoiOnly);
        fittedRef.current = true;
      }

      // mark loaded and drain anything that was queued before load fired
      loadedRef.current = true;
      const queued = pendingOpsRef.current;
      pendingOpsRef.current = [];
      queued.forEach((op) => op());
    });

    mapRef.current = map;
    return () => {
      loadedRef.current = false;
      fittedRef.current = false;
      pendingOpsRef.current = [];
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // defers to the map "load" event if the style hasn't finished loading yet (cold page render)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const apply = () => {
      const aoiSrc = map.getSource("aoi") as maplibregl.GeoJSONSource | undefined;
      if (aoiSrc) {
        aoiSrc.setData(
          aoi
            ? { type: "Feature", geometry: aoi, properties: {} }
            : { type: "FeatureCollection", features: [] }
        );
      }

      const itemsSrc = map.getSource("items") as maplibregl.GeoJSONSource | undefined;
      if (itemsSrc) {
        itemsSrc.setData({
          type: "FeatureCollection",
          features: items.map((item) => ({
            type: "Feature",
            geometry: bboxToPolygon(item.bbox),
            properties: { id: item.id, severity: item.severity, status: item.status },
          })),
        });
      }

      if (!fittedRef.current && (aoi || items.length > 0)) {
        fitBounds(map, aoi, items, fitToAoiOnly);
        fittedRef.current = true;
      }
    };

    runOrDefer(apply);
  }, [aoi, items, fitToAoiOnly]);

  // the optional TiTiler raster overlay
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const apply = () => {
      if (map.getLayer(RASTER_LAYER_ID)) map.removeLayer(RASTER_LAYER_ID);
      if (map.getSource(RASTER_SOURCE_ID)) map.removeSource(RASTER_SOURCE_ID);

      if (!rasterUrl) return;

      map.addSource(RASTER_SOURCE_ID, {
        type: "raster",
        tiles: [rasterUrl],
        tileSize: 256,
      });
      // insert below the AOI outline so the AOI border stays visible on top
      const beforeId = map.getLayer("aoi-line") ? "aoi-line" : undefined;
      map.addLayer(
        {
          id: RASTER_LAYER_ID,
          type: "raster",
          source: RASTER_SOURCE_ID,
          paint: { "raster-opacity": rasterOpacity },
        },
        beforeId,
      );
    };

    runOrDefer(apply);
  }, [rasterUrl]);

  // update raster opacity without recreating the layer
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const apply = () => {
      if (map.getLayer(RASTER_LAYER_ID)) {
        map.setPaintProperty(RASTER_LAYER_ID, "raster-opacity", rasterOpacity);
      }
    };

    runOrDefer(apply);
  }, [rasterOpacity]);

  return <div ref={containerRef} className={className} />;
}

function fitBounds(
  map: maplibregl.Map,
  aoi: GeoJSON.Geometry | null | undefined,
  items: MapViewerItem[],
  aoiOnly: boolean = false,
) {
  const coords: [number, number][] = [];

  if (aoi) {
    collectCoords(aoi, coords);
  }
  if (!aoiOnly) {
    for (const item of items) {
      const [w, s, e, n] = item.bbox;
      coords.push([w, s], [e, n]);
    }
  }

  if (coords.length === 0) return;

  const lons = coords.map(([lng]) => lng);
  const lats = coords.map(([, lat]) => lat);
  const bounds: maplibregl.LngLatBoundsLike = [
    [Math.min(...lons), Math.min(...lats)],
    [Math.max(...lons), Math.max(...lats)],
  ];
  map.fitBounds(bounds, { padding: 40, maxZoom: 14, duration: 300 });
}

function collectCoords(geom: GeoJSON.Geometry, out: [number, number][]) {
  if (geom.type === "Polygon") {
    geom.coordinates[0].forEach(([lng, lat]) => out.push([lng, lat]));
  } else if (geom.type === "MultiPolygon") {
    geom.coordinates.forEach((poly) =>
      poly[0].forEach(([lng, lat]) => out.push([lng, lat]))
    );
  }
}
