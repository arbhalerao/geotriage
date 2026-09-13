// the shape the infrastructure endpoint will return; the page renders from this and nothing else,
// so swapping the sample data for the API changes where it comes from, not how it is drawn

export interface InfraStatus {
  generated_at: string;
  workers: WorkerProcess[];
  queue: QueueStatus;
  runs: RunsStatus;
  storage: StorageStatus;
  services: ServiceCheck[];
}

export interface WorkerProcess {
  id: string;
  host: string;
  pid: number;
  threads: number;
  busy_threads: number;
  started_at: string;
  last_heartbeat: string;
  is_scheduler_leader: boolean;
  current_jobs: { id: string; task: string; started_at: string }[];
}

export type JobStatus = "blocked" | "ready" | "running" | "succeeded" | "failed" | "dead" | "skipped";

export interface QueueStatus {
  // live states are current; terminal states count the last 24 hours
  counts: Record<JobStatus, number>;
  oldest_ready_wait_s: number | null;
  // one entry per minute for the last hour, oldest first
  throughput: { minute: string; succeeded: number; failed: number }[];
  by_task: TaskStats[];
  running: { id: string; task: string; args: unknown[]; worker: string; attempts: number; started_at: string }[];
  queued: { id: string; task: string; args: unknown[]; status: "ready" | "blocked"; run_after: string }[];
  dead: { id: string; task: string; args: unknown[]; attempts: number; last_error: string; finished_at: string }[];
  recurring: { task: string; interval_s: number; next_run_at: string; enabled: boolean }[];
}

export interface TaskStats {
  task: string;
  running: number;
  queued: number;
  succeeded_1h: number;
  failed_1h: number;
  avg_duration_s: number | null;
  p95_duration_s: number | null;
}

export type RunOutcome = "succeeded" | "failed" | "memory_killed" | "timed_out";

export interface RunsStatus {
  limits: { memory: string; cpus: string; timeout_s: number };
  running: { container_id: string; image: string; command: string; started_at: string }[];
  recent: { container_id: string; image: string; command: string; started_at: string; duration_s: number; exit_code: number; outcome: RunOutcome }[];
  images: { image: string; kind: "model" | "provider"; size_bytes: number }[];
}

export interface StorageStatus {
  disk: { path: string; total_bytes: number; used_bytes: number };
  database: { size_bytes: number; tables: { name: string; size_bytes: number; rows: number }[] };
  objects: { bucket: string; size_bytes: number; objects: number };
  scratch: { path: string; size_bytes: number };
}

export interface ServiceCheck {
  name: string;
  ok: boolean;
  latency_ms: number | null;
  detail: string;
}
