"""Check generated q3 (moreHistoryThanMathAbsences) responses by compiling the
method (plus any helper methods the answer defines) into a test Attendance class and running it on several test cases.

Test data is our own (not the exam's example): shared IDs with more, equal, and
fewer history absences, IDs in only one list, different orders, and empty lists.
It also checks the postcondition that neither list is changed.

Usage:
  python check_q3.py apcs-correct/q3
Needs javac and java on the PATH.
"""
import os
import re
import subprocess
import sys
import tempfile

METHOD = "moreHistoryThanMathAbsences"
CLASS = "Attendance"

COURSE_RECORD = """
public class CourseRecord {
    private String id; private int absences;
    public CourseRecord(String id, int absences) { this.id = id; this.absences = absences; }
    public String getStudentID() { return id; }
    public int getAbsences() { return absences; }
    public String toString() { return id + ":" + absences; }
}
"""

ATTENDANCE = """
import java.util.*;
public class Attendance {
    private ArrayList<CourseRecord> historyList;
    private ArrayList<CourseRecord> mathList;
    public Attendance(ArrayList<CourseRecord> h, ArrayList<CourseRecord> m) { historyList = h; mathList = m; }
%s
}
"""

# (history, math, expected). IDs are built with new String(...) so == comparisons fail
# the way they would on real data.
CASES = [
    ([("a1", 5), ("b2", 3), ("c3", 2), ("d4", 7)], [("c3", 1), ("a1", 2), ("x9", 9), ("d4", 7)], 2),
    ([("a1", 1), ("b2", 1)], [("a1", 1), ("b2", 2)], 0),
    ([("a1", 4)], [("z0", 1)], 0),
    ([], [("a1", 1)], 0),
    ([("a1", 3), ("b2", 6), ("c3", 9)], [("c3", 8), ("b2", 5), ("a1", 2)], 3),
    ([("q1", 2), ("q2", 0), ("q3", 5), ("q4", 1), ("q5", 3), ("q6", 4)],
     [("q6", 4), ("q5", 1), ("q9", 0), ("q3", 6), ("q1", 1), ("q8", 2)], 2),
]


def java_list(name, items):
    adds = "".join(f'{name}.add(new CourseRecord(new String("{i}"), {a})); ' for i, a in items)
    return f"ArrayList<CourseRecord> {name} = new ArrayList<CourseRecord>(); {adds}"


def build_main():
    body = []
    for k, (h, m, exp) in enumerate(CASES):
        body.append("{ " + java_list("h", h) + java_list("m", m) +
                    "String hb = h.toString(), mb = m.toString(); "
                    "int got = new Attendance(h, m)." + METHOD + "(); "
                    f'System.out.println("case {k} " + got + " " + {exp} + " " + '
                    '(hb.equals(h.toString()) && mb.equals(m.toString()))); }')
    return ("import java.util.ArrayList;\npublic class Main { public static void main(String[] a) {\n"
            + "\n".join(body) + "\n} }")


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
            code = text                     # bare code, no tags or fence
    if code is None:
        return None
    fenced = re.search(r"```(?:java)?\s*\n(.*?)```", code, re.DOTALL)
    return fenced.group(1) if fenced else code


def extract_method(code):
    """Pull out just the method (signature through matching brace)."""
    m = re.search(r"(public\s+)?int\s+" + METHOD + r"\s*\([^)]*\)\s*\{", code)
    if not m:
        return None
    depth, i = 0, m.end() - 1
    for j in range(i, len(code)):
        if code[j] == "{":
            depth += 1
        elif code[j] == "}":
            depth -= 1
            if depth == 0:
                return code[m.start():j + 1]
    return None


def methods(code):
    """All method definitions (name -> source), skipping constructors and main."""
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
        if name not in KEYWORDS and rtype not in KEYWORDS and name not in (CLASS, "main") and rtype != "class":
            out.setdefault(name, code[m.start():end])
            pos = end
        else:
            pos = m.end()


def check(method):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "CourseRecord.java"), "w").write(COURSE_RECORD)
        open(os.path.join(d, "Attendance.java"), "w").write(ATTENDANCE % method)
        open(os.path.join(d, "Main.java"), "w").write(build_main())
        c = subprocess.run(["javac", "CourseRecord.java", "Attendance.java", "Main.java"], cwd=d,
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
        for line in r.stdout.split("\n"):
            p = line.split()
            if len(p) == 4 and (p[2] != p[3] or p[4 - 1] == "false"):
                pass
            if len(p) == 5:
                _, k, got, exp, unchanged = p
                if got != exp:
                    fails.append(f"case {k}: got {got}, expected {exp}")
                if unchanged != "true":
                    fails.append(f"case {k}: modified a list")
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
                status, detail = check("\n".join(ms.values()))   # target plus any helpers
            counts[status] = counts.get(status, 0) + 1
            print(f"{status:14s} {model}/{fname}  {detail}")
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
