"use client"

import { cn } from "@/lib/utils"

export function Segmented({ value, onChange, options }: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <div className="inline-flex rounded-lg border bg-background p-0.5" role="radiogroup">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-md px-2.5 py-1 text-xs text-dim transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
            value === o.value && "bg-surface-2 text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function NativeSelect({ value, onChange, options, placeholder, className, ariaLabel }: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string; disabled?: boolean }[]
  placeholder?: string
  className?: string
  ariaLabel?: string
}) {
  return (
    <select
      value={value}
      aria-label={ariaLabel ?? placeholder}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "h-8 rounded-lg border bg-input/30 px-2 text-sm text-foreground outline-none hover:bg-input/50 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
        !value && "text-dim",
        className,
      )}
    >
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => (
        <option key={o.value} value={o.value} disabled={o.disabled}>
          {o.label}
        </option>
      ))}
    </select>
  )
}
