"""Normalize judge outputs to a JSON list of {"deducted": ...}, in rubric order (the format eval.py reads).

Handles outputs like
  {"1: Declares class header": {"deducted": false}, "2: ...": {"deducted": true}}
  Explanation: ...
by taking the first JSON value in the file. No decision is changed; the
explanation text is dropped. Files already in the expected format are left alone.
Files it can't parse are listed.

Usage:
  python fix_judge_format.py "llm-judge-apcs-2-t*-claude-opus-5" test/apcs/rubric_2.json
"""
import glob
import json
import sys

pattern, f_rubric = sys.argv[1], sys.argv[2]
items = [k.split(":", 1)[0].strip() for k in json.load(open(f_rubric))]
dec = json.JSONDecoder()


def first_json(text):
    for i, ch in enumerate(text):
        if ch in "[{":
            try:
                return dec.raw_decode(text[i:])[0]
            except ValueError:
                continue
    return None


def already_ok(text):
    try:
        d = json.loads(text)
    except ValueError:
        return False
    return isinstance(d, list) and len(d) == len(items) and all(isinstance(o, dict) and "deducted" in o for o in d)


fixed, ok, bad = 0, 0, []
for f in sorted(glob.glob(f"{pattern}/*/*/score_*.txt")):
    text = open(f, errors="replace").read()
    if already_ok(text):
        ok += 1
        continue
    v = first_json(text)
    out = None
    if isinstance(v, dict) and all(isinstance(x, dict) and "deducted" in x for x in v.values()):
        by_id = {k.split(":", 1)[0].strip(): x["deducted"] for k, x in v.items()}
        if all(it in by_id for it in items):
            out = [by_id[it] for it in items]
        elif len(v) == len(items):
            out = [x["deducted"] for x in v.values()]
    elif isinstance(v, list) and len(v) == len(items) and all(isinstance(x, dict) and "deducted" in x for x in v):
        out = [x["deducted"] for x in v]
    if out is None:  # one {"deducted": ...} per line
        objs = []
        for l in text.splitlines():
            try:
                o = json.loads(l.strip().rstrip(","))
            except ValueError:
                continue
            if isinstance(o, dict) and "deducted" in o:
                objs.append(o["deducted"])
        if len(objs) == len(items):
            out = objs
    if out is None:
        bad.append(f)
        continue
    json.dump([{"deducted": bool(d)} for d in out], open(f, "w"), indent=2)
    fixed += 1

for f in bad:
    print("CANNOT PARSE", f)
print(f"{ok} already ok, {fixed} fixed, {len(bad)} unparseable")
