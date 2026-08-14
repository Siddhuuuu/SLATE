// Mirrors backend/models.py. Small enough to keep in sync by hand — if
// this file and models.py ever need a codegen step to stay aligned, the
// schema has grown past what a 4-endpoint backend should have.

export type Provider = "gemini" | "ollama" | "openrouter";
export type Tier = "fast" | "heavy";
export type Outcome =
  | "pending"
  | "accepted"
  | "discarded"
  | "cancelled"
  | "superseded"
  | "timeout"
  | "error";
export type Trigger = "idle_pause" | "explicit" | "refine";

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface RegionContext {
  bbox: BoundingBox;
  zoom: number;
  source: "selection" | "ink_cluster" | "viewport";
  nearby_shape_types: string[];
  nearby_accepted_draft_ids: string[];
  stroke_count: number;
  ink_density: number;
}

export interface CreateRequestBody {
  image_b64: string;
  image_width_px?: number;
  image_height_px?: number;
  context: RegionContext;
  t_capture_ms?: number;
  trigger: Trigger;
  prompt_chars?: number;
  config_id?: string; // ties this request to a B5 experiment arm
  provider_override?: Provider;
}

export interface CreateRequestResponse {
  request_id: string;
  tier: Tier;
  provider: Provider;
  model: string;
}

export interface OutcomeBody {
  outcome: "accepted" | "discarded";
  t_render_ms?: number;
  e2e_ms?: number; // trigger-fired -> draft-painted, measured directly client-side
}

export interface KpiSummary {
  cpad_usd: number | null;
  dar: number | null;
  wtr: number | null;
  bc: number | null;
  budget_ms: number;
}

export interface MetricsSummary {
  total_requests: number;
  in_flight: number;
  accepted: number;
  discarded: number;
  errors: number;
  superseded: number;
  timeouts: number;
  total_cost_usd: number;
  avg_render_ms: number | null;
  kpis: KpiSummary;
  generated_at: number;
}

// -- draft shape state, client-side -----------------------------------

export type DraftStatus = "pending" | "streaming" | "ready" | "accepted" | "discarded" | "error";

export interface DraftState {
  requestId: string;
  status: DraftStatus;
  text: string;
  provider?: Provider;
  tier?: Tier;
  errorMessage?: string;
}
