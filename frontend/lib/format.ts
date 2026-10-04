export const FAMILY_LABEL: Record<string, string> = {
  refund: "Refund",
  address_change: "Address change",
  discount_quote: "Discount quote",
  cancel: "Cancellation",
  complaint_triage: "Complaint triage",
}

export const FAULT_LABEL: Record<string, string> = {
  wrong_args: "Wrong arguments",
  bad_retrieval: "Stale retrieval",
  hallucination: "Hallucination",
  ignored_error: "Ignored error",
  calc_error: "Calculation error",
  early_stop: "Stopped early",
  loop: "Loop",
  prompt_injection: "Prompt injection",
  state_corruption: "State corruption",
}

export const SPLIT_LABEL: Record<string, string> = {
  train: "Train",
  val: "Validation",
  test: "Test",
  heldout_type: "Held-out fault types",
  heldout_family: "Held-out family",
  live: "Live",
  fork: "Fork",
}

export const METHOD_LABEL: Record<string, string> = {
  model: "Black Box ranker",
  llm_judge: "Gemini as judge",
  first_error: "First error",
  last_step: "Last action",
  random: "Random step",
}

export const EDIT_LABEL: Record<string, string> = {
  override_args: "Change arguments",
  override_output: "Change tool output",
  override_decision: "Change LLM decision",
  swap_document: "Swap document",
  patch_prompt: "Patch system prompt",
}

export const label = (map: Record<string, string>, key: string | null | undefined) =>
  key ? map[key] ?? key.replace(/_/g, " ") : "—"

export const pct = (x: number | null | undefined, digits = 0) =>
  x === null || x === undefined ? "—" : `${(x * 100).toFixed(digits)}%`

export const int = (x: number | null | undefined) =>
  x === null || x === undefined ? "—" : Math.round(x).toLocaleString("en-IN")

export const ms = (x: number | null | undefined) => {
  if (x === null || x === undefined) return "—"
  if (x < 1000) return `${Math.round(x)} ms`
  return `${(x / 1000).toFixed(x < 10000 ? 1 : 0)} s`
}

export const shortId = (id: string) => (id.startsWith("hero-") ? id : id.slice(0, 8))

export function timeAgo(iso: string | null | undefined) {
  if (!iso) return "—"
  const t = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z").getTime()
  const s = Math.max(0, (Date.now() - t) / 1000)
  if (s < 60) return "just now"
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return `${Math.floor(s / 86400)} d ago`
}

/* eslint-disable @typescript-eslint/no-explicit-any */
export function oneLine(value: any, max = 80): string {
  if (value === null || value === undefined) return ""
  let text: string
  if (typeof value === "string") text = value
  else if (typeof value === "object") {
    const parts = Object.entries(value)
      .filter(([k]) => !["memory_keys", "instruction"].includes(k))
      .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    text = parts.join(", ")
  } else text = String(value)
  text = text.replace(/\s+/g, " ").trim()
  return text.length > max ? text.slice(0, max - 1) + "…" : text
}

export function stepSummary(step: { kind: string; name: string; input: any; output: any; error: string | null }) {
  if (step.error) return step.error
  if (step.kind === "llm") return oneLine(step.output?.thought ?? step.output, 120)
  if (step.kind === "plan") return `${(step.output?.plan ?? []).length} planned steps`
  if (step.kind === "final") return oneLine(step.input?.answer, 120)
  if (step.kind === "retrieval")
    return step.output ? `${step.output.doc_id} · ${step.output.status} · score ${step.output.score}` : ""
  return oneLine(step.input, 90)
}
/* eslint-enable @typescript-eslint/no-explicit-any */
