"""Check generated q2 (Bottle) responses by compiling them and running the
question's worked example.

For each model folder under the response root, extracts the answer (from
<answer> tags, or else the ```java block containing "class Bottle"), compiles
it with a test Main that replays the example table, and compares the returned
values with the expected ones.

Usage:
  python check_q2.py apcs-correct/q2
Needs javac and java on the PATH.
"""
import os
import re
import subprocess
import sys
import tempfile

EXPECTED = [600.0, 500.0, 1000.0, 10.0, 40.0]

MAIN = """
public class Main {
    public static void main(String[] args) {
        double amt;
        Bottle water = new Bottle(1000.0);
        amt = water.updateAmount(400.0); System.out.println(amt);
        amt = water.updateAmount(100.0); System.out.println(amt);
        amt = water.updateAmount(300.0); System.out.println(amt);
        Bottle shampoo = new Bottle(40.0);
        amt = shampoo.updateAmount(30.0); System.out.println(amt);
        amt = shampoo.updateAmount(1.0);  System.out.println(amt);
    }
}
"""


def extract_answer(text, must_contain):
    tags = re.findall(r"<answer>(.*?)</answer>", text, re.DOTALL)
    if tags:
        code = "\n".join(t.strip() for t in tags)
    else:
        blocks = re.findall(r"```(?:java)?\s*\n(.*?)```", text, re.DOTALL)
        code = next((b for b in blocks if must_contain in b), None)
    if code is None:
        return None
    # Tags sometimes wrap a ```java fence; strip it.
    fenced = re.search(r"```(?:java)?\s*\n(.*?)```", code, re.DOTALL)
    return (fenced.group(1) if fenced else code).strip()


def check(code):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "Bottle.java"), "w").write(code)
        open(os.path.join(d, "Main.java"), "w").write(MAIN)
        c = subprocess.run(["javac", "Bottle.java", "Main.java"], cwd=d,
                           capture_output=True, text=True, timeout=60)
        if c.returncode != 0:
            first = next((l for l in c.stderr.splitlines() if "error" in l), c.stderr.strip()[:120])
            return "COMPILE ERROR", first
        r = subprocess.run(["java", "Main"], cwd=d, capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            return "RUNTIME ERROR", (r.stderr.strip().splitlines() or [""])[0][:120]
        try:
            got = [float(x) for x in r.stdout.split()]
        except ValueError:
            return "BAD OUTPUT", r.stdout.strip()[:120]
        if len(got) == len(EXPECTED) and all(abs(a - b) < 1e-6 for a, b in zip(got, EXPECTED)):
            return "PASS", ""
        return "WRONG", f"got {got}, expected {EXPECTED}"


def main():
    root = sys.argv[1]
    counts = {}
    for model in sorted(os.listdir(root)):
        mdir = os.path.join(root, model)
        if not os.path.isdir(mdir):
            continue
        for fname in sorted(os.listdir(mdir)):
            text = open(os.path.join(mdir, fname), errors="replace").read()
            code = extract_answer(text, "class Bottle")
            if code is None:
                status, detail = "NO ANSWER", ""
            elif "class Bottle" not in code:
                status, detail = "NO CLASS", "answer has no 'class Bottle'"
            else:
                status, detail = check(code)
            counts[status] = counts.get(status, 0) + 1
            print(f"{status:14s} {model}/{fname}  {detail}")
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
