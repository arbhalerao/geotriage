import { useLive } from "../api/live";
import { useWorkerStatus } from "../api/queries";

function TaskName({ name, args }: { name: string; args: unknown[] }) {
  const short = name.replace(/_/g, " ");
  const arg = typeof args[0] === "string" ? args[0].slice(0, 8) + "…" : "";
  return (
    <span>
      <span className="text-gray-800 dark:text-gray-200">{short}</span>
      {arg && <span className="text-gray-500 dark:text-gray-600 ml-1 font-mono text-xs">{arg}</span>}
    </span>
  );
}

export default function WorkerPage() {
  const { data, isLoading } = useWorkerStatus();
  const live = useLive((s) => s.connected);

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Worker</h1>
        <span className="flex items-center gap-1.5 text-xs text-gray-500">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
          {live ? "Live" : "Polling every 5s"}
        </span>
      </div>

      {isLoading && <p className="text-gray-600 dark:text-gray-400">Connecting…</p>}

      {data?.error && (
        <div className="mb-4 text-sm text-red-400 bg-red-950/40 border border-red-800 rounded px-4 py-3">
          {data.error}
        </div>
      )}

      {data && (
        <>
          <section className="mb-6 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
            <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Workers</h2>
            {data.workers.length === 0 ? (
              <p className="text-sm text-gray-500">No workers online.</p>
            ) : (
              <div className="space-y-1">
                {data.workers.map((w) => (
                  <div key={w} className="flex items-center gap-2 text-sm">
                    <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
                    <span className="font-mono text-gray-700 dark:text-gray-300 text-xs">{w}</span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="mb-6 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
            <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              Active
              {data.total_active > 0 && (
                <span className="ml-2 text-xs bg-blue-900 text-blue-300 px-1.5 py-0.5 rounded">
                  {data.total_active}
                </span>
              )}
            </h2>
            {data.active_tasks.length === 0 ? (
              <p className="text-sm text-gray-500">No tasks running.</p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-500 text-left border-b border-gray-200 dark:border-gray-800">
                    <th className="pb-2 font-medium">Task</th>
                    <th className="pb-2 font-medium">Worker</th>
                    <th className="pb-2 font-medium">Started</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200/70 dark:divide-gray-800/50">
                  {data.active_tasks.map((t) => (
                    <tr key={t.id}>
                      <td className="py-2">
                        <TaskName name={t.name} args={t.args} />
                      </td>
                      <td className="py-2 font-mono text-gray-500 text-xs">{t.worker ?? "—"}</td>
                      <td className="py-2 text-gray-500">
                        {t.time_start ? new Date(t.time_start).toLocaleTimeString() : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
            <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              Queued
              {data.total_queued > 0 && (
                <span className="ml-2 text-xs bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400 px-1.5 py-0.5 rounded">
                  {data.total_queued}
                </span>
              )}
            </h2>
            {data.queued_tasks.length === 0 ? (
              <p className="text-sm text-gray-500">No tasks queued.</p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-500 text-left border-b border-gray-200 dark:border-gray-800">
                    <th className="pb-2 font-medium">Task</th>
                    <th className="pb-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200/70 dark:divide-gray-800/50">
                  {data.queued_tasks.map((t) => (
                    <tr key={t.id}>
                      <td className="py-2">
                        <TaskName name={t.name} args={t.args} />
                      </td>
                      <td className="py-2 font-mono text-gray-500 text-xs">{t.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </div>
  );
}
