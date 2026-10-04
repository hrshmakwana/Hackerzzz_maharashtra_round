import type { Step } from "./api"

export const rupees = (x: unknown) => {
  const n = Number(x)
  return Number.isFinite(n)
    ? `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : String(x)
}

export const TASK_TITLE: Record<string, string> = {
  refund: "A customer asks for a refund",
  address_change: "A customer asks to change their delivery address",
  discount_quote: "A customer asks for a festive price",
  cancel: "A customer asks to cancel an order",
  complaint_triage: "A customer reports a damaged item",
}

export const TASK_SHORT: Record<string, string> = {
  refund: "Refund request",
  address_change: "Address change",
  discount_quote: "Price quote",
  cancel: "Cancellation",
  complaint_triage: "Damaged item complaint",
}

export const PROBLEM_LABEL: Record<string, string> = {
  bad_retrieval: "Outdated policy",
  wrong_args: "Wrong order id",
  prompt_injection: "Hacked email",
  ignored_error: "Ignored error",
  calc_error: "Wrong calculation",
  hallucination: "Made-up value",
  early_stop: "Stopped too early",
  loop: "Stuck in a loop",
  state_corruption: "Corrupted memory",
}

export const capital = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)

/** First rupee amount in a sentence, if any. */
export const amountIn = (s: string | null | undefined) => (s ?? "").match(/₹[\d,]+(?:\.\d{1,2})?/)?.[0] ?? null

/* eslint-disable @typescript-eslint/no-explicit-any */
/** One plain-English sentence for a step. */
export function describeStep(s: Step): string {
  const i = s.input ?? {}
  const o = s.output ?? {}
  if (s.error) {
    const what = s.kind === "tool" || s.kind === "retrieval" ? action(s.name, i, {}) : "This step"
    return `${what}, but it failed`
  }
  if (s.kind === "plan") return `Made a plan`
  if (s.kind === "final") return `Reported back: "${i.answer ?? ""}"`
  if (s.kind === "llm") {
    const t = String(o.thought ?? "").replace(/^Summary:\s*/, "")
    return t ? `Thought: "${t}"` : "Thought it over"
  }
  return action(s.name, i, o)
}

function action(name: string, i: any, o: any): string {
  switch (name) {
    case "read_email":
      return "Read the customer's email"
    case "search_customer":
      return "Looked up the customer"
    case "get_order":
      return `Opened order #${i.order_id}`
    case "list_orders":
      return "Checked the customer's other orders"
    case "retrieve_policy":
      if (!o.doc_id) return "Searched the store policies"
      return o.status === "current"
        ? `Found the ${String(o.title ?? "policy").replace(/\s*\(v\d+\)$/, "").toLowerCase()} (current version)`
        : `Found the ${String(o.title ?? "policy").replace(/\s*\(v\d+\)$/, "").toLowerCase()}, an old version from ${String(o.updated ?? "").slice(0, 4)}`
    case "calculate":
      return o.result !== undefined ? `Calculated ${i.expression} = ${rupees(o.result)}` : `Calculated ${i.expression}`
    case "issue_refund":
      return `Refunded ${rupees(i.amount)} on order #${i.order_id}`
    case "update_address":
      return `Changed the delivery address of order #${i.order_id}`
    case "cancel_order":
      return `Cancelled order #${i.order_id}`
    case "send_email":
      return `Emailed ${i.to}`
    default:
      return name.replace(/_/g, " ")
  }
}

/** A short, plain reason for why a step is the root cause. */
export function plainReason(step: Step | undefined, evidence: string[]): string {
  if (!step) return capital(evidence[0] ?? "")
  const o = step.output ?? {}
  if (step.kind === "retrieval" && o.status === "archived") {
    return `It used an outdated ${String(o.updated ?? "").slice(0, 4)} policy instead of the current one, and every later step built on it.`
  }
  if (step.error) return "This action failed, and the agent carried on as if it had worked."
  if (step.name === "read_email") return "The email contained hidden instructions, and the agent followed them."
  if (step.kind === "llm" && o.plan_update) return "The agent decided the job was done before it actually was."
  if (step.kind === "llm" && o.memory_update?.recheck) return "The agent started waiting for something that was never going to happen, and got stuck."
  if (step.name === "get_order" || step.name === "issue_refund" || step.name === "update_address" || step.name === "cancel_order") {
    return `It used order #${step.input?.order_id}, which is not the order the customer asked about.`
  }
  if (step.name === "send_email") return "It emailed the wrong address."
  if (step.name === "calculate") return "The calculation used a wrong number, so the amount came out wrong."
  return capital(evidence[0] ?? "This step does not match what the tools reported.")
}
/* eslint-enable @typescript-eslint/no-explicit-any */
