"use client"

import {
  ArrowLeft, Check, Crosshair, FileText, GitBranch, Loader2, RotateCcw, ShieldCheck, ShieldX, Sparkles, Wand2, X,
} from "lucide-react"
import Link from "next/link"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import { Suspense, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

import { CanonBadge, ErrorNote, Loading, Panel, StatusBadge } from "@/components/bits"
import { DemoCoach } from "@/components/demo-coach"
import { ExecGraph } from "@/components/flight/exec-graph"
import { ForkDrawer } from "@/components/flight/fork-drawer"
import { Inspector } from "@/components/flight/inspector"
import { Tape } from "@/components/flight/tape"
import { Markdown } from "@/components/markdown"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { api, post, type Diagnosis, type ForkResult, type Meta, type Run, type SweepResult, type Verify } from "@/lib/api"
import { FAMILY_LABEL, FAULT_LABEL, SPLIT_LABEL, label, pct, shortId } from "@/lib/format"
import { useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

export default function FlightDeckPage() {
  return (
    <Suspense fallback={<Loading />}>
      <FlightDeck />
    </Suspense>
  )
}

function FlightDeck() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const search = useSearchParams()
  const demo = search.get("demo") === "1"
  const runQ = useApi<Run>(`/runs/${id}`)
  const meta = useApi<Meta>("/meta")
  const run = runQ.data

  const [diag, setDiag] = useState<Diagnosis | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [tab, setTab] = useState("io")
  const [busy, setBusy] = useState<string | null>(null)
  const [verify, setVerify] = useState<Verify | null>(null)
  const [sweep, setSweep] = useState<SweepResult | null>(null)
  const [report, setReport] = useState<string | null>(null)
  const [reportOpen, setReportOpen] = useState(false)
  const [forkOpen, setForkOpen] = useState(false)
  const [demoStep, setDemoStep] = useState(1)

  // adopt a cached diagnosis and pick a sensible step to show first
  useEffect(() => {
    if (!run) return
    /* eslint-disable react-hooks/set-state-in-effect -- sync local view state with the loaded run */
    if (run.diagnosis && !diag) {
      setDiag(run.diagnosis)
      if (run.diagnosis.report_md) setReport(run.diagnosis.report_md)
      if (demo) setDemoStep(2)
    }
    if (selected === null && run.steps.length) {
      setSelected(run.diagnosis?.canon_event.idx ?? run.fork_step_idx ?? run.steps[run.steps.length - 1].idx)
    }
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [run, diag, selected, demo])

  // keep polling while a live run is still going
  useEffect(() => {
    if (run?.status !== "running") return
    const t = setInterval(runQ.reload, 1000)
    return () => clearInterval(t)
  }, [run?.status, runQ.reload])

  const blame = useMemo(() => (diag ? new Map(diag.ranking.map((r) => [r.idx, r.prob])) : null), [diag])
  const canon = diag?.canon_event.idx ?? null
  const injected = diag?.ground_truth?.step ?? null
  const step = run?.steps.find((s) => s.idx === selected) ?? null
  const rank = diag?.ranking.find((r) => r.idx === selected) ?? null

  const act = async <T,>(name: string, fn: () => Promise<T>): Promise<T | null> => {
    setBusy(name)
    try {
      return await fn()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
      return null
    } finally {
      setBusy(null)
    }
  }

  const diagnose = async () => {
    const d = await act("diagnose", () => post<Diagnosis>(`/runs/${id}/diagnose`))
    if (!d) return
    setDiag(d)
    setSelected(d.canon_event.idx)
    setTab("why")
    if (demo) setDemoStep(2)
  }

  const openReport = async () => {
    if (report) return setReportOpen(true)
    const d = await act("report", () => post<Diagnosis>(`/runs/${id}/diagnose?report=true`))
    if (d?.report_md) {
      setReport(d.report_md)
      setReportOpen(true)
    }
  }

  const compareUrl = (fork: string) => `/compare?a=${id}&b=${fork}${demo ? "&demo=1" : ""}`

  const autofix = async (at?: number) => {
    const k = at ?? selected ?? canon
    const r = await act("autofix", () => post<ForkResult>(`/runs/${id}/autofix${k !== null && k !== undefined ? `?step=${k}` : ""}`))
    if (r) router.push(compareUrl(r.id))
  }

  const replay = async () => {
    if (selected === null) return
    const r = await act("replay", () => post<ForkResult>(`/runs/${id}/replay?step=${selected}`))
    if (r) {
      toast(`Replayed from step ${selected}: ${r.status === run?.status ? "same outcome" : "outcome changed"}`, {
        description: `${r.savings.steps_reused} steps reused, ${r.savings.steps_rerun} re-run. ${r.outcome_detail}`,
        action: { label: "Compare", onClick: () => router.push(compareUrl(r.id)) },
      })
      runQ.reload()
    }
  }

  const doSweep = async () => {
    const r = await act("sweep", () => post<SweepResult>(`/runs/${id}/sweep?top_k=3`))
    if (r) {
      setSweep(r)
      if (!diag) {
        const d = await api<Diagnosis>(`/runs/${id}/diagnosis`).catch(() => null)
        if (d) setDiag(d)
      }
      runQ.reload()
    }
  }

  const doVerify = async () => {
    const v = await act("verify", () => api<Verify>(`/runs/${id}/verify`))
    if (v) setVerify(v)
  }

  if (runQ.error) return <ErrorNote message={runQ.error} onRetry={runQ.reload} className="flex-1" />
  if (!run) return <Loading label="Loading run…" className="flex-1" />

  const failed = run.status === "fail"

  return (
    <main className="mx-auto flex w-full max-w-[1600px] flex-col gap-3 px-4 py-3 lg:h-[calc(100dvh-3rem)]">
      {/* header */}
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Link href="/runs" className="text-dim hover:text-foreground" aria-label="Back to all runs">
              <ArrowLeft className="size-4" />
            </Link>
            <h1 className="font-heading text-xl font-semibold tracking-tight">{label(FAMILY_LABEL, run.task_family)}</h1>
            <span className="font-mono text-xs text-dim">{shortId(run.id)}</span>
            <StatusBadge status={run.status} />
            <span className="text-xs text-dim">{label(SPLIT_LABEL, run.split)} split, {run.policy === "gemini" ? "Gemini agent" : "simulated agent"}</span>
            <Link href={`/story/${run.id}`} className="text-xs text-orange hover:underline">Simple view</Link>
            {run.parent_run_id && (
              <Link href={`/compare?a=${run.parent_run_id}&b=${run.id}`} className="text-xs text-orange hover:underline">
                Fork of {shortId(run.parent_run_id)} at step {run.fork_step_idx}
              </Link>
            )}
          </div>
          <p className="mt-1 line-clamp-1 text-sm text-dim" title={run.task_text}>{run.task_text}</p>
          {run.status !== "running" && (
            <p className={cn("mt-0.5 text-sm", failed ? "text-fail" : "text-success")}>
              {failed ? "Failed: " : "Passed: "}
              <span className="text-foreground/90">{run.outcome_detail}</span>
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Button onClick={diagnose} disabled={!!busy || run.status === "running"} variant={diag ? "outline" : "default"}>
            {busy === "diagnose" ? <Loader2 className="animate-spin" /> : <Crosshair />} Diagnose
          </Button>
          <ActionButton tip="Re-execute from the selected step without changes" onClick={replay} busy={busy === "replay"} disabled={!!busy || selected === null || run.status === "running"} icon={<RotateCcw />}>
            Replay from here
          </ActionButton>
          <ActionButton tip="Edit the selected step and re-run only what follows" onClick={() => setForkOpen(true)} disabled={!!busy || selected === null || run.status === "running"} icon={<GitBranch />}>
            Fork and fix
          </ActionButton>
          <ActionButton tip="Repair the selected step from evidence in the trace, then fork" onClick={() => autofix()} busy={busy === "autofix"} disabled={!!busy || run.status === "running"} icon={<Wand2 />}>
            Auto-fix
          </ActionButton>
          <ActionButton tip="Fork at each of the top 3 blamed steps with auto-fix and see which flips the outcome" onClick={doSweep} busy={busy === "sweep"} disabled={!!busy || run.status === "running"} icon={<Sparkles />}>
            Multiverse sweep
          </ActionButton>
          <ActionButton tip="Recompute the hash chain over every stored step" onClick={doVerify} busy={busy === "verify"} disabled={!!busy} icon={verify ? (verify.valid ? <ShieldCheck className="text-success" /> : <ShieldX className="text-fail" />) : <ShieldCheck />}>
            {verify ? (verify.valid ? "Integrity verified" : `Tampered at step ${verify.broken_at}`) : "Verify integrity"}
          </ActionButton>
        </div>
      </header>

      {demo && (
        <DemoCoach
          step={demoStep}
          busy={!!busy}
          action={demoStep === 1 ? "Diagnose" : demoStep === 2 ? "Show me the proof" : demoStep === 3 ? `Auto-fix step ${canon}` : undefined}
          onAction={demoStep === 1 ? diagnose : demoStep === 2 ? () => setDemoStep(3) : demoStep === 3 ? () => autofix(canon ?? undefined) : undefined}
        >
          {demoStep === 1 && <>This refund failed at the very end. Ask the trained model which earlier step actually caused it.</>}
          {demoStep === 2 && <>The model blames step {canon}. The tape shows blame per step; the panel on the right lists the evidence and what drove the score.</>}
          {demoStep === 3 && <>Don&apos;t take the model&apos;s word for it. Fork the run at step {canon}, repair just that step, and re-run only what follows.</>}
        </DemoCoach>
      )}

      {diag && (
        <CanonBanner diag={diag} runFailed={failed} onApply={() => autofix(diag.canon_event.idx)} busy={busy === "autofix"} onReport={openReport} reportBusy={busy === "report"} />
      )}

      {sweep && <SweepStrip sweep={sweep} runId={id} demo={demo} />}

      <div className="grid min-h-[560px] flex-1 gap-3 lg:min-h-0 lg:grid-cols-[290px_minmax(0,1fr)_370px]">
        <Panel title={<span className="flex items-center gap-2">Tape <span className="font-normal text-dim">{run.steps.length} steps</span></span>}
          action={diag ? <span className="text-xs text-dim">blame</span> : null}>
          <Tape steps={run.steps} blame={blame} canon={canon} injected={injected} selected={selected} onSelect={setSelected} />
        </Panel>
        <Panel title="Execution graph" className="min-h-[420px]" action={<span className="text-xs text-dim">dashed lines show where values flow</span>}>
          <ExecGraph steps={run.steps} edges={run.edges} blame={blame} canon={canon} selected={selected} injected={injected} onSelect={setSelected} />
        </Panel>
        <Panel title="Step inspector">
          <Inspector runId={id} step={step} rank={rank} diagnosed={!!diag} tab={tab} onTab={setTab} />
        </Panel>
      </div>

      <ForkDrawer
        open={forkOpen}
        onOpenChange={setForkOpen}
        runId={id}
        step={step}
        meta={meta.data}
        onForked={() => runQ.reload()}
      />

      <Dialog open={reportOpen} onOpenChange={setReportOpen}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle className="font-heading">Incident report</DialogTitle>
            <DialogDescription>
              Written from the model&apos;s ranking and the evidence above
              {diag?.report_source === "template" ? " (template: Gemini is not configured)" : ""}.
            </DialogDescription>
          </DialogHeader>
          {report ? <Markdown text={report} /> : <Loading />}
        </DialogContent>
      </Dialog>
    </main>
  )
}

function ActionButton({ children, tip, icon, busy, ...props }: {
  children: React.ReactNode
  tip: string
  icon: React.ReactNode
  busy?: boolean
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <Tooltip>
      <TooltipTrigger render={<Button variant="outline" {...props} />}>
        {busy ? <Loader2 className="animate-spin" /> : icon}
        {children}
      </TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  )
}

function CanonBanner({ diag, runFailed, onApply, busy, onReport, reportBusy }: {
  diag: Diagnosis
  runFailed: boolean
  onApply: () => void
  busy: boolean
  onReport: () => void
  reportBusy: boolean
}) {
  const ce = diag.canon_event
  const gt = diag.ground_truth
  const hit = gt ? gt.step === ce.idx : null
  return (
    <section className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-orange/40 bg-card px-4 py-2.5" aria-live="polite">
      <CanonBadge />
      <div className="min-w-0 flex-1">
        <p className="text-sm">
          <span className="font-heading font-semibold">Step {ce.idx}</span>
          {!ce.headline.startsWith(ce.name) && <span className="ml-2 font-mono text-xs text-dim">{ce.name}</span>}
          <span className="ml-2 text-foreground/90">{ce.headline}</span>
        </p>
        {!runFailed && <p className="text-xs text-dim">This run succeeded, so this is only the step the model trusts least.</p>}
        {diag.suggested_fix && runFailed && (
          <p className="mt-0.5 text-xs text-dim">Suggested fix: {diag.suggested_fix.explanation}</p>
        )}
      </div>
      <div className="flex items-center gap-3">
        <div className="text-right">
          <div className="font-heading text-2xl font-semibold leading-none tabular-nums text-orange">{pct(ce.prob)}</div>
          <div className="text-[11px] text-dim">blame</div>
        </div>
        {gt && (
          <div className={cn("rounded-md border px-2 py-1 text-xs", hit ? "border-success/40 text-success" : "border-fail/40 text-fail")}
            title="The step where the fault was injected (ground truth, never shown to the model)">
            <span className="flex items-center gap-1">
              {hit ? <Check className="size-3.5" /> : <X className="size-3.5" />}
              Injected at step {gt.step}
            </span>
            <span className="block text-dim">{label(FAULT_LABEL, gt.type)}</span>
          </div>
        )}
        <Button variant="outline" size="sm" onClick={onReport} disabled={reportBusy}>
          {reportBusy ? <Loader2 className="animate-spin" /> : <FileText />} Incident report
        </Button>
        {diag.suggested_fix && runFailed && (
          <Button size="sm" onClick={onApply} disabled={busy}>
            {busy ? <Loader2 className="animate-spin" /> : <Wand2 />} Apply fix and prove it
          </Button>
        )}
      </div>
    </section>
  )
}

function SweepStrip({ sweep, runId, demo }: { sweep: SweepResult; runId: string; demo: boolean }) {
  return (
    <section className="rounded-lg border bg-card px-4 py-2.5">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-sm font-medium">Multiverse sweep</h2>
        <p className="text-xs text-dim">
          {sweep.confirmed_step !== null
            ? `Fixing step ${sweep.confirmed_step} flips the outcome: Canon Event confirmed.`
            : "No single repaired step flipped the outcome."}
        </p>
      </div>
      <ol className="grid gap-2 md:grid-cols-3">
        {sweep.universes.map((u) => (
          <li key={u.step} className={cn("rounded-md border px-3 py-2 text-xs", u.step === sweep.confirmed_step ? "border-orange/60 bg-orange/[0.06]" : "bg-background")}>
            <div className="flex items-center justify-between gap-2">
              <span>
                <span className="text-dim">Universe {u.rank}</span>
                <span className="ml-2 font-mono text-foreground">step {u.step} {u.name}</span>
              </span>
              <span className="font-mono text-dim">{pct(u.prob)}</span>
            </div>
            <p className="mt-1 line-clamp-2 text-dim">{u.fix ? u.fix.explanation : u.note}</p>
            <div className="mt-1.5 flex items-center justify-between">
              {u.status ? <StatusBadge status={u.status} /> : <span className="text-dim">not forked</span>}
              {u.fork_id && (
                <Link href={`/compare?a=${runId}&b=${u.fork_id}${demo ? "&demo=1" : ""}`} className="text-orange hover:underline">
                  Compare
                </Link>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
