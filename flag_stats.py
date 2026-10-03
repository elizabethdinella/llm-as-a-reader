"""Measure the flagging mode: does "flag a test sample when an unresolved
ambiguity applies to it" catch the samples the Reader gets wrong?

For each ambg run, recomputes flags offline exactly as validate.py does
(calibrate on the run's selected.json, then flag a sample if any UNTOUCHED
ambiguity covers it in G), and compares with exact-match correctness on the
test samples.

No API calls: all model-query functions are disabled. If a run would need one
(uncached decision), it is reported and skipped.

Usage (from auto-rubric-eval):
  python flag_stats.py                          # all ambg runs (Java, Python, APCS)
  python flag_stats.py "ambg-java-3-t*-claude-opus-5"
Writes flag_stats.csv (one row per run) and prints per-question means.
"""
import contextlib
import csv
import glob
import io
import json
import os
import re
import sys
from collections import defaultdict

import consts
import utils
import validate
from consts import Mode
from models import Sample


class NoAPI(Exception):
    pass


def _blocked(*a, **k):
    raise NoAPI("would call a model")


for name in ("query_cld", "query_gpt", "query_gpt_mini"):
    if hasattr(utils, name):
        setattr(utils, name, _blocked)

pattern = sys.argv[1] if len(sys.argv) > 1 else "ambg-*-t[0-9]-*"
RUN = re.compile(r"^ambg-(java|py|apcs)-(\w+?)-t(\d+)-(.+)$")

rows = []
for run in sorted(d for d in glob.glob(pattern) if os.path.isdir(d)):
    m = RUN.match(run)
    if not m:
        continue
    lang, n, trial, model = m.groups()
    mode = Mode.APCS if lang == "apcs" else Mode.RDB
    clang = "java" if lang == "apcs" else lang
    sample_num = int(n) if n.isdigit() else n
    f_sel = os.path.join(run, "round-1", "selected.json")
    preds_root = os.path.join(run, "round-1", "preds")
    if not os.path.exists(f_sel) or not os.path.isdir(preds_root):
        print(f"skip {run}: no selected.json or preds")
        continue
    try:
        consts.set_mode(mode, clang, sample_num)
        with contextlib.redirect_stdout(io.StringIO()):
            # validate.load expects <run>/round-1/preds as its eval dir (it takes .parent.parent)
            samples, ambiguities = validate.load(1, preds_root, model)
            train = {(s["model"], str(s["answer_trial"])) for s in json.load(open(f_sel))}
            stats = defaultdict(int)
            for s in samples:
                if (s.model, str(s.answer_trial)) in train:
                    continue
                f_pred = glob.glob(os.path.join(preds_root, "*", s.model, "*", f"score_{s.answer_trial}_1.txt"))
                if not f_pred:
                    stats["missing_pred"] += 1
                    continue
                pred = utils.load_preds(f_pred[0])
                gold = utils.manually_label(Sample(None, None, s.model, str(s.answer_trial), "1", str(sample_num))).scores
                correct = all(bool(pred[i]) == bool(gold[i]) for i in consts.ITEMS)
                flagged = validate.validate(s, samples, ambiguities, model)
                stats[("flag" if flagged else "noflag", "right" if correct else "wrong")] += 1
    except NoAPI:
        print(f"skip {run}: would need an API call (uncached decision)")
        continue
    except Exception as e:
        print(f"skip {run}: {type(e).__name__}: {e}")
        continue

    tp, fp = stats[("flag", "wrong")], stats[("flag", "right")]
    fn, tn = stats[("noflag", "wrong")], stats[("noflag", "right")]
    total = tp + fp + fn + tn
    if total == 0:
        print(f"skip {run}: no test samples scored")
        continue
    row = {
        "run": run, "question": f"{lang} {n}", "model": model, "trial": trial, "n_test": total,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "accuracy": (fp + tn) / total,
        "flag_rate": (tp + fp) / total,
        "flag_recall": tp / (tp + fn) if tp + fn else float("nan"),
        "flag_precision": tp / (tp + fp) if tp + fp else float("nan"),
        "acc_unflagged": tn / (fn + tn) if fn + tn else float("nan"),
        "acc_with_review": (tp + fp + tn) / total,   # flagged samples fixed by a human
        "missing_pred": stats["missing_pred"],
    }
    rows.append(row)
    print(f"{run:45s} n={total:3d} acc={row['accuracy']:.3f} flag_rate={row['flag_rate']:.3f} "
          f"recall={row['flag_recall']:.3f} precision={row['flag_precision']:.3f} "
          f"acc_unflagged={row['acc_unflagged']:.3f} acc_with_review={row['acc_with_review']:.3f}")

if rows:
    with open("flag_stats.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print("\n=== Mean over trials ===")
    keys = ["accuracy", "flag_rate", "flag_recall", "flag_precision", "acc_unflagged", "acc_with_review"]
    print(f"{'question':10s} {'model':14s} " + " ".join(f"{k:>15s}" for k in keys))
    groups = defaultdict(list)
    for r in rows:
        groups[(r["question"], r["model"])].append(r)
    for (q, mdl), rs in sorted(groups.items()):
        vals = []
        for k in keys:
            xs = [r[k] for r in rs if r[k] == r[k]]   # drop NaN
            vals.append(sum(xs) / len(xs) if xs else float("nan"))
        print(f"{q:10s} {mdl:14s} " + " ".join(f"{v:15.3f}" for v in vals))
    print("\nWrote flag_stats.csv")
