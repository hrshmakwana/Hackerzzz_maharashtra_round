"use client"

import { Check, GitFork, Loader2, Minus, X } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { btnSecondary } from "@/components/kit"
import { post, type SweepResult } from "@/lib/api"
import { cn } from "@/lib/utils"

/** Fix each of the top suspects in its own replay. Only the true cause flips the outcome. */
export function Universes({ runId, labelFor, describe }: {
  runId: string
  labelFor: (idx: number) => string
  describe: (idx: number) => string
}) {
  const [data, setData] = useState<SweepResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      setData(await post<SweepResult>(`/runs/${runId}/sweep?top_k=3`))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="mt-12">
      <h2 className="text-lg font-medium">Parallel universes</h2>
      <p className="mt-1 text-sm leading-6 text-dim">
        What if we had fixed a different step instead? Black Box replays the run three times, fixing a different
        suspect each time. If only one universe comes out right, that step decided the outcome: the Canon Event.
      </p>

      {!data && (
        <button onClick={run} disabled={busy} className={cn(btnSecondary, "mt-4 w-full sm:w-auto")}>
          {busy ? <Loader2 className="size-4 animate-spin" /> : <GitFork className="size-4" />}
          {busy ? "Replaying three universes…" : "Try fixing the other suspects"}
        </button>
      )}
      {error && <p className="mt-3 text-sm text-fail">{error}</p>}

      {data && (
        <>
          <ol className="mt-5 grid gap-3 md:grid-cols-3">
            {[...data.universes].sort((a, b) => a.step - b.step).map((u, i) => {
              const canon = u.step === data.confirmed_step
              const result = u.status === null ? "none" : u.flipped ? "right" : "wrong"
              const unchanged = !u.fix
              return (
                <li
                  key={u.step}
                  className={cn("rise flex flex-col rounded-lg border bg-surface p-5", canon && "root-glow border-orange")}
                  style={{ animationDelay: `${i * 120}ms` }}
                >
                  <p className="text-xs text-dim">Universe {i + 1}</p>
                  <p className="mt-2 text-sm font-medium">{unchanged ? "Replay" : "Fix"} {labelFor(u.step)}</p>
                  <p className="mt-1 flex-1 text-sm leading-6 text-dim">{describe(u.step)}</p>
                  <p
                    className={cn(
                      "mt-4 flex items-center gap-1.5 text-sm font-medium",
                      result === "right" ? "text-success" : result === "wrong" ? "text-fail" : "text-dim",
                    )}
                  >
                    {result === "right" ? <Check className="size-4" /> : result === "wrong" ? <X className="size-4" /> : <Minus className="size-4" />}
                    {result === "right" ? "Comes out right" : result === "wrong" ? "Still wrong" : "Nothing to fix here"}
                  </p>
                  {unchanged && result !== "none" && (
                    <p className="mt-1 text-xs text-dim">Nothing looked wrong here, so it was replayed as it was.</p>
                  )}
                  {canon && <p className="mt-1 text-xs font-medium text-orange">Canon Event</p>}
                  {u.fork_id && result !== "none" && (
                    <Link href={`/runs/${u.fork_id}`} className="mt-2 text-xs text-dim hover:text-ink">
                      Open this universe
                    </Link>
                  )}
                </li>
              )
            })}
          </ol>
          <p className="mt-4 text-sm text-dim">
            {data.confirmed_step !== null
              ? `Only fixing ${labelFor(data.confirmed_step)} changes the ending. That is the proof the model picked the real cause.`
              : "None of these single fixes changed the ending."}
          </p>
        </>
      )}
    </section>
  )
}
