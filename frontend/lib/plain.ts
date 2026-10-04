import type { Step } from "./api"

const rupees = (x: unknown) => {
  const n = Number(x)
  return Number.isFinite(n) ? `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : String(x)
}

/** One plain-English sentence for a step, for people who don't read JSON. */
export function describeStep(s: Step): string {
  const i = s.input ?? {}
  const o = s.output ?? {}
  if (s.error) {
    const what = s.kind === "tool" || s.kind === "retrieval" ? describeAction(s.name, i, {}) : "This step"
    return `${what} — but it failed (${s.error.split(":")[0]})`
  }
  if (s.kind === "plan") return `Made a plan with ${(o.plan ?? []).length} steps`
  if (s.kind === "final") return `Reported back: "${i.answer ?? ""}"`
  if (s.kind === "llm") {
    const t = String(o.thought ?? "").replace(/^Summary:\s*/, "")
    return t ? `Thought: "${t}"` : "Thought it over"
  }
  return describeAction(s.name, i, o)
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function describeAction(name: string, i: any, o: any): string {
  switch (name) {
    case "read_email":
      return `Read the customer's email`
    case "search_customer":
      return `Looked up the customer ${i.query ?? ""}`.trim()
    case "get_order":
      return `Opened order #${i.order_id}`
    case "list_orders":
      return `Checked the customer's other orders`
    case "retrieve_policy":
      if (!o.doc_id) return `Searched the policy documents`
      return o.status === "current"
        ? `Found the policy "${o.title}" — the current version`
        : `Found the policy "${o.title}" — an OLD version from ${String(o.updated ?? "").slice(0, 4)}`
    case "calculate":
      return o.result !== undefined ? `Calculated ${i.expression} = ${o.result}` : `Calculated ${i.expression}`
    case "issue_refund":
      return `Refunded ${rupees(i.amount)} on order #${i.order_id}`
    case "update_address":
      return `Changed the delivery address of order #${i.order_id}`
    case "cancel_order":
      return `Cancelled order #${i.order_id}`
    case "send_email":
      return `Emailed ${i.to}: "${i.subject ?? ""}"`
    default:
      return name.replace(/_/g, " ")
  }
}
/* eslint-enable @typescript-eslint/no-explicit-any */

export const TASK_TITLE: Record<string, string> = {
  refund: "A customer asks for a refund",
  address_change: "A customer asks to change their delivery address",
  discount_quote: "A customer asks for a festive price quote",
  cancel: "A customer asks to cancel an order",
  complaint_triage: "A customer complains about a damaged item",
}
