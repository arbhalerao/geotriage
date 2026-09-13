import { useState } from "react";
import { useModels } from "../api/queries";
import RegistrySection, { type CardDetails } from "../components/RegistrySection";
import { CheckItem, Collapsible } from "../components/Panel";
import type { ModelInfo, Registered } from "../api/types";

type ScoreDeclaration = {
  description?: string;
  unit?: string;
  range?: [number, number];
  primary?: boolean;
  thresholds?: { green: [number, number]; yellow: [number, number] } | null;
};

type ModelDescriptor = {
  requires?: { bands?: string[]; max_cloud_cover?: number | null };
  scores?: Record<string, ScoreDeclaration>;
};

function Compatibility({ collections }: { collections: ModelInfo["compatible_collections"] }) {
  const order = ["full", "partial", "incompatible"];
  const entries = Object.entries(collections).sort(([, a], [, b]) => order.indexOf(a.level) - order.indexOf(b.level));
  if (!entries.length) return <p className="text-sm text-gray-500">No collections registered.</p>;

  return (
    <ul className="space-y-1">
      {entries.map(([slug, c]) => (
        <CheckItem
          key={slug}
          state={c.level === "incompatible" ? "failed" : "passed"}
          note={c.level === "partial" ? ["partial", ...c.reasons].join(": ") : c.level === "incompatible" ? c.reasons.join("; ") : undefined}
        >
          {slug}
        </CheckItem>
      ))}
    </ul>
  );
}

function ScoresTable({ scores }: { scores: Record<string, ScoreDeclaration> }) {
  const range = (r?: [number, number]) => (r ? `${r[0]} to ${r[1]}` : "not set");
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-gray-500 text-left border-b border-gray-200">
          <th className="py-2 pr-4 font-medium">Score</th>
          <th className="py-2 pr-4 font-medium">Description</th>
          <th className="py-2 pr-4 font-medium">Unit</th>
          <th className="py-2 pr-4 font-medium">Range</th>
          <th className="py-2 pr-4 font-medium text-green-700">Green</th>
          <th className="py-2 pr-4 font-medium text-amber-700">Yellow</th>
          <th className="py-2 font-medium text-red-700">Red</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100">
        {Object.entries(scores).map(([name, score]) => (
          <tr key={name} className="align-top">
            <td className="py-2 pr-4 text-gray-900 whitespace-nowrap">
              {name}
              {score.primary && <span className="ml-1.5 text-gray-500">(primary)</span>}
            </td>
            <td className="py-2 pr-4 text-gray-900">{score.description || "no description"}</td>
            <td className="py-2 pr-4 text-gray-900">{score.unit || "none"}</td>
            <td className="py-2 pr-4 text-gray-900 whitespace-nowrap">{range(score.range)}</td>
            <td className="py-2 pr-4 text-gray-900 whitespace-nowrap">{range(score.thresholds?.green)}</td>
            <td className="py-2 pr-4 text-gray-900 whitespace-nowrap">{range(score.thresholds?.yellow)}</td>
            <td className="py-2 text-gray-900 whitespace-nowrap">{score.thresholds ? "anything else" : "not set"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function modelDetails(entry: Registered, catalogue: ModelInfo | undefined): CardDetails {
  const descriptor = entry.descriptor as ModelDescriptor;
  const scores = descriptor.scores ?? {};
  const primary = Object.keys(scores).find((name) => scores[name].primary);
  const cloud = descriptor.requires?.max_cloud_cover;

  // compatibility depends on the providers registered right now, which only the catalogue knows,
  // and the catalogue only carries models that passed their smoke test
  const collections = catalogue ? Object.values(catalogue.compatible_collections) : [];
  const usable = collections.filter((c) => c.level !== "incompatible").length;

  return {
    declared: [
      ["Bands", descriptor.requires?.bands?.join(", ") || "none"],
      ["Primary score", primary ?? "none"],
      ["Cloud limit", cloud != null ? `${cloud}% or less` : "none"],
    ],
    sections: (
      <>
        {catalogue && (
          <Collapsible title="Compatibility" summary={`${usable} of ${collections.length} collections`}>
            <Compatibility collections={catalogue.compatible_collections} />
          </Collapsible>
        )}
        {Object.keys(scores).length > 0 && (
          <Collapsible title="Thresholds">
            <ScoresTable scores={scores} />
          </Collapsible>
        )}
      </>
    ),
  };
}

export default function ModelsPage() {
  const [adding, setAdding] = useState(false);
  const { data: models } = useModels();

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Models</h1>
        <button
          type="button"
          onClick={() => setAdding((open) => !open)}
          aria-expanded={adding}
          className={`text-sm px-4 py-2 rounded transition-colors ${
            adding ? "bg-gray-100 hover:bg-gray-200 text-gray-700" : "bg-brand-600 hover:bg-brand-700 text-white"
          }`}
        >
          {adding ? "Cancel" : "Add Model"}
        </button>
      </div>

      <RegistrySection
        kind="model"
        adding={adding}
        onClose={() => setAdding(false)}
        details={(entry) => modelDetails(entry, entry.is_enabled ? models?.find((m) => m.slug === entry.slug) : undefined)}
      />
    </div>
  );
}
