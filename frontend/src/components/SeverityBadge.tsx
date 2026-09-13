import { SEVERITY, TONE_TEXT } from "../status";

export default function SeverityBadge({ severity, status }: { severity: string | null; status?: string }) {
  if (!severity) {
    return <span className="text-sm text-gray-500">{status === "processed" ? "no data" : "not scored"}</span>;
  }
  const { tone, label } = SEVERITY[severity] ?? { tone: "neutral" as const, label: severity };
  return <span className={`text-sm font-medium ${TONE_TEXT[tone]}`}>{label}</span>;
}
