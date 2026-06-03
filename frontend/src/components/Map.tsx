import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";

type DrawMode = "polygon" | "rectangle" | "point";

interface MapProps {
  geometry?: GeoJSON.Geometry | null;
  onDraw?: (geometry: GeoJSON.Polygon, mode: DrawMode) => void;
  onClear?: () => void;
  className?: string;
}

const EMPTY_FC: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

const POINT_BUFFER = 0.05; // ~5 km

function pointToBox(lng: number, lat: number): GeoJSON.Polygon {
  return rectFromCorners([lng - POINT_BUFFER, lat - POINT_BUFFER], [lng + POINT_BUFFER, lat + POINT_BUFFER]);
}

function rectFromCorners(a: [number, number], b: [number, number]): GeoJSON.Polygon {
  const [x0, y0] = a;
  const [x1, y1] = b;
  return {
    type: "Polygon",
    coordinates: [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]],
  };
}

function setSource(map: maplibregl.Map, id: string, data: GeoJSON.GeoJSON) {
  (map.getSource(id) as maplibregl.GeoJSONSource | undefined)?.setData(data);
}

export default function Map({ geometry, onDraw, onClear, className = "" }: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  const polyPtsRef = useRef<[number, number][]>([]);
  const [polyCount, setPolyCount] = useState(0);

  const rectStartRef = useRef<[number, number] | null>(null);

  const [mode, setMode] = useState<DrawMode>("rectangle");
  const modeRef = useRef<DrawMode>("rectangle");
  const [isDone, setIsDone] = useState(false);

  useEffect(() => { modeRef.current = mode; }, [mode]);

  useEffect(() => {
    if (!containerRef.current) return;

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
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showZoom: false, showCompass: true }), "top-right");

    map.on("load", () => {
      map.addSource("aoi", { type: "geojson", data: EMPTY_FC });
      map.addLayer({
        id: "aoi-fill", type: "fill", source: "aoi",
        paint: { "fill-color": "#22c55e", "fill-opacity": 0.2 }
      });
      map.addLayer({
        id: "aoi-line", type: "line", source: "aoi",
        paint: { "line-color": "#22c55e", "line-width": 2 }
      });
      map.addLayer({
        id: "aoi-point", type: "circle", source: "aoi",
        paint: {
          "circle-radius": 7, "circle-color": "#22c55e",
          "circle-stroke-width": 2, "circle-stroke-color": "#fff"
        }
      });

      // the in-progress shape, before it is finalized
      map.addSource("preview", { type: "geojson", data: EMPTY_FC });
      map.addLayer({
        id: "preview-fill", type: "fill", source: "preview",
        paint: { "fill-color": "#3b82f6", "fill-opacity": 0.15 }
      });
      map.addLayer({
        id: "preview-line", type: "line", source: "preview",
        paint: { "line-color": "#3b82f6", "line-width": 2, "line-dasharray": [3, 2] }
      });

      // a dot per clicked point, shown in every draw mode
      map.addSource("pts", { type: "geojson", data: EMPTY_FC });
      map.addLayer({
        id: "pts-circle", type: "circle", source: "pts",
        paint: {
          "circle-radius": 5, "circle-color": "#3b82f6",
          "circle-stroke-width": 2, "circle-stroke-color": "#fff"
        }
      });

      if (geometry) showFinalized(map, geometry);
      if (onDraw) attachEvents(map);
    });

    return () => map.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    if (geometry) {
      showFinalized(map, geometry);
      setIsDone(true);
    } else {
      clearAll(map);
      setIsDone(false);
    }
  }, [geometry]);

  function showFinalized(map: maplibregl.Map, geom: GeoJSON.Geometry) {
    setSource(map, "aoi", {
      type: "FeatureCollection",
      features: [{ type: "Feature", geometry: geom, properties: {} }]
    });
    if (geom.type === "Point") {
      const [lng, lat] = geom.coordinates as [number, number];
      map.fitBounds(
        [[lng - POINT_BUFFER, lat - POINT_BUFFER], [lng + POINT_BUFFER, lat + POINT_BUFFER]],
        { padding: 50 },
      );
    } else if (geom.type === "Polygon") {
      const coords = geom.coordinates[0];
      if (coords.length > 1) {
        const lngs = coords.map((c) => c[0]);
        const lats = coords.map((c) => c[1]);
        map.fitBounds(
          [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
          { padding: 50 },
        );
      }
    }
  }

  function clearAll(map: maplibregl.Map) {
    setSource(map, "aoi", EMPTY_FC);
    setSource(map, "preview", EMPTY_FC);
    setSource(map, "pts", EMPTY_FC);
  }

  function updatePolyPreview(map: maplibregl.Map, pts: [number, number][]) {
    // always show dots for every clicked point
    setSource(map, "pts", {
      type: "FeatureCollection",
      features: pts.map(([lng, lat]) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [lng, lat] },
        properties: {},
      })),
    });

    if (pts.length < 2) {
      setSource(map, "preview", EMPTY_FC);
      return;
    }
    if (pts.length === 2) {
      // show a line so you see something immediately
      setSource(map, "preview", {
        type: "FeatureCollection",
        features: [{
          type: "Feature",
          geometry: { type: "LineString", coordinates: pts }, properties: {}
        }],
      });
      return;
    }
    // 3+ — filled polygon closing back to first point
    setSource(map, "preview", {
      type: "FeatureCollection",
      features: [{
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [[...pts, pts[0]]] }, properties: {}
      }],
    });
  }

  function finalizePolygon(map: maplibregl.Map, pts: [number, number][]) {
    const polygon: GeoJSON.Polygon = { type: "Polygon", coordinates: [[...pts, pts[0]]] };
    onDraw!(polygon, "polygon");
    showFinalized(map, polygon);
    setSource(map, "preview", EMPTY_FC);
    setSource(map, "pts", EMPTY_FC);
    setIsDone(true);
  }

  function attachEvents(map: maplibregl.Map) {
    map.getCanvas().style.cursor = "crosshair";

    map.on("click", (e) => {
      const lng = e.lngLat.lng;
      const lat = e.lngLat.lat;

      if (modeRef.current === "point") {
        const poly = pointToBox(lng, lat);
        onDraw!(poly, "point");
        showFinalized(map, { type: "Point", coordinates: [lng, lat] });
        setSource(map, "pts", EMPTY_FC);
        setIsDone(true);
        return;
      }

      if (modeRef.current === "polygon") {
        polyPtsRef.current = [...polyPtsRef.current, [lng, lat]];
        setPolyCount(polyPtsRef.current.length);
        updatePolyPreview(map, polyPtsRef.current);
        return;
      }

      if (modeRef.current === "rectangle") {
        if (!rectStartRef.current) {
          // first click — set first corner, show a dot
          rectStartRef.current = [lng, lat];
          setSource(map, "pts", {
            type: "FeatureCollection",
            features: [{
              type: "Feature",
              geometry: { type: "Point", coordinates: [lng, lat] }, properties: {}
            }]
          });
          setPolyCount(1);
        } else {
          // second click — finalize
          const poly = rectFromCorners(rectStartRef.current, [lng, lat]);
          rectStartRef.current = null;
          setPolyCount(0);
          setSource(map, "pts", EMPTY_FC);
          onDraw!(poly, "rectangle");
          showFinalized(map, poly);
          setSource(map, "preview", EMPTY_FC);
          setIsDone(true);
        }
      }
    });

    // live rectangle preview while waiting for second click
    map.on("mousemove", (e) => {
      if (modeRef.current !== "rectangle" || !rectStartRef.current) return;
      const poly = rectFromCorners(rectStartRef.current, [e.lngLat.lng, e.lngLat.lat]);
      setSource(map, "preview", {
        type: "FeatureCollection",
        features: [{ type: "Feature", geometry: poly, properties: {} }]
      });
    });

    // polygon: right-click undoes last point
    map.on("contextmenu", (e) => {
      e.preventDefault();
      if (modeRef.current !== "polygon" || polyPtsRef.current.length === 0) return;
      polyPtsRef.current = polyPtsRef.current.slice(0, -1);
      setPolyCount(polyPtsRef.current.length);
      updatePolyPreview(map, polyPtsRef.current);
    });

    // polygon: double-click finishes
    map.on("dblclick", (e) => {
      e.preventDefault();
      if (modeRef.current !== "polygon") return;
      const pts = [...polyPtsRef.current, [e.lngLat.lng, e.lngLat.lat]] as [number, number][];
      if (pts.length >= 3) finalizePolygon(map, pts);
      polyPtsRef.current = [];
      setPolyCount(0);
    });
  }

  function switchMode(m: DrawMode) {
    const map = mapRef.current;
    setMode(m);
    modeRef.current = m;
    if (map) {
      polyPtsRef.current = [];
      rectStartRef.current = null;
      setPolyCount(0);
      setSource(map, "preview", EMPTY_FC);
      setSource(map, "pts", EMPTY_FC);
    }
  }

  function handleReset() {
    const map = mapRef.current;
    if (!map) return;
    polyPtsRef.current = [];
    rectStartRef.current = null;
    setPolyCount(0);
    setIsDone(false);
    clearAll(map);
    onClear?.();
  }

  function handleUndo() {
    const map = mapRef.current;
    if (!map || polyPtsRef.current.length === 0) return;
    polyPtsRef.current = polyPtsRef.current.slice(0, -1);
    setPolyCount(polyPtsRef.current.length);
    updatePolyPreview(map, polyPtsRef.current);
  }

  const inProgress = polyCount > 0 || isDone;

  return (
    <div className="relative">
      <div ref={containerRef} className={`rounded-lg overflow-hidden ${className}`} />

      {/* mode toolbar + clear — shown while drawing */}
      {onDraw && (
        <div className="absolute top-2 left-2 flex gap-1 z-10">
          {!isDone && (
            <>
              {(["rectangle", "point", "polygon"] as DrawMode[]).map((m) => (
                <button key={m} type="button" onClick={() => switchMode(m)}
                  title={m === "rectangle" ? "Draw bounding box (two clicks)" : m === "polygon" ? "Draw polygon (click points)" : "Place a point"}
                  className={`p-1.5 rounded border transition-colors ${mode === m
                    ? "bg-blue-700 border-blue-500 text-white"
                    : "bg-gray-900/90 border-gray-600 text-gray-300 hover:bg-gray-800"
                    }`}>
                  {m === "rectangle" ? (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <rect x="2" y="4" width="12" height="8" rx="0.5" />
                    </svg>
                  ) : m === "polygon" ? (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <polygon points="8,2 14,6 12,13 4,13 2,6" />
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                      <circle cx="8" cy="8" r="3.5" />
                    </svg>
                  )}
                </button>
              ))}
            </>
          )}
          {inProgress && (
            <>
              {polyCount > 0 && (
                <button type="button" onClick={handleUndo}
                  className="px-2.5 py-1 text-xs bg-gray-900/90 border border-gray-600 text-gray-200 rounded hover:bg-gray-800 transition-colors">
                  ↩ Undo ({polyCount})
                </button>
              )}
              <button type="button" onClick={handleReset}
                className="px-2.5 py-1 text-xs bg-gray-900/90 border border-red-700 text-red-300 rounded hover:bg-red-950/60 transition-colors">
                ✕ Clear
              </button>
            </>
          )}
        </div>
      )}

      {/* hint bar at bottom */}
      {onDraw && !isDone && (
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 z-10 pointer-events-none">
          <span className="px-2.5 py-1 text-xs bg-gray-900/80 text-gray-400 rounded whitespace-nowrap">
            {mode === "point"
              ? "Click to place a point"
              : mode === "rectangle"
                ? polyCount === 0
                  ? "Click to place the first corner"
                  : "Click to place the opposite corner"
                : polyCount === 0
                  ? "Click to add points · Double-click to finish · Right-click to undo"
                  : `${polyCount} point${polyCount !== 1 ? "s" : ""} placed · Double-click to finish · Right-click to undo`}
          </span>
        </div>
      )}
    </div>
  );
}
