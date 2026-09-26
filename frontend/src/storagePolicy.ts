import type { StorageEstimateResult } from "./api/types";

export type StoragePolicy = "everything" | "alert_and_caution_in_full" | "alert_in_full" | "results_only" | "scores_only";

export type ImageryKept = "inputs_and_results" | "results" | "none" | null;

export const DEFAULT_POLICY: StoragePolicy = "alert_and_caution_in_full";

export const POLICIES: { value: StoragePolicy; label: string; description: string; selected: string; kept: "all" | "some" | "results" | "none" }[] = [
  { value: "everything", label: "Everything", description: "Imagery and maps for every scene", selected: "border-red-500 bg-red-50", kept: "all" },
  { value: "alert_and_caution_in_full", label: "Alert and Caution in full", description: "Imagery for Alert and Caution, maps for every scene", selected: "border-orange-500 bg-orange-50", kept: "some" },
  { value: "alert_in_full", label: "Alert in full", description: "Imagery for Alert, maps for every scene", selected: "border-amber-400 bg-amber-50", kept: "some" },
  { value: "results_only", label: "Maps only", description: "No imagery, maps for every scene", selected: "border-lime-500 bg-lime-50", kept: "results" },
  { value: "scores_only", label: "Scores only", description: "No imagery or maps, scores for every scene", selected: "border-green-500 bg-green-50", kept: "none" },
];

export function policyLabel(policy: string): string {
  return POLICIES.find((p) => p.value === policy)?.label ?? policy;
}

export function keptBytes(kept: "all" | "some" | "results" | "none", e: StorageEstimateResult): [number, number] {
  const all = e.input_bytes + e.result_bytes;
  if (kept === "all") return [all, all];
  if (kept === "results") return [e.result_bytes, e.result_bytes];
  if (kept === "none") return [0, 0];
  return [e.result_bytes, all];
}

export function layersKept(imagery: ImageryKept, finished: boolean): { inputs: boolean; results: boolean } {
  if (imagery === null) return { inputs: finished, results: finished };
  return { inputs: imagery === "inputs_and_results", results: imagery !== "none" };
}
