import type { InfraStatus } from "./types";

// SAMPLE DATA: stands in for the infrastructure endpoint until it exists, shaped exactly like its response.
// Task names, images and hosts match this stack so the page reads the way it will with real data.

const GB = 1024 ** 3;
const MB = 1024 ** 2;

// seeded, so the sample looks the same on every load rather than jumping around
function random(seed: number) {
  let t = seed;
  return () => {
    t = (t + 0x6d2b79f5) | 0;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r = (r + Math.imul(r ^ (r >>> 7), 61 | r)) ^ r;
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

const ago = (now: Date, seconds: number) => new Date(now.getTime() - seconds * 1000).toISOString();
const ahead = (now: Date, seconds: number) => new Date(now.getTime() + seconds * 1000).toISOString();
const uuid = (rand: () => number) => {
  const hex = Array.from({ length: 32 }, () => Math.floor(rand() * 16).toString(16)).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
};

export function sampleInfraStatus(now: Date): InfraStatus {
  const rand = random(42);
  const worker = "6624fac2e202-1";

  const throughput = Array.from({ length: 60 }, (_, i) => {
    const minute = new Date(now.getTime() - (59 - i) * 60_000);
    minute.setSeconds(0, 0);
    const load = i < 25 ? 1 + rand() * 2 : 14 + rand() * 10;
    return { minute: minute.toISOString(), succeeded: Math.round(load), failed: rand() > 0.9 ? 1 : 0 };
  });

  const running = [
    { task: "store_item_bands", seconds: 48, attempts: 1 },
    { task: "store_item_bands", seconds: 31, attempts: 1 },
    { task: "score_model_run", seconds: 12, attempts: 1 },
    { task: "store_item_bands", seconds: 95, attempts: 2 },
  ].map((j) => ({ id: uuid(rand), task: j.task, args: [uuid(rand)], worker: `${worker}-${Math.floor(rand() * 4)}`, attempts: j.attempts, started_at: ago(now, j.seconds) }));

  return {
    generated_at: now.toISOString(),

    workers: [
      {
        id: worker,
        host: "6624fac2e202",
        pid: 1,
        threads: 4,
        busy_threads: 4,
        started_at: ago(now, 3 * 3600 + 1260),
        last_heartbeat: ago(now, 3),
        is_scheduler_leader: true,
        current_jobs: running.map((j) => ({ id: j.id, task: j.task, started_at: j.started_at })),
      },
      {
        id: "a91c03d7be44-1",
        host: "a91c03d7be44",
        pid: 1,
        threads: 4,
        busy_threads: 0,
        started_at: ago(now, 1500),
        last_heartbeat: ago(now, 2),
        is_scheduler_leader: false,
        current_jobs: [],
      },
    ],

    queue: {
      counts: { blocked: 1812, ready: 436, running: running.length, succeeded: 2604, failed: 2, dead: 3, skipped: 11 },
      oldest_ready_wait_s: 184,
      throughput,
      by_task: [
        { task: "store_item_bands", running: 3, queued: 431, succeeded_1h: 402, failed_1h: 2, avg_duration_s: 41.2, p95_duration_s: 96.4 },
        { task: "score_model_run", running: 1, queued: 1812, succeeded_1h: 380, failed_1h: 1, avg_duration_s: 6.8, p95_duration_s: 14.1 },
        { task: "screen_item", running: 0, queued: 4, succeeded_1h: 420, failed_1h: 0, avg_duration_s: 0.4, p95_duration_s: 1.2 },
        { task: "run_workflow", running: 0, queued: 0, succeeded_1h: 1, failed_1h: 0, avg_duration_s: 207.6, p95_duration_s: 207.6 },
        { task: "check_due_workflows", running: 0, queued: 1, succeeded_1h: 60, failed_1h: 0, avg_duration_s: 0.1, p95_duration_s: 0.2 },
        { task: "smoke_test_model", running: 0, queued: 0, succeeded_1h: 2, failed_1h: 0, avg_duration_s: 8.9, p95_duration_s: 11.3 },
      ],
      running,
      queued: [
        ...Array.from({ length: 6 }, (_, i) => ({ id: uuid(rand), task: "store_item_bands", args: [uuid(rand)], status: "ready" as const, run_after: ago(now, 184 - i * 9) })),
        ...Array.from({ length: 4 }, () => ({ id: uuid(rand), task: "score_model_run", args: [uuid(rand)], status: "blocked" as const, run_after: ago(now, 212) })),
      ],
      dead: [
        {
          id: uuid(rand),
          task: "store_item_bands",
          args: [uuid(rand)],
          attempts: 3,
          last_error: "image 'localhost/geotriage/planetary-computer:0.1' exited 3 on 'sign': AttributeError: module 'planetary_computer' has no attribute 'sign'",
          finished_at: ago(now, 5400),
        },
        {
          id: uuid(rand),
          task: "store_item_bands",
          args: [uuid(rand)],
          attempts: 3,
          last_error: "RasterioIOError: HTTP response code: 403 while reading LC09_L2SP_030037_20260901_20260902_02_T1_ST_B10.TIF",
          finished_at: ago(now, 2280),
        },
        {
          id: uuid(rand),
          task: "delete_workflow_artifacts",
          args: [uuid(rand)],
          attempts: 3,
          last_error: "EndpointConnectionError: Could not connect to the endpoint URL: \"http://minio:9000/artifacts\"",
          finished_at: ago(now, 760),
        },
      ],
      recurring: [{ task: "check_due_workflows", interval_s: 60, next_run_at: ahead(now, 23), enabled: true }],
    },

    runs: {
      limits: { memory: "2g", cpus: "2", timeout_s: 900 },
      running: [
        { container_id: "3f9a1c2b7d10", image: "localhost/geotriage/planetary-computer:0.1", command: "sign", started_at: ago(now, 2) },
        { container_id: "81be44c09a3f", image: "localhost/geotriage/ndwi-water:0.1", command: "run", started_at: ago(now, 9) },
      ],
      recent: [
        { container_id: "c02d9e1f4a88", image: "localhost/geotriage/ndwi-water:0.1", command: "run", started_at: ago(now, 40), duration_s: 6.2, exit_code: 0, outcome: "succeeded" },
        { container_id: "7ab3e5d2c119", image: "localhost/geotriage/earth-search:0.1", command: "sign", started_at: ago(now, 55), duration_s: 1.1, exit_code: 0, outcome: "succeeded" },
        { container_id: "e4f60a7b3d21", image: "localhost/geotriage/lst:0.1", command: "run", started_at: ago(now, 140), duration_s: 38.4, exit_code: 137, outcome: "memory_killed" },
        { container_id: "19d8c3b2a6f0", image: "localhost/geotriage/planetary-computer:0.1", command: "search", started_at: ago(now, 212), duration_s: 4.7, exit_code: 0, outcome: "succeeded" },
        { container_id: "5c7e2a9d1b34", image: "localhost/geotriage/ndwi-water:0.1", command: "run", started_at: ago(now, 300), duration_s: 5.9, exit_code: 0, outcome: "succeeded" },
        { container_id: "a0b1c2d3e4f5", image: "localhost/geotriage/lst:0.1", command: "run", started_at: ago(now, 1100), duration_s: 900, exit_code: 124, outcome: "timed_out" },
      ],
      images: [
        { image: "localhost/geotriage/ndwi-water:0.1", kind: "model", size_bytes: 1.21 * GB },
        { image: "localhost/geotriage/lst:0.1", kind: "model", size_bytes: 1.21 * GB },
        { image: "localhost/geotriage/earth-search:0.1", kind: "provider", size_bytes: 1.19 * GB },
        { image: "localhost/geotriage/planetary-computer:0.1", kind: "provider", size_bytes: 1.2 * GB },
      ],
    },

    storage: {
      disk: { path: "/", total_bytes: 78 * GB, used_bytes: 66.2 * GB },
      database: {
        size_bytes: 412 * MB,
        tables: [
          { name: "stac_items", size_bytes: 268 * MB, rows: 2260 },
          { name: "jobs", size_bytes: 71 * MB, rows: 7153 },
          { name: "model_runs", size_bytes: 29 * MB, rows: 2260 },
          { name: "workflow_items", size_bytes: 18 * MB, rows: 2260 },
          { name: "model_scores", size_bytes: 9 * MB, rows: 760 },
        ],
      },
      objects: { bucket: "artifacts", size_bytes: 11.8 * GB, objects: 1164 },
      scratch: { path: ".run-scratch", size_bytes: 386 * MB },
    },

    services: [
      { name: "PostgreSQL", ok: true, latency_ms: 2, detail: "PostgreSQL 15.4, 14 of 100 connections, no queries running over 30s" },
      { name: "MinIO", ok: true, latency_ms: 6, detail: "bucket artifacts reachable" },
      { name: "TiTiler", ok: true, latency_ms: 11, detail: "tile server responding" },
      { name: "Earth Search", ok: true, latency_ms: 238, detail: "STAC API responding" },
      { name: "Planetary Computer", ok: false, latency_ms: null, detail: "STAC API timed out after 10s" },
      { name: "Live updates", ok: true, latency_ms: null, detail: "listening on geotriage_changes, 2 browsers connected" },
      { name: "Docker", ok: true, latency_ms: 18, detail: "Docker 27.3, 2 run containers" },
    ],
  };
}
