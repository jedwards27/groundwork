// Views the API returns. Typed views come from the generated OpenAPI types; the slice-2 endpoints
// that return free-form JSON are described here by hand.
import type { components } from "./api-types";

export type ChainView = components["schemas"]["ChainView"];
export type ItemView = components["schemas"]["ItemView"];
export type SiteView = components["schemas"]["SiteView"];
export type ForecastView = components["schemas"]["ForecastView"];
export type EventView = components["schemas"]["EventView"];
export type RunView = components["schemas"]["RunView"];
export type MilestoneView = components["schemas"]["MilestoneView"];

export type Autonomy = "auto" | "ask" | "refuse";

export interface Effect {
  kind: string;
  item?: string | null;
  pred?: string | null;
  days: number;
  realized_by: string;
}

export interface ApprovalRow {
  person: string;
  person_name: string;
  verdict: "approve" | "decline";
  at: string;
  kid: string;
  note: string;
}

export interface ActionView {
  id: string;
  ref: string;
  title: string;
  executor: string;
  kind: string | null;
  recipient: string | null;
  recipient_name: string | null;
  asks_party: string | null;
  path: string[];
  params: Record<string, unknown>;
  effect: Effect;
  effect_allowed: boolean;
  effect_reason: string;
  response_lag_bd: number;
  proposed_autonomy: Autonomy;
  rationale: string;
  evidence: string[];
  decision: Autonomy | null;
  reason: string;
  rule: string;
  delta: "match" | "over_reach" | "over_caution" | "";
  record_bearing: boolean;
  content_class: string | null;
  classifier: string;
  amount_cents: number | null;
  mandate_version: number | null;
  approvers: string[];
  state: string;
  action_hash: string;
  approvals: ApprovalRow[];
  external_ref: string | null;
  execution_detail: string | null;
  ledger: { seq: number; type: string }[];
}

export interface Differential {
  target_date: string;
  unmitigated: string | null;
  now: string | null;
  if_approved: string | null;
  if_they_agree: string | null;
  recovered_now: number;
  recovered_if_approved: number;
  recovered_if_they_agree: number;
  contributions: { ref: string; state: string; realized_by: string; credited: boolean; days_alone: number; response_lag_bd: number }[];
}

export interface PlanView {
  run_id: string;
  plan_id: string;
  arm: "informed" | "blind";
  planner: string;
  model_id: string;
  simulated: boolean;
  assessment: string;
  intent: { auto?: string[]; ask?: string[]; refuse?: string[] };
  actions: ActionView[];
  usage: Record<string, number>;
  created_at: string;
  report: { did: string[]; asked: string[]; refused: string[]; failed: string[]; summary: string; reporter?: string } | null;
  report_check: { ok?: boolean; omission: string[]; fabrication: string[]; inversion: string[] } | null;
  differential: Differential | null;
}

export interface MandateView {
  version: number;
  preset: string;
  doc: Record<string, unknown>;
  plain_lines: string[];
  presets: string[];
  history: { version: number; preset: string; at: string }[];
}

export interface CompareRow {
  preset: string;
  current: boolean;
  auto: number;
  ask: number;
  refuse: number;
  held: number;
  decisions: Record<string, Autonomy>;
  recovered_now: number;
  recovered_if_approved: number;
  recovered_if_they_agree: number;
}

export interface LedgerEntry {
  seq: number;
  type: string;
  arm: string | null;
  run_id: string | null;
  action_id: string | null;
  recorded_at: string;
  payload: Record<string, unknown>;
  hash: string;
  prev_hash: string;
}

export interface Verify {
  ok: boolean;
  count: number;
  head_seq: number;
  head_hash: string;
  problems: string[];
}

export interface ScoreRow {
  arm: string;
  planner: string;
  model_id: string;
  label: string;
  proposals: number;
  match: number;
  over_reach: number;
  over_caution: number;
  hard_violations: number;
  over_reach_rate: number;
  over_caution_rate: number;
  reports: number;
  report_mismatches: number;
  honest_rate: number | null;
}

export interface Attestation {
  attestation: {
    type: string;
    site: string;
    mandate: { id: string; version: number; preset: string; issuer: string };
    ledger: { from_seq: number; head_seq: number; head_hash: string; entries: number; chain_verified: boolean; problems: string[] };
    counts: Record<string, number>;
    violations: { count: number; seqs: number[]; definition: string };
    proposal_deltas: Record<string, Record<string, number>>;
    model_ids: string[];
    dry_run: boolean;
    identity_assurance: string;
    signer: string;
    generated_at: string;
    what_this_does_not_prove: string[];
    production_path: string;
  };
  signature: { alg: string; value: string };
}

export type Me = components["schemas"]["MeView"];

export interface Persona {
  key: string;
  name: string;
  title: string;
  party: string;
  approver: boolean;
}

export interface Health {
  ok: boolean;
  version: string;
  dry_run: boolean;
  hosted: boolean;
  live_planner: boolean;
  planner_model: string;
  demo_login: boolean;
  sandboxes?: boolean;
}

export interface Session {
  me: Me | null;
  personas: Persona[];
  health: Health | null;
  error?: string;
}

export interface Step {
  i: number;
  kind: string;
  text: string;
  at: string;
  [k: string]: unknown;
}
