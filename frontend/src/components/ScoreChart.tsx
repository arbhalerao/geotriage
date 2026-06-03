import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useWorkflowTimeseries } from "../api/queries";
import type { ModelInfo } from "../api/types";

const SERIES_COLORS = ["#2563eb", "#059669", "#d97706", "#7c3aed", "#dc2626", "#ea580c"];
const SEVERITY_FILL: Record<string, string> = {
  green: "#16a34a",
  yellow: "#eab308",
  red: "#dc2626",
};

interface ChartRecord {
  ts: number;
  label: string;
  item_id: string;
  stac_item_id: string;
  [key: string]: unknown;
}

interface Props {
  workflowId: string;
  models?: ModelInfo[];
}

function getUnit(score: string, models?: ModelInfo[]): string {
  for (const m of models ?? []) {
    if (m.score_outputs[score]) return m.score_outputs[score].unit;
  }
  return "";
}

function SeverityDot(props: {
  cx?: number;
  cy?: number;
  payload?: ChartRecord;
  stroke?: string;
  severityKey: string;
}) {
  const { cx, cy, payload, stroke, severityKey } = props;
  if (cx == null || cy == null || payload == null) return null;
  const severity = payload[severityKey] as string | undefined;
  const fill = (severity && SEVERITY_FILL[severity]) ?? stroke ?? "#6b7280";
  return (
    <circle
      cx={cx}
      cy={cy}
      r={3.5}
      fill={fill}
      fillOpacity={0.55}
      stroke={stroke}
      strokeOpacity={0.6}
      strokeWidth={1.25}
    />
  );
}

function CustomTooltip(props: {
  active?: boolean;
  payload?: Array<{ dataKey: string; value: number; color: string; payload: ChartRecord }>;
  label?: string;
  activeScores: string[];
  models?: ModelInfo[];
}) {
  const { active, payload, label, activeScores, models } = props;
  if (!active || !payload?.length) return null;
  const sceneId = payload[0]?.payload?.stac_item_id;
  return (
    <div className="bg-white border border-gray-200 rounded-lg px-3 py-2.5 shadow-lg text-xs min-w-[160px] max-w-[280px]">
      <p className="text-gray-700 font-medium">{label}</p>
      {sceneId && (
        <p className="text-gray-400 font-mono text-[11px] mb-2 truncate" title={sceneId}>
          {sceneId}
        </p>
      )}
      {activeScores.map((score) => {
        const entry = payload.find((p) => p.dataKey === score);
        if (!entry || entry.value == null) return null;
        const severity = entry.payload[`${score}_severity`] as string | undefined;
        const unit = getUnit(score, models);
        return (
          <div key={score} className="flex items-center gap-1.5 mb-1 last:mb-0">
            <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: entry.color }} />
            <span className="text-gray-500 shrink-0">{score}:</span>
            <span className="text-gray-900 font-mono ml-auto pl-2">{entry.value.toFixed(4)}</span>
            {unit && <span className="text-gray-400">{unit}</span>}
            {severity && (
              <span
                className={`ml-1 px-1.5 py-0.5 rounded text-xs font-medium ${
                  severity === "green"
                    ? "bg-green-100 text-green-700"
                    : severity === "yellow"
                    ? "bg-yellow-100 text-yellow-700"
                    : "bg-red-100 text-red-700"
                }`}
              >
                {severity}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function ScoreChart({ workflowId, models }: Props) {
  const { data, isLoading } = useWorkflowTimeseries(workflowId);

  const [selectedScores, setSelectedScores] = useState<Set<string>>(new Set());
  const [zoomRange, setZoomRange] = useState<{ startIndex: number; endIndex: number } | null>(null);

  // pivot flat points into per-item records
  const { chartData, availableScores } = useMemo(() => {
    if (!data) return { chartData: [] as ChartRecord[], availableScores: [] as string[] };

    const byItem: Record<string, ChartRecord> = {};
    for (const p of data.points) {
      if (!byItem[p.item_id]) {
        byItem[p.item_id] = {
          ts: new Date(p.scene_datetime).getTime(),
          label: new Date(p.scene_datetime).toLocaleDateString(undefined, {
            year: "numeric",
            month: "short",
            day: "numeric",
          }),
          item_id: p.item_id,
          stac_item_id: p.stac_item_id,
        };
      }
      byItem[p.item_id][p.score_name] = p.score_value;
      byItem[p.item_id][`${p.score_name}_severity`] = p.severity;
    }

    const chartData = Object.values(byItem).sort((a, b) => a.ts - b.ts);
    return { chartData, availableScores: data.available_scores };
  }, [data]);

  useEffect(() => {
    if (availableScores.length > 0) {
      setSelectedScores(new Set(availableScores));
    }
  }, [availableScores.join(",")]);

  const zoomRangeRef = useRef(zoomRange);
  zoomRangeRef.current = zoomRange;
  const dataLenRef = useRef(chartData.length);
  dataLenRef.current = chartData.length;

  const toggleScore = (score: string) => {
    setSelectedScores((prev) => {
      const next = new Set(prev);
      if (next.has(score)) {
        if (next.size > 1) next.delete(score);
      } else {
        next.add(score);
      }
      return next;
    });
  };

  const startIndex = zoomRange?.startIndex ?? 0;
  const endIndex = zoomRange?.endIndex ?? Math.max(0, chartData.length - 1);

  // zoom is applied by slicing the data to the selected index window
  const displayData = useMemo(
    () => (zoomRange ? chartData.slice(startIndex, endIndex + 1) : chartData),
    [chartData, zoomRange, startIndex, endIndex],
  );

  const zoomIn = useCallback(() => {
    const len = dataLenRef.current;
    const r = zoomRangeRef.current;
    const si = r?.startIndex ?? 0;
    const ei = r?.endIndex ?? Math.max(0, len - 1);
    const span = ei - si;
    const delta = Math.max(1, Math.floor(span * 0.25));
    setZoomRange({
      startIndex: Math.min(si + delta, ei - 1),
      endIndex: Math.max(ei - delta, si + 1),
    });
  }, []);

  const zoomOut = useCallback(() => {
    const len = dataLenRef.current;
    const r = zoomRangeRef.current;
    const si = r?.startIndex ?? 0;
    const ei = r?.endIndex ?? Math.max(0, len - 1);
    const span = ei - si;
    const delta = Math.max(1, Math.floor(span * 0.33));
    setZoomRange({
      startIndex: Math.max(0, si - delta),
      endIndex: Math.min(len - 1, ei + delta),
    });
  }, []);

  const resetZoom = () => setZoomRange(null);

  // callback ref so the wheel listener attaches whenever the chart node actually mounts (it doesn't exist during the loading/empty states)
  const wheelCleanupRef = useRef<(() => void) | null>(null);
  const chartWrapperRef = useCallback(
    (el: HTMLDivElement | null) => {
      wheelCleanupRef.current?.();
      wheelCleanupRef.current = null;
      if (!el) return;
      const handler = (e: WheelEvent) => {
        if (dataLenRef.current < 3) return;
        e.preventDefault();
        if (e.deltaY < 0) zoomIn();
        else zoomOut();
      };
      el.addEventListener("wheel", handler, { passive: false });
      wheelCleanupRef.current = () => el.removeEventListener("wheel", handler);
    },
    [zoomIn, zoomOut],
  );

  if (isLoading) {
    return (
      <div className="h-48 flex items-center justify-center text-gray-500 text-sm">
        Loading chart…
      </div>
    );
  }

  if (!data || chartData.length === 0) {
    return (
      <div className="h-24 flex items-center justify-center text-gray-500 text-sm">
        No scored scenes yet — run the workflow to populate the chart.
      </div>
    );
  }

  const activeScores = availableScores.filter((s) => selectedScores.has(s));
  const isZoomed = zoomRange !== null;

  return (
    <div className="space-y-3 bg-white rounded-lg p-3 text-gray-700">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-500">Series:</span>
          {availableScores.map((score, i) => {
            const active = selectedScores.has(score);
            const color = SERIES_COLORS[i % SERIES_COLORS.length];
            return (
              <button
                key={score}
                onClick={() => toggleScore(score)}
                className="text-xs px-2.5 py-1 rounded border transition-colors flex items-center gap-1.5"
                style={
                  active
                    ? { borderColor: color, backgroundColor: color + "1a", color: "#111827" }
                    : { borderColor: "#d1d5db", color: "#9ca3af" }
                }
              >
                <span
                  className="inline-block w-2 h-2 rounded-full shrink-0"
                  style={{ backgroundColor: active ? color : "#d1d5db" }}
                />
                {score}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-1.5 text-xs">
          <button
            onClick={zoomOut}
            title="Zoom out"
            className="w-7 h-7 flex items-center justify-center rounded bg-gray-50 border border-gray-300 text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition-colors"
          >
            −
          </button>
          <button
            onClick={zoomIn}
            title="Zoom in"
            className="w-7 h-7 flex items-center justify-center rounded bg-gray-50 border border-gray-300 text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition-colors"
          >
            +
          </button>
          {isZoomed && (
            <button
              onClick={resetZoom}
              className="px-2 h-7 rounded bg-gray-50 border border-gray-300 text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition-colors"
            >
              Reset
            </button>
          )}
          <span className="text-gray-400 ml-1 hidden sm:inline">scroll to zoom</span>
        </div>
      </div>

      <div
        ref={chartWrapperRef}
        className="select-none cursor-crosshair [&_svg]:outline-none [&_*:focus]:outline-none"
      >
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={displayData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: "#6b7280" }}
              tickLine={false}
              axisLine={{ stroke: "#d1d5db" }}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#6b7280" }}
              tickLine={false}
              axisLine={false}
              width={52}
              tickFormatter={(v: number) => v.toFixed(2)}
            />
            <Tooltip
              content={
                <CustomTooltip activeScores={activeScores} models={models} />
              }
              cursor={{ stroke: "#9ca3af", strokeWidth: 1, strokeDasharray: "4 2" }}
            />
            {activeScores.map((score, i) => {
              const color = SERIES_COLORS[i % SERIES_COLORS.length];
              return (
                <Line
                  key={score}
                  type="monotone"
                  dataKey={score}
                  stroke={color}
                  strokeWidth={1.75}
                  strokeOpacity={0.6}
                  dot={(dotProps) => (
                    <SeverityDot
                      key={`dot-${dotProps.index}`}
                      cx={dotProps.cx}
                      cy={dotProps.cy}
                      payload={dotProps.payload as ChartRecord}
                      stroke={color}
                      severityKey={`${score}_severity`}
                    />
                  )}
                  activeDot={false}
                  connectNulls={false}
                  name={score}
                  isAnimationActive={false}
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <p className="text-xs text-gray-600">
        {chartData.length} scene{chartData.length !== 1 ? "s" : ""} · dots colored by severity
      </p>
    </div>
  );
}
