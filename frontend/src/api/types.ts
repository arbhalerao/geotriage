import type { ImageryKept, StoragePolicy } from "../storagePolicy";

export interface CollectionInfo {
  slug: string;
  display_name: string;
  processing_level: string;
  resolution_m: number;
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
  required_bands: string[];
  derived_rasters: string[];
  max_cloud_cover: number | null;
  score_outputs: Record<string, ScoreOutput>;
  default_thresholds: Record<string, ThresholdBand>;
  compatible_collections: Record<string, { level: string; reasons: string[] }>;
}

interface WorkflowBase {
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

export interface WorkflowSummary extends WorkflowBase {
  total_items: number;
  processed_items: number;
  identified_items: number;
  failed_items: number;
}

export interface ModelConfigResponse {
  id: string;
  model_slug: string;
  user_label: string | null;
  parameters: Record<string, unknown> | null;
}

export interface Workflow extends WorkflowBase {
  aoi_id: string;
  aoi_geometry: GeoJSON.Geometry;
  aoi_filter_mode: string;
  poll_interval_minutes: number | null;
  storage_policy: StoragePolicy;
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
  imagery_kept: ImageryKept;
  collection_slug: string;
  stac_item_id: string;
  scene_datetime: string;
  status: string;
  overall_severity: string | null;
  discovered_at: string;
  processed_at: string | null;
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

export interface WorkflowItemDetail extends WorkflowItemSummary {
  stac_item: StacItem;
  model_runs: ModelRun[];
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

export interface BuilderMessage {
  role: "user" | "assistant";
  content: string;
}

export interface BuilderDraft {
  name: string;
  geometry: GeoJSON.Polygon;
  time_mode: "historical" | "recurring";
  time_start?: string;
  time_end: string;
  poll_interval_minutes?: number;
  collection_slugs: string[];
  models: { model_slug: string }[];
}

export interface StorageEstimateResult {
  scenes: number;
  staged_bytes: number;
  free_bytes: number;
  capped: boolean;
  from_past_window: boolean;
  verdict: "fits" | "large" | "too_large";
  input_bytes: number;
  result_bytes: number;
}

export interface StorageEstimateRun {
  id: string;
  status: "queued" | "running" | "done" | "failed";
  result: StorageEstimateResult | null;
  error: string | null;
}

// what a workflow stages depends on these, and nothing else on the form
export interface EstimateRequest {
  geometry: GeoJSON.Polygon;
  time_mode: "historical" | "recurring";
  time_start: string | null;
  time_end: string;
  poll_interval_minutes: number | null;
  collection_slugs: string[];
  models: { model_slug: string }[];
}

export interface BuilderOutcome {
  kind: "draft" | "question" | "cannot";
  message: string;
  draft: BuilderDraft | null;
  warnings: string[];
  estimate: StorageEstimateResult | null;
}

export interface BuilderRun {
  id: string;
  status: "queued" | "running" | "done" | "failed";
  steps: string[];
  outcome: BuilderOutcome | null;
  error: string | null;
}
