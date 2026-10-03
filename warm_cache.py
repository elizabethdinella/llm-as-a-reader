"""Fill the ambiguity coverage cache for one question in parallel.

Greedy selection scores every initial ambiguity against every answer, one call
at a time (the "loading G" bar: ~3,000 calls, ~8 hours at 10 s each). Those
results are cached per (backbone, ambiguity, answer), so filling the cache here
with many calls in flight lets calibrate.py read them instead of waiting.

Usage:
  python warm_cache.py 4 java --model claude-opus-5 --workers 16
  python warm_cache.py 4 java --model gpt-oss-120  --workers 4
  python warm_cache.py 2 java --model claude-opus-5 --mode apcs   # APCS question 2
"""
import argparse
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm

import consts
import utils
from consts import Mode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sample_num", type=lambda v: int(v) if v.isdigit() else v)
    ap.add_argument("lang")
    ap.add_argument("--model", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--mode", choices=["rdb", "apcs"], default="rdb")
    args = ap.parse_args()

    mode = Mode.APCS if args.mode == "apcs" else Mode.RDB
    consts.set_mode(mode, args.lang, args.sample_num)
    ambiguities = utils.load_initial_ambiguities(mode, args.model)  # sequential, may generate
    samples = utils.load_samples()

    prefix = consts.get_cache_prefix(args.model)
    todo = []
    for a in ambiguities:
        for s in samples:
            f = os.path.join(prefix, a.id, s.key().replace(" ", "-") + ".txt")
            if not os.path.exists(f):
                todo.append((s, a))

    total = len(ambiguities) * len(samples)
    print(f"{args.mode} {args.lang} {args.sample_num} {args.model}: {len(ambiguities)} ambiguities x "
          f"{len(samples)} answers = {total}; {total - len(todo)} cached, {len(todo)} to score")
    if not todo:
        return

    errors = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(utils.load_or_gen_ambiguity_coverage, s, a, args.model) for s, a in todo]
        for fut in tqdm(as_completed(futs), total=len(futs), desc="warming cache"):
            try:
                fut.result()
            except BaseException as e:  # score_side_* calls sys.exit on a parse failure
                errors += 1
                print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
                if errors == 1:  # full traceback once, so the cause is visible
                    traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)

    print(f"done in {(time.time() - t0) / 60:.1f} min, {errors} errors "
          f"(failed pairs are left uncached; calibrate.py will retry them)")


if __name__ == "__main__":
    main()
