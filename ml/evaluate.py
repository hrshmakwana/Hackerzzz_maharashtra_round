"""Evaluate model + baselines on every split; writes metrics.json and eval_report.md.

    python -m ml.evaluate            # metrics + replay/fix stats
    python -m ml.evaluate --fast     # skip the replay experiments
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Callable, Optional

import numpy as np
from sklearn.metrics import roc_auc_score

from .baselines import (
    JUDGE2_CACHE,
    load_judge_cache,
    rank_first_error,
    rank_last_step,
    rank_llm_judge,
    rank_random,
)
from .common import ARTIFACTS, ROOT, load_models, load_runs

SPLITS = ["val", "test", "heldout_type", "heldout_family", "live"]
SPLIT_LABELS = {
    "val": "Validation",
    "test": "Test (in-distribution)",
    "heldout_type": "Held-out fault types",
    "heldout_family": "Held-out task family",
    "live": "Real Gemini agent",
}
METHODS = ["model", "llm_judge", "llm_judge2", "first_error", "last_step", "random"]


def ranking_metrics(runs: list[dict], rank: Callable[[dict], Optional[list[int]]]) -> dict:
    hits1 = hits3 = 0
    rr, dist = [], []
    per_type = defaultdict(list)
    n = 0
    for r in runs:
        order = rank(r)
        if order is None:
            continue
        n += 1
        target = r["fault_step"]
        pos = order.index(target) if target in order else len(order)
        hits1 += pos == 0
        hits3 += pos < 3
        rr.append(1 / (pos + 1))
        dist.append(abs(order[0] - target))
        per_type[r["fault_type"]].append(pos == 0)
    if n == 0:
        return {"n": 0}
    return {
        "n": n,
        "top1": round(hits1 / n, 4),
        "top3": round(hits3 / n, 4),
        "mrr": round(float(mean(rr)), 4),
        "mean_step_distance": round(float(mean(dist)), 3),
        "per_type_top1": {t: {"top1": round(mean(v), 4), "n": len(v)}
                          for t, v in sorted(per_type.items())},
    }


def model_ranker(models) -> Callable[[dict], list[int]]:
    def rank(run: dict) -> list[int]:
        scores, _, _ = models.score_steps(run)
        idx = [s["idx"] for s in sorted(run["steps"], key=lambda s: s["idx"])]
        return [idx[i] for i in np.argsort(-scores, kind="stable")]

    return rank


def evaluate(runs: list[dict] | None = None, replay: bool = True, quiet: bool = False) -> dict:
    t0 = time.time()
    runs = runs or load_runs()
    live_path = ROOT / "data" / "live_runs.jsonl"
    if live_path.exists():
        runs = runs + load_runs(live_path)
    models = load_models()
    judge_cache = load_judge_cache()
    judge2_cache = load_judge_cache(JUDGE2_CACHE)
    rankers = {
        "model": model_ranker(models),
        "llm_judge": lambda r: rank_llm_judge(r, judge_cache),
        "llm_judge2": lambda r: rank_llm_judge(r, judge2_cache),
        "first_error": rank_first_error,
        "last_step": rank_last_step,
        "random": rank_random,
    }

    splits: dict = {}
    for split in SPLITS:
        failed = [r for r in runs if r["split"] == split and r["status"] == "fail"
                  and r.get("fault_step") is not None]
        if not failed:
            continue
        splits[split] = {"label": SPLIT_LABELS[split], "runs": len([r for r in runs if r["split"] == split]),
                         "failed_with_label": len(failed),
                         "methods": {m: ranking_metrics(failed, fn) for m, fn in rankers.items()}}

    # run-level failure classifier
    auroc = {}
    for split in ("test", "heldout_family", "val"):
        sub = [r for r in runs if r["split"] == split]
        y = [int(r["status"] == "fail") for r in sub]
        if len(set(y)) == 2:
            p = [models.fail_risk(r) for r in sub]
            auroc[split] = round(float(roc_auc_score(y, p)), 4)

    info = json.loads((ARTIFACTS / "train_info.json").read_text())
    dataset = json.loads((ARTIFACTS / "dataset_report.json").read_text()) \
        if (ARTIFACTS / "dataset_report.json").exists() else {}
    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_version": models.version,
        "dataset": {k: dataset.get(k) for k in ("runs", "status", "splits", "fault_types",
                                                  "mean_steps", "mean_gap", "mean_gap_by_type",
                                                  "pct_last_step_is_fault",
                                                  "pct_last_action_is_fault")},
        "splits": splits,
        "auroc": auroc,
        "feature_importance": info["feature_importance"][:20],
        "train": {k: info[k] for k in ("train_runs", "ranking_groups", "features", "best_iteration")},
        "judge_runs": sum(1 for v in judge_cache.values() if v.get("ranking") is not None),
        "judge_models": {
            "llm_judge": next((v.get("model") for v in judge_cache.values() if v.get("model")), None),
            "llm_judge2": next((v.get("model") for v in judge2_cache.values() if v.get("model")), None),
        },
    }
    if replay:
        from .replay_eval import replay_stats

        metrics["replay"] = replay_stats(runs, models)
    metrics["seconds"] = round(time.time() - t0, 1)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "metrics.json").write_text(json.dumps(metrics, indent=1) + "\n")
    (ROOT / "docs" / "eval_report.md").write_text(render_report(metrics))
    update_readme(metrics)
    if not quiet:
        print_summary(metrics)
    return metrics


# ------------------------------------------------------------------- report


def _pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


def render_report(m: dict) -> str:
    lines = ["# Evaluation report", "",
             f"_Generated by `make eval` on {m['generated_at']} for model `{m['model_version']}`. "
             "Do not edit by hand._", ""]
    ds = m.get("dataset") or {}
    if ds.get("runs"):
        lines += ["## Dataset", "",
                  f"- {ds['runs']} recorded runs ({ds['status']})",
                  f"- splits: {ds['splits']}",
                  f"- mean run length {ds['mean_steps']} steps; a fault becomes visible on average "
                  f"{ds['mean_gap']} steps after the faulty step",
                  f"- the last step is the cause in {ds['pct_last_step_is_fault']}% of failed runs, "
                  f"the last action in {ds['pct_last_action_is_fault']}%", ""]
    lines += ["## Root-cause localisation", "",
              "Each failed run has exactly one injected faulty step. A method ranks all steps; "
              "Top-1 means its first pick is the injected step.", ""]
    for split, s in m["splits"].items():
        lines += [f"### {s['label']} (`{split}`, {s['failed_with_label']} failed runs)", "",
                  "| Method | n | Top-1 | Top-3 | MRR | Mean step distance |",
                  "|---|---|---|---|---|---|"]
        for meth in METHODS:
            r = s["methods"].get(meth, {})
            if not r.get("n"):
                continue
            name = "**Black Box ranker**" if meth == "model" else meth
            lines.append(f"| {name} | {r['n']} | {_pct(r['top1'])} | {_pct(r['top3'])} | "
                         f"{r['mrr']:.3f} | {r['mean_step_distance']:.2f} |")
        lines.append("")
        per = s["methods"]["model"].get("per_type_top1", {})
        if per:
            base = s["methods"]["last_step"].get("per_type_top1", {})
            lines += ["| Fault type | n | Ranker Top-1 | last_step Top-1 |", "|---|---|---|---|"]
            for t, v in per.items():
                lines.append(f"| {t} | {v['n']} | {_pct(v['top1'])} | "
                             f"{_pct(base.get(t, {}).get('top1'))} |")
            lines.append("")
    if m.get("auroc"):
        lines += ["## Run-level failure classifier", "",
                  "| Split | AUROC |", "|---|---|"]
        lines += [f"| {k} | {v:.3f} |" for k, v in m["auroc"].items()]
        lines.append("")
    rp = m.get("replay")
    if rp:
        lines += ["## Fork, fix and prove", "",
                  f"Auto-fix applied at the ranker's top-1 step on {rp['n']} failed runs per split "
                  "(sampled). A *flip* means the forked run now passes the checker.", "",
                  "| Split | Runs | Flip @ top-1 | Sweep flip @ top-3 | Confirmed = true cause | "
                  "Flip @ true step | Steps reused | Tokens saved / fork |",
                  "|---|---|---|---|---|---|---|---|"]
        for split, v in rp["splits"].items():
            lines.append(f"| {split} | {v['n']} | {_pct(v['flip_rate_top1'])} | "
                         f"{_pct(v['flip_rate_sweep'])} | {_pct(v.get('confirmed_precision'))} | "
                         f"{_pct(v['flip_rate_at_true_step'])} | {_pct(v['avg_reused_frac'])} | "
                         f"{v['avg_tokens_saved']:.0f} |")
        lines += ["", "*Confirmed = true cause*: when the sweep finds a flip, how often the earliest "
                  "flipping step is the injected one (patching a later symptom can also flip a run).",
                  ""]
    lines += ["## Most important features (gain)", "", "| Feature | Gain |", "|---|---|"]
    lines += [f"| {f['feature']} | {f['gain']:.0f} |" for f in m["feature_importance"][:12]]
    lines += ["", "## Notes", "",
              "- `last_step` blames the last tool call (where the failure becomes visible); "
              "`first_error` blames the first errored step and falls back to `last_step`.",
              "- `llm_judge` is Gemini reading the whole trace; it runs on a cached sample only.",
              "- Held-out fault types (prompt_injection, state_corruption) and the held-out family "
              "(complaint_triage) never appear in training.", ""]
    return "\n".join(lines)


def update_readme(m: dict) -> None:
    """Rewrite the results table in README.md between its marker comments."""
    path = ROOT / "README.md"
    start, end = "<!-- results:start -->", "<!-- results:end -->"
    text = path.read_text() if path.exists() else ""
    if start not in text or end not in text:
        return
    rows = ["| Split | Black Box ranker Top-1 | Top-3 | Gemini as judge Top-1 | Last action | First error | Random |",
            "|---|---|---|---|---|---|---|"]
    for split in ("test", "heldout_family", "heldout_type"):
        s = m["splits"].get(split)
        if not s:
            continue
        me = s["methods"]
        judge = me.get("llm_judge", {})
        rows.append(f"| {s['label']} | **{_pct(me['model']['top1'])}** | {_pct(me['model']['top3'])} | "
                    f"{_pct(judge.get('top1')) if judge.get('n') else '—'} | {_pct(me['last_step']['top1'])} | "
                    f"{_pct(me['first_error']['top1'])} | {_pct(me['random']['top1'])} |")
    rp = (m.get("replay") or {}).get("splits", {})
    extra = []
    if rp:
        extra = ["", f"Auto-fix at the top-ranked step flips {_pct(rp.get('test', {}).get('flip_rate_top1'))} of "
                     f"failed test runs to success; a sweep over the top 3 flips "
                     f"{_pct(rp.get('heldout_type', {}).get('flip_rate_sweep'))} on unseen fault types. "
                     f"Forks reuse {_pct(rp.get('test', {}).get('avg_reused_frac'))} of the original steps.",
                 "", f"_Generated by `make eval` ({m['generated_at']}). Full report: "
                     f"[docs/eval_report.md](docs/eval_report.md)._"]
    block = "\n".join([start, *rows, *extra, end])
    before, rest = text.split(start, 1)
    after = rest.split(end, 1)[1]
    path.write_text(before + block + after)


def print_summary(m: dict) -> None:
    for split, s in m["splits"].items():
        cells = []
        for meth in METHODS:
            r = s["methods"].get(meth, {})
            if r.get("n"):
                cells.append(f"{meth} {_pct(r['top1'])}/{_pct(r['top3'])}")
        print(f"{split:15} n={s['failed_with_label']:<4} " + " | ".join(cells))
        per = s["methods"]["model"].get("per_type_top1", {})
        print("    per type:", ", ".join(f"{t} {_pct(v['top1'])}" for t, v in per.items()))
    print("AUROC:", m["auroc"])
    if m.get("replay"):
        for split, v in m["replay"]["splits"].items():
            print(f"replay {split}: flip@1 {_pct(v['flip_rate_top1'])}, sweep@3 "
                  f"{_pct(v['flip_rate_sweep'])}, reused {_pct(v['avg_reused_frac'])}")
    print(f"({m['seconds']}s)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="skip replay experiments")
    args = ap.parse_args()
    evaluate(replay=not args.fast)


if __name__ == "__main__":
    main()
