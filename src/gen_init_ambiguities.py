"""Generate (or load, if already there) the initial ambiguities for one question,
without scoring anything. Prints how many each rubric item got.

Usage:
  python gen_ambiguities.py 2 java --mode apcs --model claude-opus-5
Writes scratch-apcs/java/2/<item>.txt (APCS) or scratch/java/<n>/<item>.txt (RDB).
"""
import argparse
import json
import os

import consts
import utils
from consts import Mode

ap = argparse.ArgumentParser()
ap.add_argument("sample_num", type=lambda v: int(v) if v.isdigit() else v)
ap.add_argument("lang")
ap.add_argument("--mode", choices=["rdb", "apcs"], default="apcs")
ap.add_argument("--model", default="claude-opus-5")
args = ap.parse_args()

mode = Mode.APCS if args.mode == "apcs" else Mode.RDB
consts.set_mode(mode, args.lang, args.sample_num)
d = f"{consts.get_initial_ambiguity_dir()}/{consts.lang}/{consts.sample_num}"
os.makedirs(d, exist_ok=True)
print(f"Rubric items: {consts.ITEMS}")

ambiguities = utils.load_initial_ambiguities(mode, args.model)

print(f"\n{len(ambiguities)} ambiguities in {d}/")
for item in consts.ITEMS:
    f = os.path.join(d, f"{item}.txt")
    n = len(json.load(open(f))) if os.path.exists(f) else 0
    print(f"  item {item}: {n}")
