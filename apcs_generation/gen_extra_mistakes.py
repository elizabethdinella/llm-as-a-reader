"""Generate five more incorrect variants for a cluster, from a cluster member other
than the representative. The member is shown its OWN correct answer as its
"first submission" (same prompt as gen_mistakes.py).

Run from ~/projects/llm-query (the folder with eval.py):
  python gen_extra_mistakes.py 3 1 gemini-2.5-pro 2 qwen3
     -> q3: cluster1 gets gemini-2.5-pro's mistakes, cluster2 gets qwen3's
Cluster numbers are the folder numbers (cluster1, cluster2, ...), i.e. the
position in q<n>_clusters.json starting at 1.

Output: apcs-mistakes/q<n>/cluster<k>/<model>/1.txt
"""
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

# Same prompt as gen_mistakes.py (copied, since importing it would run it)
PROMPT = """You are computer science student taking a college level exam in Java. Answer each sub-question and explain your answer. Put your final answer to each sub-question (only including the required code response) in <answer> tags. Do not include anything (e.g. comments) indicating what your mistakes are in the final answer.

Here is your first submission:
{code}


Take the exam five times making increasingly severe mistakes in each attempt. Your mistakes should be edits to your first submission. Make sure your mistakes are realistic.
"""

QDIR = "data/apcs"
n = sys.argv[1]
pairs = list(zip(sys.argv[2::2], sys.argv[3::2]))


def own_answer(model):
    d = os.path.join(QDIR, "apcs-correct", f"q{n}", model)
    files = sorted(f for f in os.listdir(d) if f.endswith(".txt"))
    text = open(os.path.join(d, files[0]), errors="replace").read()
    tags = re.findall(r"<answer>(.*?)(?:</answer>|\Z)", text, re.DOTALL)
    code = "\n".join(tags) if tags else text
    fenced = re.findall(r"```(?:java)?\s*\n(.*?)```", code, re.DOTALL)
    return ("\n".join(fenced) if fenced else code).strip()


def run(pair):
    k, model = pair
    task_dir = os.path.join("apcs-mistake-tasks", f"q{n}")
    os.makedirs(task_dir, exist_ok=True)
    task = os.path.join(task_dir, f"cluster{k}-{model}.txt")
    open(task, "w").write(PROMPT.format(code=own_answer(model)))
    out = os.path.join("apcs-mistakes", f"q{n}", f"cluster{k}")
    os.makedirs(out, exist_ok=True)
    if os.path.exists(os.path.join(out, model, "1.txt")):
        return f"skip   cluster{k} {model}: already generated"
    log = f"logs/gen-extra-q{n}-cluster{k}-{model}.log"
    os.makedirs("logs", exist_ok=True)
    with open(log, "w") as lf:
        r = subprocess.run(["python", "eval.py", model, os.path.join(QDIR, f"q{n}.txt"), task, out, "1"],
                           stdout=lf, stderr=subprocess.STDOUT)
    ok = r.returncode == 0 and os.path.exists(os.path.join(out, model, "1.txt"))
    return f"{'done  ' if ok else 'FAILED'} cluster{k} {model}" + ("" if ok else f" (see {log})")


with ThreadPoolExecutor(len(pairs)) as ex:
    for line in ex.map(run, pairs):
        print(line, flush=True)
