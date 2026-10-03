"""Split each mistake generation (5 attempts in one response) into one file per
attempt, keeping only the code inside the <answer> tags.

Run from the folder with apcs-mistakes/ (~/projects/llm-query):
  python split_attempts.py 2
  python split_attempts.py 2 --strip-comments    # also remove // and /* */ comments

Input : apcs-mistakes/q<n>/cluster<k>/<model>/1.txt
Output: apcs-mistakes-split/q<n>/cluster<k>/<model>/attempt<a>.txt   (a = 1..5)
Files that do not split cleanly into 5 attempts are listed and skipped.
"""
import argparse
import glob
import os
import re

ap = argparse.ArgumentParser()
ap.add_argument("q")
ap.add_argument("--src", default="apcs-mistakes")
ap.add_argument("--out", default="apcs-mistakes-split")
ap.add_argument("--attempts", type=int, default=5)
ap.add_argument("--strip-comments", action="store_true")
args = ap.parse_args()

ANSWER = re.compile(r"<answer>(.*?)(?:</answer>|(?=<answer>)|\Z)", re.DOTALL | re.IGNORECASE)  # last one may be unclosed
FENCE = re.compile(r"```[a-zA-Z]*\s*\n(.*?)```", re.DOTALL)
ATTEMPT = re.compile(r"(?i)\battempt\s*#?\s*(\d+)\b")   # "Attempt 3" anywhere in the text


def strip_comments(code):
    code = "\n".join(l for l in code.split("\n") if not l.strip().startswith("//"))
    code = re.sub(r"\n[ \t]*/\*.*?\*/[ \t]*(?=\n)", "", code, flags=re.DOTALL)
    out, i, n = [], 0, len(code)
    while i < n:
        c = code[i]
        if c in "\"'":
            j = i + 1
            while j < n and code[j] != c:
                j += 2 if code[j] == "\\" else 1
            out.append(code[i:j + 1]); i = j + 1
        elif code.startswith("//", i):
            while i < n and code[i] != "\n":
                i += 1
        elif code.startswith("/*", i):
            j = code.find("*/", i + 2)
            i = n if j == -1 else j + 2
        else:
            out.append(c); i += 1
    return "\n".join(l.rstrip() for l in "".join(out).split("\n"))


def code_of(block):
    m = FENCE.search(block)
    code = (m.group(1) if m else block).strip("\n")
    if args.strip_comments:
        code = strip_comments(code)
    return code.strip() + "\n"


def split(text, k):
    """k code strings (one per attempt), or None if unclear."""
    first = {}
    for h in ATTEMPT.finditer(text):
        first.setdefault(int(h.group(1)), h.start())
    if all(i in first for i in range(1, k + 1)):
        starts = [first[i] for i in range(1, k + 1)] + [len(text)]
        if starts == sorted(starts):
            parts = [text[starts[i]:starts[i + 1]] for i in range(k)]
            if all(ANSWER.search(p) for p in parts):
                # several <answer> blocks in one attempt (sub-questions) are joined in order
                return ["\n".join(code_of(b) for b in ANSWER.findall(p)) for p in parts]
    blocks = ANSWER.findall(text)
    if len(blocks) == k:
        return [code_of(b) for b in blocks]
    if len(blocks) == k + 1:          # model restated its first submission before the k attempts
        return [code_of(b) for b in blocks[1:]]
    return None


done, bad = 0, []
for path in sorted(glob.glob(os.path.join(args.src, f"q{args.q}", "cluster*", "*", "*.txt"))):
    parts = split(open(path, errors="replace").read(), args.attempts)
    if parts is None:
        bad.append(path)
        continue
    rel = os.path.relpath(os.path.dirname(path), args.src)          # q<n>/cluster<k>/<model>
    odir = os.path.join(args.out, rel)
    os.makedirs(odir, exist_ok=True)
    for a, code in enumerate(parts, 1):
        with open(os.path.join(odir, f"attempt{a}.txt"), "w") as f:
            f.write(code)
    done += 1

print(f"q{args.q}: split {done} files into {done * args.attempts} attempts -> {args.out}/q{args.q}/")
if bad:
    print(f"Could not split into {args.attempts} attempts (skipped):")
    for p in bad:
        print("  " + p)
