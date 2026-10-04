"use client"

import { X } from "lucide-react"
import { useRouter } from "next/navigation"
import type { ReactNode } from "react"

import { Button } from "@/components/ui/button"

export const DEMO_STEPS = ["Diagnose", "Canon Event", "Auto-fix", "Multiverse view", "Model Lab"]

/** Slim guide for the five-step demo walk-through. */
export function DemoCoach({ step, children, action, onAction, busy }: {
  step: number
  children: ReactNode
  action?: string
  onAction?: () => void
  busy?: boolean
}) {
  const router = useRouter()
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-orange/40 bg-orange/[0.06] px-3.5 py-2">
      <ol className="flex items-center gap-1" aria-label="Demo progress">
        {DEMO_STEPS.map((name, i) => (
          <li
            key={name}
            title={name}
            aria-current={i + 1 === step ? "step" : undefined}
            className={`h-1.5 w-6 rounded-full ${i + 1 < step ? "bg-orange/70" : i + 1 === step ? "bg-orange" : "bg-border"}`}
          />
        ))}
      </ol>
      <span className="text-xs text-dim">
        {step} of {DEMO_STEPS.length}
      </span>
      <p className="min-w-0 flex-1 text-sm">{children}</p>
      {action && onAction && (
        <Button size="sm" onClick={onAction} disabled={busy}>
          {action}
        </Button>
      )}
      <Button variant="ghost" size="icon-sm" aria-label="Leave demo mode" onClick={() => router.replace(window.location.pathname + window.location.search.replace(/[?&]demo=1/, "").replace(/^&/, "?"))}>
        <X />
      </Button>
    </div>
  )
}
