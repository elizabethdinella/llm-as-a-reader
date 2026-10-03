#!/usr/bin/env python3
"""
For every subdirectory present in both A and B, compare each .txt file's JSON
array and report where the "deducted" fields differ between A and B.

Usage: python compare_deducted.py A B [--field deducted]
"""
import argparse
import json
import sys
from pathlib import Path


def load_json_array(path):
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the outermost [...] in case the file has surrounding text
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1:
            raise
        data = json.loads(text[start:end + 1])
    if not isinstance(data, list):
        raise ValueError("top-level JSON is not an array")
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a_dir", type=Path)
    ap.add_argument("b_dir", type=Path)
    ap.add_argument("--field", default="decision")
    args = ap.parse_args()

    a_subdirs = {p.name for p in args.a_dir.iterdir() if p.is_dir()}
    b_subdirs = {p.name for p in args.b_dir.iterdir() if p.is_dir()}
    shared = sorted(a_subdirs & b_subdirs)

    n_files = n_diff_files = n_diff_elems = n_missing = 0

    for sub in shared:
        a_files = {p.name for p in (args.a_dir / sub).glob("*.txt")}
        b_files = {p.name for p in (args.b_dir / sub).glob("*.txt")}

        for name in sorted(a_files ^ b_files):
            side = "A" if name in a_files else "B"
            print(f"[only in {side}] {sub}/{name}")

        for name in sorted(a_files & b_files):
            a_path = args.a_dir / sub / name
            b_path = args.b_dir / sub / name
            try:
                a_arr = load_json_array(a_path)
                b_arr = load_json_array(b_path)
            except (ValueError, json.JSONDecodeError) as e:
                print(f"[parse error] {sub}/{name}: {e}", file=sys.stderr)
                continue

            n_files += 1
            diffs = []
            if len(a_arr) != len(b_arr):
                diffs.append(f"  array length differs: A={len(a_arr)} B={len(b_arr)}")

            for i, (a_el, b_el) in enumerate(zip(a_arr, b_arr)):
                missing = [
                    side for side, el in (("A", a_el), ("B", b_el))
                    if not isinstance(el, dict) or args.field not in el
                ]
                if missing:
                    n_missing += 1
                    if n_missing <= 3:
                        sample = a_el if "A" in missing else b_el
                        keys = list(sample.keys()) if isinstance(sample, dict) else type(sample).__name__
                        print(f"[field missing in {','.join(missing)}] {sub}/{name}[{i}] keys/type: {keys}")
                    continue
                a_val, b_val = a_el[args.field], b_el[args.field]
                if a_val != b_val:
                    diffs.append(f"  [{i}] {args.field}: A={a_val!r} B={b_val!r}")
                    n_diff_elems += 1

            if diffs:
                n_diff_files += 1
                print(f"{sub}/{name}")
                print("\n".join(diffs))

    print(
        f"\nShared dirs: {len(shared)} | files compared: {n_files} | "
        f"files with differences: {n_diff_files} | differing elements: {n_diff_elems} | "
        f"elements missing '{args.field}': {n_missing}"
    )


if __name__ == "__main__":
    main()
