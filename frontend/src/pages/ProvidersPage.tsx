import { useState } from "react";
import { useCollections } from "../api/queries";
import RegistrySection from "../components/RegistrySection";
import type { CollectionInfo } from "../api/types";

function BandsTable({ bands }: { bands: CollectionInfo["bands"] }) {
  return (
    <table className="w-full text-xs mt-2">
      <thead>
        <tr className="text-gray-500 text-left border-b border-gray-200 dark:border-gray-800">
          <th className="pb-1.5 font-medium">Normalized name</th>
          <th className="pb-1.5 font-medium">Asset key</th>
          <th className="pb-1.5 font-medium">Description</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-200/70 dark:divide-gray-800/60">
        {bands.map((b) => (
          <tr key={b.asset_key}>
            <td className="py-1.5 font-mono text-blue-300">{b.normalized_name}</td>
            <td className="py-1.5 font-mono text-gray-600 dark:text-gray-400">{b.asset_key}</td>
            <td className="py-1.5 text-gray-500">{b.description}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CollectionCard({ col }: { col: CollectionInfo }) {
  const [bandsOpen, setBandsOpen] = useState(false);

  return (
    <div className="border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden">
      <div className="px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">{col.display_name}</h3>
            <p className="text-xs font-mono text-gray-500 mt-0.5">{col.slug}</p>
          </div>
          <div className="flex flex-wrap gap-1 justify-end">
            <span className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 px-2 py-0.5 rounded">
              {col.processing_level}
            </span>
            <span className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 px-2 py-0.5 rounded">
              {col.sensor_type}
            </span>
            <span className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 px-2 py-0.5 rounded">
              {col.resolution_m}m
            </span>
          </div>
        </div>

        <p className="text-xs text-gray-600 dark:text-gray-400 mt-2">{col.description}</p>

        <div className="flex flex-wrap gap-4 mt-2 text-xs text-gray-500">
          <span>
            Cloud cover{" "}
            <span className={col.cloud_cover_property ? "text-green-400" : "text-gray-500 dark:text-gray-600"}>
              {col.cloud_cover_property ?? "not reported"}
            </span>
          </span>
          <span>{col.bands.length} bands</span>
        </div>
      </div>

      <div className="border-t border-gray-200 dark:border-gray-800">
        <button
          onClick={() => setBandsOpen((o) => !o)}
          className="w-full px-4 py-2 flex items-center justify-between text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100/60 dark:hover:bg-gray-800/40 transition-colors"
        >
          <span>Bands</span>
          <span>{bandsOpen ? "▲" : "▼"}</span>
        </button>
        {bandsOpen && (
          <div className="px-4 pb-3">
            <BandsTable bands={col.bands} />
          </div>
        )}
      </div>
    </div>
  );
}

export default function ProvidersPage() {
  const { data: collections, isLoading } = useCollections();

  const byProvider = (collections ?? []).reduce<Record<string, { name: string; cols: CollectionInfo[] }>>(
    (acc, col) => {
      if (!acc[col.provider_slug]) {
        acc[col.provider_slug] = { name: col.provider_name, cols: [] };
      }
      acc[col.provider_slug].cols.push(col);
      return acc;
    },
    {}
  );

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-1">Providers</h1>
      <p className="text-sm text-gray-500 mb-6">
        Every provider is a container image, added through the form below and checked before it is
        accepted.
      </p>

      <RegistrySection kind="provider" />

      <h2 className="text-sm font-semibold mb-3">Collections on offer</h2>
      {isLoading && <p className="text-gray-500 text-sm">Loading…</p>}
      {!isLoading && Object.keys(byProvider).length === 0 && (
        <p className="text-gray-500 text-sm">No collections available yet.</p>
      )}
      <div className="space-y-8">
        {Object.entries(byProvider).map(([slug, { name, cols }]) => (
          <section key={slug}>
            <div className="mb-3">
              <h2 className="text-base font-semibold">{name}</h2>
              <p className="text-xs font-mono text-gray-500">{slug}</p>
            </div>
            <div className="space-y-3">
              {cols.map((col) => <CollectionCard key={col.slug} col={col} />)}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
