"use client"

import { Play, Search, Sparkles } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useMemo, useState } from "react"

import { Empty, ErrorNote, Loading, Mono, Panel, Readouts, StatusBadge } from "@/components/bits"
import { HBars } from "@/components/charts"
import { Button } from "@/components/ui/button"
import { NativeSelect, Segmented } from "@/components/controls"
import { Input } from "@/components/ui/input"
import type { DemoRun, Meta, RunSummary, Stats } from "@/lib/api"
import { FAMILY_LABEL, FAULT_LABEL, SPLIT_LABEL, int, label, pct, shortId, timeAgo } from "@/lib/format"
import { useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

const PAGE = 40

export default function AllRuns() {
  const router = useRouter()
  const stats = useApi<Stats>("/stats")
  const meta = useApi<Meta>("/meta")
  const demo = useApi<{ runs: DemoRun[] }>("/demo")

  const [status, setStatus] = useState("fail")
  const [family, setFamily] = useState("")
  const [split, setSplit] = useState("")
  const [fault, setFault] = useState("")
  const [q, setQ] = useState("")
  const [limit, setLimit] = useState(PAGE)

  const path = useMemo(() => {
    const p = new URLSearchParams({ limit: String(limit), forks: "false" })
    if (status) p.set("status", status)
    if (family) p.set("family", family)
    if (split) p.set("split", split)
    if (fault) p.set("fault_type", fault)
    if (q.trim()) p.set("q", q.trim())
    return `/runs?${p}`
  }, [status, family, split, fault, q, limit])
  const runs = useApi<{ items: RunSummary[]; total: number }>(path)

  const s = stats.data
  const heldout = new Set(meta.data?.heldout_fault_types ?? [])
  const faultBars = s
    ? Object.entries(s.by_fault_type)
        .filter(([k]) => k !== "None")
        .sort((a, b) => b[1] - a[1])
        .map(([k, v]) => ({
          label: label(FAULT_LABEL, k) + (heldout.has(k) ? " *" : ""),
          value: v,
          note: heldout.has(k) ? "held out of training" : undefined,
        }))
    : []

  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-5">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl font-semibold tracking-tight">All runs</h1>
          <p className="text-sm text-dim">Every recorded agent run, with the technical view. Open a failed one to find the step that caused it.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => router.push("/runs/hero-refund-stale-policy?demo=1")}>
            <Sparkles /> Demo mode
          </Button>
          <Button onClick={() => router.push("/live")}>
            <Play /> Start live run
          </Button>
        </div>
      </div>

      {stats.error ? (
        <ErrorNote message={stats.error} onRetry={stats.reload} className="rounded-lg border bg-card" />
      ) : (
        <Readouts
          className="mb-4"
          items={[
            { label: "Runs recorded", value: s ? int(s.runs) : "—", hint: s?.dataset_runs ? `${int(s.dataset_runs)} in the training dataset` : undefined },
            { label: "Failure rate", value: s ? pct(s.fail_rate) : "—", hint: s ? `${int(s.by_status.fail)} failed runs` : undefined },
            { label: "Canon Event found first try", value: s ? pct(s.top1_test) : "—", hint: s?.top3_test != null ? `${pct(s.top3_test)} within the top 3 (test split)` : undefined, accent: true },
            { label: "Steps reused per fork", value: s ? pct(s.avg_steps_reused) : "—", hint: s ? `${int(s.forks)} forks · ${int(s.fork_flips)} turned fail into success` : undefined },
          ]}
        />
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Panel
          title={
            <span className="flex items-center gap-2">
              Runs
              {runs.data && <span className="font-normal text-dim">{int(runs.data.total)}</span>}
            </span>
          }
          action={
            <div className="flex flex-wrap items-center gap-2">
              <Segmented
                value={status}
                onChange={(v) => { setStatus(v); setLimit(PAGE) }}
                options={[{ value: "fail", label: "Failed" }, { value: "success", label: "Succeeded" }, { value: "", label: "All" }]}
              />
              <NativeSelect value={family} onChange={(v) => { setFamily(v); setLimit(PAGE) }} placeholder="All tasks"
                options={(meta.data?.families ?? []).map((f) => ({ value: f, label: label(FAMILY_LABEL, f) }))} />
              <NativeSelect value={fault} onChange={(v) => { setFault(v); setLimit(PAGE) }} placeholder="Any injected fault"
                options={(meta.data?.fault_types ?? []).map((f) => ({ value: f, label: label(FAULT_LABEL, f) }))} />
              <NativeSelect value={split} onChange={(v) => { setSplit(v); setLimit(PAGE) }} placeholder="All splits"
                options={["train", "val", "test", "heldout_type", "heldout_family", "live"].map((x) => ({ value: x, label: label(SPLIT_LABEL, x) }))} />
              <div className="relative">
                <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-dim" />
                <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Run id or text" className="h-8 w-40 pl-7" />
              </div>
            </div>
          }
        >
          {runs.error ? (
            <ErrorNote message={runs.error} onRetry={runs.reload} />
          ) : !runs.data && runs.loading ? (
            <Loading />
          ) : runs.data && runs.data.items.length === 0 ? (
            <Empty>No runs match these filters. Clear a filter, or run <Mono>make data</Mono> to generate the dataset.</Empty>
          ) : (
            <RunsTable runs={runs.data?.items ?? []} />
          )}
          {runs.data && runs.data.items.length < runs.data.total && (
            <div className="border-t p-2 text-center">
              <Button variant="ghost" size="sm" onClick={() => setLimit(limit + PAGE)} disabled={runs.loading}>
                Show {Math.min(PAGE, runs.data.total - runs.data.items.length)} more
              </Button>
            </div>
          )}
        </Panel>

        <div className="flex flex-col gap-4">
          <Panel title="Demo flights">
            {demo.error ? (
              <ErrorNote message={demo.error} />
            ) : !demo.data ? (
              <Loading />
            ) : (
              <ol className="divide-y">
                {demo.data.runs.map((d) => (
                  <li key={d.id}>
                    <Link href={d.available ? `/story/${d.id}` : "#"} className={cn("block px-3.5 py-3 transition-colors hover:bg-surface-2", !d.available && "pointer-events-none opacity-50")}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium">{d.title}</span>
                        <StatusBadge status={d.status} />
                      </div>
                      <p className="mt-1 text-xs leading-relaxed text-dim">{d.story}</p>
                    </Link>
                  </li>
                ))}
              </ol>
            )}
          </Panel>
          <Panel title="Failed runs by injected fault" bodyClassName="px-3 py-3">
            {stats.error ? (
              <ErrorNote message={stats.error} />
            ) : !s ? (
              <Loading />
            ) : faultBars.length === 0 ? (
              <Empty>No failed runs yet.</Empty>
            ) : (
              <>
                <HBars data={faultBars} labelWidth={140} format={(v) => int(v)} ariaLabel="Number of failed runs per injected fault type" />
                <p className="mt-2 text-xs text-dim">* never shown to the model during training</p>
              </>
            )}
          </Panel>
        </div>
      </div>
    </main>
  )
}

function RunsTable({ runs }: { runs: RunSummary[] }) {
  const router = useRouter()
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-dim">
            <th className="px-3.5 py-2 font-normal">Run</th>
            <th className="px-2 py-2 font-normal">Outcome</th>
            <th className="px-2 py-2 text-right font-normal">Steps</th>
            <th className="px-2 py-2 font-normal">Split</th>
            <th className="px-2 py-2 font-normal">Injected fault</th>
            <th className="px-3.5 py-2 text-right font-normal">Recorded</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr
              key={r.id}
              onClick={() => router.push(`/runs/${r.id}`)}
              className="cursor-pointer border-b border-border/60 transition-colors last:border-0 hover:bg-surface-2"
            >
              <td className="px-3.5 py-2">
                <Link href={`/runs/${r.id}`} className="block" onClick={(e) => e.stopPropagation()}>
                  <span className="text-foreground">{label(FAMILY_LABEL, r.task_family)}</span>
                  <span className="ml-2 font-mono text-xs text-dim">{shortId(r.id)}</span>
                </Link>
              </td>
              <td className="max-w-[360px] px-2 py-2">
                <div className="flex items-center gap-2">
                  <StatusBadge status={r.status} />
                  <span className="truncate text-xs text-dim" title={r.outcome_detail}>
                    {r.status === "fail" ? r.outcome_detail : ""}
                  </span>
                </div>
              </td>
              <td className="px-2 py-2 text-right font-mono text-xs tabular-nums">{r.n_steps}</td>
              <td className="px-2 py-2 text-xs text-dim">{label(SPLIT_LABEL, r.split)}</td>
              <td className="px-2 py-2 text-xs text-dim">
                {r.fault_type ? `${label(FAULT_LABEL, r.fault_type)} at step ${r.fault_step}` : "—"}
              </td>
              <td className="px-3.5 py-2 text-right text-xs whitespace-nowrap text-dim">{timeAgo(r.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
