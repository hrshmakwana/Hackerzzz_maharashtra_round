"use client"

import { Check, Minus, X } from "lucide-react"

import type { ReviewResult } from "@/lib/api"
import { useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

export interface Leaderboard {
  basis: string
  methods: {
    key: string
    name: string
    maker: string
    benchmark: { top1: number; n: number } | null
    live: { correct: number; total: number; rate: number | null }
  }[]
}

const pct = (x: number | null | undefined) => (x === null || x === undefined ? "—" : `${Math.round(x * 100)}%`)

/** Who found the right step: this run, the fixed benchmark, and every run tested here. */
export function Scorecard({ truth, modelStep, review, labelFor, compact }: {
  truth?: number | null
  modelStep?: number | null
  review?: ReviewResult | null
  labelFor?: (idx: number) => string
  compact?: boolean
}) {
  const { data } = useApi<Leaderboard>("/leaderboard")
  if (!data) return null
  const picks: Record<string, number | null | undefined> = { "Black Box": modelStep }
  for (const r of review?.reviews ?? []) picks[r.name] = r.error ? undefined : r.step
  const showRun = truth !== undefined && truth !== null && modelStep !== undefined

  return (
    <section className={cn("rounded-lg border bg-surface", !compact && "mt-12")}>
      <div className="border-b px-5 py-4">
        <h2 className="text-base font-medium">Who found the right step?</h2>
        <p className="mt-1 text-sm leading-6 text-dim">
          {showRun && labelFor ? `The right answer for this run is ${labelFor(truth!)}. ` : ""}
          {data.basis}
        </p>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-dim">
            <th className="px-5 py-2.5 font-normal">Method</th>
            {showRun && <th className="px-2 py-2.5 font-normal">This run</th>}
            <th className="px-2 py-2.5 text-right font-normal">Benchmark</th>
            <th className="px-5 py-2.5 text-right font-normal">Tested here</th>
          </tr>
        </thead>
        <tbody>
          {data.methods.map((m) => {
            const pick = picks[m.name]
            const state = !showRun ? null : pick === undefined ? "none" : pick === truth ? "right" : "wrong"
            const ours = m.key === "model"
            return (
              <tr key={m.key} className="border-b border-line/60 last:border-0">
                <td className="px-5 py-3">
                  <span className={cn("font-medium", ours && "text-orange")}>{m.name}</span>
                  <span className="block text-xs text-dim">{m.maker}</span>
                </td>
                {showRun && (
                  <td className="px-2 py-3">
                    <span className={cn("flex items-center gap-1.5",
                      state === "right" ? "text-success" : state === "wrong" ? "text-fail" : "text-dim")}>
                      {state === "right" ? <Check className="size-4" /> : state === "wrong" ? <X className="size-4" /> : <Minus className="size-4" />}
                      <span className="hidden sm:inline">
                        {state === "none" ? "no answer" : pick !== null && pick !== undefined && labelFor ? labelFor(pick) : "—"}
                      </span>
                    </span>
                  </td>
                )}
                <td className="px-2 py-3 text-right">
                  <span className="font-mono tabular-nums">{pct(m.benchmark?.top1)}</span>
                  {m.benchmark && <span className="block text-xs text-dim">{m.benchmark.n} runs</span>}
                </td>
                <td className="px-5 py-3 text-right">
                  <span className="font-mono tabular-nums">{pct(m.live.rate)}</span>
                  <span className="block text-xs text-dim">
                    {m.live.total ? `${m.live.correct} of ${m.live.total}` : "none yet"}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="border-t px-5 py-3 text-xs leading-5 text-dim">
        Benchmark: the same failed test runs for every method. Tested here: every run checked in this app so far, which
        grows each time you press Find the cause.
      </p>
    </section>
  )
}
