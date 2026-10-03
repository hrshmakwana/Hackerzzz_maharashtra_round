"""Train the LGBMRanker (step blame) and LGBMClassifier (run risk).

    python -m ml.train

Ranking data: every failed run with a known injected step in the train split; one group
per run, label 1 on the injected step. Validation uses the val split for early stopping.
The transition model behind ``transition_surprisal`` is fit on successful train runs only.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import warnings

import lightgbm as lgb
import numpy as np

warnings.filterwarnings("ignore", message=".*eval_set.*")

from .common import ARTIFACTS, load_runs
from .features import TransitionModel, feature_names, run_features, run_matrix

# Validation saturates within a handful of trees on in-distribution data, so early stopping
# would leave a 2-tree model. A fixed budget with feature subsampling spreads the signal
# over redundant features, which is what carries over to unseen failure types.
RANKER_PARAMS = dict(objective="lambdarank", n_estimators=300, learning_rate=0.03,
                     num_leaves=15, min_child_samples=30, subsample=0.8, subsample_freq=1,
                     colsample_bytree=0.5, reg_lambda=2.0, random_state=7, verbose=-1)
CLF_PARAMS = dict(n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=20,
                  subsample=0.9, subsample_freq=1, colsample_bytree=0.9, random_state=7,
                  verbose=-1)


def label_of(run: dict) -> int | None:
    """The injected step (only training code reads this)."""
    return run.get("fault_step")


def ranking_set(runs: list[dict], tm: TransitionModel, names: list[str]):
    X, y, groups = [], [], []
    for r in runs:
        target = label_of(r)
        if r["status"] != "fail" or target is None:
            continue
        rows, _ = run_matrix(r, tm, names)
        X += rows
        y += [int(s["idx"] == target) for s in sorted(r["steps"], key=lambda s: s["idx"])]
        groups.append(len(rows))
    return np.asarray(X, dtype=float), np.asarray(y), groups


def run_set(runs: list[dict], tm: TransitionModel, run_names: list[str] | None = None):
    feats = [run_features(r, tm) for r in runs]
    run_names = run_names or list(feats[0].keys())
    X = np.asarray([[f[k] for k in run_names] for f in feats], dtype=float)
    y = np.asarray([int(r["status"] == "fail") for r in runs])
    return X, y, run_names


def train(runs: list[dict] | None = None, quiet: bool = False) -> dict:
    t0 = time.time()
    runs = runs or load_runs()
    train_runs = [r for r in runs if r["split"] == "train"]
    val_runs = [r for r in runs if r["split"] == "val"]

    tm = TransitionModel.fit(r for r in train_runs if r["status"] == "success")
    names = feature_names()

    Xtr, ytr, gtr = ranking_set(train_runs, tm, names)
    Xva, yva, gva = ranking_set(val_runs, tm, names)
    ranker = lgb.LGBMRanker(**RANKER_PARAMS)
    ranker.fit(Xtr, ytr, group=gtr, eval_set=[(Xva, yva)], eval_group=[gva], eval_at=[1, 3])

    Xc, yc, run_names = run_set(train_runs, tm)
    Xcv, ycv, _ = run_set(val_runs, tm, run_names)
    clf = lgb.LGBMClassifier(**CLF_PARAMS)
    clf.fit(Xc, yc, eval_set=[(Xcv, ycv)], callbacks=[lgb.early_stopping(60, verbose=False)])

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    ranker.booster_.save_model(str(ARTIFACTS / "model.txt"))
    clf.booster_.save_model(str(ARTIFACTS / "classifier.txt"), num_iteration=clf.best_iteration_)
    (ARTIFACTS / "feature_list.json").write_text(json.dumps(names, indent=1) + "\n")
    (ARTIFACTS / "run_feature_list.json").write_text(json.dumps(run_names, indent=1) + "\n")
    (ARTIFACTS / "transitions.json").write_text(json.dumps(tm.to_json()) + "\n")

    gain = ranker.booster_.feature_importance(importance_type="gain")
    importance = sorted(zip(names, gain.tolist()), key=lambda x: -x[1])
    info = {
        "version": "ranker-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M"),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "train_runs": len(train_runs),
        "ranking_groups": {"train": len(gtr), "val": len(gva)},
        "train_steps": int(len(ytr)),
        "features": len(names),
        "best_iteration": {"ranker": RANKER_PARAMS["n_estimators"],
                           "classifier": int(clf.best_iteration_ or CLF_PARAMS["n_estimators"])},
        "params": {"ranker": RANKER_PARAMS, "classifier": CLF_PARAMS},
        "feature_importance": [{"feature": n, "gain": round(g, 2)} for n, g in importance],
        "seconds": round(time.time() - t0, 1),
    }
    (ARTIFACTS / "train_info.json").write_text(json.dumps(info, indent=1) + "\n")
    if not quiet:
        print(f"trained on {len(gtr)} failed runs ({len(ytr)} steps), val {len(gva)} runs, "
              f"{len(names)} features, best iteration {info['best_iteration']['ranker']}, "
              f"{info['seconds']}s")
        print("top features:", ", ".join(n for n, _ in importance[:10]))
    return info


def main() -> None:
    train()


if __name__ == "__main__":
    main()
