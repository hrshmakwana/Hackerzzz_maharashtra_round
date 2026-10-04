"use client"

import { Recycle } from "lucide-react"

import { Empty, ErrorNote, KindDot, Loading } from "@/components/bits"
import { JsonView } from "@/components/json-view"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { RankItem, Step, StepState } from "@/lib/api"
import { int, ms } from "@/lib/format"
import { useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

export function Inspector({ runId, step, rank, diagnosed, tab, onTab }: {
  runId: string
  step: Step | null
  rank: RankItem | null
  diagnosed: boolean
  tab: string
  onTab: (t: string) => void
}) {
  if (!step) return <Empty>Select a step on the tape or in the graph.</Empty>
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b px-3.5 py-2.5">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-dim">step {step.idx}</span>
          <KindDot kind={step.kind} />
          <span className="font-mono text-sm">{step.kind === "llm" ? "llm" : step.name}</span>
          {step.reused && (
            <span className="ml-auto flex items-center gap-1 text-xs text-dim" title="Copied from the parent run, not re-executed">
              <Recycle className="size-3.5" /> reused
            </span>
          )}
        </div>
        <div className="mt-1 flex flex-wrap gap-x-4 text-xs text-dim">
          <span>{ms(step.latency_ms)}</span>
          {(step.tokens_in > 0 || step.tokens_out > 0) && <span>{int(step.tokens_in + step.tokens_out)} tokens</span>}
          <span className="font-mono" title={step.hash}>hash {step.hash.slice(0, 10)}</span>
        </div>
      </div>
      <Tabs value={tab} onValueChange={(v) => onTab(String(v))} className="flex min-h-0 flex-1 flex-col gap-0">
        <TabsList variant="line" className="w-full justify-start gap-1 border-b px-2">
          <TabsTrigger value="io" className="flex-none px-2">Input and output</TabsTrigger>
          <TabsTrigger value="state" className="flex-none px-2">State change</TabsTrigger>
          <TabsTrigger value="why" className="flex-none px-2">Why blamed</TabsTrigger>
        </TabsList>
        <TabsContent value="io" className="min-h-0 flex-1 overflow-y-auto px-3.5 py-3">
          <h3 className="mb-1 text-xs text-dim">Input</h3>
          <JsonView value={step.input} />
          <h3 className={cn("mt-4 mb-1 text-xs", step.error ? "text-fail" : "text-dim")}>{step.error ? "Error" : "Output"}</h3>
          {step.error ? <p className="font-mono text-[12px] text-fail">{step.error}</p> : <JsonView value={step.output} />}
        </TabsContent>
        <TabsContent value="state" className="min-h-0 flex-1 overflow-y-auto px-3.5 py-3">
          <StatePane runId={runId} idx={step.idx} />
        </TabsContent>
        <TabsContent value="why" className="min-h-0 flex-1 overflow-y-auto px-3.5 py-3">
          {!diagnosed ? (
            <Empty>Run Diagnose to see how much this step is blamed and why.</Empty>
          ) : rank ? (
            <WhyPane rank={rank} />
          ) : (
            <Empty>No ranking for this step.</Empty>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}

function StatePane({ runId, idx }: { runId: string; idx: number }) {
  const { data, error, loading } = useApi<StepState>(`/runs/${runId}/steps/${idx}/state`)
  if (loading && !data) return <Loading label="Loading checkpoint…" />
  if (error) return <ErrorNote message={error} />
  if (!data || !data.after) return <Empty>No checkpoint was stored for this step.</Empty>
  return (
    <div className="space-y-3">
      <p className="text-xs text-dim">
        Checkpoint <span className="font-mono">{data.checkpoint_id?.slice(0, 12)}</span> holds the agent&apos;s memory and the
        world after this step. Forks resume from here.
      </p>
      {data.diff.length === 0 ? (
        <p className="text-sm text-dim">This step changed nothing in memory or the world.</p>
      ) : (
        <ul className="space-y-1.5">
          {data.diff.map((d) => (
            <li key={d.path} className="rounded-md border bg-background px-2.5 py-1.5">
              <div className="flex items-center gap-2 font-mono text-[11px]">
                <span className={cn(d.op === "added" ? "text-success" : d.op === "removed" ? "text-fail" : "text-[var(--bb-kind-retrieval)]")}>
                  {d.op}
                </span>
                <span className="truncate text-foreground">{d.path.replace(/^agent\./, "memory: ").replace(/^world\./, "world: ")}</span>
              </div>
              {d.op === "changed" && (
                <div className="mt-0.5 truncate font-mono text-[11px] text-dim">
                  {short(d.before)} → <span className="text-foreground">{short(d.after)}</span>
                </div>
              )}
              {d.op === "added" && <div className="mt-0.5 truncate font-mono text-[11px] text-foreground">{short(d.after)}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/* eslint-disable-next-line @typescript-eslint/no-explicit-any */
function short(v: any) {
  const s = typeof v === "string" ? v : JSON.stringify(v)
  return s && s.length > 90 ? s.slice(0, 89) + "…" : s
}

function WhyPane({ rank }: { rank: RankItem }) {
  const maxAbs = Math.max(...rank.shap.map((s) => Math.abs(s.contribution)), 0.0001)
  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <span className="text-xs text-dim">Blame probability</span>
        <span className="font-heading text-xl font-semibold tabular-nums text-orange">{Math.round(rank.prob * 100)}%</span>
      </div>
      <section>
        <h3 className="mb-1.5 text-xs text-dim">Evidence from the trace</h3>
        {rank.evidence.length ? (
          <ul className="space-y-1.5 text-sm leading-snug">
            {rank.evidence.map((e, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-1.5 size-1 shrink-0 rounded-full bg-orange" />
                <span>{e}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-dim">Nothing unusual found in this step.</p>
        )}
      </section>
      <section>
        <h3 className="mb-1 text-xs text-dim">What moved the score (SHAP)</h3>
        <p className="mb-2 text-[11px] text-dim">Orange pushes toward blame, blue pushes away.</p>
        <ul className="space-y-1.5" aria-label="SHAP feature contributions">
          {rank.shap.map((s) => {
            const w = (Math.abs(s.contribution) / maxAbs) * 50
            const pos = s.contribution > 0
            return (
              <li key={s.feature} title={`${s.feature} = ${s.value}; contribution ${s.contribution.toFixed(3)}`}>
                <div className="flex items-center justify-between text-[11px]">
                  <span className="truncate text-foreground">{s.label}</span>
                  <span className="font-mono text-dim">{s.contribution > 0 ? "+" : ""}{s.contribution.toFixed(2)}</span>
                </div>
                <div className="relative mt-0.5 h-1.5 rounded-full bg-border/60">
                  <span className="absolute top-0 left-1/2 h-1.5 w-px bg-dim/50" />
                  <span
                    className="absolute top-0 h-1.5 rounded-full"
                    style={{
                      width: `${w}%`,
                      left: pos ? "50%" : `${50 - w}%`,
                      background: pos ? "#FF6A13" : "#6cc3f0",
                    }}
                  />
                </div>
              </li>
            )
          })}
        </ul>
      </section>
    </div>
  )
}
