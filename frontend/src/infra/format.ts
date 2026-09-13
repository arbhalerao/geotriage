import { formatTime } from "../time";

const UNITS = ["B", "KB", "MB", "GB", "TB"];

export function formatBytes(bytes: number): string {
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 100 || unit === 0 ? Math.round(value) : value.toFixed(1)} ${UNITS[unit]}`;
}

export function formatDuration(seconds: number): string {
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const pair = (big: number, bigUnit: string, small: number, smallUnit: string) => (small ? `${big}${bigUnit} ${small}${smallUnit}` : `${big}${bigUnit}`);
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return pair(minutes, "m", Math.round(seconds % 60), "s");
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return pair(hours, "h", minutes % 60, "m");
  return pair(Math.floor(hours / 24), "d", hours % 24, "h");
}

export function secondsBetween(from: string, to: Date): number {
  return Math.max(0, (to.getTime() - new Date(from).getTime()) / 1000);
}

export function formatAgo(iso: string, now: Date): string {
  const s = secondsBetween(iso, now);
  return s < 5 ? "just now" : `${formatDuration(s)} ago`;
}

export function formatUntil(iso: string, now: Date): string {
  const s = (new Date(iso).getTime() - now.getTime()) / 1000;
  return s <= 0 ? "due now" : `in ${formatDuration(s)}`;
}

export function formatClock(iso: string): string {
  return formatTime(iso, true);
}

export function formatCount(n: number): string {
  return n.toLocaleString();
}

export function taskLabel(task: string): string {
  const words = task.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
