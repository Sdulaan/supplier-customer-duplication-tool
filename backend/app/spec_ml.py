"""Learned layer on top of the rule matrix in spec_model.

The rule matrix needs exact evidence (a tax id, a phone, an exact street). The model learns what duplicates look
like when that evidence is missing, so it can surface pairs the rules score under 40.

Training data, in order of preference:
  1. Steward decisions: [{"a": id, "b": id, "duplicate": true|false}] (optional, weighted heavily).
  2. Anchor supervision, no labelling needed: pairs that share a valid registration / cross-reference id (A01/A02) are
     positives, pairs whose registration numbers clearly conflict are negatives. The A01/A02 points are NOT model
     features, so the model has to predict "same legal entity" from name, address, contact, purchasing context
     and ID shape alone.
"""
import random
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import spec_model as sm

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "spec_pair_model.joblib"
LABEL_WEIGHT = 5.0
MIN_PER_CLASS = 8
# The model may only add pairs the rules missed once it has proven itself: enough positives and a good cross-validated AUC.
SURFACE_MIN_POSITIVES = 30
SURFACE_MIN_AUC = 0.85


class PairModel:
    def __init__(self, pipeline, meta: dict, surface_threshold: float = 0.9):
        self.pipeline, self.meta, self.surface_threshold = pipeline, meta, surface_threshold

    @property
    def can_surface(self) -> bool:
        m = self.meta
        return bool(m.get("cvAuc") and m["cvAuc"] >= SURFACE_MIN_AUC and m["positives"] >= SURFACE_MIN_POSITIVES)

    def predict(self, features: dict) -> float:
        x = np.array([[features[n] for n in sm.FEATURE_NAMES]])
        return float(self.pipeline.predict_proba(x)[0, 1])

    def weights(self) -> dict:
        coef = self.pipeline[-1].coef_[0]
        return {n: round(float(c), 3) for n, c in sorted(zip(sm.FEATURE_NAMES, coef), key=lambda t: -abs(t[1]))}

    def save(self, path: Path = MODEL_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"pipeline": self.pipeline, "meta": self.meta, "surface_threshold": self.surface_threshold}, path)

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "PairModel | None":
        if not path.exists():
            return None
        blob = joblib.load(path)  # written by save() above; the models folder is not user-writable input
        return cls(blob["pipeline"], blob["meta"], blob.get("surface_threshold", 0.9))


def _pair_rows(tables: dict) -> list[dict]:
    sup = sm.build_suppliers(tables)
    parties = [s for s in sup.values() if sm.eligible(s)]
    ctx = sm.build_context(parties)
    cand, _ = sm.candidate_pairs(parties)
    rows = []
    for i, j in cand:
        a, b = parties[i], parties[j]
        r = sm.score_pair(a, b, ctx)
        r.update(a=a.id, b=b.id, anchor_hit=bool(r["rules"]["A01"] or r["rules"]["A02"]), anchor_conflict=sm._conflicting_anchor(a, b))
        rows.append(r)
    return rows


def training_set(tables: dict, labels: list[dict] | None = None, seed: int = 7) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    rows = _pair_rows(tables)
    given = {frozenset((d["a"], d["b"])): bool(d["duplicate"]) for d in (labels or [])}
    X, y, w = [], [], []
    src = {"steward": 0, "anchor_pos": 0, "anchor_neg": 0}
    negs = []
    for r in rows:
        key = frozenset((r["a"], r["b"]))
        vec = [r["features"][n] for n in sm.FEATURE_NAMES]
        if key in given:
            X.append(vec), y.append(int(given[key])), w.append(LABEL_WEIGHT)
            src["steward"] += 1
        elif r["anchor_hit"] and not r["anchor_conflict"]:
            X.append(vec), y.append(1), w.append(1.0)
            src["anchor_pos"] += 1
        elif r["anchor_conflict"] and not r["anchor_hit"]:
            negs.append(vec)
    # keep the classes in a workable ratio: at most 4 negatives per positive
    random.Random(seed).shuffle(negs)
    keep = negs[: max(4 * max(sum(y), 1), MIN_PER_CLASS)]
    for vec in keep:
        X.append(vec), y.append(0), w.append(1.0)
    src["anchor_neg"] = len(keep)
    return np.array(X, dtype=float), np.array(y), np.array(w), src


def train(tables: dict, labels: list[dict] | None = None, surface_threshold: float = 0.9) -> PairModel:
    X, y, w, src = training_set(tables, labels)
    if min((y == 1).sum(), (y == 0).sum()) < MIN_PER_CLASS:
        raise ValueError(f"Not enough training pairs ({int((y == 1).sum())} positive, {int((y == 0).sum())} negative; "
                         f"need {MIN_PER_CLASS} of each). Supply steward decisions or more anchor-bearing suppliers.")
    pipe = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", C=0.5, max_iter=1000))
    folds = int(min(5, (y == 1).sum(), (y == 0).sum()))
    auc = float(np.mean(cross_val_score(pipe, X, y, cv=folds, scoring="roc_auc"))) if folds >= 2 else None
    pipe.fit(X, y, logisticregression__sample_weight=w)
    return PairModel(pipe, {"positives": int((y == 1).sum()), "negatives": int((y == 0).sum()), "sources": src,
                            "cvAuc": None if auc is None else round(auc, 3), "features": sm.FEATURE_NAMES}, surface_threshold)
