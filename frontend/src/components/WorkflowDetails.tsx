import type { ReactNode } from "react";
import { useCollections, useModels, useWorkflow } from "../api/queries";
import type { Workflow } from "../api/types";
import { formatDate, formatDateTime, formatInterval } from "../time";
import { Rows } from "./Panel";

export default function WorkflowDetails({ workflow: wf }: { workflow: Workflow }) {
  const { data: models } = useModels();
  const { data: collections } = useCollections();
  const recurring = wf.time_mode === "recurring";

  const rows: [string, ReactNode][] = [
    ["Mode", recurring ? "Recurring" : "Historical"],
    ["Dates", `${formatDate(wf.time_start)} to ${formatDate(wf.time_end)}`],
    ["Model", wf.model_configs.map((m) => models?.find((x) => x.slug === m.model_slug)?.name ?? m.model_slug).join(", ")],
    ["Data sources", wf.collection_slugs.map((slug) => collections?.find((c) => c.slug === slug)?.display_name ?? slug).join(", ")],
    ["Scene filter", wf.aoi_filter_mode === "enclosed" ? "At least 80% inside the area" : "Any overlap with the area"],
  ];
  if (recurring) {
    rows.push(["Interval", wf.poll_interval_minutes ? formatInterval(wf.poll_interval_minutes) : "none"]);
    rows.push(["Last checked", wf.last_checked_at ? formatDateTime(wf.last_checked_at) : "not yet"]);
    if (wf.next_run_at && wf.status !== "running") rows.push(["Next run", formatDateTime(wf.next_run_at)]);
  }

  return <Rows rows={rows} />;
}

// for places that only have the id: fetches the workflow when first shown, and reuses the cached copy after that
export function WorkflowDetailsById({ id }: { id: string }) {
  const { data, isLoading, isError } = useWorkflow(id);
  if (isLoading) return <p className="text-sm text-gray-500">Loading…</p>;
  if (isError || !data) return <p className="text-sm text-red-700">Couldn't load the details.</p>;
  return <WorkflowDetails workflow={data} />;
}
