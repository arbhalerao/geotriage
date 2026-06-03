import { useState } from "react";
import { useModels } from "../api/queries";
import RegistrySection from "../components/RegistrySection";
import type { ModelInfo } from "../api/types";

const COMPAT_STYLES: Record<string, string> = {
  full: "bg-green-100 text-green-700 border-green-300 dark:bg-green-900/60 dark:text-green-300 dark:border-green-800",
  partial: "bg-yellow-100 text-yellow-700 border-yellow-300 dark:bg-yellow-900/60 dark:text-yellow-300 dark:border-yellow-800",
  incompatible: "bg-red-100 text-red-700 border-red-300 dark:bg-red-900/60 dark:text-red-400 dark:border-red-900",
};

function CompatBadge({ level, reasons }: { level: string; reasons: string[] }) {
  const cls = COMPAT_STYLES[level] ?? "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-300 dark:border-gray-700";
  return (
    <span className={`relative group inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded border ${cls}`}>
      {level}
      {reasons.length > 0 && (
        <>
          <span className="cursor-default underline decoration-dotted">!</span>
          <span className="pointer-events-none absolute left-0 top-full mt-1 z-10 w-60 rounded bg-gray-50 dark:bg-gray-950 border border-gray-300 dark:border-gray-700 px-2 py-1.5 text-xs text-gray-700 dark:text-gray-300 shadow-lg opacity-0 group-hover:opacity-100 transition-opacity whitespace-normal">
            {reasons.map((r, i) => <span key={i} className="block">{r}</span>)}
          </span>
        </>
      )}
    </span>
  );
}

function ScoresTable({ model }: { model: ModelInfo }) {
  return (
    <table className="w-full text-xs mt-2">
      <thead>
        <tr className="text-gray-500 text-left border-b border-gray-200 dark:border-gray-800">
          <th className="pb-1.5 font-medium">Score</th>
          <th className="pb-1.5 font-medium">Description</th>
          <th className="pb-1.5 font-medium">Unit</th>
          <th className="pb-1.5 font-medium">Range</th>
          <th className="pb-1.5 font-medium text-green-400">Green</th>
          <th className="pb-1.5 font-medium text-yellow-400">Yellow</th>
          <th className="pb-1.5 font-medium text-red-400">Red</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-200/70 dark:divide-gray-800/60">
        {Object.entries(model.default_thresholds).map(([name, t]) => {
          const out = model.score_outputs[name];
          const isPrimary = name === model.primary_score;
          return (
            <tr key={name}>
              <td className="py-1.5 font-mono text-gray-700 dark:text-gray-300 whitespace-nowrap">
                {name}
                {isPrimary && (
                  <span className="ml-1.5 text-xs bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400 px-1 py-0.5 rounded">primary</span>
                )}
              </td>
              <td className="py-1.5 text-gray-600 dark:text-gray-400">{out?.description ?? "—"}</td>
              <td className="py-1.5 text-gray-500">{out?.unit || "—"}</td>
              <td className="py-1.5 text-gray-500">
                {out ? `${out.value_range[0]} – ${out.value_range[1]}` : "—"}
              </td>
              <td className="py-1.5 text-gray-600 dark:text-gray-400">{t.green[0]} – {t.green[1]}</td>
              <td className="py-1.5 text-gray-600 dark:text-gray-400">{t.yellow[0]} – {t.yellow[1]}</td>
              <td className="py-1.5 text-gray-500">anything else</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function ModelCard({ model }: { model: ModelInfo }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden">
      <div className="px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold">{model.name}</h2>
            <p className="text-xs text-gray-500 font-mono mt-0.5">{model.slug}</p>
          </div>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">{model.description}</p>

        <div className="flex flex-wrap gap-4 mt-3 text-xs text-gray-600 dark:text-gray-400">
          <span>
            <span className="text-gray-500">Bands </span>
            {model.required_bands.join(", ")}
          </span>
          <span>
            <span className="text-gray-500">Primary score </span>
            {model.primary_score}
          </span>
          <span>
            <span className="text-gray-500">Cloud filter </span>
            {model.max_cloud_cover != null ? `≤${model.max_cloud_cover}%` : "none"}
          </span>
        </div>
      </div>

      {Object.keys(model.compatible_collections).length > 0 && (
        <div className="px-5 py-3 border-t border-gray-200 dark:border-gray-800">
          <p className="text-xs text-gray-500 mb-2">Collection compatibility</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(model.compatible_collections).map(([slug, c]) => (
              <span key={slug} className="flex items-center gap-1.5">
                <span className="text-xs text-gray-600 dark:text-gray-400">{slug}</span>
                <CompatBadge level={c.level} reasons={c.reasons} />
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="border-t border-gray-200 dark:border-gray-800">
        <button
          onClick={() => setOpen((o) => !o)}
          className="w-full px-5 py-2.5 flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 hover:bg-gray-100/60 dark:hover:bg-gray-800/40 transition-colors"
        >
          <span>Scores &amp; thresholds</span>
          <span>{open ? "▲" : "▼"}</span>
        </button>
        {open && (
          <div className="px-5 pb-4 overflow-x-auto">
            <ScoresTable model={model} />
          </div>
        )}
      </div>
    </div>
  );
}

export default function ModelsPage() {
  const { data: models, isLoading } = useModels();

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-1">Models</h1>
      <p className="text-sm text-gray-500 mb-6">
        Every model is a container image, added through the form below and checked before it is
        accepted.
      </p>

      <RegistrySection kind="model" />

      <h2 className="text-sm font-semibold mb-3">Selectable in a workflow</h2>
      {isLoading && <p className="text-gray-500 text-sm">Loading…</p>}
      {!isLoading && !models?.length && (
        <p className="text-gray-500 text-sm">
          Nothing yet — a model becomes selectable once it has passed its smoke test.
        </p>
      )}
      <div className="space-y-4">
        {models?.map((m) => <ModelCard key={m.slug} model={m} />)}
      </div>
    </div>
  );
}
