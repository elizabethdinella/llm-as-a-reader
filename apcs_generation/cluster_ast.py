
'''
1. i need to get responses from the models (out)
2. get embeddings for each reponse
3. cluster these responses
4. check!

''' 
import os
import re
from openai import OpenAI
import json
from sklearn.cluster import KMeans, HDBSCAN
import numpy as np
from glob import glob

import tree_sitter_java as tsjava
from tree_sitter import Language, Parser

JAVA = Language(tsjava.language())
_parser = Parser(JAVA)


def parse_method(snippet: str):
    """Parse an arbitrary standalone Java method into its AST subtree.

    Returns (method_declaration node, wrapped source bytes).
    """
    src = snippet.encode() if isinstance(snippet, str) else snippet
    wrapped = b"class _W {\n" + src + b"\n}"
    tree = _parser.parse(wrapped)

    method = _find_first(tree.root_node, "method_declaration")
    if method is None:
        # fallback: bare statement body with no signature
        wrapped = b"class _W { void _m() {\n" + src + b"\n} }"
        tree = _parser.parse(wrapped)
        method = _find_first(tree.root_node, "method_declaration")

    return method, wrapped


def _find_first(node, type_name):
    if node.type == type_name:
        return node
    for c in node.children:
        r = _find_first(c, type_name)
        if r is not None:
            return r
    return None


def dump(node, src, depth=0):
    text = src[node.start_byte:node.end_byte].decode(errors="replace")
    leaf = repr(text) if node.child_count == 0 else ""
    print("  " * depth + f"{node.type} {leaf}".rstrip())
    for c in node.named_children:
        dump(c, src, depth + 1)


def to_string(node, src, idmap):
    if node.child_count == 0:
        if node.type == "identifier":
            name = src[node.start_byte:node.end_byte].decode()
            return f"(identifier {idmap.setdefault(name, f'ID{len(idmap)}')})"
        #if node.type in ("string_literal", "string_fragment", "character_literal",
        #                 "decimal_integer_literal", "decimal_floating_point_literal",
        #                 "hex_integer_literal", "true", "false", "null_literal"):
        #    return f"(<{node.type}>)"
        text = src[node.start_byte:node.end_byte].decode(errors="replace")
        return f"({node.type} {text})"

    inner = " ".join(to_string(c, src, idmap) for c in _named_children(node))
    return f"({node.type} {inner})"

#Filter out comments
def _named_children(node):
    return [c for c in node.named_children if c.type not in ("comment", "line_comment", "block_comment")]

def normalize_text(text):
    #text = unicodedata.normalize('NFC', text)
    # Replace newlines, tabs, and multiple spaces with a single space
    text = text.lower()
    text = text.replace("```java","")
    text = text.replace("```","")
    text = text.replace("<answer>","")
    text = text.replace("</answer>","")
    text = re.sub(r'\s+', ' ', text)
    # Strip leading and trailing whitespace
    return text.strip()

client = OpenAI()

MODELS = ["gpt-4.1", "gpt-5", "gpt-mini-120", "gpt-mini-20", "gpt-o3", "deepseek-r1-70b", "claude-opus-5", "claude-opus-4.8", "claude-fable-5", "claude-sonnet-5", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-3.6-flash", "grok-4.5", "grok-4", "grok-3", "qwen3-coder", "qwen3", "mistral-large", "llama-scout-4", "llama3.3-70"]

LANGS = ["python", "java", "c++"]

data = {}
embeddings = []
metadata = []
def generate_embedding(content, dims: int=1536):
  resp = client.embeddings.create(
    model="text-embedding-3-large",
    input=content,
    dimensions=dims
  )
  return resp.data[0].embedding


#for file_path in glob("data/apcs/sub/mistakes/cluster*/*/answer_*.txt"):
for MODEL in MODELS:
    
    #MODEL = file_path.split(os.sep)[-2]
    data[MODEL] = {}
   # for SAMPLE_NUM in range(1, 6):
   #     for TRIAL in range(1, 4):
    #file_path = f"test/a-levels/sub/{MODEL}/answer_3.txt" 
    file_path = f"data/apcs/sub/llms/{MODEL}/answer_1.txt" 

    print(file_path)

    if not os.path.exists(file_path):
        print("skipping", file_path)
        continue

    with open(file_path, "r") as file:
        raw_content = file.read()

    content = normalize_text(raw_content)
    method, wrapped = parse_method(content)
    #dump(method, wrapped)
    #print(to_string(method, wrapped, idmap={}))

    embedding = generate_embedding(to_string(method, wrapped, idmap={}))
    data[MODEL] = embedding
    embeddings.append(embedding)
    metadata.append({
        "model": MODEL,
        "function": raw_content,
        #"ast": to_string(method, wrapped)
    })


X = np.array(embeddings)
X = X / np.linalg.norm(X, axis=1, keepdims=True)

labels = HDBSCAN(min_cluster_size=2,
            metric="euclidean").fit_predict(X)

# Reassign outliers to nearest cluster centroid
valid = labels != -1
if valid.any():
    cluster_ids = sorted(set(labels[valid]))
    centroids = np.array([X[labels == c].mean(axis=0) for c in cluster_ids])
    for i in np.where(labels == -1)[0]:
        labels[i] = cluster_ids[np.argmax(centroids @ X[i])]

reps = []
for c in sorted(set(labels)):
    idxs = np.where(labels == c)
    idx = idxs[0]
    #if c == -1:
    #    reps.extend(metadata[i] for i in idx)   # outliers = unique approaches
    #else:
    sub = X[idx]
    centroid = sub.mean(axis=0)
    medoid = idx[np.argmax(sub @ centroid)]

    _all = [metadata[i] for i in idxs[0].tolist() if not i == medoid]
    reps.append({"rep": metadata[medoid], "all": _all})

reps_str = ""
print("TOTAL CLUSTERS: ", len(reps))
print("REPRESENTATIVE SAMPLES==============")
for elem in reps:
    sample = elem["rep"]
    others = elem["all"]
    print(f"{len(others)+1} samples in this cluster")
    print(sample["model"])
    print(sample["function"])
    print("others:")
    for other in others:
        print("\t" + other["model"])
        print("\t" + other["function"])
        print()

    print()
    reps_str += "FUNC: " + sample["function"] + "\n"
    

'''
prompt = "Can you describe the differences between these representative samples : " + reps_str

messages = [
        {"role": "user", "content": prompt}
] 

response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0,
        max_tokens=1024,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0)

print(response.choices[0].message.content.replace("\n", ""))
'''


with open("apcs_generation/cluster_embeddings.json", "w") as f:
    json.dump(data, f, indent = 4)
