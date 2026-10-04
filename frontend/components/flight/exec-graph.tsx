"use client"

import { Background, Controls, Handle, Position, ReactFlow, type Edge as FlowEdge, type Node, type NodeProps } from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { AlertTriangle, Recycle } from "lucide-react"
import { useMemo } from "react"

import { KIND_COLOR } from "@/components/bits"
import type { Edge, Step } from "@/lib/api"
import { cn } from "@/lib/utils"

const COLS = 4
const W = 150
const H = 46
const GX = 26
const GY = 34

type StepNodeData = {
  step: Step
  heat: number
  canon: boolean
  selected: boolean
  injected: boolean
}

function place(i: number) {
  const row = Math.floor(i / COLS)
  const col = row % 2 === 0 ? i % COLS : COLS - 1 - (i % COLS)
  return { x: col * (W + GX), y: row * (H + GY), row }
}

function StepNode({ data }: NodeProps<Node<StepNodeData>>) {
  const { step, heat, canon, selected } = data
  const hidden = "!size-1.5 !min-w-0 !border-0 !bg-transparent"
  return (
    <div
      className={cn(
        "relative flex h-[46px] w-[150px] flex-col justify-center rounded-md border bg-card px-2.5 transition-shadow",
        selected && "ring-2 ring-foreground/70",
        canon && "border-orange shadow-[0_0_0_3px_rgba(255,106,19,0.18),0_0_22px_rgba(255,106,19,0.35)]",
        step.reused && "opacity-50",
        step.error && !canon && "border-fail/60",
      )}
      style={{
        borderColor: canon ? undefined : step.error ? undefined : `color-mix(in srgb, ${KIND_COLOR[step.kind]} 45%, transparent)`,
        background: heat > 0.02 ? `color-mix(in srgb, #FF6A13 ${Math.round(heat * 30)}%, var(--bb-surface))` : undefined,
      }}
    >
      {(["Left", "Right", "Top", "Bottom"] as const).map((side) => (
        <span key={side}>
          <Handle id={`s${side}`} type="source" position={Position[side]} className={hidden} />
          <Handle id={`t${side}`} type="target" position={Position[side]} className={hidden} />
        </span>
      ))}
      <div className="flex items-center gap-1.5">
        <span className="font-mono text-[10px] text-dim">{String(step.idx).padStart(2, "0")}</span>
        <span className="truncate font-mono text-[12px] text-foreground">{step.kind === "llm" ? "llm" : step.name}</span>
        {step.error && <AlertTriangle className="size-3 shrink-0 text-fail" />}
        {step.reused && <Recycle className="size-3 shrink-0 text-dim" />}
      </div>
      <div className="flex items-center gap-1.5 text-[10px] text-dim">
        <span className="size-1.5 rounded-full" style={{ background: KIND_COLOR[step.kind] }} />
        {step.kind}
        {canon && <span className="ml-auto font-heading font-semibold text-orange">Canon Event</span>}
      </div>
    </div>
  )
}

const nodeTypes = { step: StepNode }

function sides(a: ReturnType<typeof place>, b: ReturnType<typeof place>) {
  if (a.row !== b.row) {
    return b.row > a.row ? { s: "sBottom", t: "tTop" } : { s: "sTop", t: "tBottom" }
  }
  return b.x > a.x ? { s: "sRight", t: "tLeft" } : { s: "sLeft", t: "tRight" }
}

export function ExecGraph({ steps, edges, blame, canon, selected, injected, onSelect }: {
  steps: Step[]
  edges: Edge[]
  blame: Map<number, number> | null
  canon: number | null
  selected: number | null
  injected: number | null
  onSelect: (idx: number) => void
}) {
  const max = blame ? Math.max(...blame.values(), 0.0001) : 1
  const { nodes, flowEdges } = useMemo(() => {
    const pos = new Map(steps.map((s, i) => [s.idx, place(i)]))
    const nodes: Node<StepNodeData>[] = steps.map((s) => ({
      id: String(s.idx),
      type: "step",
      position: { x: pos.get(s.idx)!.x, y: pos.get(s.idx)!.y },
      data: {
        step: s,
        heat: blame ? (blame.get(s.idx) ?? 0) / max : 0,
        canon: canon === s.idx,
        selected: selected === s.idx,
        injected: injected === s.idx,
      },
      draggable: false,
    }))
    const focus = new Set([selected, canon].filter((x): x is number => x !== null))
    const flowEdges: FlowEdge[] = []
    for (const e of edges) {
      const a = pos.get(e.source)
      const b = pos.get(e.target)
      if (!a || !b) continue
      if (e.kind === "seq") {
        const h = sides(a, b)
        flowEdges.push({
          id: `s${e.source}-${e.target}`, source: String(e.source), target: String(e.target),
          sourceHandle: h.s, targetHandle: h.t, type: "smoothstep",
          style: { stroke: "#3a3a46", strokeWidth: 1.5 },
        })
      } else if (focus.has(e.source)) {
        flowEdges.push({
          id: `d${e.source}-${e.target}`, source: String(e.source), target: String(e.target),
          sourceHandle: "sBottom", targetHandle: "tTop", type: "default", animated: true,
          style: { stroke: e.source === canon ? "#FF6A13" : "#6cc3f0", strokeWidth: 1.5, strokeDasharray: "4 4", opacity: 0.8 },
        })
      }
    }
    return { nodes, flowEdges }
  }, [steps, edges, blame, canon, selected, injected, max])

  return (
    <ReactFlow
      nodes={nodes}
      edges={flowEdges}
      nodeTypes={nodeTypes}
      colorMode="dark"
      fitView
      fitViewOptions={{ padding: 0.12, maxZoom: 1.1 }}
      minZoom={0.35}
      maxZoom={1.6}
      nodesConnectable={false}
      nodesDraggable={false}
      elementsSelectable={false}
      onNodeClick={(_, n) => onSelect(Number(n.id))}
      proOptions={{ hideAttribution: true }}
    >
      <Background color="#1d1d26" gap={18} size={1} />
      <Controls showInteractive={false} position="bottom-right" />
    </ReactFlow>
  )
}
