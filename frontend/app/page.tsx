"use client"

import Link from "next/link"

import { ErrorNote, Loading, StatusBadge } from "@/components/bits"
import type { DemoRun, Metrics, Stats } from "@/lib/api"
import { int, pct } from "@/lib/format"
import { useApi } from "@/lib/use-api"

const HOW = [
  { name: "Record", text: "Every step the AI agent takes is saved, with a snapshot of everything it knew at that moment." },
  { name: "Blame", text: "A model trained on thousands of runs points to the step that actually caused the failure." },
  { name: "Fork", text: "We restart the run from just before that step, fix it, and replay only what comes after." },
  { name: "Prove", text: "If the run now succeeds, we have proof that this step was the cause." },
]

export default function Home() {
  const demo = useApi<{ runs: DemoRun[] }>("/demo")
  const metrics = useApi<Metrics>("/eval")
  const stats = useApi<Stats>("/stats")

  const test = metrics.data?.splits.test?.methods
  const flip = metrics.data?.replay?.splits.test?.flip_rate_top1

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-5 py-10">
      <section className="max-w-3xl">
        <h1 className="font-heading text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
          Find the step that broke your AI agent, and prove it.
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-foreground/80">
          AI agents now issue refunds, send emails and cancel orders. When one gets it wrong, the mistake usually happened
          several steps before anyone notices. Black Box is a flight recorder for these agents: it records every step,
          points to the one that caused the failure, and proves it by fixing only that step and replaying the run.
        </p>
      </section>

      <section className="mt-10 grid gap-4 sm:grid-cols-3" aria-label="Results">
        <Figure value={pct(test?.model?.top1)} text="of failures traced to the right step on the first try" accent />
        <Figure value={test?.llm_judge?.n ? pct(test.llm_judge.top1) : "—"} text="if you just ask Gemini to read the same recordings" />
        <Figure value={pct(flip)} text="of fixes at the blamed step turn the failure into a success" />
      </section>

      <section className="mt-12">
        <h2 className="font-heading text-2xl font-semibold tracking-tight">Try it on a broken agent</h2>
        <p className="mt-1 text-dim">Each case is a real recording where the agent got something wrong. Open one and find out why.</p>
        {demo.error ? (
          <ErrorNote message={demo.error} onRetry={demo.reload} />
        ) : !demo.data ? (
          <Loading />
        ) : (
          <ul className="mt-5 grid gap-4 md:grid-cols-3">
            {demo.data.runs.map((d) => (
              <li key={d.id}>
                <Link
                  href={`/story/${d.id}`}
                  className="flex h-full flex-col rounded-xl border bg-card p-5 transition-colors hover:border-orange/60 focus-visible:border-orange focus-visible:outline-none"
                >
                  <StatusBadge status={d.status} className="self-start" />
                  <h3 className="mt-3 font-heading text-lg font-semibold leading-snug">{d.title}</h3>
                  <p className="mt-2 flex-1 text-sm leading-relaxed text-dim">{d.story}</p>
                  <span className="mt-4 text-sm font-medium text-orange">Open this case</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-14">
        <h2 className="font-heading text-2xl font-semibold tracking-tight">How it works</h2>
        <ol className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {HOW.map((h, i) => (
            <li key={h.name} className="rounded-xl border bg-card p-5">
              <span className="font-mono text-sm text-orange">{i + 1}</span>
              <h3 className="mt-1 font-heading text-lg font-semibold">{h.name}</h3>
              <p className="mt-1 text-sm leading-relaxed text-dim">{h.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-12 flex flex-wrap gap-x-8 gap-y-2 border-t pt-6 text-sm">
        <Link href="/runs" className="text-orange hover:underline">
          Browse all {stats.data ? int(stats.data.runs) : ""} recorded runs
        </Link>
        <Link href="/lab" className="text-orange hover:underline">See how the model was tested</Link>
        <Link href="/live" className="text-orange hover:underline">Run an agent live</Link>
      </section>
    </main>
  )
}

function Figure({ value, text, accent }: { value: string; text: string; accent?: boolean }) {
  return (
    <div className="rounded-xl border bg-card p-5">
      <div className={`font-heading text-4xl font-semibold tabular-nums ${accent ? "text-orange" : ""}`}>{value}</div>
      <p className="mt-2 text-sm leading-relaxed text-dim">{text}</p>
    </div>
  )
}
