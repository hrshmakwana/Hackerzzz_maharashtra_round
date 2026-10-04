"use client"

import { ArrowLeft, ArrowRight, GitBranch, Recycle } from "lucide-react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Fragment, Suspense } from "react"

import { Empty, ErrorNote, KindDot, Loading, Readouts, StatusBadge } from "@/components/bits"
import { DemoCoach } from "@/components/demo-coach"
import type { Comparison, Pair, Run, Step } from "@/lib/api"
import { EDIT_LABEL, FAMILY_LABEL, int, label, ms, shortId, stepSummary } from "@/lib/format"
import { useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

export default function ComparePage() {
  return (
    <Suspense fallback={<Loading />}>
      <Multiverse />
    </Suspense>
  )
}

function Multiverse() {
  const search = useSearchParams()
  const a = search.get("a")
  const b = search.get("b")
  const demo = search.get("demo") === "1"
  if (!a) return <Empty className="flex-1">Open a run and fork it to compare two universes.</Empty>
  if (!b) return <PickFork a={a} />
  return <CompareView a={a} b={b} demo={demo} />
}

function PickFork({ a }: { a: string }) {
  const { data, error } = useApi<Run>(`/runs/${a}`)
  if (error) return <ErrorNote message={error} />
  if (!data) return <Loading />
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-6">
      <h1 className="font-heading text-xl font-semibold">Pick a fork of {shortId(a)} to compare</h1>
      {data.forks.length === 0 ? (
        <Empty>This run has no forks yet. Use Auto-fix or Fork and fix on its Flight Deck.</Empty>
      ) : (
        <ul className="mt-4 divide-y rounded-lg border bg-card">
          {data.forks.map((f) => (
            <li key={f.id}>
              <Link href={`/compare?a=${a}&b=${f.id}`} className="flex items-center justify-between px-4 py-3 hover:bg-surface-2">
                <span className="font-mono text-sm">{shortId(f.id)} at step {f.fork_step_idx}</span>
                <StatusBadge status={f.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}

function CompareView({ a, b, demo }: { a: string; b: string; demo: boolean }) {
  const router = useRouter()
  const { data, error, loading, reload } = useApi<Comparison>(`/compare?a=${a}&b=${b}`)
  if (error) return <ErrorNote message={error} onRetry={reload} className="flex-1" />
  if (!data || loading) return <Loading label="Lining up the two universes…" className="flex-1" />

  const stepsA = new Map(data.steps_a.map((s) => [s.idx, s]))
  const stepsB = new Map(data.steps_b.map((s) => [s.idx, s]))
  const edit = data.edits?.[0]
  const flip = data.outcome.flipped
  const forkAt = data.fork_step

  return (
    <main className="mx-auto flex w-full max-w-[1400px] flex-col gap-4 px-4 py-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Link href={`/runs/${data.a.id}`} className="text-dim hover:text-foreground" aria-label="Back to the original run">
            <ArrowLeft className="size-4" />
          </Link>
          <h1 className="font-heading text-xl font-semibold tracking-tight">Multiverse view</h1>
          <span className="text-sm text-dim">{label(FAMILY_LABEL, data.a.task_family)}</span>
        </div>
      </header>

      {demo && (
        <DemoCoach step={4} action="Next: Model Lab" onAction={() => router.push("/lab?demo=1")}>
          {flip
            ? <>Same run, two universes. The fork reused {data.savings?.steps_reused ?? 0} steps, changed one, and the outcome flipped. That is the proof.</>
            : <>The fork did not change the outcome, so this step was not the cause.</>}
        </DemoCoach>
      )}

      {/* the outcome, as large as anything on the page */}
      <section className="grid items-center gap-4 rounded-lg border bg-card px-5 py-4 md:grid-cols-[1fr_auto_1fr]">
        <UniverseHead title="Original run" run={data.a} />
        <div className="flex flex-col items-center gap-1 text-center">
          <div className={cn("font-heading text-3xl font-bold tracking-tight", flip ? "text-success" : data.outcome.regressed ? "text-fail" : "text-foreground")}>
            {data.outcome.a === "fail" ? "Fail" : "Success"}
            <ArrowRight className="mx-2 inline size-6 align-[-2px] text-dim" />
            {data.outcome.b === "fail" ? "Fail" : "Success"}
          </div>
          <p className="text-xs text-dim">
            {flip ? `Canon Event confirmed at step ${forkAt}` : data.outcome.regressed ? "The change broke a working run" : "Outcome unchanged"}
          </p>
        </div>
        <UniverseHead title={data.is_fork ? `Fork at step ${forkAt}` : "Other run"} run={data.b} right />
      </section>

      {data.savings && (
        <Readouts
          items={[
            { label: "Steps reused from the checkpoint", value: int(data.savings.steps_reused), hint: `${Math.round(data.savings.reused_frac * 100)}% of the original run`, accent: true },
            { label: "Steps re-executed", value: int(data.savings.steps_rerun) },
            { label: "Tokens not spent again", value: int(data.savings.tokens_saved) },
            { label: "Time not spent again", value: ms(data.savings.time_saved_ms) },
          ]}
        />
      )}

      {edit && (
        <p className="flex items-start gap-2 rounded-lg border border-orange/30 bg-orange/[0.05] px-4 py-2.5 text-sm">
          <GitBranch className="mt-0.5 size-4 shrink-0 text-orange" />
          <span>
            <span className="font-medium">{label(EDIT_LABEL, edit.type)} at step {edit.step ?? forkAt}.</span>{" "}
            <span className="text-foreground/80">{edit.note ?? ""}</span>
          </span>
        </p>
      )}

      <section className="rounded-lg border bg-card">
        <div className="grid grid-cols-[1fr_1fr] border-b text-xs text-dim">
          <div className="px-4 py-2">Original <span className="font-mono">{shortId(data.a.id)}</span></div>
          <div className="border-l px-4 py-2">{data.is_fork ? "Fork" : "Other"} <span className="font-mono">{shortId(data.b.id)}</span></div>
        </div>
        <ol>
          {data.pairs.map((p, i) => (
            <Fragment key={i}>
              {forkAt !== null && p.b === forkAt && (
                <li className="relative grid grid-cols-[1fr_1fr] border-y border-orange/40 bg-orange/[0.06] text-xs">
                  <span className="col-span-2 px-4 py-1 text-orange">
                    The universes split here: everything above was reused, everything below ran again.
                  </span>
                </li>
              )}
              <PairRow pair={p} a={p.a !== null ? stepsA.get(p.a) : undefined} b={p.b !== null ? stepsB.get(p.b) : undefined} />
            </Fragment>
          ))}
        </ol>
      </section>
    </main>
  )
}

function UniverseHead({ title, run, right }: { title: string; run: Comparison["a"]; right?: boolean }) {
  return (
    <div className={cn("min-w-0", right && "md:text-right")}>
      <div className={cn("flex items-center gap-2", right && "md:justify-end")}>
        <span className="text-sm text-dim">{title}</span>
        <StatusBadge status={run.status} />
      </div>
      <p className="mt-1 truncate text-sm" title={run.outcome_detail}>{run.outcome_detail}</p>
      <p className="truncate font-mono text-xs text-dim" title={run.final_answer}>{run.final_answer || "no final answer"}</p>
      <Link href={`/runs/${run.id}`} className="text-xs text-orange hover:underline">Open in Flight Deck</Link>
    </div>
  )
}

function Cell({ step, dim, changed }: { step?: Step; dim?: boolean; changed?: boolean }) {
  if (!step) return <div className="px-4 py-2 text-xs text-dim/60 italic">no step here</div>
  return (
    <div className={cn("min-w-0 px-4 py-1.5", dim && "opacity-45", changed && "bg-orange/[0.05]")}>
      <div className="flex items-center gap-1.5">
        <span className="font-mono text-[11px] text-dim">{String(step.idx).padStart(2, "0")}</span>
        <KindDot kind={step.kind} />
        <span className="truncate font-mono text-[12px]">{step.kind === "llm" ? "llm" : step.name}</span>
        {step.reused && <Recycle className="size-3 shrink-0 text-dim" aria-label="reused" />}
        {step.error && <span className="text-[11px] text-fail">error</span>}
      </div>
      <p className="truncate text-[11px] text-dim" title={stepSummary(step)}>{stepSummary(step)}</p>
    </div>
  )
}

function PairRow({ pair, a, b }: { pair: Pair; a?: Step; b?: Step }) {
  const same = pair.op === "equal"
  return (
    <li className="grid grid-cols-[1fr_1fr] border-b border-border/50 last:border-0">
      <Cell step={a} dim={same && pair.reused} changed={!same} />
      <div className="border-l">
        <Cell step={b} dim={same && pair.reused} changed={!same} />
      </div>
    </li>
  )
}
