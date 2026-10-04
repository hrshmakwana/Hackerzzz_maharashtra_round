"use client"

import { Crosshair, Dice5, Loader2, Play, Square } from "lucide-react"
import Link from "next/link"
import { useEffect, useRef, useState } from "react"

import { CanonBadge, Empty, ErrorNote, KindDot, Panel, StatusBadge } from "@/components/bits"
import { NativeSelect, Segmented } from "@/components/controls"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { API_URL, api, post, type Meta, type Run, type Step } from "@/lib/api"
import { FAMILY_LABEL, FAULT_LABEL, label, ms, stepSummary } from "@/lib/format"
import { useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

type Phase = "idle" | "starting" | "streaming" | "done"

export default function MissionControl() {
  const meta = useApi<Meta>("/meta")
  const [family, setFamily] = useState("refund")
  const [fault, setFault] = useState("bad_retrieval")
  const [seed, setSeed] = useState(() => String(Math.floor(Math.random() * 100000)))
  const [speed, setSpeed] = useState("350")
  const [phase, setPhase] = useState<Phase>("idle")
  const [runId, setRunId] = useState<string | null>(null)
  const [injectedAt, setInjectedAt] = useState<number | null>(null)
  const [steps, setSteps] = useState<Step[]>([])
  const [final, setFinal] = useState<Run | null>(null)
  const [error, setError] = useState<string | null>(null)
  const source = useRef<EventSource | null>(null)
  const tail = useRef<HTMLOListElement>(null)

  useEffect(() => () => source.current?.close(), [])
  useEffect(() => {
    tail.current?.lastElementChild?.scrollIntoView({ block: "nearest" })
  }, [steps.length])

  const start = async () => {
    source.current?.close()
    setSteps([])
    setFinal(null)
    setError(null)
    setPhase("starting")
    try {
      const r = await post<{ id: string; fault: { step: number } | null }>("/runs", {
        family,
        seed: Number(seed) || 0,
        policy: "sim",
        fault: fault ? { type: fault } : null,
        delay_ms: Number(speed),
      })
      setRunId(r.id)
      setInjectedAt(r.fault?.step ?? null)
      setPhase("streaming")
      const es = new EventSource(`${API_URL}/runs/${r.id}/stream`)
      source.current = es
      es.addEventListener("step", (e) => {
        const s = JSON.parse((e as MessageEvent).data) as Step
        setSteps((prev) => (prev.some((p) => p.idx === s.idx) ? prev : [...prev, s]))
      })
      es.addEventListener("done", async () => {
        es.close()
        // the API diagnoses failed runs on its own; give it a moment
        for (let i = 0; i < 12; i++) {
          const run = await api<Run>(`/runs/${r.id}`).catch(() => null)
          if (run && (run.status !== "fail" || run.diagnosis)) {
            setFinal(run)
            break
          }
          await new Promise((res) => setTimeout(res, 400))
        }
        setPhase("done")
      })
      es.onerror = () => {
        es.close()
        setError("Lost the live stream. The run may still be going; open it in the Flight Deck.")
        setPhase("done")
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setPhase("idle")
    }
  }

  const stop = () => {
    source.current?.close()
    setPhase("done")
  }

  const diag = final?.diagnosis
  const busy = phase === "starting" || phase === "streaming"

  return (
    <main className="mx-auto grid w-full max-w-[1400px] flex-1 gap-4 px-4 py-4 lg:grid-cols-[340px_minmax(0,1fr)]">
      <div className="flex flex-col gap-4">
        <header>
          <h1 className="font-heading text-2xl font-semibold tracking-tight">Mission Control</h1>
          <p className="text-sm text-dim">Launch an agent run, watch every step get recorded, and see it diagnosed the moment it fails.</p>
        </header>
        <Panel title="New run" bodyClassName="flex flex-col gap-4 p-4">
          <Field label="Task">
            <NativeSelect value={family} onChange={setFamily} className="w-full"
              options={(meta.data?.families ?? ["refund"]).map((f) => ({ value: f, label: label(FAMILY_LABEL, f) }))} />
          </Field>
          <Field label="Break something on purpose" hint="One step will be corrupted; the failure usually shows up later.">
            <NativeSelect value={fault} onChange={setFault} className="w-full" placeholder="No fault (clean run)"
              options={(meta.data?.fault_types ?? []).map((f) => ({ value: f, label: label(FAULT_LABEL, f) + (meta.data?.heldout_fault_types.includes(f) ? " (never trained on)" : "") }))} />
          </Field>
          <Field label="Seed" hint="Same seed, same run: everything is deterministic.">
            <div className="flex gap-2">
              <Input value={seed} onChange={(e) => setSeed(e.target.value.replace(/\D/g, ""))} className="font-mono" inputMode="numeric" />
              <Button variant="outline" size="icon" aria-label="Random seed" onClick={() => setSeed(String(Math.floor(Math.random() * 100000)))}>
                <Dice5 />
              </Button>
            </div>
          </Field>
          <Field label="Pace">
            <Segmented value={speed} onChange={setSpeed} options={[{ value: "700", label: "Slow" }, { value: "350", label: "Normal" }, { value: "60", label: "Fast" }]} />
          </Field>
          <p className="text-xs text-dim">Agent: the seeded ShopOps support agent.</p>
          {busy ? (
            <Button variant="outline" onClick={stop}>
              <Square /> Stop watching
            </Button>
          ) : (
            <Button onClick={start}>
              <Play /> Launch run
            </Button>
          )}
          {error && <ErrorNote message={error} className="py-2" />}
        </Panel>
      </div>

      <div className="flex min-h-[560px] flex-col gap-4">
        {phase === "done" && final && (
          <section className={cn("rounded-lg border px-4 py-3", final.status === "fail" ? "border-fail/40" : "border-success/40", "bg-card")}>
            <div className="flex flex-wrap items-center gap-3">
              <StatusBadge status={final.status} />
              <span className="text-sm">{final.outcome_detail}</span>
              <Link href={`/runs/${final.id}`} className="ml-auto text-sm text-orange hover:underline">Open in Flight Deck</Link>
            </div>
            {diag && (
              <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
                <CanonBadge />
                <span>
                  <span className="font-heading font-semibold">Step {diag.canon_event.idx}</span>
                  <span className="ml-2 text-foreground/85">{diag.canon_event.headline}</span>
                </span>
                {injectedAt !== null && (
                  <span className={cn("text-xs", injectedAt === diag.canon_event.idx ? "text-success" : "text-fail")}>
                    {injectedAt === diag.canon_event.idx ? "Matches" : "Differs from"} the injected step ({injectedAt})
                  </span>
                )}
              </div>
            )}
          </section>
        )}
        <Panel
          className="flex-1"
          title={
            <span className="flex items-center gap-2">
              Live tape
              {runId && <span className="font-mono text-xs font-normal text-dim">{runId.slice(0, 8)}</span>}
              {phase === "streaming" && <Loader2 className="size-3.5 animate-spin text-orange" />}
            </span>
          }
          action={runId && phase === "done" ? (
            <Link href={`/runs/${runId}`} className="flex items-center gap-1 text-xs text-orange hover:underline">
              <Crosshair className="size-3.5" /> Diagnose in Flight Deck
            </Link>
          ) : null}
        >
          {steps.length === 0 ? (
            <Empty>{phase === "idle" ? "Pick a task and launch a run. Steps appear here as they are recorded." : "Waiting for the first step…"}</Empty>
          ) : (
            <ol ref={tail} className="max-h-[calc(100dvh-14rem)] overflow-y-auto">
              {steps.map((s) => (
                <li key={s.idx} className={cn("grid grid-cols-[34px_minmax(0,1fr)_70px] items-center gap-2 border-b border-border/50 px-4 py-2 animate-in fade-in slide-in-from-bottom-1 duration-300", diag?.canon_event.idx === s.idx && "border-l-2 border-l-orange")}>
                  <span className="font-mono text-[11px] text-dim">{String(s.idx).padStart(2, "0")}</span>
                  <span className="min-w-0">
                    <span className="flex items-center gap-1.5">
                      <KindDot kind={s.kind} />
                      <span className="font-mono text-[12px]">{s.kind === "llm" ? "llm" : s.name}</span>
                      {s.error && <span className="text-[11px] text-fail">error</span>}
                    </span>
                    <span className="block truncate text-[11px] text-dim">{stepSummary(s)}</span>
                  </span>
                  <span className="text-right font-mono text-[11px] text-dim">{ms(s.latency_ms)}</span>
                </li>
              ))}
            </ol>
          )}
        </Panel>
      </div>
    </main>
  )
}

function Field({ label: text, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm">{text}</span>
      {children}
      {hint && <span className="text-xs text-dim">{hint}</span>}
    </label>
  )
}
