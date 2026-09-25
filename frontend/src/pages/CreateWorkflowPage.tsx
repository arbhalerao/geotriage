import { useCallback, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import {
  useCollections,
  useCreateWorkflow,
  useModels,
} from "../api/queries";
import Map from "../components/Map";
import Chevron from "../components/Chevron";
import DateField from "../components/DateField";
import { useStorageEstimate } from "../components/StorageEstimate";
import { DEFAULT_POLICY, type StoragePolicy } from "../storagePolicy";
import WorkflowBuilder from "../components/WorkflowBuilder";
import type { BuilderDraft, EstimateRequest, ModelInfo, StorageEstimateResult, ThresholdBand } from "../api/types";
import { dayAfter, startOfDayUtc, todayUtc } from "../time";

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

// a collection the model doesn't declare is treated as unusable
function compatibility(model: ModelInfo, collectionSlug: string) {
  return model.compatible_collections[collectionSlug] ?? { level: "incompatible", reasons: ["not declared compatible"] };
}

const BANDS = [
  { key: "green", label: "Green", cls: "text-green-700" },
  { key: "yellow", label: "Yellow", cls: "text-amber-700" },
] as const;

function ThresholdEditor({ model, overrides, onChange }: {
  model: ModelInfo;
  overrides: ModelThresholds;
  onChange: (next: ModelThresholds) => void;
}) {
  function set(score: string, field: keyof ThresholdOverride, raw: string) {
    const val = parseFloat(raw);
    if (!isNaN(val)) onChange({ ...overrides, [score]: { ...overrides[score], [field]: val } });
  }

  const input = "w-full bg-gray-100 border border-gray-300 rounded px-2 py-1.5 text-sm text-gray-900 focus:outline-none focus:border-brand-500";

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button type="button" onClick={() => onChange(defaultOverrides(model.default_thresholds))}
          className="text-sm text-gray-500 hover:text-gray-900">Reset defaults</button>
      </div>
      {Object.keys(model.default_thresholds).map((score) => {
        const ov = overrides[score];
        if (!ov) return null;
        return (
          <div key={score}>
            <div className="text-sm text-gray-900 mb-2">{score}</div>
            <div className="grid grid-cols-3 gap-4 text-sm">
              {BANDS.map(({ key, label, cls }) => (
                <div key={key}>
                  <div className={`mb-1 ${cls}`}>{label}</div>
                  <div className="flex gap-2 items-center">
                    <input type="number" step="0.01" aria-label={`${score} ${label} from`} value={ov[`${key}_min`]}
                      onChange={(e) => set(score, `${key}_min`, e.target.value)} className={input} />
                    <span className="text-gray-500">to</span>
                    <input type="number" step="0.01" aria-label={`${score} ${label} to`} value={ov[`${key}_max`]}
                      onChange={(e) => set(score, `${key}_max`, e.target.value)} className={input} />
                  </div>
                </div>
              ))}
              <div>
                <div className="mb-1 text-red-700">Red</div>
                <div className="py-1.5 text-gray-500">anything else</div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

const INTERVALS = [
  { label: "1 hour", value: 60 },
  { label: "6 hours", value: 360 },
  { label: "12 hours", value: 720 },
  { label: "Daily", value: 1440 },
  { label: "Weekly", value: 10080 },
];

type Mode = "historical" | "recurring";

// the builder may pick any interval; the form offers five, so it lands on the closest
function nearestInterval(minutes: number): number {
  return INTERVALS.reduce((best, { value }) => (Math.abs(value - minutes) < Math.abs(best - minutes) ? value : best), INTERVALS[0].value);
}

function FormSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    // keep the title style in step with components/Section
    <section className="bg-white border border-gray-200 rounded-lg px-5 pt-4 pb-5 space-y-4">
      <h2 className="text-sm font-medium text-gray-800">{title}</h2>
      {children}
    </section>
  );
}

export default function CreateWorkflowPage() {
  const navigate = useNavigate();
  const { data: collections } = useCollections();
  const { data: models } = useModels();
  const createWorkflow = useCreateWorkflow();
  const [drafting, setDrafting] = useState(false);
  // two ways in, neither chosen for you; the form only appears once it has something to show
  const [start, setStart] = useState<"describe" | "manual" | null>(null);
  const [hasDraft, setHasDraft] = useState(false);
  // a draft's estimate, handed to the storage section; the token tells a new draft from the last one
  const [estimateSeed, setEstimateSeed] = useState<{ result: StorageEstimateResult; token: number } | null>(null);

  const [name, setName] = useState("");
  const [mode, setMode] = useState<Mode>("historical");
  const [timeStart, setTimeStart] = useState("");
  const [timeEnd, setTimeEnd] = useState("");
  const [pollInterval, setPollInterval] = useState(1440);
  const [storagePolicy, setStoragePolicy] = useState<StoragePolicy>(DEFAULT_POLICY);

  const today = todayUtc();
  const endMax = mode === "historical" ? today : undefined;
  // a recurring workflow starts on creation, and a picked day means its midnight UTC, which for today has passed; so it ends tomorrow at the earliest
  const endMin = mode === "recurring" ? dayAfter(today) : timeStart ? dayAfter(timeStart) : undefined;

  function changeMode(next: Mode) {
    setMode(next);
    if (next === "historical" && timeEnd > today) setTimeEnd("");
    if (next === "recurring" && timeEnd && timeEnd <= today) setTimeEnd("");
  }

  function changeStart(day: string) {
    setTimeStart(day);
    if (timeEnd && timeEnd <= day) setTimeEnd("");
  }

  const [drawnGeometry, setDrawnGeometry] = useState<GeoJSON.Polygon | null>(null);
  const [drawnWithTool, setDrawnWithTool] = useState<"rectangle" | "polygon" | "point" | null>(null);
  const [aoiFilterMode, setAoiFilterMode] = useState<"intersects" | "enclosed">("intersects");

  const isPoint = drawnWithTool === "point";

  const [selectedModelSlug, setSelectedModelSlug] = useState<string | null>(null);
  const [selectedCollections, setSelectedCollections] = useState<string[]>([]);
  const [thresholdOverrides, setThresholdOverrides] = useState<ModelThresholds>({});
  const [thresholdsOpen, setThresholdsOpen] = useState(false);

  const selectedModel = (models ?? []).find((m) => m.slug === selectedModelSlug) ?? null;

  // the form is linear: sources are chosen for a model, so changing the model starts them over
  function selectModel(slug: string) {
    const m = (models ?? []).find((x) => x.slug === slug);
    if (!m) return;
    setSelectedModelSlug(slug);
    setSelectedCollections([]);
    setThresholdOverrides(defaultOverrides(m.default_thresholds));
    setThresholdsOpen(false);
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

  // a draft fills the same fields a person would, so everything stays editable before Create
  const applyDraft = useCallback(
    (draft: BuilderDraft, estimate: StorageEstimateResult | null) => {
      setHasDraft(true);
      setEstimateSeed(estimate ? { result: estimate, token: Date.now() } : null);
      const model = (models ?? []).find((m) => m.slug === draft.models[0]?.model_slug);
      setName(draft.name);
      setMode(draft.time_mode);
      setTimeStart(draft.time_mode === "historical" && draft.time_start ? draft.time_start.slice(0, 10) : "");
      setTimeEnd(draft.time_end.slice(0, 10));
      if (draft.poll_interval_minutes) setPollInterval(nearestInterval(draft.poll_interval_minutes));
      setDrawnGeometry(draft.geometry);
      setDrawnWithTool("rectangle");
      setAoiFilterMode("intersects");
      if (!model) {
        clearModel();
        return;
      }
      setSelectedModelSlug(model.slug);
      setThresholdOverrides(defaultOverrides(model.default_thresholds));
      setThresholdsOpen(false);
      setSelectedCollections(draft.collection_slugs.filter((slug) => compatibility(model, slug).level !== "incompatible"));
    },
    [models],
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    // Enter in a field submits a form even with the button disabled, so the same rule is checked here
    if (!canSubmit || !storage.estimated || drafting) return;
    const wf = await createWorkflow.mutateAsync({
      name,
      geometry: drawnGeometry,
      aoi_filter_mode: aoiFilterMode,
      time_mode: mode,
      // a recurring workflow's start is set by the server when it is created
      time_start: mode === "historical" ? startOfDayUtc(timeStart) : null,
      time_end: startOfDayUtc(timeEnd),
      poll_interval_minutes: mode === "recurring" ? pollInterval : null,
      collection_slugs: selectedCollections,
      models: [{
        model_slug: selectedModelSlug!,
        thresholds: thresholdOverrides,
      }],
      storage_policy: storagePolicy,
    });
    navigate(`/workflows/${wf.id}`);
  }

  const datesValid =
    mode === "recurring"
      ? !!timeEnd && timeEnd > today
      : !!timeStart && !!timeEnd && timeStart <= today && timeEnd > timeStart && timeEnd <= today;

  const formVisible = start === "manual" || (start === "describe" && hasDraft);

  // everything the data a workflow stages depends on, once all of it is set; sorted, so ticking collections in another order is no change
  const estimateRequest = useMemo<EstimateRequest | null>(() => {
    if (!drawnGeometry || !datesValid || !selectedModelSlug || selectedCollections.length === 0) return null;
    return {
      geometry: drawnGeometry,
      time_mode: mode,
      time_start: mode === "historical" ? startOfDayUtc(timeStart) : null,
      time_end: startOfDayUtc(timeEnd),
      poll_interval_minutes: mode === "recurring" ? pollInterval : null,
      collection_slugs: [...selectedCollections].sort(),
      models: [{ model_slug: selectedModelSlug }],
    };
  }, [drawnGeometry, datesValid, selectedModelSlug, selectedCollections, mode, timeStart, timeEnd, pollInterval]);

  // creating waits for a current estimate, so nobody creates a workflow without seeing what it stages
  const storage = useStorageEstimate(estimateRequest, estimateSeed, storagePolicy, setStoragePolicy);

  const canSubmit =
    !!name && !!drawnGeometry && datesValid &&
    !!selectedModelSlug && selectedCollections.length > 0;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-xl font-semibold mb-6">New workflow</h1>

      <form onSubmit={handleSubmit} className="space-y-6">

        {/* 0 how to start, the choice on its own; whichever is picked opens its sections below, like the rest of the form */}
        <fieldset disabled={drafting} aria-label="How to start" className="flex gap-2">
          {([
            { value: "describe", label: "Describe it", desc: "Type a sentence and review the form it fills in" },
            { value: "manual", label: "Fill it in yourself", desc: "Choose each setting in the form" },
          ] as const).map(({ value, label, desc }) => (
            <label
              key={value}
              className={`flex-1 px-3 py-2 rounded border text-left cursor-pointer transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand-500 has-[:disabled]:cursor-not-allowed ${
                start === value ? "border-brand-500 bg-brand-50 text-gray-900" : "border-gray-300 bg-white text-gray-600 hover:border-gray-400"
              }`}
            >
              <input type="radio" name="start" value={value} checked={start === value} onChange={() => setStart(value)} className="sr-only" />
              <div className="text-xs font-medium">{label}</div>
              <div className="text-xs text-gray-500 mt-0.5">{desc}</div>
            </label>
          ))}
        </fieldset>

        {start === "describe" && (
          <FormSection title="Describe">
            <WorkflowBuilder onDraft={applyDraft} onWorkingChange={setDrafting} />
          </FormSection>
        )}

        {formVisible && (
        // while a new draft is worked on the form waits, since the draft would overwrite anything typed meanwhile;
        // a disabled fieldset stops the inputs, and pointer-events stops the map, which isn't an input
        <fieldset disabled={drafting} aria-busy={drafting} className={`min-w-0 space-y-6 transition-opacity ${drafting ? "opacity-50 pointer-events-none select-none" : ""}`}>

        {/* 1 details */}
        <FormSection title="Details">
          <div>
            <label className="block text-sm mb-1 text-gray-700">Name</label>
            <input required value={name} onChange={(e) => setName(e.target.value)}
              className="w-full bg-gray-100 border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
          </div>

          <fieldset>
            <legend className="block text-sm mb-1 text-gray-700">Mode</legend>
            <div className="flex gap-2">
              {([
                { value: "historical", label: "Historical", desc: "Runs once over a past date range" },
                { value: "recurring", label: "Recurring", desc: "Keeps checking for new scenes until the end date" },
              ] as const).map(({ value, label, desc }) => (
                <label
                  key={value}
                  className={`flex-1 px-3 py-2 rounded border text-left cursor-pointer transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand-500 ${
                    mode === value ? "border-brand-500 bg-brand-50 text-gray-900" : "border-gray-300 text-gray-600 hover:border-gray-400"
                  }`}
                >
                  <input type="radio" name="mode" value={value} checked={mode === value} onChange={() => changeMode(value)} className="sr-only" />
                  <div className="text-xs font-medium">{label}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{desc}</div>
                </label>
              ))}
            </div>
          </fieldset>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm mb-1 text-gray-700">Time start (UTC)</label>
              <DateField label="Time start (UTC)" value={mode === "recurring" ? today : timeStart} max={today} disabled={mode === "recurring"} onChange={changeStart} />
            </div>
            <div>
              <label className="block text-sm mb-1 text-gray-700">Time end (UTC)</label>
              <DateField label="Time end (UTC)" value={timeEnd} min={endMin} max={endMax} onChange={setTimeEnd} />
            </div>
          </div>

          {mode === "recurring" && (
            <div>
              <label className="block text-sm mb-1 text-gray-700">
                Monitor interval
                <span className="ml-1.5 text-gray-500 font-normal text-xs">(how often to fetch new scenes)</span>
              </label>
              <div className="flex gap-2 flex-wrap">
                {INTERVALS.map(({ label, value }) => (
                  <button
                    key={label}
                    type="button"
                    onClick={() => setPollInterval(value)}
                    className={`px-3 py-1.5 rounded border text-xs transition-colors ${pollInterval === value
                      ? "border-brand-500 bg-brand-50 text-gray-900"
                      : "border-gray-300 text-gray-600 hover:border-gray-400"
                      }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </FormSection>

        {/* 2 AOI */}
        <FormSection title="Area of Interest">
          <Map
            geometry={drawnGeometry}
            onDraw={(geom, tool) => { setDrawnGeometry(geom); setDrawnWithTool(tool); if (tool === "point") setAoiFilterMode("intersects"); }}
            onClear={() => { setDrawnGeometry(null); setDrawnWithTool(null); }}
            className="h-96 w-full"
          />

          <div>
            <p className="text-xs text-gray-600 mb-2">Scene filter</p>
            {isPoint ? (
              <p className="text-xs text-gray-500">Point AOI: scenes containing the point (intersects).</p>
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
                      ? "border-brand-500 bg-brand-50 text-gray-900"
                      : "border-gray-300 text-gray-600 hover:border-gray-400"
                      }`}
                  >
                    <div className="text-xs font-medium">{label}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{desc}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </FormSection>

        {/* 3 model */}
        <FormSection title="Model">
          <div className="space-y-2">
            {models?.map((m) => {
              const selected = selectedModelSlug === m.slug;
              return (
                <div key={m.slug} className={`rounded border overflow-hidden transition-colors ${selected ? "border-brand-600" : "border-gray-300"}`}>
                  <label className={`flex items-start gap-3 p-3 cursor-pointer ${selected ? "bg-brand-50" : ""}`}>
                    {/* a checked radio fires no change event when clicked again, so the click itself unselects it */}
                    <input type="radio" name="model" checked={selected}
                      onChange={() => selectModel(m.slug)}
                      onClick={() => { if (selected) clearModel(); }}
                      className="mt-0.5 w-4 h-4 shrink-0 accent-brand-500" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900">{m.name}</div>
                      <div className="text-sm text-gray-600 mt-0.5">{m.description}</div>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-sm">
                        <span><span className="text-gray-500">Bands</span> <span className="text-gray-900">{m.required_bands.join(", ")}</span></span>
                        <span><span className="text-gray-500">Cloud limit</span> <span className="text-gray-900">{m.max_cloud_cover != null ? `${m.max_cloud_cover}% or less` : "none"}</span></span>
                      </div>
                    </div>
                  </label>

                  {/* pl-10 lines it up with the model's text, past the radio */}
                  {selected && (
                    <>
                      <button type="button"
                        onClick={() => setThresholdsOpen((o) => !o)}
                        aria-expanded={thresholdsOpen}
                        className="w-full border-t border-gray-200 pl-10 pr-3 py-2 flex items-center justify-between text-sm text-gray-700 hover:text-gray-900 hover:bg-gray-50 transition-colors">
                        Edit thresholds
                        <Chevron open={thresholdsOpen} className="text-gray-500" />
                      </button>
                      {thresholdsOpen && (
                        <div className="pl-10 pr-3 pb-4">
                          <ThresholdEditor model={m} overrides={thresholdOverrides} onChange={setThresholdOverrides} />
                        </div>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </FormSection>

        {/* 4 data sources */}
        <FormSection title="Data sources">
          {!selectedModel && <p className="text-sm text-gray-500">Select a model first.</p>}
          <div className="space-y-2">
            {(collections ?? []).map((col) => {
              const compat = selectedModel ? compatibility(selectedModel, col.slug) : null;
              const waiting = !selectedModel;
              const blocked = compat?.level === "incompatible";
              const checked = selectedCollections.includes(col.slug);
              const note = compat?.level === "partial" ? ["partial", ...compat.reasons].join(": ") : blocked ? compat.reasons.join("; ") : "";

              return (
                <label
                  key={col.slug}
                  className={`flex items-start gap-3 p-3 rounded border transition-colors ${
                    waiting
                      ? "border-gray-200 opacity-60 cursor-not-allowed"
                      : blocked
                        ? "border-red-300 bg-red-50/40 cursor-not-allowed"
                        : checked
                          ? "border-brand-600 bg-brand-50 cursor-pointer"
                          : "border-gray-300 cursor-pointer hover:border-gray-400"
                  }`}
                >
                  <input type="checkbox" checked={checked} disabled={waiting || blocked}
                    onChange={() => toggleCollection(col.slug)}
                    className="mt-1 accent-brand-500" />
                  <div className="flex-1 min-w-0 text-sm">
                    <span className="font-medium text-gray-900">{col.display_name}</span>
                    <span className="ml-2 text-gray-500">{col.processing_level}, {col.resolution_m} m</span>
                    {note && <span className={`block mt-0.5 ${blocked ? "text-red-700" : "text-gray-500"}`}>{note}</span>}
                  </div>
                </label>
              );
            })}
            {!collections?.length && <p className="text-sm text-gray-500">No data sources yet.</p>}
          </div>
        </FormSection>

        {/* 5 storage: what the workflow keeps, and an estimate of it, the same in both ways of starting */}
        <FormSection title="Storage estimate">
          {storage.body}
        </FormSection>

        </fieldset>
        )}

        {createWorkflow.error && (
          <p className="text-red-700 text-sm">{(createWorkflow.error as Error).message}</p>
        )}

        {/* only with the form: before a way in is chosen there is nothing to create or cancel */}
        {formVisible && (
          <div className="flex gap-3">
            <button type="submit" disabled={createWorkflow.isPending || !canSubmit || !storage.estimated || drafting}
              className="px-6 py-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white rounded text-sm font-medium transition-colors">
              {createWorkflow.isPending ? "Creating…" : "Create workflow"}
            </button>
            <button type="button" onClick={() => navigate("/workflows")}
              className="px-6 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded text-sm transition-colors">
              Cancel
            </button>
            {canSubmit && !storage.estimated && <span className="text-xs text-gray-500 self-center">Estimate storage first</span>}
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
        )}
      </form>
    </div>
  );
}
