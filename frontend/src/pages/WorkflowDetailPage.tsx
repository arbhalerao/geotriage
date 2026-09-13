import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useCollections, useFetchNow, useModels, useRunWorkflow, useWorkflow, useWorkflowItems } from "../api/queries";
import SeverityBadge from "../components/SeverityBadge";
import WorkflowDetails from "../components/WorkflowDetails";
import Tile from "../components/Tile";
import StatusBadge from "../components/StatusBadge";
import MapViewer from "../components/MapViewer";
import type { MapViewerItem } from "../components/MapViewer";
import ScoreChart from "../components/ScoreChart";
import Section from "../components/Section";
import { formatDate, formatDateTime } from "../time";

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
  const sentinelRef = useRef<HTMLDivElement>(null);

  const { data: wf, isLoading: wfLoading } = useWorkflow(id!);
  const { data: models } = useModels();
  const { data: collections } = useCollections();
  const isRunning = wf?.status === "running";

  const {
    data,
    isLoading: itemsLoading,
    isPlaceholderData: switchingFilter,
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

  if (wfLoading) return <div className="p-6 max-w-7xl mx-auto text-sm text-gray-500">Loading…</div>;
  if (!wf) return <div className="p-6 max-w-7xl mx-auto text-sm text-red-700">Workflow not found.</div>;

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

  const recurring = wf.time_mode === "recurring";
  const failed = wf.failed_fetch_items + wf.failed_upload_items + wf.failed_score_items;
  const failedNote = failed
    ? [
        wf.failed_fetch_items && `${wf.failed_fetch_items} fetch`,
        wf.failed_upload_items && `${wf.failed_upload_items} upload`,
        wf.failed_score_items && `${wf.failed_score_items} scoring`,
      ].filter(Boolean).join(", ")
    : "none";
  function changeFilter(f: string) {
    setSeverityFilter(f);
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="text-xs text-gray-600 mb-4 flex items-center gap-1">
        <Link to="/workflows" className="hover:text-gray-800">Workflows</Link>
        <span>/</span>
        <span className="text-gray-700 truncate">{wf.name}</span>
      </div>

      <div className="flex items-start justify-between gap-4 mb-6">
        <div className="min-w-0 flex items-center gap-3 flex-wrap">
          <h1 className="text-xl font-semibold text-gray-900">{wf.name}</h1>
          <StatusBadge status={wf.status} />
        </div>
        <div className="shrink-0">
          {(wf.status === "draft" || wf.status === "failed") && (
            <button
              onClick={() => runWf.mutate(wf.id)}
              disabled={runWf.isPending}
              className="text-sm px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white rounded transition-colors"
            >
              {runWf.isPending ? "Starting…" : "Run workflow"}
            </button>
          )}
          {recurring && wf.status !== "draft" && wf.status !== "failed" && (
            <button
              onClick={() => fetchNow.mutate(wf.id)}
              disabled={fetchNow.isPending || isRunning}
              className="text-sm px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 disabled:opacity-50 rounded transition-colors"
            >
              {fetchNow.isPending ? "Fetching…" : "Fetch now"}
            </button>
          )}
        </div>
      </div>

      {wf.error_message && (
        <div className="mb-4 rounded border border-red-200 bg-red-50/60 px-4 py-3 text-sm text-red-800">{wf.error_message}</div>
      )}

      {wf.total_items > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3 mb-4">
          <Tile label="Scenes found" value={wf.total_items.toLocaleString()} />
          <Tile label="Processed" value={wf.processed_items.toLocaleString()} note={`of ${wf.total_items.toLocaleString()}`} />
          <Tile label="Flagged" value={wf.identified_items.toLocaleString()} note="caution or alert" />
          <Tile label="Skipped" value={wf.screened_out_items.toLocaleString()} note="rejected by the prefilter" />
          <Tile label="Failed" value={failed.toLocaleString()} note={failedNote} />
        </div>
      )}

      <Section title="Details">
        <WorkflowDetails workflow={wf} />
      </Section>

      <Section title="Map: AOI &amp; scene footprints" bodyClassName="">
        <MapViewer
          aoi={wf.aoi_geometry}
          items={mapItems}
          onItemClick={(itemId) => navigate(`/workflows/${wf.id}/items/${itemId}`)}
          className="h-64 w-full"
        />
      </Section>

      {wf.processed_items > 0 && (
        <Section title="Score trends over time">
          <ScoreChart workflowId={wf.id} models={models} />
        </Section>
      )}

      {/* at least a screen tall: a filter that returns fewer rows would otherwise shorten the page,
          and if it was scrolled to the filters the browser would have to jump the view back up to fit */}
      <section className="min-h-screen">
        <div className="flex gap-2 mb-4">
          {SEVERITY_FILTERS.map(({ value, label }) => (
            <button
              key={value || "all"}
              onClick={() => changeFilter(value)}
              className={`text-xs px-3 py-1.5 rounded border transition-colors ${severityFilter === value
                  ? "border-brand-500 text-brand-700 bg-brand-50"
                  : "border-gray-300 text-gray-600 hover:border-gray-300"
                }`}
            >
              {label}
            </button>
          ))}
        </div>

        {itemsLoading && <p className="text-gray-600 text-sm">Loading items…</p>}
        {!itemsLoading && items.length === 0 && (
          <div className="text-center py-16 text-gray-500">
            <p>{severityFilter ? "No scenes match this filter." : "No items yet. Run the workflow to discover scenes."}</p>
          </div>
        )}

        {items.length > 0 && (
          <>
            {/* edge cells carry the card's padding, so a row's hover spans the full width */}
            <div className={`overflow-x-auto bg-white border border-gray-200 rounded-lg transition-opacity ${switchingFilter ? "opacity-60" : ""}`}>
              <table className="w-full text-sm [&_th:first-child]:pl-5 [&_td:first-child]:pl-5 [&_th:last-child]:pr-5 [&_td:last-child]:pr-5 [&_tbody_tr:last-child]:border-b-0">
                <thead>
                  <tr className="text-left text-xs text-gray-600 border-b border-gray-200">
                    <th className="py-3 pr-4 font-medium">Scene date</th>
                    <th className="py-3 pr-4 font-medium">STAC item ID</th>
                    <th className="py-3 pr-4 font-medium">Collection</th>
                    <th className="py-3 pr-4 font-medium">Status</th>
                    <th className="py-3 font-medium">Severity</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr
                      key={item.id}
                      onClick={() => navigate(`/workflows/${wf.id}/items/${item.id}`)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") navigate(`/workflows/${wf.id}/items/${item.id}`);
                      }}
                      tabIndex={0}
                      role="link"
                      aria-label={`Open scene ${item.stac_item_id}`}
                      // rows share their borders, so the hover edge is an outline drawn just inside
                      className="border-b border-gray-200/60 cursor-pointer hover:bg-gray-50 hover:outline hover:outline-1 hover:-outline-offset-1 hover:outline-gray-300 focus:outline-none focus-visible:bg-gray-50 focus-visible:outline focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-gray-300"
                    >
                      <td className="py-2.5 pr-4 text-gray-800 whitespace-nowrap">
                        {formatDate(item.scene_datetime)}
                      </td>
                      <td className="py-2.5 pr-4 font-mono text-xs text-gray-700 max-w-xs truncate">
                        {item.stac_item_id}
                      </td>
                      <td className="py-2.5 pr-4 text-gray-600">{collections?.find((c) => c.slug === item.collection_slug)?.display_name ?? item.collection_slug}</td>
                      <td className="py-2.5 pr-4"><StatusBadge status={item.status} /></td>
                      <td className="py-2.5 pr-4">
                        <SeverityBadge severity={item.overall_severity} status={item.status} />
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
        <div ref={sentinelRef} className="py-4 text-center text-xs text-gray-500">
          {isFetchingNextPage ? "Loading more…" : hasNextPage ? "" : items.length > 0 ? "All items loaded" : ""}
        </div>
      </section>

      <div className="mt-2 text-xs text-gray-500">
        Created {formatDateTime(wf.created_at)}
        {wf.completed_at ? ` · Completed ${formatDateTime(wf.completed_at)}` : ""}
      </div>
    </div>
  );
}
