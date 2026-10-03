"""Check generated q1b (getShortenedName) responses by compiling the method
(plus any helper methods the answer defines) into a test Account class and
running it on several usernames.

Test data is our own (not the exam's examples): one hyphen, several hyphens,
a hyphen after a single character, no hyphens, the minimum length (2), and
names with digits. All follow the preconditions (no leading/trailing hyphen,
no consecutive hyphens, length >= 2). It also checks the postcondition that
username is unchanged.

Usage:
  python check_q1b.py test/apcs/apcs-correct/q1b
Needs javac and java on the PATH.
"""
import os
import re
import subprocess
import sys
import tempfile

METHOD = "getShortenedName"
CLASS = "Account"

USERNAMES = ["Bo-Tran", "Jo-Ann-Lu-Kim", "a-b", "Q-Rx", "NoHyphens12", "xy",
             "ab-cd-ef", "Sam9-Lee8", "longname-x", "z-yz-y"]


def expected(u):
    out, i = [], 0
    chars = list(u)
    keep = [True] * len(chars)
    for i, c in enumerate(chars):
        if c == "-":
            keep[i] = False
            if i > 0:
                keep[i - 1] = False
    return "".join(c for c, k in zip(chars, keep) if k)


ACCOUNT = """
import java.util.*;
public class Account {
    private String username;
    public Account(String u, boolean testOnly) { username = u; }
    public static boolean isAvailable(String str) { return true; }
    public String peekUsername() { return username; }
%s
}
"""

KEYWORDS = {"if", "for", "while", "switch", "catch", "synchronized", "return", "new", "else"}
SIG = re.compile(r"(?:(?:public|private|protected|static|final)\s+)*([\w<>\[\],\s]+?)\s+(\w+)\s*\([^)]*\)\s*\{")


def extract_code(text):
    tags = re.findall(r"<answer>(.*?)</answer>", text, re.DOTALL)
    if tags:
        code = "\n".join(tags)
    else:
        blocks = re.findall(r"```(?:java)?\s*\n(.*?)```", text, re.DOTALL)
        code = next((b for b in blocks if METHOD in b), None)
        if code is None and METHOD in text:
            code = text
    if code is None:
        return None
    fenced = re.findall(r"```(?:java)?\s*\n(.*?)```", code, re.DOTALL)
    return "\n".join(fenced) if fenced else code


def methods(code):
    """All method definitions (name -> source), skipping constructors, main, and isAvailable."""
    out, pos = {}, 0
    while True:
        m = SIG.search(code, pos)
        if not m:
            return out
        rtype, name = m.group(1).split()[-1], m.group(2)
        depth, end = 0, None
        for j in range(m.end() - 1, len(code)):
            if code[j] == "{":
                depth += 1
            elif code[j] == "}":
                depth -= 1
                if depth == 0:
                    end = j + 1
                    break
        if end is None:
            return out
        if (name not in KEYWORDS and rtype not in KEYWORDS and rtype != "class"
                and name not in (CLASS, "main", "isAvailable")):
            out.setdefault(name, code[m.start():end])
            pos = end
        else:
            pos = m.end()


def build_main():
    lines = []
    for k, u in enumerate(USERNAMES):
        lines.append(f'{{ Account a = new Account("{u}", true); String got = a.{METHOD}(); '
                     f'System.out.println("case\\t{k}\\t" + got + "\\t" + a.peekUsername().equals("{u}")); }}')
    return "public class Main { public static void main(String[] args) {\n" + "\n".join(lines) + "\n} }"


def check(method_src):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "Account.java"), "w").write(ACCOUNT % method_src)
        open(os.path.join(d, "Main.java"), "w").write(build_main())
        c = subprocess.run(["javac", "Account.java", "Main.java"], cwd=d,
                           capture_output=True, text=True, timeout=60)
        if c.returncode != 0:
            lines = c.stderr.splitlines()
            first = next((l for l in lines if "error" in l), c.stderr.strip()[:120])
            sym = next((l.strip() for l in lines if l.strip().startswith("symbol")), "")
            return "COMPILE ERROR", (first + "  " + sym).strip()
        r = subprocess.run(["java", "Main"], cwd=d, capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            return "RUNTIME ERROR", (r.stderr.strip().splitlines() or [""])[0][:120]
        fails = []
        for line in r.stdout.splitlines():
            p = line.split("\t")
            if len(p) == 4 and p[0] == "case":
                k, got, unchanged = int(p[1]), p[2], p[3]
                exp = expected(USERNAMES[k])
                if got != exp:
                    fails.append(f'"{USERNAMES[k]}": got "{got}", expected "{exp}"')
                if unchanged != "true":
                    fails.append(f'"{USERNAMES[k]}": modified username')
        return ("PASS", "") if not fails else ("WRONG", "; ".join(fails))


def main():
    root = sys.argv[1]
    counts = {}
    for model in sorted(os.listdir(root)):
        mdir = os.path.join(root, model)
        if not os.path.isdir(mdir):
            continue
        for fname in sorted(os.listdir(mdir)):
            text = open(os.path.join(mdir, fname), errors="replace").read()
            code = extract_code(text)
            ms = methods(code) if code else {}
            if code is None:
                status, detail = "NO ANSWER", ""
            elif METHOD not in ms:
                status, detail = "NO METHOD", f"no {METHOD} found in answer"
            else:
                status, detail = check("\n".join(ms.values()))
            counts[status] = counts.get(status, 0) + 1
            print(f"{status:14s} {model}/{fname}  {detail}")
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
