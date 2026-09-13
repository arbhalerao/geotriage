import { useState, type ReactNode } from "react";
import RegistrySection, { type CardDetails } from "../components/RegistrySection";
import { Collapsible, Rows } from "../components/Panel";
import type { Registered } from "../api/types";

type BandDeclaration = {
  normalized_name: string;
  asset_key: string;
  description: string;
};

type CollectionDeclaration = {
  slug: string;
  display_name?: string;
  description?: string;
  processing_level?: string;
  sensor_type?: string;
  resolution_m?: number;
  cloud_cover_property?: string | null;
  bands?: BandDeclaration[];
};

type ProviderDescriptor = {
  stac_api_url?: string;
  collections?: Record<string, CollectionDeclaration>;
};

function BandsTable({ bands }: { bands: BandDeclaration[] }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-gray-500 text-left border-b border-gray-200">
          <th className="py-2 pr-4 font-medium">Band</th>
          <th className="py-2 pr-4 font-medium">Asset key</th>
          <th className="py-2 font-medium">Description</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100">
        {bands.map((b) => (
          <tr key={b.asset_key}>
            <td className="py-2 pr-4 text-gray-900">{b.normalized_name}</td>
            <td className="py-2 pr-4 text-gray-900">{b.asset_key}</td>
            <td className="py-2 text-gray-900">{b.description}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CollectionSection({ collection }: { collection: CollectionDeclaration }) {
  const facts = [
    collection.processing_level,
    collection.sensor_type,
    collection.resolution_m != null ? `${collection.resolution_m} m` : undefined,
  ].filter(Boolean) as string[];

  return (
    <Collapsible
      title={
        <span className="flex items-baseline gap-2 min-w-0">
          <span className="text-gray-800">{collection.display_name ?? collection.slug}</span>
          <span className="text-gray-500 truncate">{collection.slug}</span>
        </span>
      }
    >
      {collection.description && <p className="text-sm text-gray-600 mb-3 max-w-3xl">{collection.description}</p>}
      <div className="mb-3">
        <Rows
          rows={[
            ["Product", facts.join(", ") || "not described"],
            ["Cloud cover", collection.cloud_cover_property ?? "not reported, so scenes are not filtered by cloud"],
          ]}
        />
      </div>
      <BandsTable bands={collection.bands ?? []} />
    </Collapsible>
  );
}

function providerDetails(entry: Registered): CardDetails {
  const descriptor = entry.descriptor as ProviderDescriptor;
  const collections = Object.values(descriptor.collections ?? {});

  const declared: [string, ReactNode][] = [];
  if (descriptor.stac_api_url) {
    declared.push(["STAC API", descriptor.stac_api_url]);
  }

  return {
    declared,
    sections: collections.map((c) => <CollectionSection key={c.slug} collection={c} />),
  };
}

export default function ProvidersPage() {
  const [adding, setAdding] = useState(false);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Providers</h1>
        <button
          type="button"
          onClick={() => setAdding((open) => !open)}
          aria-expanded={adding}
          className={`text-sm px-4 py-2 rounded transition-colors ${
            adding ? "bg-gray-100 hover:bg-gray-200 text-gray-700" : "bg-brand-600 hover:bg-brand-700 text-white"
          }`}
        >
          {adding ? "Cancel" : "Add Provider"}
        </button>
      </div>

      <RegistrySection kind="provider" adding={adding} onClose={() => setAdding(false)} details={providerDetails} />
    </div>
  );
}
