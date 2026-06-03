export interface BandInfo {
  normalized_name: string;
  asset_key: string;
  description: string;
  scale: number;
  offset: number;
}

export interface CollectionInfo {
  slug: string;
  display_name: string;
  description: string;
  processing_level: string;
  sensor_type: string;
  resolution_m: number;
  cloud_cover_property: string | null;
  bands: BandInfo[];
  provider_slug: string;
  provider_name: string;
}

export interface ThresholdBand {
  green: [number, number];
  yellow: [number, number];
}

export interface ScoreOutput {
  description: string;
  unit: string;
  value_range: [number, number];
}

export interface ModelInfo {
  slug: string;
  name: string;
  description: string;
  primary_score: string;
  required_bands: string[];
  derived_rasters: string[];
  max_cloud_cover: number | null;
  score_outputs: Record<string, ScoreOutput>;
  default_thresholds: Record<string, ThresholdBand>;
  compatible_collections: Record<string, { level: string; reasons: string[] }>;
}

export interface WorkflowSummary {
  id: string;
  name: string;
  description: string | null;
  time_mode: string;
  time_start: string;
  time_end: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ModelConfigResponse {
  id: string;
  model_slug: string;
  user_label: string | null;
  parameters: Record<string, unknown> | null;
}

export interface Workflow extends WorkflowSummary {
  aoi_id: string;
  aoi_geometry: GeoJSON.Geometry;
  aoi_filter_mode: string;
  poll_interval_minutes: number | null;
  last_checked_at: string | null;
  next_run_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  collection_slugs: string[];
  model_configs: ModelConfigResponse[];
  total_items: number;
  processed_items: number;
  identified_items: number;
  failed_fetch_items: number;
  failed_upload_items: number;
  failed_score_items: number;
  screened_out_items: number;
}

export interface StacItem {
  id: string;
  collection: string;
  datetime: string;
  bbox: number[] | null;
  properties: Record<string, unknown>;
  assets: Record<string, Record<string, unknown>>;
}

export interface WorkflowItemSummary {
  id: string;
  collection_slug: string;
  stac_item_id: string;
  scene_datetime: string;
  status: string;
  overall_severity: string | null;
  discovered_at: string;
  processed_at: string | null;
  is_bookmarked: boolean;
  bbox: number[] | null;
}

export interface WorkflowItemPage {
  items: WorkflowItemSummary[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ModelScore {
  score_name: string;
  score_value: number;
  is_primary: boolean;
  severity: string;
}

export interface ModelRun {
  id: string;
  model_slug: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  scores: ModelScore[];
}

export interface Review {
  id: string;
  review_status: string;
  notes: string | null;
  reviewed_at: string | null;
  updated_at: string;
}

export interface WorkflowItemDetail extends WorkflowItemSummary {
  stac_item: StacItem;
  model_runs: ModelRun[];
  review: Review | null;
}

export interface Bookmark {
  id: string;
  workflow_item_id: string;
  notes: string | null;
  created_at: string;
}

export interface TimeseriesPoint {
  item_id: string;
  stac_item_id: string;
  scene_datetime: string;
  score_name: string;
  score_value: number;
  severity: string;
}

export interface TimeseriesResponse {
  available_scores: string[];
  points: TimeseriesPoint[];
}

export interface WorkerActiveTask {
  id: string;
  name: string;
  args: unknown[];
  worker: string | null;
  attempts: number;
  time_start?: string | null; // ISO datetime
}

export interface WorkerQueuedTask {
  id: string;
  name: string;
  args: unknown[];
  status: string; // "ready" | "blocked"
  run_after?: string | null; // ISO datetime
}

export interface WorkerStatus {
  workers: string[];
  active_tasks: WorkerActiveTask[];
  queued_tasks: WorkerQueuedTask[];
  total_active: number;
  total_queued: number;
  counts: Record<string, number>;
  error?: string;
}

export interface Registered {
  id: string;
  slug: string;
  name: string;
  image: string;
  is_enabled: boolean;
  descriptor: Record<string, unknown>;
  registered_at: string;
  admission: {
    checks?: AdmissionCheck[];
    problems?: string[];
    smoke_pending?: boolean;
  } | null;
}

export interface AdmissionCheck {
  name: string;
  passed: boolean;
  detail: string;
}

export interface AdmissionResponse {
  admitted: boolean;
  checks: AdmissionCheck[];
  problems: string[];
  registered: Registered | null;
}
