from consts import Mode
import consts
from models import Sample
from glob import glob
import os
import re
import csv
import json
import validate
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="Run auto eval calibration")
    parser.add_argument("--seed", default=None, help="File to the saved metadata including the k selected seeds.")
    parser.add_argument("score_dir", help="Directory with scores to evaluate")
    parser.add_argument("sample_num", type=lambda v: int(v) if v.isdigit() else v)
    parser.add_argument("mode", choices=list(Mode), type=Mode)
    parser.add_argument("model")
    parser.add_argument("lang", type=str)
    #parser.add_argument("--intial-scoring", default=None, help="Directory that stores the pre caliration scores")
    return parser.parse_args()

def judgments_to_deducted(judgments):
    return [j["item"] for j in judgments if j["deducted"]]

def judgments_to_deducted_unlabelled(judgments): #no item label in the scorer output
    #ritems = ["1a", "1b", "1c", "2a", "2b", "2c", "2d"] #hardcoded  for Java 2
    return [consts.ITEMS[idx] for idx, j in enumerate(judgments) if j["deducted"]]

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


def deductions_to_score(deductions): #deductions is a set of strings
    if consts.get_mode() == Mode.APCS:
        return len(deductions) / len(consts.ITEMS)

    rubric = json.loads(consts.get_rubric())

    scores = []
    for idx, ritem in enumerate(rubric, start=1):
        score = ritem["points"]
        
        for deduction in deductions:
            if deduction and deduction[0] == str(idx):
                score -= ritem["subitems"][ord(deduction[1]) - ord('a')]["points"]

        item_tot = score / ritem["points"]
        scores += [item_tot]

    return sum(scores) / len(scores)

def parse_score_file(f_score):
    try:
        scores = json.load(open(f_score))
    except json.decoder.JSONDecodeError:
        content = open(f_score).read().split("\n")
        scores = []
        for line in content:
            if not line: continue
            try:
                to_add = [json.loads(line)]
                if isinstance(to_add[0], list):
                    scores += to_add[0]
                else:
                    scores += to_add
            except json.decoder.JSONDecodeError:
                continue

        print(f_score, len(scores))
        assert len(scores) == len(consts.ITEMS) 


    print(f_score)
    print(scores)
    auto = judgments_to_deducted_unlabelled(scores)
    return auto

def calculate_and_print_metrics(sample, auto, manual, split, metrics):

    str_auto = ",".join(auto)
    str_manual = ",".join(manual)

    recall = 1 - len(set(manual) - set(auto)) / len(manual) if len(manual) > 0 else 1

    precision = 1 - len(set(auto) - set(manual)) / len(auto) if len(auto) > 0 else 1

    f1 = 2 * ((precision * recall) / (precision + recall)) if (precision + recall > 0) else 0

    manual_score = deductions_to_score(manual)
    auto_score = deductions_to_score(auto)

    #flagged = validate.validate(sample, samples, ambiguities, BACKBONE_LLM)
    #print(auto, manual)
    print(f"{'auto eval':<10} {str_auto}")
    #print("auto eval", r_deducted)

    print(f"{'manual':<10} {str_manual}")
    #print("manual", ",".join(deductions[key]))

    print(f"{'score error?':<10} {auto_score != manual_score}")
    print(f"{'error?':<10} {auto!=manual}")
    #print(f"{'flagged?':<10} {flagged}")
    #3print(f"{'recall':<10} {recall}")
    #print(f"{'precision':<10} {precision}")
    #print(f"{'f1':<10} {f1}")
    print("="*50)
    print()
    
    metrics[split]["tot"] += 1
    metrics[split]["cor_score"] += (auto_score == manual_score)
    metrics[split]["cor"] += (auto == manual)
    metrics[split]["precision"] += precision
    metrics[split]["recall"] += recall
    metrics[split]["f1"] += f1
        
#SCORE_DIR = "data/rdb/scores-just-answer/"
#SCORE_DIR = "data/rdb/scores-pre-just-answer/"
#SCORE_DIR = "data/rdb/scores_pre/"
#SCORE_DIR = "data/rdb/scores/"
#SCORE_DIR = "data/rdb/scores-geval/"
#SCORE_DIR = "data/rdb/scores-geval-gpt-5.6/"
#SCORE_DIR = "data/rdb/scores-geval-pre/"
#SCORE_DIR = "data/rdb/calibrate-round-1/"
#SCORE_DIR = "data/rdb/scores-geval-no-cot/"
#SCORE_DIR = "data/rdb/calibrate-round-1-with-notes4/"


args = parse_args()
consts.set_mode(args.mode, args.lang, args.sample_num)
ITEMS = consts.ITEMS
all_manual_deductions = consts.get_manual_deductions() 

#BACKBONE_LLM = "gpt-oss-120"
BACKBONE_LLM  = args.model

train = []
if not args.seed:
    print("WARNING: NO SEED FILE GIVEN... EMPTY TRAINING SET")
else:
    with open(args.seed) as f:
        selected_samples = [Sample.from_dict(s) for s in json.load(f)]

    for s in selected_samples:
        train += [(s.model, s.answer_trial)]


'''
m = re.search(r"round-(\d+)/preds/?$", args.score_dir)
last_round = int(m.group(1))

samples, ambiguities = validate.load(last_round, args.score_dir, BACKBONE_LLM)
print("Sanity check....")
print(len(ambiguities), "total ambiguties")
print(len(samples), "total samples")
input()
'''

obj = {"cor": 0, "cor_score": 0, "tot": 0, "recall": 0, "precision": 0, "f1": 0}
metrics = {"test": obj.copy(), "train": obj.copy()}

per_item = {}

for ITEM in ITEMS:
    per_item[ITEM] = {"fn": 0, "tp": 0, "tn": 0, "fp": 0}

all_preds = {}

#for f_score in glob(os.path.join(args.score_dir, args.lang, "*", "*", f"score_*_1.txt")):
for f_score in glob(os.path.join(args.score_dir,  "*", "*", f"score_*_1.txt")):
    parts = f_score.split("/")
    model = parts[-3]                                    
    sample_num = parts[-2]                                   
    #print(f_score)

    answer_trial = f_score.split('/')[-1].split('_')[1]
    score_trial = f_score.split('/')[-1].split('_')[2].split('.')[0]


    if not model in all_preds:
        all_preds[model] = {}

    if not answer_trial in all_preds[model]:
        all_preds[model][answer_trial] = {"1": None, "2": None, "3": None}

    #trial = parts[-1].replace("score_", "").replace(".txt", "")
    auto = parse_score_file(f_score)        

    if not "gpt" in model:
        m_norm = model.replace("-"," ")
    else:
        m_norm = model
    
    key = (m_norm, int(answer_trial))
    manual = [v for v in all_manual_deductions[key] if v]

    all_preds[model][answer_trial][score_trial] = auto

    for ITEM in ITEMS:
        if ITEM in manual and not ITEM in auto:
            per_item[ITEM]["fn"] += 1
        elif ITEM in manual and ITEM in auto:
            per_item[ITEM]["tp"] += 1
        elif not ITEM in manual and not ITEM in auto:
            per_item[ITEM]["tn"] += 1
        elif not ITEM in manual and ITEM in auto:
            per_item[ITEM]["fp"] += 1

    if (model, answer_trial) in train:
        split = "train"
    else:
        split =  "test"


    print(model, "Trial", answer_trial, "Split: ", split)
    sample = Sample(None, None, model, answer_trial, "1", "2")
    calculate_and_print_metrics(sample, auto, manual, split, metrics)
    

#Using only score as correctness...
#cor += 

if len(train) > 0:
    print("Train accuracy: ")
    total_train_samples = metrics["train"]["tot"]
    print("="*50)
    print("Per sample:")
    print("total samples: ", total_train_samples)
    print("\tScore Accuracy:", metrics["train"]["cor_score"] / total_train_samples)
    print("\tTotal Accuracy:", metrics["train"]["cor"] / total_train_samples)
    #print("Per rubric item:")
    #print("\tTotal Recall", metrics["train"]["recall"] / total_train_samples)
    #print("\tTotal Precision", metrics["train"]["precision"] / total_train_samples)
    #print("\tTotal F1 score:", metrics["train"]["f1"] / total_train_samples)

print("Test accuracy: ")
total_test_samples = metrics["test"]["tot"]
print("="*50)
print("Per sample:")
print("total samples: ", total_test_samples)
print("\tScore Accuracy:", metrics["test"]["cor_score"] / total_test_samples)
print("\tTotal Accuracy:", metrics["test"]["cor"] / total_test_samples)
print("Per rubric item:")
print("\tTotal Recall", metrics["test"]["recall"] / total_test_samples)
print("\tTotal Precision", metrics["test"]["precision"] / total_test_samples)
print("\tTotal F1 score:", metrics["test"]["f1"] / total_test_samples)

for ITEM, info in per_item.items():
    print(ITEM)
    for k,v in info.items():
        print("\t"+k,v)

    p_cor = info["tp"] + info["tn"]
    total = p_cor + info["fp"] + info["fn"]
    acc = p_cor / total
    recall = info["tp"] / (info["tp"] + info["fn"]) if  (info["tp"] + info["fn"]) > 0 else 1
    precision = info["tp"] / (info["tp"] + info["fp"])  if (info["tp"] + info["fp"]) > 0 else 1
    print("acc: ", acc)
    print("recall: ", recall)
    print("precision: ", precision)
    print("F1: ", 2 * precision * recall / (precision  + recall) if (precision + recall) > 0 else 0)

'''
for model, d_trial in all_preds.items():
    print(model)

    for trial, scores in d_trial.items():
        consistency = len(set(tuple(v) for v in scores.values()))
        print("trial " + trial, consistency == 1)
        if consistency > 1 :
            print("\t" , scores.values())
        print()
'''

'''
# OK need to better measure self consistency here...
flips = {}
for ITEM in ITEMS:
    flips[ITEM] = 0

for model, d_trial in all_preds.items():
    print(model, d_trial)
    for trial, scores in d_trial.items():

        consistency = len(set(tuple(v) for v in scores.values()))
        if consistency == 1: continue

        for ITEM in ITEMS:
            deductions = list(scores.values())
            no_flip = (ITEM in deductions[0] and ITEM in deductions[1] and ITEM in deductions[2])
            no_flip = no_flip or (not ITEM in deductions[0] and not ITEM in deductions[1] and not ITEM in deductions[2])

            
            if not no_flip: flips[ITEM] += 1

print(flips)
'''
