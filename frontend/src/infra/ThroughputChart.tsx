import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { QueueStatus } from "./types";
import { formatTime } from "../time";

// one series, so no legend: the panel title names it
const SERIES = "#2563eb";
const GRID = "#e5e7eb";
const AXIS_TEXT = "#6b7280";

type Point = { minute: string; label: string; finished: number; failed: number };

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded border border-gray-200 bg-white px-3 py-2 text-sm shadow-sm">
      <p className="text-gray-500">{point.label} UTC</p>
      <p className="text-gray-900">{point.finished} finished</p>
      {point.failed > 0 && <p className="text-gray-900">{point.failed} failed</p>}
    </div>
  );
}

export default function ThroughputChart({ throughput }: { throughput: QueueStatus["throughput"] }) {
  const data: Point[] = throughput.map((t) => ({
    minute: t.minute,
    label: formatTime(t.minute).replace(" UTC", ""),
    finished: t.succeeded + t.failed,
    failed: t.failed,
  }));

  return (
    <>
      <div className="h-56" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="label" tick={{ fill: AXIS_TEXT, fontSize: 12 }} tickLine={false} axisLine={{ stroke: GRID }} interval={9} minTickGap={24} />
            <YAxis allowDecimals={false} tick={{ fill: AXIS_TEXT, fontSize: 12 }} tickLine={false} axisLine={false} width={48} />
            <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#9ca3af", strokeWidth: 1 }} isAnimationActive={false} />
            <Area
              type="monotone"
              dataKey="finished"
              stroke={SERIES}
              strokeWidth={2}
              fill={SERIES}
              fillOpacity={0.1}
              dot={false}
              activeDot={{ r: 4, fill: SERIES, stroke: "#ffffff", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* the same numbers for screen readers, since the chart itself is hidden from them */}
      <table className="sr-only">
        <caption>Jobs finished per minute, last hour, times in UTC</caption>
        <thead>
          <tr>
            <th>Minute</th>
            <th>Finished</th>
            <th>Failed</th>
          </tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.minute}>
              <td>{d.label}</td>
              <td>{d.finished}</td>
              <td>{d.failed}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
