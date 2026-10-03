"""Check generated q4 (GameBoard.getPointsForRow) responses by compiling the
method (plus any helper methods the answer defines) into a test GameBoard class
and running it on several boards.

Test boards are our own (not the exam's example). Colors are built with
new String(...) so comparing colors with == fails the way it would on real data.

Usage:
  python check_q4.py apcs-correct/q4
Needs javac and java on the PATH.
"""
import os
import re
import subprocess
import sys
import tempfile

METHOD = "getPointsForRow"
CLASS = "GameBoard"

SPACE = """
public class Space {
    private String color; private int points;
    public Space(String color, int points) { this.color = color; this.points = points; }
    public String getColor() { return color; }
    public int getPoints() { return points; }
}
"""

GAMEBOARD = """
public class GameBoard {
    private Space[][] board;
    public GameBoard(Space[][] b) { board = b; }
%s
}
"""

# Each board is a list of rows; each cell is (color, points).
B1 = [[("red", 1), ("red", 2), ("red", 3)],
      [("red", 1), ("blue", 2), ("red", 3)],
      [("blue", 5), ("blue", 5), ("green", 5)],
      [("green", 4), ("blue", 4), ("blue", 4)]]
B2 = [[("a", 10), ("a", 20)],
      [("a", 10), ("b", 20)]]
B3 = [[("x", 0), ("x", 7), ("x", 1), ("x", 2), ("x", 3)],
      [("y", 1), ("y", 1), ("y", 1), ("y", 1), ("z", 1)]]
BOARDS = [B1, B2, B3]


def expected(board, r):
    row = board[r]
    s = sum(p for _, p in row)
    return 2 * s if len({c for c, _ in row}) == 1 else s


def build_main():
    parts = []
    for bi, b in enumerate(BOARDS):
        rows = ", ".join("{" + ", ".join(f'new Space(new String("{c}"), {p})' for c, p in row) + "}" for row in b)
        parts.append(f"Space[][] b{bi} = {{{rows}}}; GameBoard g{bi} = new GameBoard(b{bi});")
        for r in range(len(b)):
            parts.append(f'System.out.println("b{bi}r{r} " + g{bi}.{METHOD}({r}) + " {expected(b, r)}");')
    return "public class Main { public static void main(String[] a) {\n" + "\n".join(parts) + "\n} }"


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
    fenced = re.search(r"```(?:java)?\s*\n(.*?)```", code, re.DOTALL)
    return fenced.group(1) if fenced else code


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


def check(body):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "Space.java"), "w").write(SPACE)
        open(os.path.join(d, "GameBoard.java"), "w").write(GAMEBOARD % body)
        open(os.path.join(d, "Main.java"), "w").write(build_main())
        c = subprocess.run(["javac", "Space.java", "GameBoard.java", "Main.java"], cwd=d,
                           capture_output=True, text=True, timeout=60)
        if c.returncode != 0:
            lines = c.stderr.splitlines()
            first = next((l for l in lines if "error" in l), c.stderr.strip()[:120])
            sym = next((l.strip() for l in lines if l.strip().startswith("symbol")), "")
            return "COMPILE ERROR", (first + "  " + sym).strip()
        r = subprocess.run(["java", "Main"], cwd=d, capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            return "RUNTIME ERROR", (r.stderr.strip().splitlines() or [""])[0][:120]
        fails = [f"{k}: got {g}, expected {e}" for k, g, e in
                 (l.split() for l in r.stdout.splitlines() if len(l.split()) == 3) if g != e]
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
