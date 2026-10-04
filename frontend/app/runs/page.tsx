"use client"

import { useState } from "react"

import { Loading, Problem } from "@/components/kit"
import { RunRows } from "@/components/run-rows"
import type { RunSummary, Stats } from "@/lib/api"
import { int } from "@/lib/format"
import { useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

const PAGE = 20

export default function RunsPage() {
  const [filter, setFilter] = useState<"" | "fail" | "success">("")
  const [limit, setLimit] = useState(PAGE)
  const stats = useApi<Stats>("/stats")
  const runs = useApi<{ items: RunSummary[]; total: number }>(
    `/runs?limit=${limit}&forks=false${filter ? `&status=${filter}` : ""}`,
  )
  const s = stats.data
  const chips = [
    { v: "" as const, label: "All", n: s?.runs },
    { v: "fail" as const, label: "Failed", n: s?.by_status.fail },
    { v: "success" as const, label: "Passed", n: s?.by_status.success },
  ]

  return (
    <main className="mx-auto max-w-3xl px-5 pt-10 md:px-8 md:pt-14">
      <h1 className="text-[28px] leading-9 font-medium md:text-[32px] md:leading-10">Recorded runs</h1>
      <p className="mt-2 text-dim">Every action is recorded step by step. Open a failed run to find what caused it.</p>

      <div className="mt-6 flex gap-2 overflow-x-auto pb-1" role="radiogroup" aria-label="Filter runs">
        {chips.map((c) => (
          <button
            key={c.label}
            role="radio"
            aria-checked={filter === c.v}
            onClick={() => {
              setFilter(c.v)
              setLimit(PAGE)
            }}
            className={cn(
              "flex shrink-0 items-center gap-2 rounded border px-3 py-1.5 text-sm text-dim transition-colors hover:text-ink",
              filter === c.v && "border-dim/50 bg-raised text-ink",
            )}
          >
            {c.label}
            {c.n !== undefined && <span className="font-mono text-xs text-dim">{int(c.n)}</span>}
          </button>
        ))}
      </div>

      {runs.error ? (
        <Problem message={runs.error} onRetry={runs.reload} />
      ) : !runs.data ? (
        <Loading />
      ) : (
        <>
          <RunRows runs={runs.data.items} />
          {runs.data.items.length < runs.data.total && (
            <div className="mt-6 text-center">
              <button
                onClick={() => setLimit(limit + PAGE)}
                disabled={runs.loading}
                className="rounded border px-4 py-2 text-sm text-ink hover:bg-raised disabled:opacity-60"
              >
                {runs.loading ? "Loading…" : "Show more"}
              </button>
            </div>
          )}
        </>
      )}
    </main>
  )
}
