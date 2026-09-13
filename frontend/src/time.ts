// the platform runs on UTC: dates are picked, sent and shown in UTC, whatever timezone the viewer is in

const UTC = "UTC";

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { timeZone: UTC, year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(iso: string): string {
  const text = new Date(iso).toLocaleString(undefined, { timeZone: UTC, year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  return `${text} UTC`;
}

export function formatTime(iso: string, withSeconds = false): string {
  const text = new Date(iso).toLocaleTimeString(undefined, { timeZone: UTC, hour: "2-digit", minute: "2-digit", ...(withSeconds ? { second: "2-digit" } : {}) });
  return `${text} UTC`;
}

export function todayUtc(): string {
  return new Date().toISOString().slice(0, 10);
}

export function dayAfter(day: string): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

export function startOfDayUtc(day: string): string {
  return `${day}T00:00:00.000Z`;
}

export function formatInterval(minutes: number): string {
  const named: Record<number, string> = { 60: "Every hour", 360: "Every 6 hours", 720: "Every 12 hours", 1440: "Daily", 10080: "Weekly" };
  return named[minutes] ?? `Every ${minutes} minutes`;
}
