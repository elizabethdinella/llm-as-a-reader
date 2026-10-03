"""Repair judge pred files that hold one {"deducted": ...} object per line.

gpt-oss sometimes writes the 11 judgments as separate lines instead of one JSON
list. If a file has exactly the expected number of objects, they are wrapped in
a list with no decision changed. Files that can't be repaired this way (e.g. a
single object instead of all items) are listed, and deleted with --delete so the
judge regenerates them.

The expected count is the most common list length among the valid files.

Also flags valid lists with the wrong number of items (e.g. 10 instead of 11).

Usage (the pattern is the folder that holds <model>/<n>/score_*.txt):
  python fix_preds.py "llm-judge-java-4-t*-gpt-oss-120"                       # report + repair
  python fix_preds.py "llm-judge-java-4-t*-gpt-oss-120" --delete              # also delete the rest
  python fix_preds.py "random-java-5-t*-gpt-oss-120/round-1/preds/java" --delete   # calibrate preds
"""
import glob
import json
import sys
from collections import Counter

pattern = sys.argv[1]
delete = "--delete" in sys.argv
files = sorted(glob.glob(f"{pattern}/*/*/score_*.txt"))


def load(path):
    try:
        d = json.load(open(path))
        if isinstance(d, list) and all(isinstance(x, dict) and "deducted" in x for x in d):
            return d
    except Exception:
        pass
    return None


lengths = Counter(len(d) for d in map(load, files) if d is not None)
if not lengths and "--n=15" not in sys.argv:
    sys.exit("no valid files to infer the item count from")
expected = 15 if "--n=15" in sys.argv else lengths.most_common(1)[0][0]
print(f"{len(files)} files, expected {expected} judgments each")

repaired, bad = 0, []
for f in files:
    d = load(f)
    if d is not None:
        if len(d) != expected:          # valid JSON but the wrong number of items
            bad.append(f)
        continue
    objs = []
    for line in open(f).read().splitlines():
        line = line.strip().rstrip(",")
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            objs = None
            break
        if isinstance(o, dict) and "deducted" in o:
            objs.append(o)
        elif isinstance(o, list):
            objs = None
            break
    if objs is not None and len(objs) == expected:
        json.dump(objs, open(f, "w"), indent=2)
        repaired += 1
        print("repaired", f)
    else:
        bad.append(f)

for f in bad:
    print(("deleted " if delete else "CANNOT REPAIR ") + f)
    if delete:
        import os
        os.remove(f)

print(f"repaired {repaired}, {'deleted' if delete else 'left'} {len(bad)}")
