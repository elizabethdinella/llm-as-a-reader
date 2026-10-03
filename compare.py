from glob import glob
import os
import csv
import json

def judgments_to_deducted(judgments):
    return [j["item"] for j in judgments if j["deducted"]]

def judgments_to_deducted_unlabelled(judgments): #no item label in the scorer output
    ritems = ["1a", "1b", "1c", "2a", "2b", "2c", "2d"] #hardcoded  for Java 2
    return [ritems[idx] for idx, j in enumerate(judgments) if j["deducted"]]

def load_deductions(csv_path):
    table = {}
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            model = row["model name"].lower()
            if model == "deepseek-r1": model = "deepseek r1 70b"
            elif model == "qwen 3 coder": model = "qwen3 coder"
            elif model == "qwen 3": model = "qwen3"
            elif model == "llama 4 scout": model = "llama scout 4"
            elif model == "o3": model = "gpt-o3"
            elif "gpt-oss" in model: model = model.replace("oss","mini")

            table[(model, int(row["trial"]))] = \
                row["rubric items deducted"].split(",")
    return table


def deductions_to_score(deductions, F_RUBRIC): #deductions is a set of strings
    rubric = json.load(open(F_RUBRIC))

    scores = []
    for idx, ritem in enumerate(rubric, start=1):
        score = ritem["points"]
        
        for deduction in deductions:
            if deduction and deduction[0] == str(idx):
                score -= ritem["subitems"][ord(deduction[1]) - ord('a')]["points"]

        item_tot = score / ritem["points"]
        scores += [item_tot]

    return sum(scores) / len(scores)

        

SCORE_DIR_1 = "test/rdb/scores-geval-no-cot/"
SCORE_DIR_2 = "test/rdb/calibrate-round-1-with-notes5/"
MANUAL_DIR = "../crqbench/artifact/results/rubric-applications/"
F_RUBRIC   =  "../crqbench/artifact/dataset/java/rubrics/2.json"

lang = "java"
sample_num = 2

ITEMS = ["1a", "1b", "1c", "2a", "2b", "2c", "2d"] 

f_manual = os.path.join(MANUAL_DIR, f"{lang}{sample_num}.csv")
deductions = load_deductions(f_manual)

tot, cor, cor_score = 0, 0, 0
tot_r, tot_p, tot_f1 = 0, 0, 0

per_item = {}

for ITEM in ITEMS:
    per_item[ITEM] = {"fn": 0, "tp": 0, "tn": 0, "fp": 0}



foo = []
all_preds = {}
all_manual = {}

for f_score in glob(os.path.join(SCORE_DIR_1, "*", "*", f"score_*_1.txt")):
    parts = f_score.split("/")
    model = parts[-3]                                    
    sample_num = parts[-2]                                   

    answer_trial = f_score.split('/')[-1].split('_')[1]
    score_trial = f_score.split('/')[-1].split('_')[2].split('.')[0]


    if not model in all_preds:
        all_preds[model] = {}
        all_manual[model] = {}

    if not answer_trial in all_preds[model]:
        all_preds[model][answer_trial] = {"1": None, "2": None, "3": None}

    try:
        scores = json.load(open(f_score))
    except json.decoder.JSONDecodeError:
        content = open(f_score).read().split("\n")
        scores = []
        for line in content:
            if not line: continue
            try:
                scores += [json.loads(line)]
            except json.decoder.JSONDecodeError:
                continue

        assert len(scores) == 7 #hardcoded for Java 2
             

    if not "gpt" in model:
        m_norm = model.replace("-"," ")
    else:
        m_norm = model
    
    key = (m_norm, int(answer_trial))
    auto = judgments_to_deducted_unlabelled(scores)
    manual = [v for v in deductions[key] if v]


    all_preds[model][answer_trial][score_trial] =  auto


foo.append(all_preds)

all_preds = {}
for f_score in glob(os.path.join(SCORE_DIR_2, "*", "*", f"score_*_1.txt")):
    parts = f_score.split("/")
    model = parts[-3]                                    
    sample_num = parts[-2]                                   

    answer_trial = f_score.split('/')[-1].split('_')[1]
    score_trial = f_score.split('/')[-1].split('_')[2].split('.')[0]


    if not model in all_preds:
        all_preds[model] = {}

    if not answer_trial in all_preds[model]:
        all_preds[model][answer_trial] = {"1": None, "2": None, "3": None}

    try:
        scores = json.load(open(f_score))
    except json.decoder.JSONDecodeError:
        content = open(f_score).read().split("\n")
        scores = []
        for line in content:
            if not line: continue
            try:
                scores += [json.loads(line)]
            except json.decoder.JSONDecodeError:
                continue

        assert len(scores) == 7 #hardcoded for Java 2
             

    if not "gpt" in model:
        m_norm = model.replace("-"," ")
    else:
        m_norm = model
    
    key = (m_norm, int(answer_trial))
    auto = judgments_to_deducted_unlabelled(scores)
    manual = [v for v in deductions[key] if v]

    all_preds[model][answer_trial][score_trial] =  auto
    all_manual[model][answer_trial] = manual


foo.append(all_preds)

#print(foo)



for k,v in foo[0].items(): #pre calibration
    print(k)
    print()
    #print("Pre calibration")
    pre = v
    post = foo[1][k]
    for answertrial, v in pre.items():
        if v["1"] != post[answertrial]["1"]:
            print("trial", answertrial)
            print("Pre calibration", v["1"])
            print("Post calibration", post[answertrial]["1"])
            print("Manual deductions", all_manual[k][answertrial])
            print()
    print()
    
