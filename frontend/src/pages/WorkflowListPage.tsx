import { Link } from "react-router-dom";
import { useDeleteWorkflow, useRunWorkflow, useWorkflows } from "../api/queries";

import StatusBadge from "../components/StatusBadge";

function fmtDate(d: string) {
  return new Date(d).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function WorkflowListPage() {
  const { data: workflows, isLoading } = useWorkflows();
  const deleteWf = useDeleteWorkflow();
  const runWf = useRunWorkflow();

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Workflows</h1>
        <Link
          to="/workflows/new"
          className="bg-brand-600 hover:bg-brand-700 text-white text-sm px-4 py-2 rounded transition-colors"
        >
          + New workflow
        </Link>
      </div>

      {isLoading && <p className="text-gray-600 dark:text-gray-400">Loading…</p>}

      {!isLoading && (!workflows || workflows.length === 0) && (
        <div className="text-center py-20 text-gray-500">
          <p className="text-4xl mb-3">🛰</p>
          <p>No workflows yet. Create one to start monitoring.</p>
        </div>
      )}

      <div className="space-y-3">
        {workflows?.map((wf) => (
          <div
            key={wf.id}
            className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg px-5 py-4 flex items-center gap-4"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <Link
                  to={`/workflows/${wf.id}`}
                  className="font-medium hover:text-brand-400 truncate"
                >
                  {wf.name}
                </Link>
                <StatusBadge status={wf.status} />
              </div>
              <div className="text-xs text-gray-600 dark:text-gray-400">
                {wf.time_mode} · {fmtDate(wf.time_start)}
                {wf.time_end ? ` → ${fmtDate(wf.time_end)}` : ""}
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              {(wf.status === "draft" || wf.status === "failed") && (
                <button
                  onClick={() => runWf.mutate(wf.id)}
                  disabled={runWf.isPending}
                  className="text-xs px-3 py-1.5 bg-blue-800 hover:bg-blue-700 text-blue-200 rounded transition-colors"
                >
                  Run
                </button>
              )}
              <Link
                to={`/workflows/${wf.id}`}
                className="text-xs px-3 py-1.5 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded transition-colors"
              >
                View
              </Link>
              <button
                onClick={() => {
                  if (confirm("Delete this workflow?")) deleteWf.mutate(wf.id);
                }}
                className="text-xs px-3 py-1.5 bg-gray-100 dark:bg-gray-800 hover:bg-red-900 text-gray-600 dark:text-gray-400 hover:text-red-300 rounded transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
