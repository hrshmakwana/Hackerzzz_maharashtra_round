"use client"

import { Check, CircleSlash, Loader2, X } from "lucide-react"

import type { ReviewResult } from "@/lib/api"
import { cn } from "@/lib/utils"

/** Independent AIs reviewing the model's diagnosis. */
export function SecondOpinion({ result, loading, error, labelFor }: {
  result: ReviewResult | null
  loading: boolean
  error: string | null
  labelFor: (idx: number) => string
}) {
  if (result && !result.available) return null
  const total = result?.reviews.length ?? 0
  return (
    <section className="rise mt-6 rounded-lg border bg-surface p-5" aria-live="polite">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-medium">Second opinion from other AIs</h2>
        {result && total > 0 && (
          <span className="text-sm text-dim">
            {result.agree} of {total} agree
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-dim">
        Independent AI models read the same recording and check our answer.
      </p>

      {loading && !result && (
        <p className="mt-4 flex items-center gap-2 text-sm text-dim">
          <Loader2 className="size-4 animate-spin" /> Asking other AIs to review…
        </p>
      )}
      {error && <p className="mt-4 text-sm text-dim">Could not reach the reviewers right now.</p>}

      {result && (
        <ul className="mt-4 space-y-3">
          {result.reviews.map((r) => {
            const state = r.error ? "error" : r.agree ? "agree" : "disagree"
            return (
              <li key={r.name} className="flex gap-3">
                <span
                  className={cn(
                    "mt-0.5 grid size-6 shrink-0 place-items-center rounded",
                    state === "agree" && "bg-success/15 text-success",
                    state === "disagree" && "bg-fail/15 text-fail",
                    state === "error" && "bg-raised text-dim",
                  )}
                  aria-hidden
                >
                  {state === "agree" ? <Check className="size-3.5" /> : state === "disagree" ? <X className="size-3.5" /> : <CircleSlash className="size-3.5" />}
                </span>
                <div className="min-w-0 text-sm">
                  <p>
                    <span className="font-medium">{r.name}</span>{" "}
                    <span className={cn(state === "agree" ? "text-success" : state === "disagree" ? "text-fail" : "text-dim")}>
                      {state === "agree" ? "agrees" : state === "disagree" ? `would blame ${r.step !== null ? labelFor(r.step) : "a different step"}` : "did not answer"}
                    </span>
                  </p>
                  {r.reason && <p className="mt-0.5 leading-6 text-dim">{r.reason}</p>}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
