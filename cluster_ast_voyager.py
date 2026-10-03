
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
import voyageai
from sklearn.cluster import KMeans
import numpy as np

import tree_sitter_java as tsjava
from tree_sitter import Language, Parser

JAVA = Language(tsjava.language())
_parser = Parser(JAVA)

vo = voyageai.Client()


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

    inner = " ".join(to_string(c, src, idmap) for c in node.named_children)
    return f"({node.type} {inner})"

def normalize_text(text):
    #text = unicodedata.normalize('NFC', text)
    # Replace newlines, tabs, and multiple spaces with a single space
    text = text.lower()
    text = text.replace("<answer>","")
    text = text.replace("</answer>","")
    text = re.sub(r'\s+', ' ', text)
    # Strip leading and trailing whitespace
    return text.strip()

#client = OpenAI()

MODELS = ["gpt-4.1", "gpt-5", "gpt-mini-120", "gpt-mini-20", "gpt-o3", "deepseek-r1-70b", "claude-opus-5", "claude-opus-4.8", "claude-fable-5", "claude-sonnet-5", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-3.6-flash", "grok-4.5", "grok-4", "grok-3", "qwen3-coder", "qwen3", "mistral-large", "llama-scout-4", "llama3.3-70"]

LANGS = ["python", "java", "c++"]

data = {}
embeddings = []
metadata = []

def generate_embedding(content, dims: int=1536):
  resp = vo.embed(
    model="voyage-code-3",
    texts=[content]#,
    #dimensions=dims
  )
  return resp.embeddings


for MODEL in MODELS:
    data[MODEL] = {}
   # for SAMPLE_NUM in range(1, 6):
   #     for TRIAL in range(1, 4):
    file_path = f"test/a-levels/sub/{MODEL}/answer_4.txt" 

    if not os.path.exists(file_path):
        print("skipping", file_path)
        continue

    with open(file_path, "r") as file:
        raw_content = file.read()

    content = normalize_text(raw_content)
    method, wrapped = parse_method(content)
    #dump(method, wrapped)
    print(to_string(method, wrapped, idmap={}))

    embedding = generate_embedding(to_string(method, wrapped, idmap={}))
    data[MODEL] = embedding
    embeddings.append(embedding)
    metadata.append({
        "model": MODEL,
        "function": raw_content,
        #"ast": to_string(method, wrapped)
    })

X = np.array(embeddings)
print(X.shape)
X = X.squeeze(axis=1)
X = X / np.linalg.norm(X, axis=1, keepdims=True)
print(X.shape)

kmeans = KMeans(
    n_clusters=2,
    random_state=42,
    n_init="auto"
)
labels = kmeans.fit_predict(X)
for i, label in enumerate(labels):
    metadata[i]["cluster"] = int(label)


'''
for i in range(0,2):
    print(f"Cluster {i} Theme:", end=" ")

    functions = []
    for meta in metadata:
        if meta["cluster"] == i:
            functions += [meta["ast"]]

    fstr = "\n".join(functions)
    prompt = f'What do the following function ASTs have in common?\n\nFunctions:\n"""\n{fstr}\n"""\n\n'
    print(prompt)

    messages = [
        {"role": "user", "content": prompt}
    ] 

    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0,
        max_tokens=64,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0)

    print(response.choices[0].message.content.replace("\n", ""))

'''
    

cluster_str = ""
sorted_meta = sorted(metadata, key=lambda x: x["cluster"])
for item in sorted_meta:
    cluster_str += "\t Cluster: " + str(item["cluster"]) + "\n" + item["function"] + "\n"
    print("\t Cluster: " + str(item["cluster"]))
    print(item["model"])
    print(item["function"])


prompt = "Can you describe these clusters: " + cluster_str

messages = [
        {"role": "user", "content": prompt}
] 

response = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0,
        max_tokens=1024,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0)

print(response.choices[0].message.content.replace("\n", ""))


with open("cluster_embeddings.json", "w") as f:
    json.dump(data, f, indent = 4)
