const STYLES: Record<string, { cls: string; label: string }> = {
  green: {
    cls: "bg-green-100 text-green-700 border-green-300 dark:bg-green-900 dark:text-green-300 dark:border-green-700",
    label: "Normal",
  },
  yellow: {
    cls: "bg-yellow-100 text-yellow-700 border-yellow-300 dark:bg-yellow-900 dark:text-yellow-300 dark:border-yellow-700",
    label: "Caution",
  },
  red: {
    cls: "bg-red-100 text-red-700 border-red-300 dark:bg-red-900 dark:text-red-300 dark:border-red-700",
    label: "Alert",
  },
};

export default function SeverityBadge({ severity, status }: { severity: string | null; status?: string }) {
  if (!severity) {
    const label = status === "processed" ? "no data" : "—";
    return <span className="text-gray-500 text-xs">{label}</span>;
  }
  const { cls, label } = STYLES[severity] ?? {
    cls: "bg-gray-100 text-gray-600 border-gray-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-600",
    label: severity,
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded border text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}
