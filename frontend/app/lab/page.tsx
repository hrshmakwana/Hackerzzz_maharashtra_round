"use client"

import { useRouter, useSearchParams } from "next/navigation"
import { Suspense, useState } from "react"

import { ErrorNote, Loading, Panel, Readouts } from "@/components/bits"
import { HBars } from "@/components/charts"
import { Segmented } from "@/components/controls"
import { DemoCoach } from "@/components/demo-coach"
import type { Metrics } from "@/lib/api"
import { FAULT_LABEL, METHOD_LABEL, SPLIT_LABEL, int, label, pct } from "@/lib/format"
import { useApi } from "@/lib/use-api"

const METHODS = ["model", "llm_judge", "first_error", "last_step", "random"]
const SPLITS = ["test", "heldout_family", "heldout_type", "val", "live"]

export default function LabPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Lab />
    </Suspense>
  )
}

function Lab() {
  const router = useRouter()
  const demo = useSearchParams().get("demo") === "1"
  const { data: m, error, reload } = useApi<Metrics & { feature_importance_full: { feature: string; gain: number }[] }>("/eval")
  const [split, setSplit] = useState("test")

  if (error) return <ErrorNote message={error} onRetry={reload} className="flex-1" />
  if (!m) return <Loading label="Loading evaluation…" className="flex-1" />

  const splits = SPLITS.filter((s) => m.splits[s])
  const model = (s: string) => m.splits[s]?.methods.model
  const best = (s: string) =>
    Math.max(...METHODS.filter((x) => x !== "model").map((x) => m.splits[s]?.methods[x]?.n ? m.splits[s].methods[x].top1 : 0))
  const types = m.splits.heldout_type?.methods.model.per_type_top1 ?? {}
  const sel = m.splits[split]
  const replay = m.replay?.splits ?? {}

  return (
    <main className="mx-auto flex w-full max-w-[1400px] flex-col gap-4 px-4 py-4">
      <header>
        <h1 className="font-heading text-2xl font-semibold tracking-tight">Model Lab</h1>
        <p className="text-sm text-dim">
          How often the ranker puts the true faulty step first, against the obvious alternatives. Every number here is
          written by <span className="font-mono">make eval</span>.
        </p>
      </header>

      {demo && (
        <DemoCoach step={5} action="Finish" onAction={() => router.push("/")}>
          The model was trained on four task types and seven fault types. On a task type and two fault types it never
          saw, it still finds the cause, and the multiverse sweep confirms it.
        </DemoCoach>
      )}

      <Readouts
        items={[
          { label: "Test: Canon Event ranked first", value: pct(model("test")?.top1, 1), hint: `best baseline ${pct(best("test"), 1)}`, accent: true },
          { label: "Unseen task type: ranked first", value: pct(model("heldout_family")?.top1, 1), hint: `${pct(model("heldout_family")?.top3, 1)} within the top 3` },
          { label: "Unseen fault types: within top 3", value: pct(model("heldout_type")?.top3, 1), hint: `${pct(model("heldout_type")?.top1, 1)} ranked first` },
          { label: "Auto-fix flips the outcome", value: pct(replay.test?.flip_rate_top1, 0), hint: `sweep over top 3 on unseen faults: ${pct(replay.heldout_type?.flip_rate_sweep, 0)}` },
        ]}
      />

      <Panel title="Ranked first, by split" bodyClassName="grid gap-x-6 gap-y-4 p-4 md:grid-cols-2 xl:grid-cols-4">
        {splits.filter((s) => s !== "val").map((s) => (
          <div key={s}>
            <h3 className="text-sm font-medium">{m.splits[s].label}</h3>
            <p className="mb-2 text-xs text-dim">{int(m.splits[s].failed_with_label)} failed runs</p>
            <HBars
              ariaLabel={`Top-1 accuracy per method on ${m.splits[s].label}`}
              labelWidth={118}
              max={1}
              format={(v) => pct(v)}
              data={METHODS.filter((x) => m.splits[s].methods[x]?.n).map((x) => ({
                label: label(METHOD_LABEL, x),
                value: m.splits[s].methods[x].top1,
                highlight: x === "model",
                note: x === "llm_judge" ? `${m.splits[s].methods[x].n} runs sampled` : undefined,
              }))}
            />
          </div>
        ))}
      </Panel>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <Panel
          title="All metrics"
          action={<Segmented value={split} onChange={setSplit} options={splits.map((s) => ({ value: s, label: label(SPLIT_LABEL, s) }))} />}
        >
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-dim">
                <th className="px-4 py-2 font-normal">Method</th>
                <th className="px-2 py-2 text-right font-normal">Runs</th>
                <th className="px-2 py-2 text-right font-normal">Top-1</th>
                <th className="px-2 py-2 text-right font-normal">Top-3</th>
                <th className="px-2 py-2 text-right font-normal">MRR</th>
                <th className="px-4 py-2 text-right font-normal">Steps off</th>
              </tr>
            </thead>
            <tbody>
              {METHODS.filter((x) => sel?.methods[x]?.n).map((x) => {
                const r = sel.methods[x]
                return (
                  <tr key={x} className="border-b border-border/50 last:border-0">
                    <td className="px-4 py-2">
                      <span className="flex items-center gap-2">
                        <span className="size-2 rounded-full" style={{ background: x === "model" ? "#FF6A13" : "#7C7C88" }} />
                        {label(METHOD_LABEL, x)}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-right font-mono text-xs tabular-nums text-dim">{int(r.n)}</td>
                    <td className="px-2 py-2 text-right font-mono tabular-nums">{pct(r.top1, 1)}</td>
                    <td className="px-2 py-2 text-right font-mono tabular-nums">{pct(r.top3, 1)}</td>
                    <td className="px-2 py-2 text-right font-mono tabular-nums">{r.mrr.toFixed(3)}</td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums">{r.mean_step_distance.toFixed(2)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="border-t px-4 py-2 text-xs text-dim">
            Last action blames the final tool call, where the failure shows. First error blames the first failed call.
            {m.judge_runs ? ` Gemini as judge reads the whole trace (${m.judge_runs} cached runs).` : ""}
          </p>
        </Panel>

        <Panel title={`By fault type: ${label(SPLIT_LABEL, split)}`} bodyClassName="p-4">
          {sel?.methods.model.per_type_top1 && Object.keys(sel.methods.model.per_type_top1).length ? (
            <HBars
              ariaLabel="Top-1 accuracy of the ranker per fault type"
              labelWidth={130}
              max={1}
              format={(v) => pct(v)}
              data={Object.entries(sel.methods.model.per_type_top1)
                .sort((x, y) => y[1].top1 - x[1].top1)
                .map(([t, v]) => ({ label: label(FAULT_LABEL, t), value: v.top1, highlight: true, note: `${v.n} runs` }))}
            />
          ) : (
            <p className="text-sm text-dim">No labelled failures in this split.</p>
          )}
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="What the model learned to look at" bodyClassName="p-4">
          <HBars
            ariaLabel="Feature importance by total gain"
            labelWidth={170}
            format={(v) => int(v)}
            data={m.feature_importance.slice(0, 12).map((f) => ({ label: f.feature.replace(/_/g, " "), value: f.gain, highlight: true }))}
          />
        </Panel>
        <Panel title="Generalisation, honestly" bodyClassName="space-y-3 p-4 text-sm leading-relaxed">
          <p>
            <span className="font-medium">Unseen task type.</span> Complaint triage never appeared in training. The
            ranker still puts the cause first in {pct(model("heldout_family")?.top1, 1)} of failed runs.
          </p>
          {types.state_corruption && (
            <p>
              <span className="font-medium">Unseen fault: state corruption.</span> {pct(types.state_corruption.top1, 1)} ranked
              first. Overwritten memory contradicts what the tools reported, a signal the model learned from other faults.
            </p>
          )}
          {types.prompt_injection && (
            <p>
              <span className="font-medium">Unseen fault: prompt injection.</span> Only {pct(types.prompt_injection.top1, 1)} ranked
              first. The bad values arrive inside a real email, so they look grounded. The step is usually in the top 3, and
              the multiverse sweep confirms it causally in {pct(replay.heldout_type?.flip_rate_sweep, 0)} of runs.
            </p>
          )}
          <p className="text-dim">
            Runs per split: {splits.map((s) => `${label(SPLIT_LABEL, s)} ${int(m.splits[s].failed_with_label)}`).join(", ")}.
            Failure classifier AUROC on test: {m.auroc.test?.toFixed(3) ?? "—"}.
          </p>
        </Panel>
      </div>

      {m.replay && (
        <Panel title="Fork, fix, prove" bodyClassName="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-dim">
                <th className="px-4 py-2 font-normal">Split</th>
                <th className="px-2 py-2 text-right font-normal">Auto-fix at top 1 flips</th>
                <th className="px-2 py-2 text-right font-normal">Sweep over top 3 flips</th>
                <th className="px-2 py-2 text-right font-normal">Confirmed step is the true cause</th>
                <th className="px-2 py-2 text-right font-normal">Steps reused</th>
                <th className="px-4 py-2 text-right font-normal">Tokens saved per fork</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(m.replay.splits).map(([s, v]) => (
                <tr key={s} className="border-b border-border/50 last:border-0">
                  <td className="px-4 py-2">{label(SPLIT_LABEL, s)}</td>
                  <td className="px-2 py-2 text-right font-mono tabular-nums">{pct(v.flip_rate_top1)}</td>
                  <td className="px-2 py-2 text-right font-mono tabular-nums">{pct(v.flip_rate_sweep)}</td>
                  <td className="px-2 py-2 text-right font-mono tabular-nums">{pct(v.confirmed_precision)}</td>
                  <td className="px-2 py-2 text-right font-mono tabular-nums">{pct(v.avg_reused_frac)}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">{int(v.avg_tokens_saved)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </main>
  )
}
