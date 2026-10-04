import { AlertTriangle, CircleCheck, CircleX, Inbox, Loader2 } from "lucide-react"
import type { ReactNode } from "react"

import type { RunStatus, StepKind } from "@/lib/api"
import { cn } from "@/lib/utils"

export function StatusBadge({ status, className }: { status: RunStatus | null; className?: string }) {
  if (!status) return null
  const map = {
    success: { icon: CircleCheck, text: "Success", cls: "text-success border-success/30 bg-success/10" },
    fail: { icon: CircleX, text: "Failed", cls: "text-fail border-fail/30 bg-fail/10" },
    running: { icon: Loader2, text: "Running", cls: "text-orange border-orange/30 bg-orange/10" },
  }[status]
  const Icon = map.icon
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium", map.cls, className)}>
      <Icon className={cn("size-3.5", status === "running" && "animate-spin")} aria-hidden />
      {map.text}
    </span>
  )
}

export const KIND_COLOR: Record<StepKind, string> = {
  plan: "var(--bb-kind-plan)",
  llm: "var(--bb-kind-llm)",
  tool: "var(--bb-kind-tool)",
  retrieval: "var(--bb-kind-retrieval)",
  final: "var(--bb-kind-final)",
}

export function KindDot({ kind, className }: { kind: StepKind; className?: string }) {
  return (
    <span
      className={cn("inline-block size-2 shrink-0 rounded-full", className)}
      style={{ background: KIND_COLOR[kind] }}
      aria-label={kind}
    />
  )
}

export function Panel({ title, action, children, className, bodyClassName }: {
  title?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={cn("flex min-h-0 flex-col rounded-lg border bg-card", className)}>
      {(title || action) && (
        <header className="flex min-h-10 items-center justify-between gap-3 border-b px-3.5 py-2">
          {title && <h2 className="text-sm font-medium">{title}</h2>}
          {action}
        </header>
      )}
      <div className={cn("min-h-0 flex-1", bodyClassName)}>{children}</div>
    </section>
  )
}

export function Loading({ label = "Loading…", className }: { label?: string; className?: string }) {
  return (
    <div className={cn("flex items-center justify-center gap-2 py-10 text-sm text-dim", className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </div>
  )
}

export function ErrorNote({ message, onRetry, className }: { message: string; onRetry?: () => void; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center gap-2 px-4 py-8 text-center text-sm", className)}>
      <AlertTriangle className="size-5 text-fail" aria-hidden />
      <p className="max-w-md text-foreground">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="text-sm text-orange underline-offset-4 hover:underline">
          Try again
        </button>
      )}
    </div>
  )
}

export function Empty({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center gap-2 px-4 py-10 text-center text-sm text-dim", className)}>
      <Inbox className="size-5" aria-hidden />
      <div className="max-w-sm">{children}</div>
    </div>
  )
}

/** A row of instrument readouts separated by hairlines. */
export function Readouts({ items, className }: {
  items: { label: string; value: ReactNode; hint?: ReactNode; accent?: boolean }[]
  className?: string
}) {
  return (
    <dl className={cn("grid divide-x divide-border rounded-lg border bg-card", className)}
      style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}>
      {items.map((it) => (
        <div key={it.label} className="flex min-w-0 flex-col gap-1 px-4 py-3">
          <dt className="truncate text-xs text-dim">{it.label}</dt>
          <dd className={cn("font-heading text-2xl font-semibold tabular-nums leading-none", it.accent && "text-orange")}>
            {it.value}
          </dd>
          {it.hint && <dd className="truncate text-xs text-dim">{it.hint}</dd>}
        </div>
      ))}
    </dl>
  )
}

export function CanonBadge({ className }: { className?: string }) {
  return (
    <span className={cn("canon-badge inline-flex items-center rounded border border-fail/50 px-1.5 py-0.5 font-heading text-xs font-semibold text-fail", className)}>
      Canon Event
    </span>
  )
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("font-mono text-[0.8em]", className)}>{children}</span>
}
