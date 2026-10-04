"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useState } from "react"

import { api, type Health } from "@/lib/api"
import { cn } from "@/lib/utils"

const REPO = "https://github.com/hrshmakwana/Hackerzzz_maharashtra_round"

const NAV = [
  { href: "/", label: "Home" },
  { href: "/runs", label: "Runs" },
  { href: "/results", label: "Results" },
  { href: "/live", label: "Live" },
]

export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={cn("size-6", className)} aria-hidden>
      <rect x="3" y="3" width="18" height="18" rx="5" fill="#0B0B0F" stroke="#FF6A13" strokeWidth="1.8" />
      <path d="M12 7.5v9M7.5 12h9" stroke="#FF6A13" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="12" cy="12" r="2.4" fill="#FF6A13" />
    </svg>
  )
}

export function SiteHeader() {
  const path = usePathname()
  const [online, setOnline] = useState<boolean | null>(null)

  useEffect(() => {
    let alive = true
    const tick = () =>
      api<Health>("/health")
        .then(() => alive && setOnline(true))
        .catch(() => alive && setOnline(false))
    tick()
    const t = setInterval(tick, 30000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  return (
    <header className="sticky top-0 z-40 border-b bg-bg/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-5 md:gap-8 md:px-8">
        <Link href="/" className="flex shrink-0 items-center gap-2" aria-label="Black Box home">
          <Logo />
          <span className="font-heading text-[17px] font-medium tracking-tight">Black Box</span>
        </Link>
        <nav className="flex items-center gap-0.5 text-sm" aria-label="Main">
          {NAV.map((n) => {
            const active = n.href === "/" ? path === "/" : path.startsWith(n.href)
            return (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded px-2 py-1.5 text-dim transition-colors hover:text-ink sm:px-3",
                  active && "bg-raised text-ink",
                )}
              >
                {n.label}
              </Link>
            )
          })}
        </nav>
        {online !== null && (
          <span className="ml-auto hidden items-center gap-2 text-xs text-dim sm:flex">
            <span className={cn("size-1.5 rounded-full", online ? "bg-success" : "bg-fail")} />
            {online ? "Recorder online" : "Recorder offline"}
          </span>
        )}
      </div>
    </header>
  )
}

export function SiteFooter() {
  return (
    <footer className="mt-20 border-t">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-5 py-6 text-sm text-dim md:px-8">
        <span>Black Box: a flight recorder for AI agents</span>
        <a href={REPO} className="hover:text-ink" target="_blank" rel="noreferrer">
          GitHub
        </a>
      </div>
    </footer>
  )
}

export { REPO }
