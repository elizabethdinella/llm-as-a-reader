"""Repair coverage-cache files whose side decisions aren't plain objects.

Each cache file should hold [side_a, side_b], each a {"decision": ...} object.
gpt-oss sometimes wraps its answer in a list, so a side comes back as
[{"decision": ...}]. This unwraps those, and deletes any file it can't repair
so calibrate.py regenerates it.

Usage: python fix_cache.py cache-gpt-oss-120/java/4   (or just cache-gpt-oss-120)
"""
import json
import os
import sys


def fix_side(x):
    if isinstance(x, dict) and "decision" in x:
        return x
    if isinstance(x, list) and len(x) >= 1 and isinstance(x[0], dict) and "decision" in x[0]:
        return x[0]
    return None


fixed = deleted = ok = 0
for root, _, files in os.walk(sys.argv[1]):
    for name in files:
        path = os.path.join(root, name)
        try:
            data = json.load(open(path))
            sides = [fix_side(s) for s in data] if isinstance(data, list) and len(data) == 2 else None
        except Exception:
            sides = None
        if sides is None or None in sides:
            os.remove(path)
            deleted += 1
        elif sides != data:
            json.dump(sides, open(path, "w"))
            fixed += 1
        else:
            ok += 1

print(f"ok {ok}, unwrapped {fixed}, deleted {deleted} (will be regenerated)")
