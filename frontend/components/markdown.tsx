import type { ReactNode } from "react"

/** Small markdown renderer for incident reports: headings, bold, code, lists, paragraphs. */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith("**")) out.push(<strong key={i++} className="font-semibold text-foreground">{tok.slice(2, -2)}</strong>)
    else out.push(<code key={i++} className="rounded bg-surface-2 px-1 font-mono text-[0.85em]">{tok.slice(1, -1)}</code>)
    last = m.index + tok.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = []
  const lines = text.split("\n")
  let list: string[] = []
  const flush = () => {
    if (list.length) {
      blocks.push(
        <ul key={blocks.length} className="ml-4 list-disc space-y-1">
          {list.map((l, i) => <li key={i}>{inline(l)}</li>)}
        </ul>,
      )
      list = []
    }
  }
  for (const raw of lines) {
    const line = raw.trimEnd()
    if (/^\s*[-*] /.test(line)) {
      list.push(line.replace(/^\s*[-*] /, ""))
      continue
    }
    flush()
    if (!line.trim()) continue
    const h = line.match(/^(#{1,4})\s+(.*)$/)
    if (h) blocks.push(<h3 key={blocks.length} className="font-heading text-sm font-semibold text-foreground">{inline(h[2])}</h3>)
    else blocks.push(<p key={blocks.length}>{inline(line)}</p>)
  }
  flush()
  return <div className="space-y-2 text-sm leading-relaxed text-foreground/85">{blocks}</div>
}
