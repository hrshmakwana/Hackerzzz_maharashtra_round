"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useState } from "react"

import { api, type Health } from "@/lib/api"
import { cn } from "@/lib/utils"

const NAV = [
  { href: "/", label: "Home" },
  { href: "/runs", label: "All runs" },
  { href: "/lab", label: "Model Lab" },
  { href: "/live", label: "Try it live" },
]

export function TopBar() {
  const path = usePathname()
  const [health, setHealth] = useState<Health | null>(null)
  const [down, setDown] = useState(false)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const h = await api<Health>("/health")
        if (alive) {
          setHealth(h)
          setDown(false)
        }
      } catch {
        if (alive) setDown(true)
      }
    }
    tick()
    const t = setInterval(tick, 15000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-12 max-w-[1600px] items-center gap-6 px-4">
        <Link href="/" className="flex items-center gap-2.5" aria-label="Black Box home">
          <span className="grid size-6 place-items-center rounded-[5px] bg-orange font-mono text-[10px] font-bold leading-none text-black">
            BB
          </span>
          <span className="font-heading text-[15px] font-semibold tracking-tight">Black Box</span>
          <span className="hidden text-xs text-dim lg:inline">Record → Blame → Fork → Prove</span>
        </Link>
        <nav className="flex items-center gap-1">
          {NAV.map((n) => {
            const active = n.href === "/" ? path === "/" || path.startsWith("/story")
              : n.href === "/runs" ? path.startsWith("/runs") || path.startsWith("/compare")
              : path.startsWith(n.href)
            return (
              <Link
                key={n.href}
                href={n.href}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-sm text-dim transition-colors hover:text-foreground",
                  active && "bg-surface-2 text-foreground",
                )}
              >
                {n.label}
              </Link>
            )
          })}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-xs text-dim">
          {down ? (
            <span className="flex items-center gap-1.5 text-fail">
              <span className="size-1.5 rounded-full bg-fail" /> API offline
            </span>
          ) : health ? (
            <>
              {health.seeding && <span className="text-orange">Seeding runs…</span>}
              <span className="hidden md:inline" title="Gemini is used for live runs and incident reports">
                Gemini {health.gemini ? "on" : "off"}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-success" />
                <span className="font-mono">{health.model ?? "no model"}</span>
              </span>
            </>
          ) : null}
        </div>
      </div>
    </header>
  )
}
