"use client"

import { ArrowRight } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { Eyebrow, Loading, Problem, StatusPill, btnPrimary, btnSecondary } from "@/components/kit"
import { RunRows } from "@/components/run-rows"
import type { DemoRun, Metrics, RunSummary } from "@/lib/api"
import { pct } from "@/lib/format"
import { useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

const CASE_TAG: Record<string, string> = {
  bad_retrieval: "Outdated policy",
  prompt_injection: "Hacked email",
  wrong_args: "Wrong order",
}

export default function Home() {
  const metrics = useApi<Metrics>("/eval")
  const demo = useApi<{ runs: DemoRun[] }>("/demo")
  const [onlyFailed, setOnlyFailed] = useState(false)
  const runs = useApi<{ items: RunSummary[]; total: number }>(
    `/runs?limit=5&forks=false${onlyFailed ? "&status=fail" : ""}`,
  )

  const m = metrics.data
  const test = m?.splits.test?.methods
  const stats = [
    { value: pct(test?.model?.top1), text: "of failures traced to the right step on the first try", accent: true },
    { value: test?.llm_judge?.n ? pct(test.llm_judge.top1) : "—", text: "if you just ask Gemini to read the same recordings" },
    { value: pct(m?.replay?.splits.test?.flip_rate_top1), text: "of fixes turn the failure into a success" },
  ]

  return (
    <main className="mx-auto max-w-6xl px-5 md:px-8">
      {/* hero */}
      <section className="relative pt-14 pb-12 md:pt-24 md:pb-16">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-10 right-0 -z-10 hidden h-96 w-[40rem] rounded-full bg-[radial-gradient(closest-side,rgba(255,106,19,0.10),transparent)] md:block"
        />
        <h1 className="max-w-3xl text-[32px] leading-10 font-semibold md:text-5xl md:leading-[3.6rem]">
          Find the step that broke your AI agent, and prove it.
        </h1>
        <p className="mt-5 max-w-xl text-base leading-7 text-dim md:text-lg md:leading-8">
          Black Box records every step an AI agent takes, finds the one that caused the mistake, and proves it by fixing
          just that step.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link href="/runs/hero-refund-stale-policy" className={btnPrimary}>
            See a sample run <ArrowRight className="size-4" />
          </Link>
          <Link href="/live" className={btnSecondary}>
            Try it live
          </Link>
        </div>
      </section>

      {/* three numbers */}
      <section aria-label="Results" className="grid gap-4 sm:grid-cols-3">
        {stats.map((s) => (
          <div key={s.text} className="rounded-lg border bg-surface p-6">
            <p className={cn("font-heading text-4xl font-semibold tabular-nums md:text-5xl", s.accent && "text-orange")}>
              {metrics.loading && !m ? "…" : s.value}
            </p>
            <p className="mt-3 text-sm leading-6 text-dim">{s.text}</p>
          </div>
        ))}
      </section>

      {/* example cases */}
      <section className="mt-20">
        <Eyebrow>Example cases</Eyebrow>
        <h2 className="text-2xl font-medium md:text-[32px] md:leading-10">Open a broken run and see why it failed</h2>
        {demo.error ? (
          <Problem message={demo.error} onRetry={demo.reload} />
        ) : !demo.data ? (
          <Loading />
        ) : (
          <ul className="mt-8 grid gap-4 md:grid-cols-3">
            {demo.data.runs.map((d) => (
              <li key={d.id}>
                <Link
                  href={`/runs/${d.id}`}
                  className="group flex h-full flex-col rounded-lg border bg-surface p-6 transition-colors hover:border-orange/60 hover:bg-raised"
                >
                  <StatusPill status={d.status} className="self-start" />
                  <h3 className="mt-4 text-xl font-medium leading-7">{d.title}</h3>
                  <p className="mt-2 flex-1 text-sm leading-6 text-dim">{d.story}</p>
                  <div className="mt-6 flex items-center justify-between text-sm">
                    <span className="text-dim">{CASE_TAG[d.fault.type] ?? ""}</span>
                    <span className="flex items-center gap-1 font-medium text-orange">
                      Open case <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
                    </span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* recent runs */}
      <section className="mt-20">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <Eyebrow>Recorded runs</Eyebrow>
            <h2 className="text-2xl font-medium md:text-[32px] md:leading-10">Recent runs</h2>
          </div>
          <div className="flex rounded border bg-bg p-0.5 text-sm" role="radiogroup" aria-label="Filter runs">
            {[
              { v: false, label: "All runs" },
              { v: true, label: "Only failed" },
            ].map((o) => (
              <button
                key={o.label}
                role="radio"
                aria-checked={onlyFailed === o.v}
                onClick={() => setOnlyFailed(o.v)}
                className={cn("rounded px-3 py-1.5 text-dim transition-colors hover:text-ink", onlyFailed === o.v && "bg-raised text-ink")}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>
        {runs.error ? (
          <Problem message={runs.error} onRetry={runs.reload} />
        ) : !runs.data ? (
          <Loading />
        ) : (
          <RunRows runs={runs.data.items} />
        )}
        <div className="mt-4 flex justify-end">
          <Link href="/runs" className="flex items-center gap-1 text-sm text-ink hover:text-orange">
            View all runs <ArrowRight className="size-4" />
          </Link>
        </div>
      </section>
    </main>
  )
}
