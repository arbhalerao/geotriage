import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useCollections, useModels, useWorkflow, useWorkflowItem } from "../api/queries";
import SeverityBadge from "../components/SeverityBadge";
import StatusBadge from "../components/StatusBadge";
import MapViewer from "../components/MapViewer";
import DotLine from "../components/DotLine";
import Section from "../components/Section";
import { formatDate, formatDateTime } from "../time";

// per-band visualization parameters for TiTiler
// falls back to the default for unknown bands
// stored bands are calibrated to physical units — reflectance for optical,
// Kelvin for thermal — so these ranges are in those units, not digital numbers
const BAND_STYLE: Record<string, { colormap: string; rescale: string; label: string }> = {
  ndwi:     { colormap: "rdylbu",  rescale: "-0.5,0.5",     label: "NDWI" },
  lst:      { colormap: "inferno", rescale: "-10,60",       label: "LST (°C)" },
  green:    { colormap: "gray",    rescale: "0,0.5",        label: "Green" },
  nir:      { colormap: "gray",    rescale: "0,0.6",        label: "NIR" },
  red:      { colormap: "gray",    rescale: "0,0.5",        label: "Red" },
  blue:     { colormap: "gray",    rescale: "0,0.35",       label: "Blue" },
  thermal1: { colormap: "inferno", rescale: "250,320",      label: "Thermal (K)" },
};
// the colormaps above as CSS gradients, sampled from their matplotlib definitions, so the legend matches the tiles
const COLORMAP_GRADIENT: Record<string, string> = {
  inferno: "#000004, #420a68, #932667, #dd513a, #fca50a, #fcffa4",
  viridis: "#440154, #3b528b, #21918c, #5ec962, #fde725",
  gray: "#000000, #ffffff",
  rdylbu: "#a50026, #f46d43, #fee090, #e0f3f8, #74add1, #313695",
};

const BAND_STYLE_DEFAULT = { colormap: "viridis", rescale: "0,1", label: "" };

function bandStyle(name: string) {
  return BAND_STYLE[name] ?? { ...BAND_STYLE_DEFAULT, label: name };
}

function buildRasterUrl(workflowId: string, itemId: string, band: string): string {
  const { colormap, rescale } = bandStyle(band);
  const cogUrl = `s3://artifacts/${workflowId}/${itemId}/${band}.tif`;
  const params = new URLSearchParams({
    url: cogUrl,
    colormap_name: colormap,
    rescale,
  });
  return `/titiler/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?${params.toString()}`;
}

// the clipboard API only exists on secure pages (https or localhost); opened over plain http on a network address,
// fall back to selecting hidden text and copying it
async function copyToClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
    }
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    document.body.removeChild(area);
  }
}

function StacViewer({ stacItem }: { stacItem: object }) {
  const [query, setQuery] = useState("");
  const [copy, setCopy] = useState<"idle" | "copied" | "failed">("idle");
  const json = JSON.stringify(stacItem, null, 2);
  const lines = json.split("\n");

  // the whole item, whatever the search is filtering to
  async function copyJson() {
    const ok = await copyToClipboard(json);
    setCopy(ok ? "copied" : "failed");
    setTimeout(() => setCopy("idle"), 2000);
  }
  const q = query.trim().toLowerCase();
  const filtered = q ? lines.filter((l) => l.toLowerCase().includes(q)) : lines;

  return (
    <Section title="STAC item" defaultOpen={false} bodyClassName="">
      <div className="px-5 pb-3">
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Search keys or values"
            aria-label="Search the STAC item"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1 min-w-0 bg-gray-100 border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 placeholder-gray-500 focus:outline-none focus:border-brand-500"
          />
          <button
            type="button"
            onClick={copyJson}
            className={`shrink-0 min-w-24 whitespace-nowrap px-3 py-2 rounded text-sm transition-colors ${
              copy === "failed" ? "bg-red-50 text-red-700" : "bg-gray-100 hover:bg-gray-200 text-gray-700"
            }`}
          >
            <span aria-live="polite">{copy === "copied" ? "Copied" : copy === "failed" ? "Couldn't copy" : "Copy"}</span>
          </button>
        </div>
        {q && <p className="text-sm text-gray-500 mt-1">{filtered.length} line{filtered.length !== 1 ? "s" : ""} matched</p>}
      </div>
      <pre className="px-5 py-4 text-xs text-gray-700 overflow-auto max-h-[32rem] bg-gray-50 border-t border-gray-200 leading-relaxed">
        {filtered.map((line, i) => {
          if (!q) return line + "\n";
          const idx = line.toLowerCase().indexOf(q);
          return (
            <span key={i}>
              {line.slice(0, idx)}
              <mark className="bg-amber-200 text-gray-900 rounded-sm">{line.slice(idx, idx + q.length)}</mark>
              {line.slice(idx + q.length)}
              {"\n"}
            </span>
          );
        })}
      </pre>
    </Section>
  );
}

const SEVERITY_FILL: Record<string, string> = {
  green: "bg-green-500",
  yellow: "bg-amber-500",
  red: "bg-red-500",
};

const UNITLESS = new Set(["", "fraction", "index", "ratio"]);

function formatScore(value: number, unit: string | undefined): string {
  const digits = Math.abs(value) >= 100 ? 1 : 2;
  const text = value.toFixed(digits);
  return unit && !UNITLESS.has(unit) ? `${text} ${unit}` : text;
}

// without a declared range there is nothing honest to draw
function ScoreBar({ value, severity, range }: { value: number; severity: string; range?: [number, number] }) {
  if (!range || range[1] <= range[0]) return null;
  const pct = Math.max(0, Math.min(100, ((value - range[0]) / (range[1] - range[0])) * 100));
  return (
    <div className="flex items-center gap-3">
      <span className="w-12 shrink-0 text-right text-xs text-gray-500 tabular-nums">{range[0]}</span>
      <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
        <div className={`h-full rounded-full ${SEVERITY_FILL[severity] ?? "bg-gray-400"}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-12 shrink-0 text-xs text-gray-500 tabular-nums">{range[1]}</span>
    </div>
  );
}

export default function ItemDetailPage() {
  const { wfId, itemId } = useParams<{ wfId: string; itemId: string }>();
  const { data: item, isLoading } = useWorkflowItem(wfId!, itemId!);
  const { data: wf } = useWorkflow(wfId!);
  const { data: models } = useModels();
  const { data: collections } = useCollections();

  const [activeBand, setActiveBand] = useState<string | null>(null);

  // bands available for this item = union of required_bands + derived_rasters across the model runs that actually succeeded
  const availableBands = useMemo(() => {
    if (!item || !models) return [] as string[];
    const successfulSlugs = new Set(
      item.model_runs.filter((r) => r.status === "success").map((r) => r.model_slug),
    );
    const out = new Set<string>();
    for (const m of models) {
      if (!successfulSlugs.has(m.slug)) continue;
      (m.required_bands ?? []).forEach((b) => out.add(b));
      (m.derived_rasters ?? []).forEach((d) => out.add(d));
    }
    return Array.from(out);
  }, [item, models]);

  const [rasterOpacity, setRasterOpacity] = useState(0.75);

  const rasterUrl =
    activeBand && wfId && itemId ? buildRasterUrl(wfId, itemId, activeBand) : null;

  if (isLoading) return <div className="p-6 max-w-7xl mx-auto text-sm text-gray-500">Loading…</div>;
  if (!item) return <div className="p-6 max-w-7xl mx-auto text-sm text-red-700">Scene not found.</div>;

  const collectionName = collections?.find((c) => c.slug === item.collection_slug)?.display_name ?? item.collection_slug;
  const rawCloud = item.stac_item.properties["eo:cloud_cover"];
  const cloudCover = typeof rawCloud === "number" ? rawCloud : null;
  const footprint = item.bbox && item.bbox.length === 4
    ? [{ id: item.id, bbox: item.bbox as [number, number, number, number], severity: item.overall_severity, status: item.status }]
    : [];

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="text-xs text-gray-600 mb-4 flex items-center gap-1 min-w-0">
        <Link to="/workflows" className="shrink-0 hover:text-gray-800">Workflows</Link>
        <span>/</span>
        <Link to={`/workflows/${wfId}`} className="truncate hover:text-gray-800">{wf?.name ?? wfId}</Link>
        <span>/</span>
        <span className="truncate text-gray-700">{item.stac_item_id}</span>
      </div>

      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900 mb-1 break-words">{item.stac_item_id}</h1>
        <DotLine parts={[
          formatDate(item.scene_datetime),
          <StatusBadge status={item.status} />,
          <SeverityBadge severity={item.overall_severity} status={item.status} />,
          collectionName,
          cloudCover != null ? `${Math.round(cloudCover)}% cloud` : null,
        ]} />
      </div>

      {(wf?.aoi_geometry || item.stac_item.bbox) && (
        <Section title="Map: AOI &amp; scene footprint" bodyClassName="">
          {availableBands.length > 0 && (
            <div className="px-5 pb-4 space-y-3">
              <div className="flex items-end justify-between gap-4 flex-wrap">
                <fieldset>
                  <legend className="block text-sm mb-1 text-gray-700">Overlay</legend>
                  <div className="flex gap-2 flex-wrap">
                    {[null, ...availableBands].map((b) => {
                      const selected = activeBand === b;
                      return (
                        <label
                          key={b ?? "none"}
                          className={`px-2.5 py-1 rounded border text-xs cursor-pointer transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand-500 ${
                            selected ? "border-brand-500 bg-brand-50 text-gray-900" : "border-gray-300 text-gray-600 hover:border-gray-400"
                          }`}
                        >
                          <input type="radio" name="overlay" checked={selected} onChange={() => setActiveBand(b)} className="sr-only" />
                          {b === null ? "None" : bandStyle(b).label || b}
                        </label>
                      );
                    })}
                  </div>
                </fieldset>

                {activeBand && (
                  <div className="flex items-center gap-4">
                    <label className="flex items-center gap-2 text-xs">
                      <span className="text-gray-500">Opacity</span>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={rasterOpacity}
                        onChange={(e) => setRasterOpacity(parseFloat(e.target.value))}
                        className="w-24 accent-brand-500"
                      />
                      <span className="text-gray-600 w-10 tabular-nums">{Math.round(rasterOpacity * 100)}%</span>
                    </label>
                    <a
                      href={`/api/workflows/${wfId}/items/${itemId}/assets/${activeBand}`}
                      download={`${activeBand}.tif`}
                      className="px-2.5 py-1 rounded text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 transition-colors"
                    >
                      Download GeoTIFF
                    </a>
                  </div>
                )}
              </div>

              {activeBand && (() => {
                const style = bandStyle(activeBand);
                const [low, high] = style.rescale.split(",");
                return (
                  <div className="flex items-center gap-3 text-sm text-gray-600">
                    <span className="tabular-nums">{low}</span>
                    <div
                      className="h-2.5 w-56 rounded-full border border-gray-200"
                      style={{ background: `linear-gradient(to right, ${COLORMAP_GRADIENT[style.colormap] ?? COLORMAP_GRADIENT.viridis})` }}
                      aria-hidden
                    />
                    <span className="tabular-nums">{high}</span>
                    <span className="text-gray-500">{style.label || activeBand}</span>
                  </div>
                );
              })()}
            </div>
          )}
          <MapViewer
            aoi={wf?.aoi_geometry}
            items={footprint}
            rasterUrl={rasterUrl}
            rasterOpacity={rasterOpacity}
            className="h-80 w-full border-t border-gray-200"
          />
        </Section>
      )}

      <Section title="Model runs">
        {item.model_runs.length === 0 && <p className="text-sm text-gray-500">No model runs yet.</p>}
        <div className="divide-y divide-gray-200">
          {item.model_runs.map((run) => {
            const model = models?.find((m) => m.slug === run.model_slug);
            return (
              <div key={run.id} className="py-4 first:pt-0 last:pb-0">
                <div className="flex items-baseline justify-between gap-4 mb-3">
                  <DotLine parts={[
                    <span className="font-medium text-gray-900">{model?.name ?? run.model_slug}</span>,
                    <StatusBadge status={run.status} />,
                  ]} />
                  {run.completed_at && <span className="shrink-0 text-sm text-gray-500">{formatDateTime(run.completed_at)}</span>}
                </div>
                {run.error_message && (
                  <div className="mb-3 rounded border border-red-200 bg-red-50/60 px-3 py-2 text-sm text-red-800">{run.error_message}</div>
                )}
                {run.scores.length === 0 && !run.error_message && <p className="text-sm text-gray-500">No scores.</p>}
                <div className="space-y-4">
                  {run.scores.map((score) => {
                    const output = model?.score_outputs[score.score_name];
                    return (
                      <div key={score.score_name}>
                        <div className="flex items-baseline justify-between gap-4 mb-1.5 text-sm">
                          <span className="text-gray-900">
                            {score.score_name}
                            {score.is_primary && <span className="ml-1.5 text-gray-500">(primary)</span>}
                          </span>
                          <span className="flex items-baseline gap-3">
                            <span className="text-gray-900 tabular-nums">{formatScore(score.score_value, output?.unit)}</span>
                            <SeverityBadge severity={score.severity} />
                          </span>
                        </div>
                        <ScoreBar value={score.score_value} severity={score.severity} range={output?.value_range} />
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </Section>

      <StacViewer stacItem={item.stac_item} />

      <div className="mt-4 text-sm text-gray-500">
        Discovered {formatDateTime(item.discovered_at)}
        {item.processed_at ? ` · Processed ${formatDateTime(item.processed_at)}` : ""}
      </div>
    </div>
  );
}
