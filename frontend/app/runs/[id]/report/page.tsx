"use client"

import { ArrowLeft, Download } from "lucide-react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { useEffect, useState } from "react"

import { Loading, Problem, btnPrimary, visibleSteps } from "@/components/kit"
import type { Leaderboard } from "@/components/scorecard"
import { api, post, type Diagnosis, type ForkResult, type ReviewResult, type Run, type Verify } from "@/lib/api"
import { amountIn, capital, describeStep, plainReason, TASK_TITLE } from "@/lib/plain"

interface Data {
  run: Run
  diag: Diagnosis
  review: ReviewResult | null
  fork: Run | null
  fixNote: string | null
  board: Leaderboard | null
  verify: Verify | null
}

export default function ReportPage() {
  const { id } = useParams<{ id: string }>()
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const run = await api<Run>(`/runs/${id}`)
        const diag = await post<Diagnosis>(`/runs/${id}/diagnose`)
        const [review, board, verify] = await Promise.all([
          post<ReviewResult>(`/runs/${id}/review`).catch(() => null),
          api<Leaderboard>("/leaderboard").catch(() => null),
          api<Verify>(`/runs/${id}/verify`).catch(() => null),
        ])
        let fork: Run | null = null
        let fixNote: string | null = null
        if (run.status === "fail") {
          const existing = run.forks.find((f) => f.fork_step_idx === diag.canon_event.idx && f.status === "success")
          if (existing) {
            fork = await api<Run>(`/runs/${existing.id}`)
            fixNote = fork.edits?.[0]?.note ?? null
          } else {
            const res = await post<ForkResult>(`/runs/${id}/autofix?step=${diag.canon_event.idx}`).catch(() => null)
            if (res) {
              fork = await api<Run>(`/runs/${res.id}`)
              fixNote = res.fix?.explanation ?? null
            }
          }
        }
        if (alive) setData({ run, diag, review, fork, fixNote, board, verify })
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e))
      }
    })()
    return () => {
      alive = false
    }
  }, [id])

  if (error) return <Problem message={error} />
  if (!data) return <Loading label="Preparing the report…" />

  const { run, diag, review, fork, fixNote, board, verify } = data
  const root = run.steps.find((s) => s.idx === diag.canon_event.idx)
  const numbering = new Map(visibleSteps(run.steps, diag.canon_event.idx).map((x) => [x.step.idx, x.n]))
  const label = (idx: number | null | undefined) =>
    idx === null || idx === undefined ? "no answer" : numbering.has(idx) ? `step ${numbering.get(idx)}` : "a reasoning step"
  const truth = run.fault_step
  const amountCase = /amount/.test(run.outcome_detail)
  const picks: Record<string, number | null | undefined> = { "Black Box": diag.canon_event.idx }
  for (const r of review?.reviews ?? []) picks[r.name] = r.error ? undefined : r.step
  const today = new Date().toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })

  return (
    <main className="mx-auto max-w-[820px] px-4 py-8 print:max-w-none print:p-0">
      <div className="mb-4 flex items-center justify-between gap-3 print:hidden">
        <Link href={`/runs/${run.id}`} className="flex items-center gap-1.5 text-sm text-dim hover:text-ink">
          <ArrowLeft className="size-4" /> Back to the run
        </Link>
        <button onClick={() => window.print()} className={btnPrimary}>
          <Download className="size-4" /> Download PDF
        </button>
      </div>

      <article className="report rounded-lg bg-white px-8 py-8 text-[13px] leading-[1.55] text-neutral-900 sm:px-10 print:rounded-none print:px-0 print:py-0">
        <header className="flex items-start justify-between gap-4 border-b border-neutral-200 pb-4">
          <div>
            <p className="text-[11px] font-medium text-[#C2410C]">Black Box incident report</p>
            <h1 className="mt-1 text-[22px] leading-7 font-semibold text-neutral-900">{TASK_TITLE[run.task_family] ?? "Agent run"}</h1>
          </div>
          <p className="shrink-0 text-right text-[11px] text-neutral-500">
            {today}
            <br />
            Run {run.id.startsWith("hero-") ? run.id.slice(5) : run.id.slice(0, 8)}
          </p>
        </header>

        <Section title="What went wrong">
          {run.status === "fail" ? capital(run.outcome_detail) + "." : "Nothing: this run passed every check."}
        </Section>

        {run.status === "fail" && root && (
          <Section title="Where it started">
            <p>
              <b>{capital(label(root.idx))}: {describeStep(root)}.</b> {plainReason(root, diag.ranking[0]?.evidence ?? [])}
            </p>
            <p className="mt-1 text-neutral-500">
              Our model is {Math.round(diag.canon_event.prob * 100)}% sure. The failure only became visible later, at the end of the run.
            </p>
          </Section>
        )}

        {fork && (
          <Section title="The fix and the proof">
            {fixNote && <p>{fixNote}</p>}
            <div className="mt-2 grid grid-cols-2 gap-3">
              <div className="rounded border border-red-200 bg-red-50 px-3 py-2">
                <p className="text-[11px] text-red-700">Before the fix</p>
                <p className="font-semibold">{(amountCase && amountIn(run.final_answer)) || run.final_answer}</p>
                <p className="text-[11px] text-red-700">Wrong</p>
              </div>
              <div className="rounded border border-green-200 bg-green-50 px-3 py-2">
                <p className="text-[11px] text-green-700">After the fix</p>
                <p className="font-semibold">{(amountCase && amountIn(fork.final_answer)) || fork.final_answer}</p>
                <p className="text-[11px] text-green-700">{fork.status === "success" ? "Correct: every check passed" : "Still wrong"}</p>
              </div>
            </div>
            <p className="mt-2 text-neutral-500">
              Only the steps after the fix were run again; everything before it was reused from the recording.
            </p>
          </Section>
        )}

        {review && review.reviews.length > 0 && (
          <Section title="What the other AIs said">
            <p className="mb-1 text-neutral-500">Each AI read the recording on its own, without seeing our answer.</p>
            <ul className="space-y-1">
              {review.reviews.map((r) => (
                <li key={r.name}>
                  <b>{r.name}</b> ({r.maker}): {r.error ? "did not answer." : `picked ${label(r.step)}. ${r.reason}`}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {board && (
          <Section title="Who found the right step">
            <table className="w-full">
              <thead>
                <tr className="border-b border-neutral-200 text-left text-[11px] text-neutral-500">
                  <th className="py-1 font-normal">Method</th>
                  {truth !== null && <th className="py-1 font-normal">This run</th>}
                  <th className="py-1 text-right font-normal">Accuracy on the benchmark</th>
                </tr>
              </thead>
              <tbody>
                {board.methods.map((m) => {
                  const pick = picks[m.name]
                  return (
                    <tr key={m.key} className="border-b border-neutral-100">
                      <td className="py-1"><b>{m.name}</b> <span className="text-neutral-500">({m.maker})</span></td>
                      {truth !== null && (
                        <td className="py-1">{pick === undefined ? "no answer" : pick === truth ? "✓ right" : `✗ ${label(pick)}`}</td>
                      )}
                      <td className="py-1 text-right">
                        {m.benchmark ? `${Math.round(m.benchmark.top1 * 100)}% of ${m.benchmark.n} runs` : "not measured"}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <p className="mt-2 text-neutral-500">How we know the right answer: {board.basis}</p>
          </Section>
        )}

        <footer className="mt-5 flex justify-between gap-4 border-t border-neutral-200 pt-3 text-[11px] text-neutral-500">
          <span>{verify ? (verify.valid ? `Recording verified: all ${verify.steps_checked} steps untouched.` : `Recording was changed at step ${verify.broken_at}.`) : ""}</span>
          <span>Black Box: a flight recorder for AI agents</span>
        </footer>
      </article>
    </main>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-4">
      <h2 className="mb-1 text-[13px] font-semibold text-neutral-900">{title}</h2>
      <div>{children}</div>
    </section>
  )
}
