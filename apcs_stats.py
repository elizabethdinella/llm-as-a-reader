"""Diversity statistics for the APCS response set, from each question's manual.csv.

Usage (from ~/projects/auto-rubric-eval):
  python apcs_stats.py            # 1a 1b 2 3 4
Prints, per question: responses, rubric items, items deducted at least once,
distinct deduction patterns, responses with no deduction, mean deductions per response.
"""
import csv
import json
import os
import sys
from collections import Counter

QS = sys.argv[1:] or ["1a", "1b", "2", "3", "4"]
ROOT = "test/apcs"

print(f"{'Q':4} {'resp':>4} {'items':>5} {'covered':>7} {'patterns':>8} {'none':>4} {'mean ded':>8}  top pattern")
tot = Counter()
for q in QS:
    items = [k.split(":", 1)[0].strip() for k in json.load(open(os.path.join(ROOT, f"rubric_{q}.json")))]
    models = set(os.listdir(os.path.join(ROOT, "sub", "mistakes", q))) - {"manual.csv"}
    pats, per_item = Counter(), Counter()
    n = 0
    for row in csv.DictReader(open(os.path.join(ROOT, "sub", "mistakes", q, "manual.csv"))):
        name = row["model name"].strip()
        folder = name if name.startswith("gpt-") else name.replace(" ", "-")
        if not any(m.lower() == folder.lower() or m.lower().startswith(folder.lower()) for m in models):
            continue  # rows for responses no longer in the set
        ded = tuple(sorted(x.strip() for x in row["rubric items deducted"].split(",") if x.strip()))
        pats[ded] += 1
        per_item.update(ded)
        n += 1
    covered = sum(1 for it in items if per_item[it] > 0)
    none = pats[()]
    mean = sum(len(p) * c for p, c in pats.items()) / n if n else 0
    top, topc = pats.most_common(1)[0]
    print(f"{q:4} {n:4} {len(items):5} {covered:4}/{len(items):<2} {len(pats):8} {none:4} {mean:8.2f}  "
          f"{','.join(top) or 'none'} ({topc}/{n})")
    print(f"     per item: " + ", ".join(f"{it}:{per_item[it]}" for it in items))
    tot.update(resp=n, items=len(items), covered=covered, patterns=len(pats), none=none)
print(f"all  {tot['resp']:4} {tot['items']:5} {tot['covered']:4}/{tot['items']:<2} {tot['patterns']:8} {tot['none']:4}")
