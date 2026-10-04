"use client"

import { ArrowLeft, Check, Loader2, Search, Wrench, X } from "lucide-react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { useEffect, useRef, useState } from "react"

import { ErrorNote, Loading } from "@/components/bits"
import { Button } from "@/components/ui/button"
import { post, type Diagnosis, type ForkResult, type Run } from "@/lib/api"
import { describeStep, TASK_TITLE } from "@/lib/plain"
import { useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

const STAGES = ["Record", "Blame", "Fork", "Prove"]

export default function StoryPage() {
  const { id } = useParams<{ id: string }>()
  const { data: run, error, reload } = useApi<Run>(`/runs/${id}`)
  const [diag, setDiag] = useState<Diagnosis | null>(null)
  const [fix, setFix] = useState<ForkResult | null>(null)
  const [busy, setBusy] = useState<"blame" | "fix" | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [showThinking, setShowThinking] = useState(false)
  const blamedRef = useRef<HTMLLIElement>(null)
  const resultRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (diag) blamedRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })
  }, [diag])
  useEffect(() => {
    if (fix) resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
  }, [fix])

  if (error) return <ErrorNote message={error} onRetry={reload} className="flex-1" />
  if (!run) return <Loading className="flex-1" />

  const stage = fix ? 4 : diag ? 2 : 1
  const blamed = diag?.canon_event.idx ?? null
  const top = diag?.ranking[0]
  const failed = run.status === "fail"

  const findCause = async () => {
    setBusy("blame")
    setProblem(null)
    try {
      setDiag(await post<Diagnosis>(`/runs/${id}/diagnose`))
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const fixIt = async () => {
    if (blamed === null) return
    setBusy("fix")
    setProblem(null)
    try {
      setFix(await post<ForkResult>(`/runs/${id}/autofix?step=${blamed}`))
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-5 py-6">
      <Link href="/" className="mb-4 inline-flex items-center gap-1 text-sm text-dim hover:text-foreground">
        <ArrowLeft className="size-4" /> All cases
      </Link>

      {/* Record → Blame → Fork → Prove */}
      <ol className="mb-6 flex items-center gap-2 text-sm" aria-label="Progress">
        {STAGES.map((s, i) => (
          <li key={s} className="flex items-center gap-2">
            <span className={cn("rounded-full border px-3 py-1",
              i + 1 < stage || (i + 1 === stage && stage === 4) ? "border-orange/50 bg-orange/10 text-orange"
                : i + 1 === stage ? "border-foreground/50 text-foreground" : "text-dim")}>
              {s}
            </span>
            {i < STAGES.length - 1 && <span className="text-dim">→</span>}
          </li>
        ))}
      </ol>

      <h1 className="font-heading text-3xl font-semibold tracking-tight">{TASK_TITLE[run.task_family] ?? "Agent run"}</h1>

      <div className={cn("mt-4 flex items-start gap-3 rounded-xl border px-4 py-3",
        failed ? "border-fail/40 bg-fail/[0.07]" : "border-success/40 bg-success/[0.07]")}>
        {failed ? <X className="mt-0.5 size-5 shrink-0 text-fail" /> : <Check className="mt-0.5 size-5 shrink-0 text-success" />}
        <div>
          <p className="font-medium">{failed ? "The agent got it wrong" : "The agent got it right"}</p>
          <p className="text-sm text-foreground/80">{failed ? capital(run.outcome_detail) : run.final_answer}</p>
        </div>
      </div>

      {/* what the agent did */}
      <section className="mt-8">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2 className="font-heading text-lg font-semibold">What the agent did</h2>
          <label className="flex items-center gap-2 text-xs text-dim">
            <input type="checkbox" checked={showThinking} onChange={(e) => setShowThinking(e.target.checked)} />
            Show its thinking too
          </label>
        </div>
        <ol className="rounded-xl border bg-card">
          {run.steps.filter((s) => showThinking || s.kind === "tool" || s.kind === "retrieval" || s.kind === "final" || s.idx === blamed).map((s, n) => {
            const isBlamed = blamed === s.idx
            return (
              <li
                key={s.idx}
                ref={isBlamed ? blamedRef : undefined}
                className={cn("flex gap-3 border-b border-border/60 px-4 py-2.5 text-[15px] last:border-0",
                  isBlamed && "border-l-4 border-l-orange bg-orange/[0.08]",
                  blamed !== null && !isBlamed && "opacity-60")}
              >
                <span className="w-6 shrink-0 text-right font-mono text-sm text-dim">{n + 1}</span>
                <div className="min-w-0">
                  <p className={cn("break-words", isBlamed && "font-medium")}>{describeStep(s)}</p>
                  {isBlamed && top && (
                    <div className="mt-2 rounded-lg border border-orange/40 bg-background px-3 py-2 text-sm">
                      <p className="font-heading font-semibold text-orange">This is where it went wrong</p>
                      <p className="mt-1 text-foreground/90">{capital(top.evidence[0] ?? diag?.canon_event.headline ?? "")}</p>
                      <p className="mt-1 text-xs text-dim">
                        Our model is {Math.round(top.prob * 100)}% sure.
                        {diag?.ground_truth && (diag.ground_truth.step === s.idx
                          ? " It matches the step we broke on purpose."
                          : " We actually broke a different step.")}
                      </p>
                    </div>
                  )}
                </div>
              </li>
            )
          })}
        </ol>
      </section>

      {/* actions */}
      {failed && (
        <section className="sticky bottom-4 mt-6 flex flex-wrap items-center gap-3 rounded-xl border bg-card/95 px-4 py-3 shadow-lg backdrop-blur">
          {!diag ? (
            <>
              <p className="flex-1 text-sm text-dim">The mistake shows at the end, but which step caused it?</p>
              <Button size="lg" onClick={findCause} disabled={busy !== null}>
                {busy === "blame" ? <Loader2 className="animate-spin" /> : <Search />} Find what caused it
              </Button>
            </>
          ) : !fix ? (
            <>
              <p className="flex-1 text-sm text-dim">Prove it: fix only that step and replay the rest.</p>
              <Button size="lg" onClick={fixIt} disabled={busy !== null}>
                {busy === "fix" ? <Loader2 className="animate-spin" /> : <Wrench />} Fix it and re-run
              </Button>
            </>
          ) : (
            <>
              <p className="flex-1 text-sm text-dim">Want the full technical picture?</p>
              <Link href={`/compare?a=${run.id}&b=${fix.id}`} className="text-sm text-orange hover:underline">Side-by-side comparison</Link>
              <Link href={`/runs/${run.id}`} className="text-sm text-orange hover:underline">Technical view</Link>
            </>
          )}
          {problem && <p className="w-full text-sm text-fail">{problem}</p>}
        </section>
      )}

      {/* before / after */}
      {fix && (
        <section ref={resultRef} className="mt-8 scroll-mt-20">
          <h2 className="mb-3 font-heading text-lg font-semibold">
            {fix.flipped ? "Fixed one step, and the whole run comes out right" : "That fix did not change the outcome"}
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-fail/40 bg-fail/[0.06] p-4">
              <p className="flex items-center gap-2 text-sm font-medium text-fail"><X className="size-4" /> Before</p>
              <p className="mt-2 text-[15px]">{run.final_answer}</p>
              <p className="mt-1 text-xs text-dim">{capital(run.outcome_detail)}</p>
            </div>
            <div className={cn("rounded-xl border p-4", fix.status === "success" ? "border-success/40 bg-success/[0.06]" : "border-fail/40 bg-fail/[0.06]")}>
              <p className={cn("flex items-center gap-2 text-sm font-medium", fix.status === "success" ? "text-success" : "text-fail")}>
                {fix.status === "success" ? <Check className="size-4" /> : <X className="size-4" />} After the fix
              </p>
              <p className="mt-2 text-[15px]">{fix.final_answer}</p>
              <p className="mt-1 text-xs text-dim">{fix.status === "success" ? "Every check passed" : capital(fix.outcome_detail)}</p>
            </div>
          </div>
          <div className="mt-3 rounded-xl border bg-card px-4 py-3 text-sm">
            <p><span className="font-medium">The fix:</span> {fix.fix?.explanation}</p>
            <p className="mt-1 text-dim">
              Everything before the broken step was reused from the recording, not run again. Only what came after was
              replayed.
            </p>
          </div>
        </section>
      )}
    </main>
  )
}

function capital(s: string) {
  return s ? s[0].toUpperCase() + s.slice(1) : s
}
