"use client"

import { useState } from "react"

import { cn } from "@/lib/utils"

/* eslint-disable @typescript-eslint/no-explicit-any */
function Value({ value, depth }: { value: any; depth: number }) {
  if (value === null || value === undefined) return <span className="text-dim">null</span>
  if (typeof value === "boolean") return <span className="text-[var(--bb-kind-plan)]">{String(value)}</span>
  if (typeof value === "number") return <span className="text-[var(--bb-kind-retrieval)]">{value}</span>
  if (typeof value === "string") return <LongString text={value} />
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-dim">[]</span>
    return (
      <span>
        [
        <div className="pl-4">
          {value.map((v, i) => (
            <div key={i}>
              <Value value={v} depth={depth + 1} />
              {i < value.length - 1 && <span className="text-dim">,</span>}
            </div>
          ))}
        </div>
        ]
      </span>
    )
  }
  const entries = Object.entries(value)
  if (entries.length === 0) return <span className="text-dim">{"{}"}</span>
  return (
    <span>
      {"{"}
      <div className="pl-4">
        {entries.map(([k, v], i) => (
          <div key={k}>
            <span className="text-[var(--bb-kind-llm)]">{k}</span>
            <span className="text-dim">: </span>
            <Value value={v} depth={depth + 1} />
            {i < entries.length - 1 && <span className="text-dim">,</span>}
          </div>
        ))}
      </div>
      {"}"}
    </span>
  )
}

function LongString({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  const long = text.length > 160 || text.includes("\n")
  if (!long) return <span className="text-[#C9E8B4]">&quot;{text}&quot;</span>
  return (
    <span className="text-[#C9E8B4]">
      {open ? (
        <span className="whitespace-pre-wrap">&quot;{text}&quot;</span>
      ) : (
        <>&quot;{text.slice(0, 140).replace(/\n/g, " ")}…&quot;</>
      )}{" "}
      <button onClick={() => setOpen(!open)} className="text-xs text-orange hover:underline">
        {open ? "less" : "more"}
      </button>
    </span>
  )
}

export function JsonView({ value, className }: { value: any; className?: string }) {
  return (
    <div className={cn("overflow-x-auto font-mono text-[12px] leading-relaxed break-words", className)}>
      <Value value={value} depth={0} />
    </div>
  )
}
/* eslint-enable @typescript-eslint/no-explicit-any */
