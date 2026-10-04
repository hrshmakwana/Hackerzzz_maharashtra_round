export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api").replace(/\/$/, "")

export type StepKind = "plan" | "llm" | "tool" | "retrieval" | "final"
export type RunStatus = "success" | "fail" | "running"

/* eslint-disable @typescript-eslint/no-explicit-any */
export interface Step {
  idx: number
  parent_idx: number | null
  kind: StepKind
  name: string
  input: Record<string, any>
  output: any
  error: string | null
  latency_ms: number
  tokens_in: number
  tokens_out: number
  checkpoint_id: string | null
  prev_hash: string
  hash: string
  reused: boolean
}

export interface RunSummary {
  id: string
  task_family: string
  task_id: string
  seed: number
  policy: string
  status: RunStatus
  outcome_detail: string
  split: string
  parent_run_id: string | null
  fork_step_idx: number | null
  fault_type: string | null
  fault_step: number | null
  n_steps: number
  steps_reused: number
  steps_rerun: number
  tokens_total: number
  latency_total_ms: number
  created_at: string
}

export interface Edge {
  source: number
  target: number
  kind: "seq" | "data"
}

export interface Edit {
  type: "override_args" | "override_output" | "override_decision" | "swap_document" | "patch_prompt"
  step?: number
  args?: Record<string, any>
  output?: any
  doc_id?: string
  prompt?: string
  note?: string
}

export interface Fix {
  edit: Edit
  rule: string
  explanation: string
}

export interface ShapItem {
  feature: string
  label: string
  value: number
  contribution: number
}

export interface RankItem {
  idx: number
  name: string
  kind: StepKind
  score: number
  prob: number
  evidence: string[]
  shap: ShapItem[]
}

export interface Diagnosis {
  model_version: string
  ranking: RankItem[]
  fail_risk: number
  canon_event: { idx: number; name: string; prob: number; headline: string }
  ground_truth?: { step: number; type: string }
  suggested_fix: Fix | null
  report_md: string | null
  report_source?: string
  run_status: RunStatus
}

export interface Run extends RunSummary {
  task_text: string
  final_answer: string
  edits: Edit[] | null
  fault_meta: Record<string, any> | null
  chain_head: string
  steps: Step[]
  edges: Edge[]
  diagnosis: (Diagnosis & { report_md: string | null }) | null
  forks: RunSummary[]
}

export interface Savings {
  steps_reused: number
  steps_rerun: number
  tokens_saved: number
  time_saved_ms: number
  reused_frac: number
}

export interface ForkResult {
  id: string
  parent_run_id: string
  fork_step_idx: number
  status: RunStatus
  outcome_detail: string
  final_answer: string
  parent_status: RunStatus
  flipped: boolean
  savings: Savings
  edits: Edit[] | null
  fix?: Fix
}

export interface Universe {
  rank: number
  step: number
  name: string
  prob: number
  fix: Fix | null
  status: RunStatus | null
  flipped: boolean
  fork_id: string | null
  note?: string
  savings?: Savings
}

export interface SweepResult {
  run_id: string
  universes: Universe[]
  confirmed_step: number | null
  confirmed_fork: string | null
  model_top1: number
}

export interface Verify {
  valid: boolean
  broken_at: number | null
  steps_checked: number
  head_matches: boolean | null
}

export interface StateDiff {
  path: string
  op: "added" | "removed" | "changed"
  before: any
  after: any
}

export interface StepState {
  idx: number
  checkpoint_id: string | null
  after: { id: string; agent_state: any; world_state: any } | null
  diff: StateDiff[]
}

export interface Pair {
  a: number | null
  b: number | null
  op: "equal" | "output_changed" | "replace" | "insert" | "delete"
  reused: boolean
}

export interface Comparison {
  a: RunSummary & { final_answer: string; task_text: string }
  b: RunSummary & { final_answer: string; task_text: string }
  pairs: Pair[]
  divergence: { a: number | null; b: number | null } | null
  fork_step: number | null
  is_fork: boolean
  outcome: { a: RunStatus; b: RunStatus; flipped: boolean; regressed: boolean }
  edits: Edit[] | null
  similarity: number
  savings?: Savings
  steps_a: Step[]
  steps_b: Step[]
}

export interface Stats {
  runs: number
  by_status: Record<string, number>
  fail_rate: number | null
  by_family: Record<string, number>
  by_fault_type: Record<string, number>
  by_split: Record<string, number>
  forks: number
  fork_flips: number
  avg_steps_reused: number | null
  top1_test: number | null
  top3_test: number | null
  dataset_runs: number | null
  model_version: string | null
}

export interface Meta {
  families: string[]
  heldout_family: string
  fault_types: string[]
  heldout_fault_types: string[]
  edit_types: string[]
  policies: { sim: boolean; gemini: boolean }
  model: { available: boolean; version: string | null }
  documents: { doc_id: string; title: string; topic: string; version: string; status: string }[]
}

export interface MethodMetrics {
  n: number
  top1: number
  top3: number
  mrr: number
  mean_step_distance: number
  per_type_top1: Record<string, { top1: number; n: number }>
}

export interface Metrics {
  generated_at: string
  model_version: string
  dataset: Record<string, any>
  splits: Record<string, { label: string; runs: number; failed_with_label: number; methods: Record<string, MethodMetrics> }>
  auroc: Record<string, number>
  feature_importance: { feature: string; gain: number }[]
  replay?: { n: number; splits: Record<string, Record<string, number>> }
  judge_runs: number
  judge_models?: Record<string, string | null>
  train: Record<string, any>
}

export interface Health {
  status: string
  runs: number
  seeding: boolean
  model: string | null
  gemini: boolean
}

export interface DemoRun {
  id: string
  title: string
  story: string
  family: string
  fault: { type: string; step: number }
  available: boolean
  status: RunStatus | null
}
/* eslint-enable @typescript-eslint/no-explicit-any */

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
      cache: "no-store",
    })
  } catch {
    throw new ApiError(0, `Can't reach the API at ${API_URL}. Start it with "make api".`)
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) })

export interface Review {
  name: string
  model: string
  agree: boolean | null
  step: number | null
  reason: string
  error?: string
}

export interface ReviewResult {
  run_id: string
  model_step: number
  reviews: Review[]
  agree: number
  available: boolean
}
