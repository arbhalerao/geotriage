import { useEffect, useState, type ReactNode } from "react";
import { useEstimate, useStartEstimate } from "../api/queries";
import type { EstimateRequest, StorageEstimateResult } from "../api/types";
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

export function useStorageEstimate(
  request: EstimateRequest | null,
  seed: { result: StorageEstimateResult; token: number } | null,
): { body: ReactNode; estimated: boolean } {
  const signature = request ? JSON.stringify({ ...request, poll_interval_minutes: null }) : null;
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

  const result = shown?.result;
  const pastDays = request ? Math.max(1, Math.round((Date.parse(request.time_end) - Date.now()) / 86_400_000)) : 0;
  const body = (
    <div className="space-y-3">
      {/* always there, blank until estimated, so the section reads like the others and nothing jumps when it fills in */}
      <Rows
        rows={[
          ["Scenes", result ? `${atLeast(String(result.scenes), result.capped)}${result.from_past_window ? ` in the past ${pastDays} days` : ""}` : "-"],
          ["Size", result ? atLeast(formatBytes(result.staged_bytes), result.capped) : "-"],
        ]}
      />
      {error && <p className="text-sm text-red-700">{error}</p>}
      <button
        type="button"
        onClick={estimate}
        disabled={!request || working}
        className="block text-sm leading-6 text-gray-700 hover:text-gray-900 disabled:text-gray-400 disabled:cursor-not-allowed"
      >
        {working ? "Estimating…" : "Estimate"}
      </button>
    </div>
  );

  return { body, estimated: !!shown };
}
