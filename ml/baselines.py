"""Baselines: random, last_step, first_error, llm_judge.

Each returns the run's step indices ordered from most to least blamed.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional

from .common import ARTIFACTS

JUDGE_CACHE = ARTIFACTS / "llm_judge_cache.json"
JUDGE2_CACHE = ARTIFACTS / "llm_judge2_cache.json"  # GPT-OSS (via Groq)
JUDGE3_CACHE = ARTIFACTS / "llm_judge3_cache.json"  # Qwen (via Groq)


def rank_random(run: dict, seed: int = 0) -> list[int]:
    idx = [s["idx"] for s in run["steps"]]
    random.Random(f"{seed}:{run['id']}").shuffle(idx)
    return idx


def rank_last_step(run: dict) -> list[int]:
    """Blame the last action the agent took (where the failure becomes visible),
    then walk backwards."""
    steps = sorted(run["steps"], key=lambda s: -s["idx"])
    actions = [s["idx"] for s in steps if s["kind"] in ("tool", "retrieval")]
    rest = [s["idx"] for s in steps if s["idx"] not in actions]
    return actions + rest


def rank_first_error(run: dict) -> list[int]:
    """Blame the first step that returned an error; without errors, fall back to
    ``last_step``."""
    errors = [s["idx"] for s in sorted(run["steps"], key=lambda s: s["idx"]) if s.get("error")]
    rest = [i for i in rank_last_step(run) if i not in errors]
    return errors + rest


# ------------------------------------------------------------------ llm judge


def load_judge_cache(path: Path = JUDGE_CACHE) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def rank_llm_judge(run: dict, cache: dict) -> Optional[list[int]]:
    """Use a cached verdict; returns None for runs the judge has not seen."""
    hit = cache.get(run["id"])
    if not hit or hit.get("ranking") is None:
        return None
    ranking = [int(i) for i in hit["ranking"] if isinstance(i, (int, float, str))
               and str(i).lstrip("-").isdigit()]
    rest = [i for i in rank_last_step(run) if i not in ranking]
    return ranking + rest


def judge_prompt(run: dict) -> str:
    lines = []
    for s in run["steps"]:
        out = s.get("error") or json.dumps(s.get("output"), ensure_ascii=False)
        if len(out) > 400:
            out = out[:400] + "..."
        args = json.dumps(s.get("input"), ensure_ascii=False)
        if len(args) > 300:
            args = args[:300] + "..."
        lines.append(f"[{s['idx']}] {s['kind']} {s['name']} input={args} -> {out}")
    trace = "\n".join(lines)
    return (
        "You are debugging an AI customer-support agent. The run below FAILED: "
        f"{run.get('outcome_detail', '')}.\n"
        "Find the root-cause step: the single earliest step that, if it had been done "
        "correctly, would have prevented the failure. It is often earlier than the step where "
        "the failure becomes visible.\n\n"
        f"Task: {run.get('task_text', '')}\n\nTrace:\n{trace}\n\n"
        'Answer with JSON only: {"ranking": [most likely step index, second, third], '
        '"reason": "one sentence"}'
    )


def run_llm_judge(runs: list[dict], limit: int = 100, path: Path = JUDGE_CACHE,
                  sleep: float = 4.5, client=None) -> dict:
    """Ask an LLM (Gemini by default) for the culprit step on up to ``limit`` runs,
    caching every answer."""
    import time

    from agent_sim.llm import GeminiClient

    cache = load_judge_cache(path)
    client = client or GeminiClient()
    todo = [r for r in runs if r["id"] not in cache][: max(0, limit - len(cache))]
    for i, run in enumerate(todo):
        try:
            data = client.json(judge_prompt(run))
            cache[run["id"]] = {"ranking": data.get("ranking"), "reason": data.get("reason"),
                                "model": client.model}
        except Exception as exc:  # noqa: BLE001 - keep going, record the failure
            cache[run["id"]] = {"ranking": None, "error": str(exc)[:200], "model": client.model}
        path.write_text(json.dumps(cache, indent=1))
        print(f"judge {i + 1}/{len(todo)}: {cache[run['id']].get('ranking')}")
        time.sleep(sleep)
    return cache


def main() -> None:
    import argparse
    import random

    from .common import load_runs

    ap = argparse.ArgumentParser(description="Run the Gemini judge baseline on a fixed sample.")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--judge", choices=["gemini", "gpt-oss", "qwen"], default="gemini")
    args = ap.parse_args()
    runs = [r for r in load_runs() if r["status"] == "fail" and r.get("fault_step") is not None]
    picked = []
    for split, share in (("test", 0.5), ("heldout_type", 0.25), ("heldout_family", 0.25)):
        pool = [r for r in runs if r["split"] == split]
        random.Random(f"judge:{split}").shuffle(pool)
        picked += pool[: int(args.limit * share)]
    if args.judge == "gemini":
        run_llm_judge(picked, limit=args.limit)
    else:
        from agent_sim.llm import GroqClient

        model, path = {"gpt-oss": ("openai/gpt-oss-120b", JUDGE2_CACHE),
                       "qwen": ("qwen/qwen3.8-27b", JUDGE3_CACHE)}[args.judge]
        run_llm_judge(picked, limit=args.limit, path=path, sleep=2.2, client=GroqClient(model))


if __name__ == "__main__":
    main()
