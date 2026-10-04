"use client"

import { ArrowLeft, Check, ChevronDown, Loader2, RotateCcw, Search, ShieldCheck, ShieldX, X } from "lucide-react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { useEffect, useRef, useState } from "react"

import { Loading, Problem, StepList, visibleSteps, btnPrimary } from "@/components/kit"
import { SecondOpinion } from "@/components/second-opinion"
import { Universes } from "@/components/universes"
import { API_URL, api, post, type Diagnosis, type ForkResult, type ReviewResult, type Run, type Verify } from "@/lib/api"
import { amountIn, capital, describeStep, plainReason, TASK_TITLE } from "@/lib/plain"
import { useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

type Stage = 1 | 2 | 3

export default function RunPage() {
  const { id } = useParams<{ id: string }>()
  const { data: run, error, reload } = useApi<Run>(`/runs/${id}`)
  const [diag, setDiag] = useState<Diagnosis | null>(null)
  const [fix, setFix] = useState<ForkResult | null>(null)
  const [busy, setBusy] = useState<"cause" | "fix" | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [reasoning, setReasoning] = useState(false)
  const [review, setReview] = useState<ReviewResult | null>(null)
  const [reviewBusy, setReviewBusy] = useState(false)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const proofRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (fix) proofRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
  }, [fix])

  if (error) return <Problem message={error} onRetry={reload} />
  if (!run) return <Loading />

  const failed = run.status === "fail"
  const rootIdx = diag?.canon_event.idx ?? null
  const rootStep = run.steps.find((s) => s.idx === rootIdx)
  const items = visibleSteps(run.steps, rootIdx, reasoning)
  const stage: Stage = fix ? 3 : diag ? 2 : 1
  const numbering = new Map(visibleSteps(run.steps, rootIdx).map((x) => [x.step.idx, x.n]))
  const labelFor = (idx: number) => {
    const n = numbering.get(idx)
    return n ? `step ${String(n).padStart(2, "0")}` : "a reasoning step"
  }
  const describe = (idx: number) => {
    const st = run.steps.find((x) => x.idx === idx)
    return st ? describeStep(st) : ""
  }

  const askReviewers = async () => {
    setReviewBusy(true)
    setReviewError(null)
    try {
      setReview(await post<ReviewResult>(`/runs/${id}/review`))
    } catch (e) {
      setReviewError(e instanceof Error ? e.message : String(e))
    } finally {
      setReviewBusy(false)
    }
  }

  const findCause = async () => {
    setBusy("cause")
    setProblem(null)
    try {
      setDiag(await post<Diagnosis>(`/runs/${id}/diagnose`))
      void askReviewers()
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const fixIt = async () => {
    if (rootIdx === null) return
    setBusy("fix")
    setProblem(null)
    try {
      setFix(await post<ForkResult>(`/runs/${id}/autofix?step=${rootIdx}`))
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-5 pt-8 md:px-8 md:pt-12">
      <div className="flex items-center justify-between gap-3 text-sm">
        <Link href="/runs" className="flex items-center gap-1.5 text-dim hover:text-ink">
          <ArrowLeft className="size-4" /> All runs
        </Link>
        <span className="font-mono text-xs text-dim">Run {run.id.startsWith("hero-") ? run.id.slice(5) : run.id.slice(0, 8)}</span>
      </div>

      <h1 className="mt-6 text-[26px] leading-9 font-medium md:text-[32px] md:leading-10">
        {TASK_TITLE[run.task_family] ?? "Agent run"}
      </h1>

      <div className={cn("mt-4 flex items-start gap-2.5 rounded-lg border px-4 py-3 text-[15px]",
        failed ? "border-fail/30 bg-fail/10" : run.status === "success" ? "border-success/30 bg-success/10" : "border-orange/30 bg-orange/10")}>
        {failed ? <X className="mt-0.5 size-4 shrink-0 text-fail" /> : <Check className="mt-0.5 size-4 shrink-0 text-success" />}
        <p>
          {failed ? `The agent got it wrong: ${run.outcome_detail}` : run.status === "success" ? `The agent got it right: ${run.final_answer}` : "This run is still in progress."}
        </p>
      </div>

      {run.parent_run_id && (
        <p className="mt-3 text-sm text-dim">
          This is a replay of{" "}
          <Link href={`/runs/${run.parent_run_id}`} className="text-ink underline-offset-4 hover:underline">another run</Link>{" "}
          with one step fixed.
        </p>
      )}

      {failed && <Stages stage={stage} />}

      <section className="mt-10">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2 className="text-lg font-medium">What the agent did</h2>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-dim">
            <input type="checkbox" className="size-3.5 accent-[#FF6A13]" checked={reasoning} onChange={(e) => setReasoning(e.target.checked)} />
            Show its reasoning
          </label>
        </div>
        <StepList
          items={items}
          rootIdx={rootIdx}
          reason={diag ? plainReason(rootStep, diag.ranking[0]?.evidence ?? []) : undefined}
          confidence={diag?.canon_event.prob}
        />
      </section>

      {diag && <SecondOpinion result={review} loading={reviewBusy} error={reviewError} labelFor={labelFor} />}

      {failed && !fix && (
        <div className="mt-8">
          {!diag ? (
            <button onClick={findCause} disabled={busy !== null} className={cn(btnPrimary, "w-full py-3.5 text-base")}>
              {busy === "cause" ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />} Find the cause
            </button>
          ) : (
            <button onClick={fixIt} disabled={busy !== null} className={cn(btnPrimary, "w-full py-3.5 text-base")}>
              {busy === "fix" ? <Loader2 className="size-4 animate-spin" /> : <RotateCcw className="size-4" />} Fix this step and replay
            </button>
          )}
          <p className="mt-2 text-center text-sm text-dim">
            {!diag
              ? "The mistake shows at the end. A trained model checks every step to find where it started."
              : "Black Box restarts the run from just before this step, fixes it, and replays the rest."}
          </p>
          {problem && <p className="mt-3 text-center text-sm text-fail">{problem}</p>}
        </div>
      )}

      {fix && <Proof ref={proofRef} run={run} fix={fix} />}

      {fix && <Universes runId={run.id} labelFor={labelFor} describe={describe} />}

      <DevDetails run={run} rootIdx={rootIdx} />
    </main>
  )
}

function Stages({ stage }: { stage: Stage }) {
  const names = ["Find the cause", "Fix it", "Proof"]
  return (
    <ol className="mt-8 grid grid-cols-3 gap-2 rounded-lg border bg-surface p-2 text-xs sm:text-sm" aria-label="Progress">
      {names.map((n, i) => {
        const state = i + 1 < stage || stage === 3 ? "done" : i + 1 === stage ? "now" : "next"
        return (
          <li key={n} aria-current={state === "now" ? "step" : undefined}
            className={cn("flex items-center gap-2 rounded px-2 py-2 sm:px-3", state === "now" && "bg-raised")}>
            <span className={cn("size-2 shrink-0 rounded-full", state === "next" ? "bg-line" : "bg-orange")} />
            <span className={cn(state === "next" ? "text-dim" : "text-ink")}>
              {i + 1}. {n}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function Proof({ run, fix, ref }: { run: Run; fix: ForkResult; ref: React.Ref<HTMLElement> }) {
  const amountCase = /amount/.test(run.outcome_detail)
  const before = amountCase ? amountIn(run.final_answer) : null
  const after = amountCase ? amountIn(fix.final_answer) : null
  const ok = fix.status === "success"
  return (
    <section ref={ref} className="rise mt-12 scroll-mt-20">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-lg font-medium">Proof of fix</h2>
        {ok && (
          <span className="flex items-center gap-1.5 rounded border border-success/30 bg-success/10 px-2 py-0.5 text-xs font-medium text-success">
            <Check className="size-3.5" /> Verified outcome
          </span>
        )}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border bg-surface p-5">
          <p className="flex items-center justify-between text-sm text-dim">
            Before the fix <X className="size-4 text-fail" aria-hidden />
          </p>
          <p className="mt-3 font-heading text-2xl font-semibold">{before ?? "Wrong outcome"}</p>
          <p className="mt-1 text-sm text-fail">{before ? "Wrong amount" : capital(run.outcome_detail)}</p>
        </div>
        <div className={cn("rounded-lg border p-5", ok ? "border-success/30 bg-success/[0.06]" : "bg-surface")}>
          <p className="flex items-center justify-between text-sm text-dim">
            After the fix {ok ? <Check className="size-4 text-success" aria-hidden /> : <X className="size-4 text-fail" aria-hidden />}
          </p>
          <p className="mt-3 font-heading text-2xl font-semibold">{after ?? (ok ? "Correct outcome" : "Still wrong")}</p>
          <p className={cn("mt-1 text-sm", ok ? "text-success" : "text-fail")}>{ok ? "Every check passed" : capital(fix.outcome_detail)}</p>
        </div>
      </div>
      <p className="mt-4 text-center text-sm text-dim">
        Everything before the fixed step was reused from the recording. Only the steps after it were replayed.
      </p>
      {fix.fix?.explanation && <p className="mt-1 text-center text-sm text-dim">The fix: {fix.fix.explanation}</p>}
    </section>
  )
}

function DevDetails({ run, rootIdx }: { run: Run; rootIdx: number | null }) {
  const [open, setOpen] = useState(false)
  const [verify, setVerify] = useState<Verify | null>(null)
  const step = run.steps.find((s) => s.idx === rootIdx) ?? null

  useEffect(() => {
    if (open && !verify) api<Verify>(`/runs/${run.id}/verify`).then(setVerify).catch(() => null)
  }, [open, verify, run.id])

  return (
    <section className="mt-12 rounded-lg border bg-surface">
      <button onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left text-sm text-dim hover:text-ink">
        Developer details
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-4 border-t px-5 py-4 text-sm">
          <p className="flex items-center gap-2">
            {verify ? (
              verify.valid ? (
                <><ShieldCheck className="size-4 text-success" /> Recording verified: all {verify.steps_checked} steps are untouched.</>
              ) : (
                <><ShieldX className="size-4 text-fail" /> Recording was changed at step {verify.broken_at}.</>
              )
            ) : (
              <span className="text-dim">Checking the recording…</span>
            )}
          </p>
          {step ? (
            <div>
              <p className="mb-1.5 text-dim">Raw data of the root-cause step ({step.name})</p>
              <pre className="max-h-72 overflow-auto rounded border bg-bg p-3 font-mono text-xs leading-5 text-ink/90">
                {JSON.stringify({ input: step.input, output: step.output, error: step.error }, null, 2)}
              </pre>
            </div>
          ) : (
            <p className="text-dim">Find the cause to see the raw data of the step that caused it.</p>
          )}
          <a href={`${API_URL.replace(/\/api$/, "")}/docs`} target="_blank" rel="noreferrer" className="inline-block text-orange hover:underline">
            Open the API docs
          </a>
        </div>
      )}
    </section>
  )
}
