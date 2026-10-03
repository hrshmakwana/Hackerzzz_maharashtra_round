"""Paths and model loading shared by training, evaluation and the API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from .features import TransitionModel, run_features, run_matrix

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "ml" / "artifacts"
DATA = ROOT / "data"


def load_runs(path: Path = DATA / "runs.jsonl") -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run `make data` first")
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


@dataclass
class Models:
    ranker: object  # lightgbm.Booster
    classifier: object  # lightgbm.Booster
    tm: TransitionModel
    names: list[str]
    run_names: list[str]
    version: str

    def score_steps(self, run: dict) -> tuple[np.ndarray, list[dict], np.ndarray]:
        X, rows = run_matrix(run, self.tm, self.names)
        X = np.asarray(X, dtype=float)
        return self.ranker.predict(X), rows, X

    def fail_risk(self, run: dict) -> float:
        rf = run_features(run, self.tm)
        x = np.asarray([[rf[k] for k in self.run_names]], dtype=float)
        return float(self.classifier.predict(x)[0])


def softmax(x: np.ndarray) -> np.ndarray:
    z = np.exp(x - x.max())
    return z / z.sum()


@lru_cache(maxsize=1)
def load_models() -> Models:
    import lightgbm as lgb

    info = json.loads((ARTIFACTS / "train_info.json").read_text())
    return Models(
        ranker=lgb.Booster(model_file=str(ARTIFACTS / "model.txt")),
        classifier=lgb.Booster(model_file=str(ARTIFACTS / "classifier.txt")),
        tm=TransitionModel.from_json(json.loads((ARTIFACTS / "transitions.json").read_text())),
        names=json.loads((ARTIFACTS / "feature_list.json").read_text()),
        run_names=json.loads((ARTIFACTS / "run_feature_list.json").read_text()),
        version=info.get("version", "unknown"),
    )


def models_available() -> bool:
    return all((ARTIFACTS / f).exists() for f in
               ("model.txt", "classifier.txt", "transitions.json", "feature_list.json",
                "run_feature_list.json", "train_info.json"))
