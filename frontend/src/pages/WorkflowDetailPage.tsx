import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useFetchNow, useModels, useRunWorkflow, useWorkflow, useWorkflowItems } from "../api/queries";
import SeverityBadge from "../components/SeverityBadge";
import StatusBadge from "../components/StatusBadge";
import MapViewer from "../components/MapViewer";
import type { MapViewerItem } from "../components/MapViewer";
import ScoreChart from "../components/ScoreChart";

function formatInterval(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  if (minutes < 1440) return `${minutes / 60}h`;
  if (minutes < 10080) return `${minutes / 1440}d`;
  return `${minutes / 10080}w`;
}

function fmtDate(d: string) {
  return new Date(d).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

const SEVERITY_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All" },
  { value: "red", label: "Alert" },
  { value: "yellow", label: "Caution" },
  { value: "green", label: "Normal" },
];

export default function WorkflowDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [severityFilter, setSeverityFilter] = useState("");
  const [mapOpen, setMapOpen] = useState(true);
  const [chartOpen, setChartOpen] = useState(true);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const { data: wf, isLoading: wfLoading } = useWorkflow(id!);
  const { data: models } = useModels();
  const isRunning = wf?.status === "running";

  const {
    data,
    isLoading: itemsLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useWorkflowItems(id!, severityFilter || undefined, isRunning);

  const runWf = useRunWorkflow();
  const fetchNow = useFetchNow();

  // intersection observer - load next page when sentinel enters viewport
  useEffect(() => {
    if (!sentinelRef.current) return;
    const obs = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) fetchNextPage(); },
      { threshold: 0.1 },
    );
    obs.observe(sentinelRef.current);
    return () => obs.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  if (wfLoading) return <div className="p-6 text-gray-600 dark:text-gray-400">Loading…</div>;
  if (!wf) return <div className="p-6 text-red-400">Workflow not found.</div>;

  const items = data?.pages.flatMap((p) => p.items) ?? [];
  const total = data?.pages[0]?.total ?? 0;

  const mapItems: MapViewerItem[] = items
    .filter((i) => i.bbox && i.bbox.length === 4)
    .map((i) => ({
      id: i.id,
      bbox: i.bbox as [number, number, number, number],
      severity: i.overall_severity,
      status: i.status,
    }));

  function changeFilter(f: string) {
    setSeverityFilter(f);
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-start justify-between mb-6">
        <div>
          <Link to="/workflows" className="text-xs text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 mb-1 block">
            ← Workflows
          </Link>
          <h1 className="text-xl font-semibold flex items-center gap-3">
            {wf.name}
            <StatusBadge status={wf.status} />
          </h1>
          <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            {wf.time_mode} · {new Date(wf.time_start).toLocaleDateString()}
            {wf.time_end ? ` → ${new Date(wf.time_end).toLocaleDateString()}` : ""}
          </div>
          {wf.error_message && (
            <div className="mt-2 text-xs text-red-400 bg-red-950 border border-red-800 rounded px-3 py-2 max-w-lg">
              {wf.error_message}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {isRunning && (
            <span className="flex items-center gap-1.5 text-xs text-blue-400">
              <span className="inline-block w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
              Live
            </span>
          )}
          {(wf.status === "draft" || wf.status === "failed") && (
            <button
              onClick={() => runWf.mutate(wf.id)}
              disabled={runWf.isPending}
              className="text-sm px-4 py-2 bg-blue-700 hover:bg-blue-600 text-white rounded transition-colors"
            >
              {runWf.isPending ? "Running…" : "Run workflow"}
            </button>
          )}
        </div>
      </div>

      <div className="flex gap-2 flex-wrap mb-3 text-xs text-gray-600 dark:text-gray-400">
        {wf.collection_slugs.map((c) => (
          <span key={c} className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-0.5">{c}</span>
        ))}
        {wf.model_configs.map((m) => (
          <span key={m.id} className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-0.5">
            🤖 {m.model_slug}
          </span>
        ))}
        <span className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-0.5">
          {wf.aoi_filter_mode === "enclosed" ? "≥80% enclosed" : "intersects"}
        </span>
      </div>

      {wf.total_items > 0 && (
        <div className="flex gap-3 mb-4 text-xs flex-wrap">
          <span className="text-gray-600 dark:text-gray-400">
            <span className="text-gray-900 dark:text-white font-medium">{wf.processed_items}</span>
            <span className="text-gray-500">/{wf.total_items}</span>
            {" "}processed
          </span>
          <span className="text-gray-500 dark:text-gray-600">·</span>
          <span className="text-gray-600 dark:text-gray-400">
            <span className={`font-medium ${wf.identified_items > 0 ? "text-yellow-400" : "text-gray-900 dark:text-white"}`}>
              {wf.identified_items}
            </span>
            {" "}identified
          </span>
          {wf.screened_out_items > 0 && (
            <>
              <span className="text-gray-500 dark:text-gray-600">·</span>
              <span
                className="text-gray-500"
                title="A model's prefilter rejected these scenes from a coarse overview, so they were never fetched at full resolution"
              >
                <span className="font-medium">{wf.screened_out_items}</span> skipped
              </span>
            </>
          )}
          {(wf.failed_fetch_items + wf.failed_upload_items + wf.failed_score_items) > 0 && (
            <>
              <span className="text-gray-500 dark:text-gray-600">·</span>
              {wf.failed_fetch_items > 0 && (
                <span className="text-red-400" title="Band download/clip failed before bands could be stored">
                  <span className="font-medium">{wf.failed_fetch_items}</span> fetch failed
                </span>
              )}
              {wf.failed_upload_items > 0 && (
                <span className="text-red-400" title="MinIO upload failed after the bands were clipped">
                  <span className="font-medium">{wf.failed_upload_items}</span> upload failed
                </span>
              )}
              {wf.failed_score_items > 0 && (
                <span className="text-red-400" title="Bands were stored but a model run errored during scoring">
                  <span className="font-medium">{wf.failed_score_items}</span> score failed
                </span>
              )}
            </>
          )}
        </div>
      )}

      {/* monitoring bar (fixed_future only) */}
      {wf.time_mode === "fixed_future" && (
        <div className="mb-4 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg px-4 py-3 flex items-center gap-4 flex-wrap text-xs">
          <span className="text-gray-600 dark:text-gray-400 font-medium">Continuous monitoring</span>
          <span className="text-gray-500 dark:text-gray-600">·</span>
          {wf.poll_interval_minutes ? (
            <>
              <span className="text-gray-600 dark:text-gray-400">
                Interval: <span className="text-gray-800 dark:text-gray-200">{formatInterval(wf.poll_interval_minutes)}</span>
              </span>
              {wf.last_checked_at && (
                <>
                  <span className="text-gray-500 dark:text-gray-600">·</span>
                  <span className="text-gray-600 dark:text-gray-400">
                    Last checked: <span className="text-gray-800 dark:text-gray-200">{fmtDate(wf.last_checked_at)}</span>
                  </span>
                </>
              )}
              {wf.next_run_at && wf.status !== "running" && (
                <>
                  <span className="text-gray-500 dark:text-gray-600">·</span>
                  <span className="text-gray-600 dark:text-gray-400">
                    Next run: <span className="text-gray-800 dark:text-gray-200">{fmtDate(wf.next_run_at)}</span>
                  </span>
                </>
              )}
            </>
          ) : (
            <span className="text-gray-500">No automatic interval set</span>
          )}
          <div className="ml-auto">
            <button
              onClick={() => fetchNow.mutate(wf.id)}
              disabled={fetchNow.isPending || isRunning}
              className="px-3 py-1.5 text-xs bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-40 transition-colors"
            >
              {fetchNow.isPending ? "Fetching…" : "Fetch now"}
            </button>
          </div>
        </div>
      )}

      <div className="mb-4 border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden">
        <button
          onClick={() => setMapOpen((o) => !o)}
          className="w-full px-4 py-2 flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 bg-white dark:bg-gray-900 hover:bg-gray-100/70 dark:hover:bg-gray-800/60 transition-colors"
        >
          <span>Map — AOI &amp; scene footprints</span>
          <span>{mapOpen ? "▲" : "▼"}</span>
        </button>
        {mapOpen && (
          <MapViewer
            aoi={wf.aoi_geometry}
            items={mapItems}
            onItemClick={(itemId) => navigate(`/workflows/${wf.id}/items/${itemId}`)}
            className="h-64 w-full"
          />
        )}
      </div>

      {wf.processed_items > 0 && (
        <div className="mb-4 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden">
          <button
            onClick={() => setChartOpen((o) => !o)}
            className="w-full px-4 py-2 flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 bg-white dark:bg-gray-900 hover:bg-gray-100/70 dark:hover:bg-gray-800/60 transition-colors"
          >
            <span>Score trends over time</span>
            <span>{chartOpen ? "▲" : "▼"}</span>
          </button>
          {chartOpen && (
            <div className="px-4 pb-4 pt-1">
              <ScoreChart workflowId={wf.id} models={models} />
            </div>
          )}
        </div>
      )}

      <div className="flex gap-2 mb-4">
        {SEVERITY_FILTERS.map(({ value, label }) => (
          <button
            key={value || "all"}
            onClick={() => changeFilter(value)}
            className={`text-xs px-3 py-1.5 rounded border transition-colors ${severityFilter === value
                ? "border-brand-500 text-brand-400 bg-brand-900/10 dark:bg-brand-900/30"
                : "border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-600"
              }`}
          >
            {label}
          </button>
        ))}
      </div>

      {itemsLoading && <p className="text-gray-600 dark:text-gray-400 text-sm">Loading items…</p>}
      {!itemsLoading && items.length === 0 && (
        <div className="text-center py-16 text-gray-500">
          <p>No items yet. Run the workflow to discover scenes.</p>
        </div>
      )}

      {items.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-600 dark:text-gray-400 border-b border-gray-200 dark:border-gray-800">
                  <th className="pb-2 pr-4">Scene date</th>
                  <th className="pb-2 pr-4">STAC item ID</th>
                  <th className="pb-2 pr-4">Collection</th>
                  <th className="pb-2 pr-4">Status</th>
                  <th className="pb-2 pr-4">Severity</th>
                  <th className="pb-2 pr-4">Bookmarked</th>
                  <th className="pb-2" />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-b border-gray-200/60 dark:border-gray-800/50 hover:bg-gray-200/50 dark:hover:bg-gray-900/40">
                    <td className="py-2.5 pr-4 text-gray-800 dark:text-gray-200 whitespace-nowrap">
                      {new Date(item.scene_datetime).toLocaleDateString()}
                    </td>
                    <td className="py-2.5 pr-4 font-mono text-xs text-gray-700 dark:text-gray-300 max-w-xs truncate">
                      {item.stac_item_id}
                    </td>
                    <td className="py-2.5 pr-4 text-gray-600 dark:text-gray-400 text-xs">{item.collection_slug}</td>
                    <td className="py-2.5 pr-4"><StatusBadge status={item.status} /></td>
                    <td className="py-2.5 pr-4">
                      <SeverityBadge severity={item.overall_severity} status={item.status} />
                    </td>
                    <td className="py-2.5 pr-4 text-gray-600 dark:text-gray-400">{item.is_bookmarked ? "★" : ""}</td>
                    <td className="py-2.5">
                      <Link
                        to={`/workflows/${wf.id}/items/${item.id}`}
                        className="text-xs text-brand-400 hover:underline"
                      >
                        Detail →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-2 text-xs text-gray-500">
            {items.length} of {total} item{total !== 1 ? "s" : ""}
          </div>
        </>
      )}

      {/* infinite scroll sentinel */}
      <div ref={sentinelRef} className="py-4 text-center text-xs text-gray-500 dark:text-gray-600">
        {isFetchingNextPage ? "Loading more…" : hasNextPage ? "" : items.length > 0 ? "All items loaded" : ""}
      </div>

      <div className="mt-2 text-xs text-gray-500 dark:text-gray-600">
        Created {fmtDate(wf.created_at)}
        {wf.completed_at ? ` · Completed ${fmtDate(wf.completed_at)}` : ""}
      </div>
    </div>
  );
}
