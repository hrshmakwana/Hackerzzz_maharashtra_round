import { Activity, AlertTriangle, Crosshair, Play, Recycle } from "lucide-react";

import { Button } from "@/components/ui/button";

const kpis = [
  { label: "Runs recorded", icon: Activity },
  { label: "Fail rate", icon: AlertTriangle },
  { label: "Top-1 blame accuracy", icon: Crosshair },
  { label: "Avg steps reused", icon: Recycle },
];

export default function Hangar() {
  return (
    <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-8">
      <header className="mb-8 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="size-3 rounded-sm bg-orange" aria-hidden />
          <div>
            <h1 className="text-2xl font-semibold">Hangar</h1>
            <p className="text-sm text-dim">Every recorded agent run, in one place.</p>
          </div>
        </div>
        <Button disabled>
          <Play /> Start live run
        </Button>
      </header>

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {kpis.map(({ label, icon: Icon }) => (
          <div key={label} className="rounded-lg border bg-card p-4">
            <div className="flex items-center justify-between text-xs uppercase tracking-wide text-dim">
              {label}
              <Icon className="size-4" />
            </div>
            <div className="mt-3 font-mono text-2xl text-muted-foreground">—</div>
          </div>
        ))}
      </section>

      <section className="mt-6 rounded-lg border bg-card">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 className="text-sm font-medium">Runs</h2>
          <span className="canon-badge rounded border border-fail/40 px-2 py-0.5 font-mono text-xs text-fail">
            CANON EVENT
          </span>
        </div>
        <div className="px-4 py-16 text-center text-sm text-dim">
          No runs yet. Generate a dataset with <code className="font-mono text-foreground">make data</code>.
        </div>
      </section>
    </main>
  );
}
