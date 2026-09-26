import { useEffect, useState, type ReactNode } from "react";
import { useEstimate, useStartEstimate } from "../api/queries";
import type { EstimateRequest, StorageEstimateResult } from "../api/types";
import { POLICIES, keptBytes, type StoragePolicy } from "../storagePolicy";
import { Rows } from "./Panel";

export function formatBytes(count: number): string {
  for (const [unit, size] of [["TB", 1024 ** 4], ["GB", 1024 ** 3], ["MB", 1024 ** 2]] as const) {
    if (count >= size) return `${(count / size).toFixed(1)} ${unit}`;
  }
  return "under 1 MB";
}

function atLeast(value: string, capped: boolean): string {
  return capped ? `${value}+` : value;
}

const MB = 1024 ** 2;

function keptSize([low, high]: [number, number], capped: boolean): string {
  if (high === 0) return "None";
  if (low === high) return atLeast(formatBytes(high), capped);
  if (low < MB) return `Up to ${atLeast(formatBytes(high), capped)}`;
  const [lowValue, lowUnit] = formatBytes(low).split(" ");
  const highText = atLeast(formatBytes(high), capped);
  return highText.replace(/\+$/, "").endsWith(lowUnit) ? `${lowValue} to ${highText}` : `${formatBytes(low)} to ${highText}`;
}

export function useStorageEstimate(
  request: EstimateRequest | null,
  seed: { result: StorageEstimateResult; token: number } | null,
  policy: StoragePolicy,
  onPolicyChange: (policy: StoragePolicy) => void,
  recurring: boolean,
): { body: ReactNode; ready: boolean } {
  const signature = request ? JSON.stringify(request) : null;
  const [estimated, setEstimated] = useState<{ result: StorageEstimateResult; signature: string | null } | null>(null);
  const [pending, setPending] = useState<{ id: string; signature: string } | null>(null);
  const [failed, setFailed] = useState<{ message: string; signature: string | null } | null>(null);
  const shown = estimated && estimated.signature === signature ? estimated : null;
  const error = failed && failed.signature === signature ? failed.message : null;

  const start = useStartEstimate();
  const { data: run } = useEstimate(pending?.id ?? null);
  const working = start.isPending || !!pending;

  useEffect(() => {
    if (!seed) return;
    setEstimated({ result: seed.result, signature });
    setFailed(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed?.token]);

  useEffect(() => {
    if (!run || !pending || run.id !== pending.id || run.status === "queued" || run.status === "running") return;
    if (run.status === "done" && run.result) setEstimated({ result: run.result, signature: pending.signature });
    else setFailed({ message: `Couldn't estimate: ${run.error ?? "no answer"}`, signature: pending.signature });
    setPending(null);
  }, [run, pending]);

  async function estimate() {
    if (!request || !signature) return;
    setFailed(null);
    try {
      setPending({ id: (await start.mutateAsync(request)).id, signature });
    } catch (err) {
      setFailed({ message: `The request failed: ${(err as Error).message}`, signature });
    }
  }

  const result = recurring ? undefined : shown?.result;
  const choosable = recurring || !!result;
  const body = (
    <div className="space-y-3">
      {recurring ? (
        <p className="text-sm text-gray-500">Storage can't be estimated for a recurring workflow. Each run checks it before downloading.</p>
      ) : (
        <Rows rows={[["Scenes", result ? atLeast(String(result.scenes), result.capped) : "-"]]} />
      )}
      {/* the boxes stay grey, with none selected, until they can be chosen;
          then the selected one takes its colour, red for the policy that keeps the most through to green for the least */}
      <div role="radiogroup" aria-label="Storage policy" aria-disabled={!choosable} className="grid grid-cols-1 sm:grid-cols-5 gap-2">
        {POLICIES.map((p) => {
          const selected = choosable && policy === p.value;
          return (
            <label
              key={p.value}
              className={`flex flex-col px-3 py-2 rounded border text-left transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand-500 ${
                !choosable
                  ? "border-gray-200 bg-gray-50 text-gray-400 cursor-not-allowed"
                  : selected
                    ? `${p.selected} text-gray-900 cursor-pointer`
                    : "border-gray-300 bg-white text-gray-600 hover:border-gray-400 cursor-pointer"
              }`}
            >
              <input type="radio" name="storage_policy" value={p.value} checked={selected} disabled={!choosable} onChange={() => onPolicyChange(p.value)} className="sr-only" />
              <span className="text-xs font-medium">{p.label}</span>
              <span className={`text-xs mt-0.5 flex-1 ${choosable ? "text-gray-500" : "text-gray-400"}`}>{p.description}</span>
              {result && <span className="text-xs text-gray-900 mt-2">{keptSize(keptBytes(p.kept, result), result.capped)}</span>}
            </label>
          );
        })}
      </div>
      {!recurring && error && <p className="text-sm text-red-700">{error}</p>}
      {!recurring && (
        <button
          type="button"
          onClick={estimate}
          disabled={!request || working}
          className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded text-sm transition-colors disabled:opacity-50 disabled:hover:bg-gray-100 disabled:cursor-not-allowed"
        >
          {working ? "Estimating…" : "Estimate"}
        </button>
      )}
    </div>
  );

  return { body, ready: recurring || !!shown };
}
