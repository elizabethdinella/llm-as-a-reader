"""Cluster the APCS responses for one question and pick one representative per
cluster as a seed for incorrect-variant generation.

Same AST approach as cluster_ast.py: parse with tree-sitter, serialize the AST
as an s-expression with identifiers renamed ID0, ID1, ... (comments skipped),
embed it with text-embedding-3-large, cluster with HDBSCAN (min_cluster_size=2,
outliers to nearest centroid). Changes for APCS:
  - the whole answer is serialized (constructor, all methods, helper methods),
    not just the first method_declaration
  - `this.x` is treated the same as `x`
  - responses with identical ASTs are grouped before embedding
  - results are written to files

Usage:
  python cluster_apcs.py test/apcs/apcs-correct/q2

Writes:
  <root>_clusters.json      clusters: rep + members (model, file, code, canonical)
  apcs-seeds/q<n>/<model>.txt  original code of each representative
"""
import json
import os
import re
import sys
from collections import OrderedDict

import numpy as np
from openai import OpenAI
from sklearn.cluster import HDBSCAN
import tree_sitter_java as tsjava
from tree_sitter import Language, Parser

root = sys.argv[1]
q = os.path.basename(os.path.normpath(root))
seed_dir = os.path.join("apcs-seeds", q)
out_json = os.path.normpath(root) + "_clusters.json"

JAVA = Language(tsjava.language())
_parser = Parser(JAVA)
SKIP = ("comment", "line_comment", "block_comment")


def extract_code(text):
    tags = re.findall(r"<answer>(.*?)</answer>", text, re.DOTALL)
    if tags:
        code = "\n".join(tags)
    else:
        blocks = re.findall(r"```(?:java)?\s*\n(.*?)```", text, re.DOTALL)
        code = max(blocks, key=len) if blocks else text
    fenced = re.search(r"```(?:java)?\s*\n(.*?)```", code, re.DOTALL)
    return (fenced.group(1) if fenced else code).strip()


def parse(code):
    """Parse a whole answer: a full class as-is, else wrap methods in a class."""
    src = code.encode()
    tree = _parser.parse(src)
    if tree.root_node.has_error or not any(c.type == "class_declaration" for c in tree.root_node.children):
        src = b"class _W {\n" + code.encode() + b"\n}"
        tree = _parser.parse(src)
    return tree.root_node, src


def to_string(node, src, idmap):
    """AST as an s-expression, identifiers renamed ID0, ID1, ... (as in cluster_ast.py).
    Covers the whole answer (constructors, all methods, helpers), skips comments,
    and treats `this.x` the same as `x`."""
    if node.type == "field_access" and node.named_child_count == 2 and node.named_children[0].type == "this":
        return to_string(node.named_children[1], src, idmap)
    if node.child_count == 0:
        text = src[node.start_byte:node.end_byte].decode(errors="replace")
        if node.type == "identifier":
            return f"(identifier {idmap.setdefault(text, f'ID{len(idmap)}')})"
        return f"({node.type} {text})"
    inner = " ".join(to_string(c, src, idmap) for c in node.named_children if c.type not in SKIP)
    return f"({node.type} {inner})"


def canonical(code):
    root_node, src = parse(code)
    return to_string(root_node, src, {})


files = sorted(f"{m}/{f}" for m in os.listdir(root) if os.path.isdir(os.path.join(root, m))
               for f in os.listdir(os.path.join(root, m)))
print(f"{len(files)} responses under {root}")

# 1. Group identical canonical forms.
forms = OrderedDict()
for rel in files:
    model, fname = rel.split("/", 1)
    code = extract_code(open(os.path.join(root, rel), errors="replace").read())
    canon = canonical(code)
    forms.setdefault(canon, []).append({"model": model, "file": fname, "code": code, "canonical": canon})
print(f"{len(forms)} distinct ASTs")

groups = list(forms.values())
canons = list(forms.keys())

# 2. Cluster the distinct forms by embedding (skip if there are too few).
if len(canons) >= 3:
    client = OpenAI()
    X = np.array([client.embeddings.create(model="text-embedding-3-large", input=c,
                                           dimensions=1536).data[0].embedding for c in canons])
    X = X / np.linalg.norm(X, axis=1, keepdims=True)
    labels = HDBSCAN(min_cluster_size=2, metric="euclidean").fit_predict(X)
    valid = labels != -1
    if valid.any():
        ids = sorted(set(labels[valid]))
        cents = np.array([X[labels == c].mean(axis=0) for c in ids])
        for i in np.where(~valid)[0]:
            labels[i] = ids[int(np.argmax(cents @ X[i]))]
    else:
        labels = np.arange(len(canons))
else:
    X = None
    labels = np.arange(len(canons))

# 3. Representative per cluster: the most common canonical form in it
#    (ties broken by closeness to the centroid), and its first response.
clusters = []
for c in sorted(set(labels)):
    idx = [i for i in range(len(canons)) if labels[i] == c]
    if X is not None:
        cent = X[idx].mean(axis=0)
        best = max(idx, key=lambda i: (len(groups[i]), float(X[i] @ cent)))
    else:
        best = max(idx, key=lambda i: len(groups[i]))
    members = [r for i in idx for r in groups[i]]
    rep = groups[best][0]
    clusters.append({"cluster": int(c), "size": len(members), "distinct_forms": len(idx),
                     "rep": rep, "members": [m for m in members if m is not rep]})
clusters.sort(key=lambda c: -c["size"])

json.dump(clusters, open(out_json, "w"), indent=2)
os.makedirs(seed_dir, exist_ok=True)
for f in os.listdir(seed_dir):
    os.remove(os.path.join(seed_dir, f))
for c in clusters:
    with open(os.path.join(seed_dir, f"{c['rep']['model']}.txt"), "w") as f:
        f.write(c["rep"]["code"] + "\n")

print(f"\n{len(clusters)} clusters")
for c in clusters:
    others = ", ".join(m["model"] for m in c["members"]) or "-"
    print(f"  size {c['size']:2d} ({c['distinct_forms']} distinct ASTs)  rep {c['rep']['model']:18s} others: {others}")
print(f"\nWrote {out_json} and {len(clusters)} seeds to {seed_dir}/")
