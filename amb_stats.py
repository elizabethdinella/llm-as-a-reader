"""Count ambiguity statuses after calibration, for ambg vs random selection.

For each run, loads the calibrated ambiguities exactly as validate.py does and
counts how many are resolved, untouched (unresolved), or in conflict.
No API calls (model queries are blocked).

Usage (from auto-rubric-eval):
  python amb_stats.py                                  # all Claude RDB runs
  python amb_stats.py "ambg-java-3-t*-claude-opus-5" "random-java-3-t*-claude-opus-5"
Prints per-run counts and per-question means; writes amb_stats.csv.
"""
import contextlib
import csv
import glob
import io
import os
import re
import sys
from collections import Counter, defaultdict

import consts
import utils
import validate
from consts import Mode


def _blocked(*a, **k):
    raise RuntimeError("would call a model")


for name in ("query_cld", "query_gpt", "query_gpt_mini"):
    if hasattr(utils, name):
        setattr(utils, name, _blocked)

patterns = sys.argv[1:] or ["ambg-java-*-t[0-9]-claude-opus-5", "random-java-*-t[0-9]-claude-opus-5",
                            "ambg-py-*-t[0-9]-claude-opus-5", "random-py-*-t[0-9]-claude-opus-5"]
RUN = re.compile(r"^(ambg|random)-(java|py|apcs)-(\w+?)-t(\d+)-(.+)$")

rows = []
for run in sorted({d for p in patterns for d in glob.glob(p) if os.path.isdir(d)}):
    m = RUN.match(run)
    if not m:
        continue
    method, lang, n, trial, model = m.groups()
    mode = Mode.APCS if lang == "apcs" else Mode.RDB
    clang = "java" if lang == "apcs" else lang
    sample_num = int(n) if n.isdigit() else n
    preds_root = os.path.join(run, "round-1", "preds")
    if not os.path.isdir(preds_root):
        print(f"skip {run}: no preds")
        continue
    try:
        consts.set_mode(mode, clang, sample_num)
        with contextlib.redirect_stdout(io.StringIO()):
            _, ambiguities = validate.load(1, preds_root, model)
    except Exception as e:
        print(f"skip {run}: {type(e).__name__}: {e}")
        continue
    c = Counter(getattr(a.status, "name", str(a.status)) for a in ambiguities)
    row = {"run": run, "method": method, "q": f"{lang}{n}", "trial": trial, "total": len(ambiguities), **c}
    rows.append(row)
    print(f"{run:40s} total {len(ambiguities):3d}  " + "  ".join(f"{k} {v}" for k, v in sorted(c.items())))

keys = sorted({k for r in rows for k in r} - {"run", "method", "q", "trial"})
with open("amb_stats.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["run", "method", "q", "trial"] + keys)
    w.writeheader()
    w.writerows(rows)

print("\n=== mean over trials ===")
agg = defaultdict(lambda: defaultdict(list))
for r in rows:
    for k in keys:
        agg[(r["q"], r["method"])][k].append(r.get(k, 0))
print(f"{'q':8} {'method':7} " + " ".join(f"{k:>10}" for k in keys))
for (q, meth), d in sorted(agg.items()):
    print(f"{q:8} {meth:7} " + " ".join(f"{sum(v)/len(v):10.1f}" for k, v in sorted(d.items())))
