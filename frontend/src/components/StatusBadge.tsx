const GRAY = "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
const BLUE = "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300";
const GREEN = "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300";
const YELLOW = "bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300";
const RED = "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300";
const CYAN = "bg-cyan-100 text-cyan-700 dark:bg-cyan-900 dark:text-cyan-300";
const PURPLE = "bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300";

const COLORS: Record<string, string> = {
  draft: GRAY,
  pending: GRAY,
  running: BLUE,
  completed: GREEN,
  completed_with_errors: YELLOW,
  failed: RED,
  queued: GRAY,
  screening: CYAN,
  screened_out: GRAY,
  fetching: BLUE,
  uploading: CYAN,
  scoring: PURPLE,
  fetch_failed: RED,
  upload_failed: RED,
  score_failed: RED,
  processed: GREEN,
  success: GREEN,
};

const LABELS: Record<string, string> = {
  completed_with_errors: "partial",
  screened_out: "skipped",
  fetch_failed: "fetch failed",
  upload_failed: "upload failed",
  score_failed: "score failed",
};

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-medium capitalize ${COLORS[status] ?? GRAY}`}
    >
      {LABELS[status] ?? status}
    </span>
  );
}
