"use client"

import { AlertTriangle, Recycle } from "lucide-react"
import { useEffect, useRef } from "react"

import { KindDot } from "@/components/bits"
import type { Step } from "@/lib/api"
import { stepSummary } from "@/lib/format"
import { cn } from "@/lib/utils"

/** The recorder tape: one row per step with the model's blame heat. */
export function Tape({ steps, blame, canon, injected, selected, onSelect }: {
  steps: Step[]
  blame: Map<number, number> | null
  canon: number | null
  injected: number | null
  selected: number | null
  onSelect: (idx: number) => void
}) {
  const max = blame ? Math.max(...blame.values(), 0.0001) : 1
  const listRef = useRef<HTMLOListElement>(null)

  useEffect(() => {
    if (selected === null) return
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${selected}"]`)
    el?.scrollIntoView({ block: "nearest" })
  }, [selected])

  const move = (dir: number) => {
    if (selected === null) return onSelect(steps[0]?.idx ?? 0)
    const next = Math.min(steps.length - 1, Math.max(0, selected + dir))
    onSelect(steps[next].idx)
  }

  return (
    <ol
      ref={listRef}
      tabIndex={0}
      aria-label="Steps of this run"
      onKeyDown={(e) => {
        if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); move(1) }
        if (e.key === "ArrowUp" || e.key === "k") { e.preventDefault(); move(-1) }
      }}
      className="h-full overflow-y-auto py-1 outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
    >
      {steps.map((s) => {
        const p = blame?.get(s.idx) ?? 0
        const isCanon = canon === s.idx
        return (
          <li key={s.idx} data-idx={s.idx}>
            <button
              onClick={() => onSelect(s.idx)}
              aria-current={selected === s.idx}
              className={cn(
                "group relative grid w-full grid-cols-[28px_minmax(0,1fr)_46px] items-center gap-2 border-l-2 border-transparent py-1.5 pr-3 pl-2 text-left transition-colors hover:bg-surface-2",
                selected === s.idx && "bg-surface-2",
                isCanon && "border-orange",
                s.reused && "opacity-55",
              )}
            >
              <span className="font-mono text-[11px] text-dim tabular-nums">{String(s.idx).padStart(2, "0")}</span>
              <span className="min-w-0">
                <span className="flex items-center gap-1.5">
                  <KindDot kind={s.kind} />
                  <span className="truncate font-mono text-[12px] text-foreground">{s.kind === "llm" ? "llm" : s.name}</span>
                  {s.error && <AlertTriangle className="size-3 shrink-0 text-fail" aria-label="error" />}
                  {s.reused && <Recycle className="size-3 shrink-0 text-dim" aria-label="reused from parent run" />}
                  {injected === s.idx && (
                    <span className="shrink-0 rounded border border-dashed border-dim/60 px-1 text-[10px] text-dim" title="Where the fault was injected (ground truth)">
                      injected
                    </span>
                  )}
                </span>
                <span className="block truncate text-[11px] text-dim">{stepSummary(s)}</span>
              </span>
              <span className="flex flex-col items-end gap-1" aria-label={blame ? `blame ${Math.round(p * 100)} percent` : undefined}>
                {blame && (
                  <>
                    <span className={cn("font-mono text-[10px] tabular-nums", isCanon ? "text-orange" : "text-dim")}>
                      {p >= 0.005 ? `${Math.round(p * 100)}%` : "·"}
                    </span>
                    <span className="h-1 w-full rounded-full bg-border">
                      <span
                        className="block h-1 rounded-full bg-orange"
                        style={{ width: `${Math.max(2, (p / max) * 100)}%`, opacity: 0.25 + 0.75 * (p / max) }}
                      />
                    </span>
                  </>
                )}
              </span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}
