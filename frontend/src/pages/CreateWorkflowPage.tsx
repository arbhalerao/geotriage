import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useCollections,
  useCreateWorkflow,
  useModels,
} from "../api/queries";
import Map from "../components/Map";
import type { ModelInfo, ThresholdBand } from "../api/types";

interface ThresholdOverride {
  green_min: number; green_max: number;
  yellow_min: number; yellow_max: number;
}
type ModelThresholds = Record<string, ThresholdOverride>;

function defaultOverrides(thresholds: Record<string, ThresholdBand>): ModelThresholds {
  return Object.fromEntries(
    Object.entries(thresholds).map(([score, t]) => [
      score,
      {
        green_min: t.green[0], green_max: t.green[1],
        yellow_min: t.yellow[0], yellow_max: t.yellow[1]
      },
    ])
  );
}

const COMPAT_STYLES: Record<string, string> = {
  full: "bg-green-100 text-green-700 border-green-300 dark:bg-green-900/60 dark:text-green-300 dark:border-green-800",
  partial: "bg-yellow-100 text-yellow-700 border-yellow-300 dark:bg-yellow-900/60 dark:text-yellow-300 dark:border-yellow-800",
  incompatible: "bg-red-100 text-red-700 border-red-300 dark:bg-red-900/50 dark:text-red-400 dark:border-red-900",
};

function CompatBadge({ level, reasons }: { level: string; reasons: string[] }) {
  const cls = COMPAT_STYLES[level] ?? "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-300 dark:border-gray-700";
  return (
    <span className={`relative group inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded border ${cls}`}>
      {level}
      {reasons.length > 0 && level !== "incompatible" && (
        <>
          <span className="cursor-default underline decoration-dotted">!</span>
          <span className="pointer-events-none absolute left-0 top-full mt-1 z-20 w-60 rounded bg-gray-50 dark:bg-gray-950 border border-gray-300 dark:border-gray-700 px-2 py-1.5 text-xs text-gray-700 dark:text-gray-300 shadow-lg opacity-0 group-hover:opacity-100 transition-opacity whitespace-normal">
            {reasons.map((r, i) => <span key={i} className="block">{r}</span>)}
          </span>
        </>
      )}
    </span>
  );
}

function ThresholdEditor({ model, overrides, onChange }: {
  model: ModelInfo;
  overrides: ModelThresholds;
  onChange: (next: ModelThresholds) => void;
}) {
  function set(score: string, field: keyof ThresholdOverride, raw: string) {
    const val = parseFloat(raw);
    if (!isNaN(val)) onChange({ ...overrides, [score]: { ...overrides[score], [field]: val } });
  }

  return (
    <div className="mt-3 border-t border-gray-300 dark:border-gray-700 pt-3 space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-700 dark:text-gray-300">Thresholds</span>
        <button type="button" onClick={() => onChange(defaultOverrides(model.default_thresholds))}
          className="text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">Reset defaults</button>
      </div>
      {Object.entries(model.default_thresholds).map(([score]) => {
        const ov = overrides[score];
        if (!ov) return null;
        return (
          <div key={score}>
            <div className="text-xs text-gray-600 dark:text-gray-400 mb-2 font-medium">{score}</div>
            <div className="grid grid-cols-3 gap-2 text-xs">
              {(["green", "yellow", "red"] as const).map((color) => (
                <div key={color}>
                  <div className={`mb-1 font-medium ${color === "green" ? "text-green-400" : color === "yellow" ? "text-yellow-400" : "text-red-400"}`}>{color}</div>
                  <div className="flex gap-1 items-center">
                    <input type="number" step="0.01" value={ov[`${color}_min` as keyof ThresholdOverride]}
                      onChange={(e) => set(score, `${color}_min` as keyof ThresholdOverride, e.target.value)}
                      className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-1.5 py-1 text-xs text-gray-800 dark:text-gray-200 focus:outline-none focus:border-brand-500" />
                    <span className="text-gray-500 dark:text-gray-600">–</span>
                    <input type="number" step="0.01" value={ov[`${color}_max` as keyof ThresholdOverride]}
                      onChange={(e) => set(score, `${color}_max` as keyof ThresholdOverride, e.target.value)}
                      className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-1.5 py-1 text-xs text-gray-800 dark:text-gray-200 focus:outline-none focus:border-brand-500" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function CreateWorkflowPage() {
  const navigate = useNavigate();
  const { data: collections } = useCollections();
  const { data: models } = useModels();
  const createWorkflow = useCreateWorkflow();

  const [name, setName] = useState("");
  const [mode, setMode] = useState<"historical" | "fixed_future">("historical");
  const [timeStart, setTimeStart] = useState("");
  const [timeEnd, setTimeEnd] = useState("");
  const [pollInterval, setPollInterval] = useState<number | null>(null);

  const [drawnGeometry, setDrawnGeometry] = useState<GeoJSON.Polygon | null>(null);
  const [drawnWithTool, setDrawnWithTool] = useState<"rectangle" | "polygon" | "point" | null>(null);
  const [aoiFilterMode, setAoiFilterMode] = useState<"intersects" | "enclosed">("intersects");

  const isPoint = drawnWithTool === "point";

  const [selectedModelSlug, setSelectedModelSlug] = useState<string | null>(null);
  const [selectedCollections, setSelectedCollections] = useState<string[]>([]);
  const [thresholdOverrides, setThresholdOverrides] = useState<ModelThresholds>({});
  const [thresholdsOpen, setThresholdsOpen] = useState(false);

  const selectedModel = (models ?? []).find((m) => m.slug === selectedModelSlug) ?? null;

  function selectModel(slug: string) {
    const m = (models ?? []).find((x) => x.slug === slug);
    if (!m) return;
    setSelectedModelSlug(slug);
    setThresholdOverrides(defaultOverrides(m.default_thresholds));
    setThresholdsOpen(false);

    const compatible = (collections ?? [])
      .filter((col) => {
        const c = m.compatible_collections[col.slug];
        return c && c.level !== "incompatible";
      })
      .map((col) => col.slug);
    setSelectedCollections(compatible);
  }

  function clearModel() {
    setSelectedModelSlug(null);
    setSelectedCollections([]);
    setThresholdOverrides({});
    setThresholdsOpen(false);
  }

  function toggleCollection(slug: string) {
    setSelectedCollections((prev) =>
      prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug]
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const wf = await createWorkflow.mutateAsync({
      name,
      geometry: drawnGeometry,
      aoi_filter_mode: aoiFilterMode,
      time_mode: mode,
      time_start: new Date(timeStart).toISOString(),
      time_end: new Date(timeEnd).toISOString(),
      poll_interval_minutes: mode === "fixed_future" ? pollInterval : null,
      collection_slugs: selectedCollections,
      models: [{
        model_slug: selectedModelSlug!,
        thresholds: thresholdOverrides,
      }],
    });
    navigate(`/workflows/${wf.id}`);
  }

  const canSubmit =
    !!name && !!drawnGeometry && !!timeStart && !!timeEnd &&
    !!selectedModelSlug && selectedCollections.length > 0;

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-6">New workflow</h1>

      <form onSubmit={handleSubmit} className="space-y-6">

        {/* 1 details */}
        <section className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-5 space-y-4">
          <h2 className="font-medium text-gray-800 dark:text-gray-200">Details</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm mb-1 text-gray-700 dark:text-gray-300">Name</label>
              <input required value={name} onChange={(e) => setName(e.target.value)}
                className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
            </div>
            <div>
              <label className="block text-sm mb-1 text-gray-700 dark:text-gray-300">Mode</label>
              <select value={mode} onChange={(e) => setMode(e.target.value as "historical" | "fixed_future")}
                className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-brand-500">
                <option value="historical">Historical</option>
                <option value="fixed_future">Fixed future</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm mb-1 text-gray-700 dark:text-gray-300">Time start</label>
              <input type="date" required value={timeStart} onChange={(e) => setTimeStart(e.target.value)}
                className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
            </div>
            <div>
              <label className="block text-sm mb-1 text-gray-700 dark:text-gray-300">Time end</label>
              <input type="date" required value={timeEnd} onChange={(e) => setTimeEnd(e.target.value)}
                className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
            </div>
          </div>

          {mode === "fixed_future" && (
            <div>
              <label className="block text-sm mb-1 text-gray-700 dark:text-gray-300">
                Monitor interval
                <span className="ml-1.5 text-gray-500 font-normal text-xs">— how often to fetch new scenes</span>
              </label>
              <div className="flex gap-2 flex-wrap">
                {([
                  { label: "Off", value: null },
                  { label: "1 hour", value: 60 },
                  { label: "6 hours", value: 360 },
                  { label: "12 hours", value: 720 },
                  { label: "Daily", value: 1440 },
                  { label: "Weekly", value: 10080 },
                ] as { label: string; value: number | null }[]).map(({ label, value }) => (
                  <button
                    key={label}
                    type="button"
                    onClick={() => setPollInterval(value)}
                    className={`px-3 py-1.5 rounded border text-xs transition-colors ${pollInterval === value
                      ? "border-brand-500 bg-brand-950/30 text-gray-900 dark:text-white"
                      : "border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-gray-400 dark:hover:border-gray-500"
                      }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {pollInterval === null && (
                <p className="text-xs text-gray-500 mt-1.5">No automatic re-fetching. You can trigger it manually.</p>
              )}
            </div>
          )}
        </section>

        {/* 2 AOI */}
        <section className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-5 space-y-3">
          <h2 className="font-medium text-gray-800 dark:text-gray-200">Area of Interest</h2>
          <Map
            geometry={drawnGeometry}
            onDraw={(geom, tool) => { setDrawnGeometry(geom); setDrawnWithTool(tool); if (tool === "point") setAoiFilterMode("intersects"); }}
            onClear={() => { setDrawnGeometry(null); setDrawnWithTool(null); }}
            className="h-96 w-full"
          />

          <div>
            <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">Scene filter</p>
            {isPoint ? (
              <p className="text-xs text-gray-500">Point AOI — scenes containing the point (intersects).</p>
            ) : (
              <div className="flex gap-2">
                {([
                  { value: "intersects", label: "Intersects", desc: "Any overlap with the AOI" },
                  { value: "enclosed", label: "Enclosed", desc: "≥80% of scene within the AOI" },
                ] as const).map(({ value, label, desc }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setAoiFilterMode(value)}
                    className={`flex-1 px-3 py-2 rounded border text-left transition-colors ${aoiFilterMode === value
                      ? "border-brand-500 bg-brand-950/30 text-gray-900 dark:text-white"
                      : "border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-gray-400 dark:hover:border-gray-500"
                      }`}
                  >
                    <div className="text-xs font-medium">{label}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{desc}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </section>

        {/* 3 model */}
        <section className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-5 space-y-3">
          <h2 className="font-medium text-gray-800 dark:text-gray-200">Model</h2>
          <p className="text-xs text-gray-500">Select one model. Compatible data sources will be shown below.</p>
          <div className="space-y-2">
            {models?.map((m) => {
              const selected = selectedModelSlug === m.slug;
              return (
                <div key={m.slug} className={`rounded border transition-colors ${selected ? "border-brand-600 bg-brand-950/20" : "border-gray-300 dark:border-gray-700"}`}>
                  <label className="flex items-start gap-3 p-3 cursor-pointer">
                    <input type="radio" name="model" checked={selected}
                      onChange={() => selected ? clearModel() : selectModel(m.slug)}
                      className="mt-0.5 accent-brand-500" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium">{m.name}</div>
                      <div className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">{m.description}</div>
                      <div className="flex flex-wrap gap-3 mt-1 text-xs text-gray-500">
                        <span>Bands: {m.required_bands.join(", ")}</span>
                        <span>{m.max_cloud_cover != null ? `≤${m.max_cloud_cover}% cloud` : "no cloud filter"}</span>
                      </div>
                    </div>
                    {selected && (
                      <button type="button"
                        onClick={(e) => { e.preventDefault(); setThresholdsOpen((o) => !o); }}
                        className="text-xs text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 whitespace-nowrap mt-0.5">
                        {thresholdsOpen ? "Hide thresholds ▲" : "Edit thresholds ▼"}
                      </button>
                    )}
                  </label>
                  {selected && thresholdsOpen && (
                    <div className="px-4 pb-4">
                      <ThresholdEditor
                        model={m}
                        overrides={thresholdOverrides}
                        onChange={setThresholdOverrides}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* 4 data sources */}
        <section className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-5 space-y-3">
          <h2 className="font-medium text-gray-800 dark:text-gray-200">Data sources</h2>

          {!selectedModel ? (
            <p className="text-sm text-gray-500">Select a model above to see compatible data sources.</p>
          ) : (
            <>
              <p className="text-xs text-gray-500">
                Compatible sources are auto-selected. Incompatible sources cannot be used with this model.
              </p>
              <div className="space-y-2">
                {(collections ?? []).map((col) => {
                  const compat = selectedModel.compatible_collections[col.slug]
                    ?? { level: "incompatible", reasons: ["Not declared compatible"] };
                  const isIncompat = compat.level === "incompatible";
                  const checked = selectedCollections.includes(col.slug);

                  return (
                    <label
                      key={col.slug}
                      className={`flex items-start gap-3 p-3 rounded border transition-colors ${
                        isIncompat
                          ? "border-gray-200 dark:border-gray-800 opacity-40 cursor-not-allowed"
                          : "border-gray-300 dark:border-gray-700 cursor-pointer hover:border-gray-300 dark:hover:border-gray-600"
                      }`}
                      title={isIncompat ? "This collection is not supported by this model" : undefined}
                    >
                      <input
                        type="checkbox"
                        checked={checked && !isIncompat}
                        disabled={isIncompat}
                        onChange={() => toggleCollection(col.slug)}
                        className="mt-0.5 accent-brand-500"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium">{col.display_name}</span>
                          <span className="text-xs text-gray-500">{col.processing_level} · {col.resolution_m}m</span>
                          <CompatBadge level={compat.level} reasons={compat.reasons} />
                        </div>
                        {isIncompat && compat.reasons.length > 0 && (
                          <p className="text-xs text-gray-500 mt-1">{compat.reasons.join(". ")}</p>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>
            </>
          )}
        </section>

        {createWorkflow.error && (
          <p className="text-red-400 text-sm">{(createWorkflow.error as Error).message}</p>
        )}

        <div className="flex gap-3">
          <button type="submit" disabled={createWorkflow.isPending || !canSubmit}
            className="px-6 py-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white rounded text-sm font-medium transition-colors">
            {createWorkflow.isPending ? "Creating…" : "Create workflow"}
          </button>
          <button type="button" onClick={() => navigate("/workflows")}
            className="px-6 py-2 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded text-sm transition-colors">
            Cancel
          </button>
          {!canSubmit && name && (
            <span className="text-xs text-gray-500 self-center">
              {!drawnGeometry
                ? "Draw an area of interest on the map"
                : !selectedModelSlug
                  ? "Select a model"
                  : selectedCollections.length === 0
                    ? "Select at least one data source"
                    : ""}
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
