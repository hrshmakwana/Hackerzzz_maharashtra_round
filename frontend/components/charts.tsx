"use client"

import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

export const ACCENT = "#FF6A13"
export const CONTEXT = "#7C7C88"
const GRID = "#26262F"
const MUTED = "#9A9AA5"
const INK = "#EDEDED"

export interface BarDatum {
  label: string
  value: number
  highlight?: boolean
  note?: string
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function TipBox({ active, payload, format }: any) {
  if (!active || !payload?.length) return null
  const d: BarDatum = payload[0].payload
  return (
    <div className="rounded-md border bg-popover px-2.5 py-1.5 text-xs shadow-lg">
      <div className="text-foreground">{d.label}</div>
      <div className="font-mono text-dim">
        {format(d.value)}
        {d.note ? ` · ${d.note}` : ""}
      </div>
    </div>
  )
}
/* eslint-enable @typescript-eslint/no-explicit-any */

/** Horizontal bars: identity comes from the row label; orange marks our model. */
export function HBars({
  data,
  format = (v) => String(v),
  max,
  labelWidth = 150,
  rowHeight = 26,
  ariaLabel,
}: {
  data: BarDatum[]
  format?: (v: number) => string
  max?: number
  labelWidth?: number
  rowHeight?: number
  ariaLabel: string
}) {
  const height = data.length * rowHeight + 28
  return (
    <div role="img" aria-label={ariaLabel} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 2, right: 52, bottom: 2, left: 0 }} barCategoryGap={4}>
          <CartesianGrid horizontal={false} stroke={GRID} strokeWidth={1} />
          <XAxis
            type="number"
            domain={[0, max ?? "auto"]}
            tick={{ fill: MUTED, fontSize: 11 }}
            tickFormatter={(v) => format(v)}
            axisLine={false}
            tickLine={false}
            tickCount={5}
          />
          <YAxis
            type="category"
            dataKey="label"
            width={labelWidth}
            tick={{ fill: INK, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip cursor={{ fill: "rgba(255,255,255,0.03)" }} content={<TipBox format={format} />} />
          <Bar dataKey="value" barSize={14} radius={[0, 4, 4, 0]} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.label} fill={d.highlight ? ACCENT : CONTEXT} />
            ))}
            <LabelList dataKey="value" position="right" formatter={(v) => format(Number(v))} fill={MUTED} fontSize={11} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
