
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
from glob import glob
import numpy as np


def normalize_text(text):
    #text = unicodedata.normalize('NFC', text)
    # Replace newlines, tabs, and multiple spaces with a single space
    text = text.lower()
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


for file_path in glob("data/apcs/sub/mistakes/cluster*/*/answer_*.txt"):
    MODEL = file_path.split(os.sep)[-2]
    #for MODEL in MODELS:
    data[MODEL] = {}
   # for SAMPLE_NUM in range(1, 6):
   #     for TRIAL in range(1, 4):
    #file_path = f"test/a-levels/sub/{MODEL}/answer_3.txt" 
    #file_path = f"data/apcs/sub/{MODEL}/answer_1.txt" 

    if not os.path.exists(file_path):
        print("skipping", file_path)
        continue

    with open(file_path, "r") as file:
        content = normalize_text(file.read())
    embedding = generate_embedding(content)
    data[MODEL] = embedding
    embeddings.append(embedding)
    metadata.append({
        "model": MODEL,
        "function": content
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



'''
kmeans = KMeans(
    n_clusters=2,
    random_state=42,
    n_init="auto"
)
labels = kmeans.fit_predict(X)
for i, label in enumerate(labels):
    metadata[i]["cluster"] = int(label)

'''

'''
for i in range(0,2):
    print(f"Cluster {i} Theme:", end=" ")

    functions = []
    for meta in metadata:
        if meta["cluster"] == i:
            functions += [meta["function"]]

    fstr = "\n".join(functions)
    prompt = f'What do the following functions have in common?\n\nFunctions:\n"""\n{fstr}\n"""\n\n'
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

    

sorted_meta = sorted(metadata, key=lambda x: x["cluster"])
for item in sorted_meta:
    print(item)



with open("apcs_generation/cluster_embeddings.json", "w") as f:
    json.dump(data, f, indent = 4)
'''
