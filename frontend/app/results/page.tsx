"use client"

import { ArrowUpRight, BadgeCheck } from "lucide-react"

import { Eyebrow, Loading, Problem } from "@/components/kit"
import { REPO } from "@/components/site"
import type { Metrics } from "@/lib/api"
import { int, pct } from "@/lib/format"
import { modelLabel } from "@/lib/plain"
import { useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

const methods = (m: Metrics) => {
  const second = modelLabel(m.judge_models?.llm_judge2)
  const third = modelLabel(m.judge_models?.llm_judge3)
  return [
    { key: "model", name: "Black Box", how: "Our trained model" },
    { key: "llm_judge", name: "Ask Gemini", how: "Gemini reads the whole recording and names the step" },
    { key: "llm_judge2", name: `Ask ${second}`, how: `${second} reads the whole recording and names the step` },
    { key: "llm_judge3", name: `Ask ${third}`, how: `${third} reads the whole recording and names the step` },
    { key: "last_step", name: "Blame the last step", how: "Assume the last action caused it" },
    { key: "random", name: "Random guess", how: "Pick any step" },
  ]
}

export default function ResultsPage() {
  const { data: m, error, reload } = useApi<Metrics>("/eval")
  if (error) return <Problem message={error} onRetry={reload} />
  if (!m) return <Loading />

  const test = m.splits.test?.methods ?? {}
  const family = m.splits.heldout_family?.methods.model
  const types = m.splits.heldout_type?.methods.model
  const flip = m.replay?.splits.test?.flip_rate_top1

  return (
    <main className="mx-auto max-w-3xl px-5 pt-10 md:px-8 md:pt-16">
      <Eyebrow>Results</Eyebrow>
      <h1 className="text-[28px] leading-9 font-semibold md:text-5xl md:leading-[3.6rem]">
        How often each method finds the real cause on the first try
      </h1>
      <p className="mt-4 max-w-2xl text-dim md:text-lg">
        Measured on failed runs where we know exactly which step was broken, because we broke it on purpose.
      </p>

      <ul className="mt-10 space-y-3">
        {methods(m).filter((x) => test[x.key]?.n).map((x) => {
          const r = test[x.key]
          const ours = x.key === "model"
          return (
            <li key={x.key} className={cn("rounded-lg border p-5", ours ? "border-orange/40 bg-surface" : "bg-surface/60")}>
              <div className="flex items-baseline justify-between gap-4">
                <p className={cn("font-heading text-lg font-medium md:text-xl", !ours && "text-ink/85")}>{x.name}</p>
                <p className={cn("font-heading text-2xl font-semibold tabular-nums", ours ? "text-orange" : "text-ink/85")}>
                  {pct(r.top1)}
                </p>
              </div>
              <div className="mt-3 h-2 rounded-full bg-line" aria-hidden>
                <div className={cn("h-2 rounded-full", ours ? "bg-orange" : "bg-dim/60")} style={{ width: `${Math.max(1.5, r.top1 * 100)}%` }} />
              </div>
              <div className="mt-2 flex justify-between gap-4 text-xs text-dim">
                <span>{x.how}</span>
                <span className="shrink-0">{int(r.n)} runs</span>
              </div>
            </li>
          )
        })}
      </ul>

      <section className="mt-16">
        <Eyebrow>Generalisation</Eyebrow>
        <h2 className="text-2xl font-medium">On things it never saw in training</h2>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <Held title="A new type of task" value={pct(family?.top1)} note="found on the first try"
            detail={family ? `${pct(family.top3)} within its top 3 picks` : undefined} />
          <Held title="New kinds of failure" value={pct(types?.top3)} note="found within its top 3 picks"
            detail={types ? `${pct(types.top1)} on the first try` : undefined} />
        </div>
      </section>

      <section className="mt-16 flex gap-4 rounded-lg border bg-surface p-6">
        <BadgeCheck className="mt-1 size-6 shrink-0 text-orange" aria-hidden />
        <div>
          <p className="font-heading text-xl font-medium">
            Fixing the step it points to turns {pct(flip)} of failed runs into successes.
          </p>
          <p className="mt-2 text-sm leading-6 text-dim">
            Each fix is checked by actually replaying the run from that step, not by trusting the model.
          </p>
        </div>
      </section>

      <div className="mt-8 flex flex-wrap justify-between gap-3 text-sm text-dim">
        <span>Measured on {int(m.dataset?.runs)} recorded runs.</span>
        <a href={`${REPO}/blob/main/docs/eval_report.md`} target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-ink">
          Full report <ArrowUpRight className="size-4" />
        </a>
      </div>
    </main>
  )
}

function Held({ title, value, note, detail }: { title: string; value: string; note: string; detail?: string }) {
  return (
    <div className="rounded-lg border bg-surface p-6">
      <p className="font-heading text-lg font-medium">{title}</p>
      <p className="mt-6 font-heading text-5xl font-semibold tabular-nums text-orange">{value}</p>
      <p className="mt-2 text-sm">{note}</p>
      {detail && <p className="mt-1 text-xs text-dim">{detail}</p>}
    </div>
  )
}
