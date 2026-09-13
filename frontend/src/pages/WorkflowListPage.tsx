import { useState } from "react";
import { Link } from "react-router-dom";
import { useDeleteWorkflow, useRunWorkflow, useWorkflows } from "../api/queries";
import Chevron from "../components/Chevron";
import DotLine from "../components/DotLine";
import { WorkflowDetailsById } from "../components/WorkflowDetails";
import StatusBadge from "../components/StatusBadge";
import type { WorkflowSummary } from "../api/types";

function WorkflowRow({ wf, onRun, running, onDelete }: { wf: WorkflowSummary; onRun: () => void; running: boolean; onDelete: () => void }) {
  const [open, setOpen] = useState(false);
  const button = "text-sm px-2.5 py-1 rounded text-gray-500 transition-colors";

  return (
    // the name's link stretches over the card; buttons and the open details sit above it
    <div className="relative bg-white border border-gray-200 rounded-lg hover:border-gray-300 hover:bg-gray-50 transition-colors">
      <div className="px-5 py-4 flex items-center gap-4">
        <div className="flex-1 min-w-0">
          <Link
            to={`/workflows/${wf.id}`}
            className="block font-medium text-gray-900 truncate mb-1 after:absolute after:inset-0 after:rounded-lg focus:outline-none focus-visible:after:ring-2 focus-visible:after:ring-brand-500"
          >
            {wf.name}
          </Link>
          <DotLine parts={[
            <StatusBadge status={wf.status} />,
            ...(wf.total_items > 0
              ? [
                  `${wf.total_items.toLocaleString()} scenes`,
                  `${wf.processed_items.toLocaleString()} processed`,
                  `${wf.identified_items.toLocaleString()} flagged`,
                  wf.failed_items > 0 ? <span className="text-red-700">{wf.failed_items.toLocaleString()} failed</span> : null,
                ]
              : ["no scenes yet"]),
          ]} />
        </div>

        <div className="relative flex items-center gap-1 shrink-0">
          <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
            className={`${button} inline-flex items-center gap-1 hover:text-gray-900 hover:bg-gray-100`}>
            Details
            <Chevron open={open} size="w-3.5 h-3.5" />
          </button>
          {(wf.status === "draft" || wf.status === "failed") && (
            <button type="button" onClick={onRun} disabled={running}
              className={`${button} hover:text-brand-700 hover:bg-brand-50 disabled:opacity-50`}>
              Run
            </button>
          )}
          <button type="button" onClick={() => { if (confirm("Delete this workflow?")) onDelete(); }}
            className={`${button} hover:text-red-700 hover:bg-red-50`}>
            Delete
          </button>
        </div>
      </div>

      {/* fetched from GET /workflows/{id} only once opened */}
      {open && (
        <div className="relative border-t border-gray-200 px-5 py-4 cursor-auto">
          <WorkflowDetailsById id={wf.id} />
        </div>
      )}
    </div>
  );
}

export default function WorkflowListPage() {
  const { data: workflows, isLoading } = useWorkflows();
  const deleteWf = useDeleteWorkflow();
  const runWf = useRunWorkflow();

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Workflows</h1>
        <Link
          to="/workflows/new"
          className="bg-brand-600 hover:bg-brand-700 text-white text-sm px-4 py-2 rounded transition-colors"
        >
          Create Workflow
        </Link>
      </div>

      {isLoading && <p className="text-gray-600">Loading…</p>}

      {!isLoading && (!workflows || workflows.length === 0) && (
        <div className="text-center py-20 text-gray-500">
          <p>No workflows yet.</p>
        </div>
      )}

      <div className="space-y-3">
        {workflows?.map((wf) => <WorkflowRow key={wf.id} wf={wf} onRun={() => runWf.mutate(wf.id)} running={runWf.isPending} onDelete={() => deleteWf.mutate(wf.id)} />)}
      </div>
    </div>
  );
}
