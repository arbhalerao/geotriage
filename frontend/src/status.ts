// one palette for every state in the app, so the same kind of state is the same colour wherever it appears:
// grey not started, blue in progress, green done, amber needs attention, red failed

export type Tone = "neutral" | "progress" | "good" | "warning" | "bad";

export const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-gray-600",
  progress: "text-blue-700",
  good: "text-green-700",
  warning: "text-amber-700",
  bad: "text-red-700",
};

const TONES: Record<string, Tone> = {
  draft: "neutral",
  pending: "neutral",
  queued: "neutral",
  screened_out: "neutral",
  skipped: "neutral",
  idle: "neutral",

  running: "progress",
  screening: "progress",
  fetching: "progress",
  uploading: "progress",
  scoring: "progress",
  testing: "progress",

  completed: "good",
  processed: "good",
  success: "good",
  succeeded: "good",
  ready: "good",

  completed_with_errors: "warning",
  timed_out: "warning",

  failed: "bad",
  fetch_failed: "bad",
  upload_failed: "bad",
  score_failed: "bad",
  memory_killed: "bad",
};

const LABELS: Record<string, string> = {
  completed_with_errors: "Completed with errors",
  screened_out: "Skipped",
  fetch_failed: "Fetch failed",
  upload_failed: "Upload failed",
  score_failed: "Score failed",
  memory_killed: "Out of memory",
  timed_out: "Timed out",
};

export function toneOf(state: string): Tone {
  return TONES[state] ?? "neutral";
}

export function labelOf(state: string): string {
  const words = LABELS[state] ?? state.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export const SEVERITY: Record<string, { tone: Tone; label: string }> = {
  green: { tone: "good", label: "Normal" },
  yellow: { tone: "warning", label: "Caution" },
  red: { tone: "bad", label: "Alert" },
};
