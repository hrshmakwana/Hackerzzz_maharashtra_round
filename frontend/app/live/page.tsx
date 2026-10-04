"use client"

import { AlertCircle, ArrowRight, Check, Loader2, Play, X } from "lucide-react"
import Link from "next/link"
import { useEffect, useRef, useState } from "react"

import { StepList, visibleSteps, btnPrimary } from "@/components/kit"
import { API_URL, api, post, type Run, type Step } from "@/lib/api"
import { capital, plainReason, PROBLEM_LABEL, TASK_SHORT } from "@/lib/plain"
import { cn } from "@/lib/utils"

type Phase = "idle" | "running" | "done"
const PROBLEMS = ["", "bad_retrieval", "wrong_args", "prompt_injection", "ignored_error", "calc_error"]

export default function LivePage() {
  const [task, setTask] = useState("refund")
  const [problemType, setProblemType] = useState("bad_retrieval")
  const [phase, setPhase] = useState<Phase>("idle")
  const [steps, setSteps] = useState<Step[]>([])
  const [run, setRun] = useState<Run | null>(null)
  const [error, setError] = useState<string | null>(null)
  const source = useRef<EventSource | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => () => source.current?.close(), [])
  useEffect(() => {
    if (phase === "running") endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" })
  }, [steps.length, phase])

  const start = async () => {
    source.current?.close()
    setSteps([])
    setRun(null)
    setError(null)
    setPhase("running")
    try {
      const r = await post<{ id: string }>("/runs", {
        family: task,
        policy: "sim",
        fault: problemType ? { type: problemType } : null,
        delay_ms: 450,
      })
      const es = new EventSource(`${API_URL}/runs/${r.id}/stream`)
      source.current = es
      es.addEventListener("step", (e) => {
        const s = JSON.parse((e as MessageEvent).data) as Step
        setSteps((prev) => (prev.some((p) => p.idx === s.idx) ? prev : [...prev, s]))
      })
      es.addEventListener("done", async () => {
        es.close()
        for (let i = 0; i < 15; i++) {
          const full = await api<Run>(`/runs/${r.id}`).catch(() => null)
          if (full && (full.status !== "fail" || full.diagnosis)) {
            setRun(full)
            break
          }
          await new Promise((res) => setTimeout(res, 400))
        }
        setPhase("done")
      })
      es.onerror = () => {
        es.close()
        setError("The live connection dropped. Open the run from the Runs page to see the result.")
        setPhase("done")
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setPhase("idle")
    }
  }

  const rootIdx = run?.diagnosis?.canon_event.idx ?? null
  const shown = visibleSteps(steps, rootIdx)
  const rootN = shown.find((x) => x.step.idx === rootIdx)?.n
  const rootStep = steps.find((s) => s.idx === rootIdx)
  const reason = run?.diagnosis ? plainReason(rootStep, run.diagnosis.ranking[0]?.evidence ?? []) : undefined

  return (
    <main className="mx-auto grid max-w-6xl gap-6 px-5 pt-10 md:px-8 md:pt-14 lg:grid-cols-[320px_minmax(0,1fr)] lg:gap-8">
      <section className="h-fit rounded-lg border bg-surface p-6 lg:sticky lg:top-20">
        <h1 className="text-2xl font-medium">Run an agent</h1>
        <p className="mt-2 text-sm leading-6 text-dim">
          Watch a support agent work, then see Black Box find what went wrong.
        </p>
        <label className="mt-6 block text-sm">
          Task
          <select value={task} onChange={(e) => setTask(e.target.value)} disabled={phase === "running"}
            className="mt-1.5 block w-full rounded border bg-bg px-3 py-2.5 text-[15px] focus-visible:border-ink focus-visible:outline-none">
            {Object.entries(TASK_SHORT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="mt-4 block text-sm">
          Break something on purpose
          <select value={problemType} onChange={(e) => setProblemType(e.target.value)} disabled={phase === "running"}
            className="mt-1.5 block w-full rounded border bg-bg px-3 py-2.5 text-[15px] focus-visible:border-ink focus-visible:outline-none">
            {PROBLEMS.map((p) => <option key={p} value={p}>{p ? PROBLEM_LABEL[p] : "Nothing (clean run)"}</option>)}
          </select>
        </label>
        <button onClick={start} disabled={phase === "running"} className={cn(btnPrimary, "mt-6 w-full py-3")}>
          {phase === "running" ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
          {phase === "running" ? "Running…" : phase === "done" ? "Run again" : "Start"}
        </button>
        <p className="mt-4 text-xs leading-5 text-dim">Runs in a sandbox shop. Nothing real is refunded or emailed.</p>
      </section>

      <section aria-live="polite">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-lg font-medium">What the agent is doing</h2>
          <span className="flex items-center gap-1.5 text-sm text-dim">
            {phase === "running" && <><Loader2 className="size-3.5 animate-spin text-orange" /> Recording</>}
            {phase === "done" && <><Check className="size-3.5 text-success" /> Complete</>}
          </span>
        </div>

        {steps.length === 0 ? (
          <p className="rounded-lg border bg-surface px-5 py-16 text-center text-sm text-dim">
            {phase === "running" ? "Starting the agent…" : "Pick a task and press Start. Each action appears here as it happens."}
          </p>
        ) : (
          <StepList items={shown} rootIdx={rootIdx} live />
        )}
        <div ref={endRef} />

        {error && <p className="mt-4 text-sm text-fail">{error}</p>}

        {phase === "done" && run && (
          <div className="rise mt-6 space-y-4">
            <div className={cn("flex items-start gap-2.5 rounded-lg border px-4 py-3",
              run.status === "fail" ? "border-fail/30 bg-fail/10" : "border-success/30 bg-success/10")}>
              {run.status === "fail" ? <X className="mt-0.5 size-4 shrink-0 text-fail" /> : <Check className="mt-0.5 size-4 shrink-0 text-success" />}
              <p className="text-[15px]">
                {run.status === "fail" ? `Failed: ${run.outcome_detail}` : `Passed: ${run.final_answer}`}
              </p>
            </div>
            {run.status === "fail" && reason && rootN && (
              <div className="rounded-lg border border-orange/40 bg-surface p-5">
                <p className="flex items-center gap-2 font-medium text-orange">
                  <AlertCircle className="size-4" /> Step {rootN} caused it
                </p>
                <p className="mt-1.5 text-[15px] leading-6">{capital(reason)}</p>
              </div>
            )}
            <Link href={`/runs/${run.id}`} className="inline-flex items-center gap-1.5 text-sm font-medium text-orange hover:underline">
              Open the full run, fix it and see the proof <ArrowRight className="size-4" />
            </Link>
          </div>
        )}
      </section>
    </main>
  )
}
