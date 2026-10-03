"""Bulk dataset generation CLI.

    python -m agent_sim.generate              # 5,000 runs -> data/runs.jsonl + seeded DB
    python -m agent_sim.generate --n 800 --db 300

Splits:
- train / val / test: the four training families, clean runs + the 7 training fault types
- heldout_type:   prompt_injection and state_corruption only (never seen in training)
- heldout_family: complaint_triage only (never seen in training)

Every faulty run is checked against a clean run with the same seed: the fault has to be
applied and has to make the run fail, otherwise another injection point or seed is tried.
"""

from __future__ import annotations

import argparse
import json
import random
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Optional

from . import faults
from .faults import HELDOUT_FAULT_TYPES, TRAIN_FAULT_TYPES
from .runner import manifest_step, run_agent
from .tasks import HELDOUT_FAMILY, TRAIN_FAMILIES

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ARTIFACTS = ROOT / "ml" / "artifacts"
NAMESPACE = uuid.UUID("6f1c2b0e-4a57-4c8e-9d2a-0b1ac4c0ffee")
MASTER_SEED = 2026
ALL_FAMILIES = TRAIN_FAMILIES + [HELDOUT_FAMILY]
# calculate() only appears in the refund and quote flows
CAN_FAIL = {t: ALL_FAMILIES for t in TRAIN_FAULT_TYPES + HELDOUT_FAULT_TYPES}
CAN_FAIL["calc_error"] = ["refund", "discount_quote"]


def build_specs(n_total: int = 5000, master_seed: int = MASTER_SEED) -> list[dict]:
    rng = random.Random(master_seed)
    n_family = round(n_total * 0.12)
    n_type = round(n_total * 0.10)
    n_rest = n_total - n_family - n_type
    n_success_total = round(n_total * 0.40)
    n_family_success = round(n_family * 0.40)
    n_rest_success = n_success_total - n_family_success

    specs: list[dict] = []
    seeds = defaultdict(int)

    def add(family: str, fault: Optional[str], split: str) -> None:
        seeds[family] += 1
        specs.append({"family": family, "seed": 1000 + seeds[family] * 7, "fault": fault,
                      "split": split})

    family_faults = [t for t in TRAIN_FAULT_TYPES if HELDOUT_FAMILY in CAN_FAIL[t]]
    for i in range(n_family):
        fault = None if i < n_family_success else family_faults[i % len(family_faults)]
        add(HELDOUT_FAMILY, fault, "heldout_family")
    for i in range(n_type):
        add(TRAIN_FAMILIES[i % 4], HELDOUT_FAULT_TYPES[i % 2], "heldout_type")
    for i in range(n_rest):
        fault = None if i < n_rest_success else TRAIN_FAULT_TYPES[i % len(TRAIN_FAULT_TYPES)]
        options = [f for f in TRAIN_FAMILIES if fault is None or f in CAN_FAIL[fault]]
        family = options[rng.randrange(len(options))]
        r = rng.random()
        split = "train" if r < 0.70 else ("val" if r < 0.85 else "test")
        add(family, fault, split)

    rng.shuffle(specs)
    for s in specs:
        key = f"{s['split']}:{s['family']}:{s['seed']}:{s['fault']}"
        s["id"] = uuid.uuid5(NAMESPACE, key).hex
    return specs


def simulate(spec: dict, keep_checkpoints: bool = False):
    """Returns ``(outcome, final_spec)`` or ``(None, None)`` if no valid run was found."""
    family, base_seed, ftype = spec["family"], spec["seed"], spec["fault"]
    rng = random.Random(f"pick:{spec['id']}")
    for attempt in range(12):
        seed = base_seed + attempt * 100_003
        if ftype is None:
            out = run_agent(family, seed, run_id=spec["id"], split=spec["split"],
                            keep_checkpoints=keep_checkpoints)
            if out.success:
                return out, {**spec, "seed": seed, "fault_step": None}
            continue
        clean = run_agent(family, seed, keep_checkpoints=False)
        if not clean.success:
            continue
        clean_steps = [s.model_dump() for s in clean.record.steps]
        cands = sorted(set(faults.candidate_steps(ftype, clean_steps, clean.tags)))
        weights = Counter(faults.candidate_steps(ftype, clean_steps, clean.tags))
        rng.shuffle(cands)
        cands.sort(key=lambda c: -weights[c] * rng.random())
        for k in cands[:3]:
            out = run_agent(family, seed, fault={"type": ftype, "step": k}, run_id=spec["id"],
                            split=spec["split"], keep_checkpoints=keep_checkpoints)
            meta = out.record.fault_meta or {}
            if meta.get("applied") and not out.success:
                steps = [s.model_dump() for s in out.record.steps]
                ms = manifest_step(clean_steps, steps, k)
                meta.update({"manifest_step": ms, "gap": ms - k})
                out.record.fault_meta = meta
                return out, {**spec, "seed": seed, "fault_step": k}
    return None, None


def _row(rec) -> dict:
    d = rec.model_dump(mode="json")
    for s in d["steps"]:
        s.pop("checkpoint_id", None)
    return d


def report(rows: list[dict]) -> dict:
    failed = [r for r in rows if r["status"] == "fail" and r["fault_type"]]
    by_type = defaultdict(list)
    for r in failed:
        by_type[r["fault_type"]].append(r)

    def last_tool_idx(r: dict) -> int:
        tools = [s["idx"] for s in r["steps"] if s["kind"] in ("tool", "retrieval")]
        return tools[-1] if tools else r["steps"][-1]["idx"]

    return {
        "runs": len(rows),
        "status": dict(Counter(r["status"] for r in rows)),
        "splits": dict(Counter(r["split"] for r in rows)),
        "families": dict(Counter(r["task_family"] for r in rows)),
        "fault_types": dict(Counter(r["fault_type"] or "none" for r in rows)),
        "split_x_status": {sp: dict(Counter(r["status"] for r in rows if r["split"] == sp))
                           for sp in sorted({r["split"] for r in rows})},
        "mean_steps": round(mean(len(r["steps"]) for r in rows), 2),
        "min_steps": min(len(r["steps"]) for r in rows),
        "max_steps": max(len(r["steps"]) for r in rows),
        "mean_gap": round(mean(r["fault_meta"]["gap"] for r in failed), 2) if failed else None,
        "mean_gap_by_type": {t: round(mean(r["fault_meta"]["gap"] for r in rs), 2)
                             for t, rs in sorted(by_type.items())},
        "pct_last_step_is_fault": round(100 * mean(
            r["fault_step"] == r["steps"][-1]["idx"] for r in failed), 2) if failed else None,
        "pct_last_action_is_fault": round(100 * mean(
            r["fault_step"] == last_tool_idx(r) for r in failed), 2) if failed else None,
        "pct_failed_runs_with_error": round(100 * mean(
            any(s["error"] for s in r["steps"]) for r in failed), 2) if failed else None,
        "pct_success_runs_with_error": round(100 * mean(
            any(s["error"] for s in r["steps"]) for r in rows if r["status"] == "success"), 2),
    }


def generate(n_total: int = 5000, n_db: int = 1500, out_path: Path = DATA / "runs.jsonl",
             db_url: Optional[str] = None, fresh_db: bool = True, quiet: bool = False) -> dict:
    t0 = time.time()
    specs = build_specs(n_total)
    rows, db_batch = [], []
    engine = None
    if n_db:
        from backend import db

        engine = _reset_db(db_url) if fresh_db else db.init_db(db.get_engine(db_url))
    now = datetime.now(timezone.utc)
    skipped = 0
    for i, spec in enumerate(specs):
        out, final = simulate(spec)
        if out is None:
            skipped += 1
            continue
        rows.append(_row(out.record))
        if engine is not None and i < n_db:
            db_batch.append((spec, final, out.record.fault_meta,
                             now - timedelta(minutes=3 * (n_db - i))))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    t_gen = time.time() - t0

    if engine is not None:
        _write_db(engine, db_batch)
        write_heroes(engine)
    rep = report(rows)
    rep.update({"skipped_specs": skipped, "seconds_generate": round(t_gen, 1),
                "seconds_total": round(time.time() - t0, 1), "db_runs": len(db_batch)})
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "dataset_report.json").write_text(json.dumps(rep, indent=2) + "\n")
    if not quiet:
        print_report(rep)
    return rep


def _reset_db(db_url: Optional[str]):
    from backend import db

    url = db.resolve_url(db_url)
    if url.startswith("sqlite:///"):
        path = Path(url[len("sqlite:///"):])
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(path) + suffix)
            if p.exists():
                p.unlink()
        db._engines.pop(url, None)
    return db.init_db(db.get_engine(url))


def _write_db(engine, batch: list) -> None:
    from backend.store import save_runs

    chunk: list = []
    for spec, final, meta, created in batch:
        fault = ({"type": spec["fault"], "step": final["fault_step"]} if spec["fault"] else None)
        out = run_agent(spec["family"], final["seed"], fault=fault, split=spec["split"],
                        run_id=spec["id"])
        out.record.fault_meta = meta
        out.record.created_at = created
        chunk.append((out.record, out.checkpoints))
        if len(chunk) >= 200:
            save_runs(engine, chunk)
            chunk = []
    if chunk:
        save_runs(engine, chunk)


def seed_database(n: int, engine) -> int:
    """Seed an empty database with the first ``n`` runs of the standard dataset."""
    specs = build_specs(max(5000, n))
    now = datetime.now(timezone.utc)
    batch = []
    for i, spec in enumerate(specs[:n]):
        out, final = simulate(spec)
        if out is None:
            continue
        batch.append((spec, final, out.record.fault_meta, now - timedelta(minutes=3 * (n - i))))
    _write_db(engine, batch)
    write_heroes(engine)
    return len(batch)


def write_heroes(engine) -> None:
    from backend.store import save_runs

    from .hero import hero_outcomes

    now = datetime.now(timezone.utc)
    items = []
    for i, out in enumerate(hero_outcomes()):
        out.record.created_at = now - timedelta(seconds=10 * i)
        items.append((out.record, out.checkpoints))
    save_runs(engine, items)


def load_runs(path: Path = DATA / "runs.jsonl") -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def print_report(rep: dict) -> None:
    print(f"runs: {rep['runs']}  ({rep['status']})  in {rep['seconds_total']}s "
          f"(generation {rep['seconds_generate']}s, db runs {rep['db_runs']})")
    print(f"splits: {rep['splits']}")
    print(f"families: {rep['families']}")
    print(f"fault types: {rep['fault_types']}")
    print(f"steps per run: mean {rep['mean_steps']}, min {rep['min_steps']}, max {rep['max_steps']}")
    print(f"mean gap fault -> visible failure: {rep['mean_gap']} steps")
    print(f"  by type: {rep['mean_gap_by_type']}")
    print(f"failed runs where the last step is the cause:   {rep['pct_last_step_is_fault']}%")
    print(f"failed runs where the last action is the cause: {rep['pct_last_action_is_fault']}%")
    print(f"runs with at least one tool error: failed {rep['pct_failed_runs_with_error']}%, "
          f"successful {rep['pct_success_runs_with_error']}%")


def main() -> None:
    import os

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=5000, help="total runs in the dataset")
    ap.add_argument("--db", type=int, default=int(os.getenv("SEED_RUNS_ON_START", "1500")),
                    help="how many of them to load into the database (with checkpoints)")
    args = ap.parse_args()
    generate(args.n, args.db)


if __name__ == "__main__":
    main()
