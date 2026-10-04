import { ChevronRight } from "lucide-react"
import Link from "next/link"

import { StatusPill } from "@/components/kit"
import type { RunSummary } from "@/lib/api"
import { timeAgo } from "@/lib/format"
import { TASK_SHORT, capital } from "@/lib/plain"

export function RunRows({ runs }: { runs: RunSummary[] }) {
  if (!runs.length) return <p className="mt-6 rounded-lg border bg-surface px-5 py-10 text-center text-sm text-dim">No runs yet.</p>
  return (
    <ul className="mt-6 divide-y divide-line/60 rounded-lg border bg-surface">
      {runs.map((r) => (
        <li key={r.id}>
          <Link href={`/runs/${r.id}`} className="flex items-center gap-4 px-4 py-4 transition-colors hover:bg-raised sm:px-5">
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{TASK_SHORT[r.task_family] ?? r.task_family}</p>
              <p className="truncate text-sm text-dim">
                {r.status === "fail" ? capital(r.outcome_detail) : r.status === "success" ? "All checks passed" : "In progress"}
              </p>
            </div>
            <StatusPill status={r.status} className="hidden sm:inline-flex" />
            <span className="hidden w-20 text-right text-sm text-dim md:inline">{timeAgo(r.created_at)}</span>
            <ChevronRight className="size-4 shrink-0 text-dim" aria-hidden />
          </Link>
        </li>
      ))}
    </ul>
  )
}
