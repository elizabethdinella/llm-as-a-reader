from glob import glob
import os
import csv
import json

def judgments_to_deducted(judgments):
    return [j["item"] for j in judgments if j["DECISION"] == "NO"]

def judgments_to_deducted_unlabelled(judgments): #no item label in the scorer output
    ritems = ["A1","A2","A3","A4"] #hardcoded  for APC
    return [ritems[idx] for idx, j in enumerate(judgments) if j["DECISION"] == "NO"]

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

            table[(model, int(row["attempt"]))] = \
                row["rubric items deducted"].split(",")
    return table


def deductions_to_score(deductions): #deductions is a set of strings
    return len(deductions) / 4

        
SCORE_DIR = "test/apcs/llm-judge-mistake-scores/"
F_MANUAL = "test/apcs/sub/mistakes/manual.csv"

lang = "java"
sample_num = 2

ITEMS = ["A1", "A2", "A3", "A4"] 

deductions = load_deductions(F_MANUAL)
print(deductions)

tot, cor, cor_score = 0, 0, 0
tot_r, tot_p, tot_f1 = 0, 0, 0

per_item = {}

for ITEM in ITEMS:
    per_item[ITEM] = {"fn": 0, "tp": 0, "tn": 0, "fp": 0}

all_preds = {}

for f_score in glob(os.path.join(SCORE_DIR, "*", "*", "score.txt")):
    print(f_score)
    parts = f_score.split("/")
    model = parts[-3]                                    
    attempt_num = parts[-2]                                   

    print(f_score, model, attempt_num)

    #answer_trial = f_score.split('/')[-1].split('_')[1]
    #score_trial = f_score.split('/')[-1].split('_')[2].split('.')[0]

    if not model in all_preds:
        all_preds[model] = {}

    if not attempt_num in all_preds[model]:
        all_preds[model] = {"1": None, "2": None, "3": None, "4": None, "5": None}

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

        print(f_score, len(scores))
        assert len(scores) == 4 #hardcoded for APCS Q1A
             

    if not "gpt" in model:
        m_norm = model.replace("-"," ")
    else:
        m_norm = model
    
    key = (m_norm, int(attempt_num))
    #print(scores)
    auto = judgments_to_deducted_unlabelled(scores)
    manual = [v for v in deductions[key] if v]


    all_preds[model][attempt_num] =  auto

    for ITEM in ITEMS:
        if ITEM in manual and not ITEM in auto:
            per_item[ITEM]["fn"] += 1
        elif ITEM in manual and ITEM in auto:
            per_item[ITEM]["tp"] += 1
        elif not ITEM in manual and not ITEM in auto:
            per_item[ITEM]["tn"] += 1
        elif not ITEM in manual and ITEM in auto:
            per_item[ITEM]["fp"] += 1

    print(model, "Trial", attempt_num)

    str_auto = ",".join(auto)
    str_manual = ",".join(manual)

    recall = 1 - len(set(manual) - set(auto)) / len(manual) if len(manual) > 0 else 0
    tot_r  += recall

    precision = 1 - len(set(auto) - set(manual)) / len(auto) if len(auto) > 0 else 0
    tot_p += precision

    f1 = 2 * ((precision * recall) / (precision + recall)) if (precision + recall > 0) else 0
    tot_f1 += f1

    manual_score = deductions_to_score(manual)
    auto_score = deductions_to_score(auto)

    cor_score += (auto_score == manual_score)

    print(f"{'auto eval':<10} {str_auto}")
    #print("auto eval", r_deducted)

    print(f"{'manual':<10} {str_manual}")
    #print("manual", ",".join(deductions[key]))

    print(f"{'score error?':<10} {auto_score != manual_score}")
    print(f"{'error?':<10} {auto!=manual}")
    print(f"{'recall':<10} {recall}")
    print(f"{'precision':<10} {precision}")
    print(f"{'f1':<10} {f1}")
    print("="*50)
    print()
    
    tot += 1
    cor += (auto == manual)


#Using only score as correctness...
#cor += 

print("="*50)
print("Per trial:")
print("\tScore Accuracy:", cor_score / tot)
print("\tTotal Accuracy:", cor / tot)
print("Per rubric item:")
print("\tTotal Recall", tot_r / tot)
print("\tTotal Precision", tot_p / tot)
print("\tTotal F1 score:", tot_f1 / tot)


for ITEM, info in per_item.items():
    print(ITEM)
    for k,v in info.items():
        print("\t"+k,v)

    p_cor = info["tp"] + info["tn"]
    total = p_cor + info["fp"] + info["fn"]
    acc = p_cor / total
    recall = info["tp"] / (info["tp"] + info["fn"])
    precision = info["tp"] / (info["tp"] + info["fp"])  if (info["tp"] + info["fp"]) > 0 else 0
    print("acc: ", acc)
    print("recall: ", recall)
    print("precision: ", precision)
    print("F1: ", 2 * precision * recall / (precision  + recall) if (precision + recall) > 0 else 0)

