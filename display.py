import argparse
import json
import os
import re
import utils
from collections import defaultdict

from models import Ambiguity, Sample, Status
from utils import manually_label


def parse_args():
    parser = argparse.ArgumentParser(description="Show resolved ambiguities for each round")
    parser.add_argument("dir", help="Run directory containing round1/, round2/, ...")
    parser.add_argument("--file", default="ambiguities.json",
                        help="Ambiguities file inside each round dir")
    parser.add_argument("--scratch", default="scratch",
                        help="Directory with the initial per-item ambiguities (<item>.txt)")
    return parser.parse_args()


def round_dirs(run_dir):
    rounds = []
    for name in os.listdir(run_dir):
        m = re.fullmatch(r"round-?(\d+)", name)
        if m and os.path.isdir(os.path.join(run_dir, name)):
            rounds.append((int(m.group(1)), os.path.join(run_dir, name)))
    if not rounds:
        raise SystemExit(f"No round directories found in {run_dir}")
    return sorted(rounds)


def load_scratch(scratch_dir):
    ambiguities = {}
    for fname in sorted(os.listdir(scratch_dir)):
        if not fname.endswith(".txt"):
            continue
        with open(os.path.join(scratch_dir, fname)) as f:
            for d in json.load(f):
                a = Ambiguity.from_dict(d)
                ambiguities[a.id] = a
    return ambiguities


def show_round(round_dir, fname, scratch_dir, few_shot):
    path = os.path.join(round_dir, fname)
    if not os.path.exists(path):
        print(f"##### {round_dir}: missing {fname}\n")
        return

    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = list(data.values())

    # few_shot accumulates across rounds, so this works whether
    # selected.json holds only this round's picks or the cumulative set
    with open(os.path.join(round_dir, "selected.json")) as f:
        selected_samples = [Sample.from_dict(s) for s in json.load(f)]

    for sample in selected_samples:
        if sample in few_shot: continue
        sample = manually_label(sample)
        few_shot.append(sample)

    # fresh objects each round: initial ambiguities, then the round's file on top
    merged = load_scratch(scratch_dir)
    for d in data:
        a = Ambiguity.from_dict(d)
        merged[a.id] = a          # round file wins on id collisions
    ambiguities = list(merged.values())

    # recalibrating from scratch, so ignore any saved status
    for a in ambiguities:
        a.status = Status.UNTOUCHED

    utils.calibrate(few_shot, ambiguities)
    resolved = [a for a in ambiguities if a.is_resolved()]

    by_item = defaultdict(list)
    for a in resolved:
        by_item[a.r_item].append(a)

    print(f"##### {round_dir}: {len(resolved)} of {len(ambiguities)} ambiguities resolved "
          f"({len(few_shot)} labeled samples)\n")
    for item in sorted(by_item):
        print(f"== {item} ==")
        for a in sorted(by_item[item], key=lambda a: a.id):
            print(a.resolved_str())
            print([s.key() for s in a.resolvers])
    print()


def main():
    args = parse_args()
    few_shot = []
    for _, round_dir in round_dirs(args.dir):
        show_round(round_dir, args.file, args.scratch, few_shot)


if __name__ == "__main__":
    main()
