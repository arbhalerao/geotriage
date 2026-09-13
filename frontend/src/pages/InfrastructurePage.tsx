import { useEffect, useMemo, useState, type ReactNode } from "react";
import { CheckItem, Collapsible, Panel, PanelBody, Rows } from "../components/Panel";
import StatusBadge, { ToneText } from "../components/StatusBadge";
import type { Tone } from "../status";
import Tile from "../components/Tile";
import ThroughputChart from "../infra/ThroughputChart";
import { sampleInfraStatus } from "../infra/sampleData";
import { formatAgo, formatBytes, formatClock, formatCount, formatDuration, formatUntil, secondsBetween, taskLabel } from "../infra/format";
import type { InfraStatus, WorkerProcess } from "../infra/types";

// a worker that hasn't heartbeated in this long is treated as gone
const HEARTBEAT_STALE_S = 30;
// below this share of the disk free, the page calls it out
const LOW_DISK_SHARE = 0.2;

function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}

// how often the sample refreshes, standing in for a poll, so heartbeats don't age into "No heartbeat"
const SAMPLE_REFRESH_MS = 5000;

// SAMPLE DATA until the infrastructure endpoint exists; the page renders from InfraStatus either way
function useInfraStatus(): { data: InfraStatus; isSample: boolean } {
  const tick = useNow(SAMPLE_REFRESH_MS);
  const data = useMemo(() => sampleInfraStatus(tick), [tick]);
  return { data, isSample: true };
}

type Column = { label: string; numeric?: boolean };

function Table({ columns, rows, empty }: { columns: Column[]; rows: ReactNode[][]; empty: string }) {
  if (!rows.length) return <p className="text-sm text-gray-500">{empty}</p>;
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-gray-200 text-gray-500">
          {columns.map((c) => (
            <th key={c.label} className={`py-2 pr-4 last:pr-0 text-xs font-medium text-gray-600 whitespace-nowrap ${c.numeric ? "text-right" : "text-left"}`}>
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100">
        {rows.map((cells, i) => (
          <tr key={i}>
            {cells.map((cell, j) => (
              <td key={j} className={`py-2 pr-4 last:pr-0 text-gray-900 ${columns[j].numeric ? "text-right tabular-nums whitespace-nowrap" : ""}`}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function shortId(id: string) {
  return id.slice(0, 8);
}

function workerState(w: WorkerProcess, now: Date): { tone: Tone; label: string } {
  if (secondsBetween(w.last_heartbeat, now) > HEARTBEAT_STALE_S) return { tone: "bad", label: "No heartbeat" };
  if (w.busy_threads === 0) return { tone: "neutral", label: "Idle" };
  return { tone: "progress", label: `${w.busy_threads} of ${w.threads} busy` };
}

function DiskMeter({ used, total }: { used: number; total: number }) {
  const share = total ? used / total : 0;
  const low = 1 - share < LOW_DISK_SHARE;
  return (
    <div className="mb-4">
      <div
        className="h-2 rounded-full bg-gray-100 overflow-hidden"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(share * 100)}
        aria-label="Disk used"
      >
        <div className={`h-full rounded-full ${low ? "bg-amber-500" : "bg-blue-600"}`} style={{ width: `${Math.min(100, share * 100)}%` }} />
      </div>
      <p className="mt-1.5 text-sm text-gray-500">{Math.round(share * 100)}% used</p>
    </div>
  );
}

export default function InfrastructurePage() {
  const { data, isSample } = useInfraStatus();
  const now = useNow();
  const { workers, queue, runs, storage, services } = data;

  const threads = workers.reduce((n, w) => n + w.threads, 0);
  const busy = workers.reduce((n, w) => n + w.busy_threads, 0);
  const online = workers.filter((w) => secondsBetween(w.last_heartbeat, now) <= HEARTBEAT_STALE_S).length;
  const waiting = queue.counts.ready + queue.counts.blocked;
  const diskFree = storage.disk.total_bytes - storage.disk.used_bytes;
  const lowDisk = diskFree / storage.disk.total_bytes < LOW_DISK_SHARE;
  const finishedLastHour = queue.throughput.reduce((n, t) => n + t.succeeded + t.failed, 0);
  const failedLastHour = queue.throughput.reduce((n, t) => n + t.failed, 0);
  const healthy = services.filter((s) => s.ok).length;
  const recentProblems = runs.recent.filter((r) => r.outcome !== "succeeded").length;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Infra (Work In Progress)</h1>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 mb-6">
        <Tile sample={isSample} label="Workers online" value={online} note={`${threads} threads, ${busy} busy`} />
        <Tile sample={isSample} label="Running" value={formatCount(queue.counts.running)} note="jobs right now" />
        <Tile sample={isSample} label="Waiting" value={formatCount(waiting)} note={`${formatCount(queue.counts.ready)} ready`} />
        <Tile sample={isSample} label="Oldest wait" value={queue.oldest_ready_wait_s != null ? formatDuration(queue.oldest_ready_wait_s) : "none"} note="for a ready job" />
        <Tile sample={isSample} label="Failed" value={formatCount(queue.counts.dead)} note="in the last 24h" />
        <Tile sample={isSample} label="Disk free" value={formatBytes(diskFree)} note={`of ${formatBytes(storage.disk.total_bytes)}`} alert={lowDisk ? "Low" : undefined} />
      </div>

      <div className="space-y-4">
        <Panel variant="section" sample={isSample} title="Throughput" subtitle={`Jobs finished per minute, last hour: ${formatCount(finishedLastHour)} finished, ${failedLastHour} failed`}>
          <PanelBody>
            <ThroughputChart throughput={queue.throughput} />
          </PanelBody>
        </Panel>

        <Panel variant="section" sample={isSample} title="Services" subtitle={`${healthy} of ${services.length} healthy`}>
          <PanelBody>
            <ul className="space-y-1">
              {services.map((s) => (
                <CheckItem key={s.name} state={s.ok ? "passed" : "failed"} note={[s.detail, s.latency_ms != null ? `${s.latency_ms} ms` : null].filter(Boolean).join(", ")}>
                  {s.name}
                </CheckItem>
              ))}
            </ul>
          </PanelBody>
        </Panel>

        <Panel variant="section" sample={isSample} title="Workers" subtitle={`${online} online, scheduler led by ${workers.find((w) => w.is_scheduler_leader)?.host ?? "nobody"}`}>
          {workers.length === 0 && (
            <PanelBody>
              <p className="text-sm text-gray-500">No workers online.</p>
            </PanelBody>
          )}
          {workers.map((w, i) => {
            const state = workerState(w, now);
            return (
              <Collapsible key={w.id} title={`${w.host} (process ${w.pid})`} summary={<ToneText tone={state.tone}>{state.label}</ToneText>} defaultOpen={i === 0}>
                <Rows
                  rows={[
                    ["Threads", `${w.threads}, ${w.busy_threads} busy`],
                    ["Up for", `${formatDuration(secondsBetween(w.started_at, now))}, since ${formatClock(w.started_at)}`],
                    ["Last heartbeat", formatAgo(w.last_heartbeat, now)],
                    ["Scheduler", w.is_scheduler_leader ? "Leader" : "Standby"],
                    [
                      "Current jobs",
                      w.current_jobs.length
                        ? w.current_jobs.map((j) => `${taskLabel(j.task)} for ${formatDuration(secondsBetween(j.started_at, now))}`).join(", ")
                        : "none",
                    ],
                  ]}
                />
              </Collapsible>
            );
          })}
        </Panel>

        <Panel variant="section" sample={isSample} title="Queue" subtitle={`${formatCount(queue.counts.running)} running, ${formatCount(waiting)} waiting, ${formatCount(queue.counts.succeeded)} done in 24h`}>
          <Collapsible title="By task" defaultOpen>
            <Table
              columns={[
                { label: "Task" },
                { label: "Running", numeric: true },
                { label: "Waiting", numeric: true },
                { label: "Done (1h)", numeric: true },
                { label: "Failed (1h)", numeric: true },
                { label: "Average", numeric: true },
                { label: "Slowest 5%", numeric: true },
              ]}
              rows={queue.by_task.map((t) => [
                taskLabel(t.task),
                formatCount(t.running),
                formatCount(t.queued),
                formatCount(t.succeeded_1h),
                formatCount(t.failed_1h),
                t.avg_duration_s != null ? formatDuration(t.avg_duration_s) : "none",
                t.p95_duration_s != null ? formatDuration(t.p95_duration_s) : "none",
              ])}
              empty="No jobs in the last hour."
            />
          </Collapsible>

          <Collapsible title="Running now" summary={formatCount(queue.running.length)}>
            <Table
              columns={[{ label: "Task" }, { label: "Job" }, { label: "Worker" }, { label: "Attempt", numeric: true }, { label: "Running for", numeric: true }]}
              rows={queue.running.map((j) => [taskLabel(j.task), shortId(j.id), j.worker, j.attempts, formatDuration(secondsBetween(j.started_at, now))])}
              empty="Nothing running."
            />
          </Collapsible>

          <Collapsible title="Waiting" summary={`${formatCount(queue.counts.ready)} ready, ${formatCount(queue.counts.blocked)} blocked`}>
            <Table
              columns={[{ label: "Task" }, { label: "Job" }, { label: "State" }, { label: "Waiting for", numeric: true }]}
              rows={queue.queued.map((j) => [
                taskLabel(j.task),
                shortId(j.id),
                j.status === "ready" ? "Ready" : "Waiting on earlier jobs",
                formatDuration(secondsBetween(j.run_after, now)),
              ])}
              empty="Nothing waiting."
            />
            {waiting > queue.queued.length && (
              <p className="mt-2 text-sm text-gray-500">
                Showing the first {queue.queued.length} of {formatCount(waiting)}.
              </p>
            )}
          </Collapsible>

          <Collapsible title="Failed" summary={`${queue.dead.length} in the last 24h`}>
            {queue.dead.length === 0 ? (
              <p className="text-sm text-gray-500">No failed jobs.</p>
            ) : (
              <ul className="space-y-3">
                {queue.dead.map((j) => (
                  <li key={j.id}>
                    <p className="text-sm text-gray-900">
                      {taskLabel(j.task)} <span className="text-gray-500">job {shortId(j.id)}, gave up after {j.attempts} attempts, {formatAgo(j.finished_at, now)}</span>
                    </p>
                    <p className="mt-1 rounded border border-red-200 bg-red-50/60 px-3 py-2 font-mono text-xs text-red-800 whitespace-pre-wrap break-words">{j.last_error}</p>
                  </li>
                ))}
              </ul>
            )}
          </Collapsible>

          <Collapsible title="Schedule" summary={`${queue.recurring.length} recurring`}>
            <Table
              columns={[{ label: "Task" }, { label: "Every", numeric: true }, { label: "Next run", numeric: true }]}
              rows={queue.recurring.map((r) => [
                `${taskLabel(r.task)}${r.enabled ? "" : " (paused)"}`,
                formatDuration(r.interval_s),
                r.enabled ? formatUntil(r.next_run_at, now) : "paused",
              ])}
              empty="Nothing scheduled."
            />
          </Collapsible>
        </Panel>

        <Panel
          variant="section"
          sample={isSample}
          title="Model and provider runs"
          subtitle={`Each run is capped at ${runs.limits.memory} memory, ${runs.limits.cpus} CPUs and ${formatDuration(runs.limits.timeout_s)}`}
        >
          <Collapsible title="Running now" summary={formatCount(runs.running.length)} defaultOpen>
            <Table
              columns={[{ label: "Image" }, { label: "Command" }, { label: "Container" }, { label: "Running for", numeric: true }]}
              rows={runs.running.map((r) => [r.image, r.command, r.container_id, formatDuration(secondsBetween(r.started_at, now))])}
              empty="No containers running."
            />
          </Collapsible>

          <Collapsible title="Recent runs" summary={recentProblems ? `${recentProblems} did not succeed` : "all succeeded"}>
            <Table
              columns={[{ label: "Image" }, { label: "Command" }, { label: "Started" }, { label: "Duration", numeric: true }, { label: "Exit", numeric: true }, { label: "Result" }]}
              rows={runs.recent.map((r) => [
                r.image,
                r.command,
                formatAgo(r.started_at, now),
                formatDuration(r.duration_s),
                r.exit_code,
                <StatusBadge status={r.outcome} />,
              ])}
              empty="No runs yet."
            />
          </Collapsible>

          <Collapsible title="Images" summary={formatBytes(runs.images.reduce((n, i) => n + i.size_bytes, 0))}>
            <Table
              columns={[{ label: "Image" }, { label: "Kind" }, { label: "Size", numeric: true }]}
              rows={runs.images.map((i) => [i.image, i.kind === "model" ? "Model" : "Provider", formatBytes(i.size_bytes)])}
              empty="No images registered."
            />
          </Collapsible>
        </Panel>

        <Panel variant="section" sample={isSample} title="Storage" subtitle={`${formatBytes(diskFree)} free on disk`}>
          <Collapsible title="Disk" summary={`${formatBytes(diskFree)} free`} defaultOpen>
            <DiskMeter used={storage.disk.used_bytes} total={storage.disk.total_bytes} />
            <Rows
              rows={[
                ["Path", storage.disk.path],
                ["Used", formatBytes(storage.disk.used_bytes)],
                ["Free", lowDisk ? `${formatBytes(diskFree)}, running low` : formatBytes(diskFree)],
                ["Total", formatBytes(storage.disk.total_bytes)],
              ]}
            />
          </Collapsible>

          <Collapsible title="Database" summary={formatBytes(storage.database.size_bytes)}>
            <Table
              columns={[{ label: "Table" }, { label: "Rows", numeric: true }, { label: "Size", numeric: true }]}
              rows={storage.database.tables.map((t) => [t.name, formatCount(t.rows), formatBytes(t.size_bytes)])}
              empty="No tables."
            />
          </Collapsible>

          <Collapsible title="Object storage" summary={formatBytes(storage.objects.size_bytes)}>
            <Rows
              rows={[
                ["Bucket", storage.objects.bucket],
                ["Objects", formatCount(storage.objects.objects)],
                ["Size", formatBytes(storage.objects.size_bytes)],
              ]}
            />
          </Collapsible>

          <Collapsible title="Run scratch" summary={formatBytes(storage.scratch.size_bytes)}>
            <Rows
              rows={[
                ["Path", storage.scratch.path],
                ["Size", formatBytes(storage.scratch.size_bytes)],
              ]}
            />
          </Collapsible>
        </Panel>
      </div>
    </div>
  );
}
