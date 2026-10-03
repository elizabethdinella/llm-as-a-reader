"""Check q1a (Account constructor) answers by compiling the constructor (plus any
helper methods the answer defines) into a test Account class and running it
with our own sets of taken usernames.

Expected behavior: if requestedName is available, username = requestedName;
otherwise username = requestedName + k for the smallest k >= 1 that is available.
isAvailable is a static helper backed by a set of taken names.

Usage:
  python check_q1a.py test/apcs/sub/llms              # checks <model>/answer_1.txt
  python check_q1a.py test/apcs/sub/llms answer_1.txt # explicit file name
Needs javac and java on the PATH.
"""
import os
import re
import subprocess
import sys
import tempfile

CLASS = "Account"

# (requested name, taken names)
CASES = [
    ("bobby", []),
    ("bobby", ["bobby"]),
    ("bobby", ["bobby", "bobby1", "bobby2"]),
    ("ann", ["ann", "ann2"]),           # ann1 free: smallest suffix wins
    ("x9", ["x9", "x91"]),              # name ending in a digit
    ("lee", ["lee1"]),                  # lee itself free
]


def expected(req, taken):
    if req not in taken:
        return req
    k = 1
    while f"{req}{k}" in taken:
        k += 1
    return f"{req}{k}"


ACCOUNT = """
import java.util.*;
public class Account {
    public static Set<String> TAKEN = new HashSet<String>();
    private String username;
    public static boolean isAvailable(String str) { return !TAKEN.contains(str); }
    public String peekUsername() { return username; }
%s
}
"""

KEYWORDS = {"if", "for", "while", "switch", "catch", "synchronized", "return", "new", "else"}
SIG = re.compile(r"(?:(?:public|private|protected|static|final)\s+)*([\w<>\[\],\s]+?)\s+(\w+)\s*\([^)]*\)\s*\{")
CTOR = re.compile(r"(?:public\s+|private\s+|protected\s+)?Account\s*\(\s*String\s+\w+\s*\)\s*\{")


def extract_code(text):
    tags = re.findall(r"<answer>(.*?)(?:</answer>|\Z)", text, re.DOTALL)
    code = "\n".join(tags) if tags else text
    fenced = re.findall(r"```(?:java)?\s*\n(.*?)```", code, re.DOTALL)
    return "\n".join(fenced) if fenced else code


def block(code, start):
    depth = 0
    for j in range(start, len(code)):
        if code[j] == "{":
            depth += 1
        elif code[j] == "}":
            depth -= 1
            if depth == 0:
                return j + 1
    return None


def pieces(code):
    """The Account(String) constructor plus any helper methods."""
    out = []
    m = CTOR.search(code)
    if not m:
        return None
    end = block(code, m.end() - 1)
    if end is None:
        return None
    out.append(code[m.start():end])
    pos = 0
    while True:
        h = SIG.search(code, pos)
        if not h:
            break
        parts = h.group(1).split(); rtype, name = (parts[-1] if parts else ""), h.group(2)
        e = block(code, h.end() - 1)
        if e is None:
            break
        if (rtype and name not in KEYWORDS and rtype not in KEYWORDS and rtype != "class"
                and name not in (CLASS, "main", "isAvailable") and not (m.start() <= h.start() < end)):
            out.append(code[h.start():e])
            pos = e
        else:
            pos = h.end()
    return "\n".join(out)


def build_main():
    lines = []
    for k, (req, taken) in enumerate(CASES):
        names = ", ".join(f'"{t}"' for t in taken)
        lines.append(f'{{ Account.TAKEN = new HashSet<String>(Arrays.asList(new String[]{{{names}}})); '
                     f'Account a = new Account("{req}"); System.out.println("case\\t{k}\\t" + a.peekUsername()); }}')
    return "import java.util.*;\npublic class Main { public static void main(String[] args) {\n" + "\n".join(lines) + "\n} }"


def check(src):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "Account.java"), "w").write(ACCOUNT % src)
        open(os.path.join(d, "Main.java"), "w").write(build_main())
        c = subprocess.run(["javac", "Account.java", "Main.java"], cwd=d, capture_output=True, text=True, timeout=60)
        if c.returncode != 0:
            lines = c.stderr.splitlines()
            first = next((l for l in lines if "error" in l), c.stderr.strip()[:120])
            return "COMPILE ERROR", first.strip()
        try:
            r = subprocess.run(["java", "Main"], cwd=d, capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            return "WRONG", "timeout (infinite loop?)"
        if r.returncode != 0:
            return "RUNTIME ERROR", (r.stderr.strip().splitlines() or [""])[0][:120]
        fails = []
        for line in r.stdout.splitlines():
            p = line.split("\t")
            if len(p) == 3 and p[0] == "case":
                req, taken = CASES[int(p[1])]
                exp = expected(req, taken)
                if p[2] != exp:
                    fails.append(f'"{req}" taken={taken}: got "{p[2]}", expected "{exp}"')
        return ("PASS", "") if not fails else ("WRONG", "; ".join(fails))


def main():
    root = sys.argv[1]
    fname = sys.argv[2] if len(sys.argv) > 2 else "answer_1.txt"
    counts = {}
    for model in sorted(os.listdir(root)):
        f = os.path.join(root, model, fname)
        if not os.path.isfile(f):
            continue
        src = pieces(extract_code(open(f, errors="replace").read()))
        status, detail = ("NO ANSWER", "no Account(String) constructor found") if src is None else check(src)
        counts[status] = counts.get(status, 0) + 1
        print(f"{status:14s} {model}/{fname}  {detail}")
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
