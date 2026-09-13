import type { ReactNode } from "react";
import { ToneText } from "./StatusBadge";

export default function Tile({
  label,
  value,
  note,
  alert,
  sample = false,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  alert?: string;
  sample?: boolean;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 min-w-0">
      <div className={sample ? "grayscale opacity-60" : ""}>
        <p className="text-sm text-gray-500">{label}</p>
        <p className="mt-1 text-2xl font-semibold text-gray-900">{value}</p>
        <div className="mt-1 flex items-center gap-2 min-h-5">
          {alert && <ToneText tone="warning">{alert}</ToneText>}
          {note && <p className="text-sm text-gray-500 truncate">{note}</p>}
        </div>
      </div>
    </div>
  );
}
