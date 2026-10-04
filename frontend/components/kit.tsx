import { AlertCircle, Check, Loader2, X } from "lucide-react"
import type { ReactNode } from "react"

import type { RunStatus, Step } from "@/lib/api"
import { describeStep } from "@/lib/plain"
import { cn } from "@/lib/utils"

export const btnPrimary =
  "inline-flex items-center justify-center gap-2 rounded bg-orange px-5 py-2.5 text-sm font-semibold text-bg transition-colors hover:bg-[#ff7f33] disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange"
export const btnSecondary =
  "inline-flex items-center justify-center gap-2 rounded border px-5 py-2.5 text-sm font-medium text-ink transition-colors hover:border-dim hover:bg-raised focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"

export function StatusPill({ status, className }: { status: RunStatus | null; className?: string }) {
  if (!status) return null
  const map = {
    fail: { icon: X, text: "Failed", cls: "border-fail/30 bg-fail/10 text-fail" },
    success: { icon: Check, text: "Passed", cls: "border-success/30 bg-success/10 text-success" },
    running: { icon: Loader2, text: "Running", cls: "border-orange/30 bg-orange/10 text-orange" },
  }[status]
  const Icon = map.icon
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1 rounded border px-2 py-0.5 text-xs font-medium", map.cls, className)}>
      <Icon className={cn("size-3.5", status === "running" && "animate-spin")} aria-hidden />
      {map.text}
    </span>
  )
}

export function Loading({ label = "Loading…", className }: { label?: string; className?: string }) {
  return (
    <p className={cn("flex items-center justify-center gap-2 py-16 text-sm text-dim", className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden /> {label}
    </p>
  )
}

export function Problem({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-2 py-16 text-center text-sm">
      <AlertCircle className="size-5 text-fail" aria-hidden />
      <p className="max-w-md">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="text-orange hover:underline">
          Try again
        </button>
      )}
    </div>
  )
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="mb-2 text-sm text-dim">{children}</p>
}

/** The agent's actions (reasoning steps hidden unless asked), numbered from 1. */
export function visibleSteps(steps: Step[], keep: number | null, withReasoning = false) {
  return steps
    .filter((s) => withReasoning || s.kind === "tool" || s.kind === "retrieval" || s.kind === "final" || s.idx === keep)
    .map((step, i) => ({ step, n: i + 1 }))
}

export function StepList({ items, rootIdx, reason, confidence, live }: {
  items: { step: Step; n: number }[]
  rootIdx: number | null
  reason?: string
  confidence?: number
  live?: boolean
}) {
  return (
    <ol className="divide-y divide-line/60 rounded-lg border bg-surface">
      {items.map(({ step, n }) => {
        const root = rootIdx === step.idx
        return (
          <li
            key={step.idx}
            className={cn(
              "px-4 py-3 sm:px-5",
              live && "rise",
              root && "root-glow relative z-10 -mx-px rounded-lg border border-orange bg-raised",
              rootIdx !== null && !root && "text-ink/60",
            )}
          >
            <div className="flex items-start gap-3 sm:gap-4">
              <span className={cn("w-6 shrink-0 pt-0.5 font-mono text-xs tabular-nums", root ? "text-orange" : "text-dim")}>
                {String(n).padStart(2, "0")}
              </span>
              <p className={cn("min-w-0 flex-1 text-[15px] leading-6 break-words", root && "font-medium text-ink")}>
                {describeStep(step)}
              </p>
              {step.error && !root && <AlertCircle className="mt-1 size-4 shrink-0 text-fail" aria-label="This call failed" />}
              {root && (
                <span className="shrink-0 rounded border border-orange/40 bg-orange/10 px-2 py-0.5 text-xs font-medium text-orange">
                  Root cause
                </span>
              )}
            </div>
            {root && reason && (
              <div className="mt-3 rounded-lg border bg-bg px-4 py-3 sm:ml-10">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="flex items-center gap-1.5 text-sm font-medium text-orange">
                    <AlertCircle className="size-4" aria-hidden /> This is where it went wrong
                  </p>
                  {confidence !== undefined && (
                    <span className="text-xs text-dim">Confidence {Math.round(confidence * 100)}%</span>
                  )}
                </div>
                <p className="mt-1 text-sm leading-6 text-ink">{reason}</p>
              </div>
            )}
          </li>
        )
      })}
    </ol>
  )
}
