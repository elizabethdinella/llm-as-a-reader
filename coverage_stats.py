"""Accuracy on test responses covered vs not covered by a RESOLVED ambiguity.

A test response is "covered" if it discriminates at least one ambiguity that the
expert labels resolved (status SIDE_A or SIDE_B), i.e. a grading note decides it.
For each ambg run, compares exact-match accuracy of the Reader, the zero-shot
judge, and the few-shot judge on the same covered / uncovered test responses.

No API calls (model queries are blocked). Coverage is computed with
validate.validate by temporarily marking the resolved ambiguities as UNTOUCHED
(validate.validate returns True when a sample discriminates an UNTOUCHED one).

Usage (from auto-rubric-eval):
  python coverage_stats.py                        # Claude RDB Java + Python
  python coverage_stats.py "ambg-java-3-t*-claude-opus-5"
"""
import contextlib
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


def _blocked(*a, **k):
    raise RuntimeError("would call a model")


for name in ("query_cld", "query_gpt", "query_gpt_mini"):
    if hasattr(utils, name):
        setattr(utils, name, _blocked)

patterns = sys.argv[1:] or ["ambg-java-*-t[0-9]-claude-opus-5", "ambg-py-*-t[0-9]-claude-opus-5"]
RUN = re.compile(r"^ambg-(java|py|apcs)-(\w+?)-t(\d+)-(.+)$")


def find_pred(root, model, trial):
    f = glob.glob(os.path.join(root, "**", model, "**", f"score_{trial}_1.txt"), recursive=True)
    return f[0] if f else None


def correct(f_pred, gold):
    try:
        pred = utils.load_preds(f_pred)
        return all(bool(pred[i]) == bool(gold[i]) for i in consts.ITEMS)
    except Exception:
        return None


tot = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # tot[group][method] = [correct, n]
perq = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0])))

for run in sorted({d for p in patterns for d in glob.glob(p) if os.path.isdir(d)}):
    m = RUN.match(run)
    if not m:
        continue
    lang, n, trial, model = m.groups()
    mode = Mode.APCS if lang == "apcs" else Mode.RDB
    clang = "java" if lang == "apcs" else lang
    sample_num = int(n) if n.isdigit() else n
    preds_root = os.path.join(run, "round-1", "preds")
    f_sel = os.path.join(run, "round-1", "selected.json")
    judges = {"judge": f"llm-judge-{lang}-{n}-t{trial}-{model}", "judge-fs": f"llm-judge-fs-{lang}-{n}-t{trial}-{model}"}
    try:
        consts.set_mode(mode, clang, sample_num)
        with contextlib.redirect_stdout(io.StringIO()):
            samples, ambiguities = validate.load(1, preds_root, model)
            Status = type(ambiguities[0].status)
            saved = [a.status for a in ambiguities]
            for a in ambiguities:  # resolved -> UNTOUCHED so validate() reports coverage by resolved ones
                a.status = Status.UNTOUCHED if a.status.name in ("SIDE_A", "SIDE_B") else Status.CONFLICT
            train = {(s["model"], str(s["answer_trial"])) for s in json.load(open(f_sel))}
            for s in samples:
                if (s.model, str(s.answer_trial)) in train:
                    continue
                gold = utils.manually_label(Sample(None, None, s.model, str(s.answer_trial), "1", str(sample_num))).scores
                covered = validate.validate(s, samples, ambiguities, model)
                group = "covered" if covered else "uncovered"
                res = {"reader": correct(find_pred(preds_root, s.model, s.answer_trial) or "", gold)}
                for k, d in judges.items():
                    fp = find_pred(d, s.model, s.answer_trial) if os.path.isdir(d) else None
                    res[k] = correct(fp, gold) if fp else None
                for k, ok in res.items():
                    if ok is None:
                        continue
                    for tgt in (tot[group][k], perq[f"{lang}{n}"][group][k]):
                        tgt[0] += ok
                        tgt[1] += 1
            for a, st in zip(ambiguities, saved):
                a.status = st
    except Exception as e:
        print(f"skip {run}: {type(e).__name__}: {e}")
        continue
    print(f"done {run}")


def fmt(c):
    return f"{100*c[0]/c[1]:5.1f}% ({c[1]:4d})" if c[1] else "      -       "


print("\n=== per question: accuracy (n) ===")
for q in sorted(perq):
    for g in ("covered", "uncovered"):
        d = perq[q][g]
        print(f"{q:7} {g:9} reader {fmt(d['reader'])}  judge {fmt(d['judge'])}  judge-fs {fmt(d['judge-fs'])}")
print("\n=== all questions ===")
for g in ("covered", "uncovered"):
    d = tot[g]
    print(f"{g:9} reader {fmt(d['reader'])}  judge {fmt(d['judge'])}  judge-fs {fmt(d['judge-fs'])}")
