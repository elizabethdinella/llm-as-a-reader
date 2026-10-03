from glob import glob
from tqdm import tqdm
import os
import csv
import json
import random
import argparse
import utils
import sys

def parse_args():
    parser = argparse.ArgumentParser(description="Run auto eval calibration")
    parser.add_argument("--seed", default=None, help="File to the saved metadata including the k selected seeds.")
    return parser.parse_args()


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


class Sample:
    def __init__(self, scores, p_scores, model, answer_trial, score_trial, sample_num):
        self.scores = scores #dict of ITEM -> true/false (true means deducted)
        self.p_scores = p_scores
        self.model  = model
        self.answer_trial = answer_trial
        self.score_trial = score_trial
        self.f_submission = os.path.join(ANSWER_DIR, model, sample_num, f"t{answer_trial}.txt")

    def __str__(self):
        return self.model + ": " + self.answer_trial + "; Score trial: " + self.score_trial + " -> " + str(self.scores)

    def __eq__(self, other):
        return self.model == other.model and self.answer_trial == other.answer_trial
    
    def key(self):
        return self.model + " " + self.answer_trial

    def to_dict(self):
        return {
            "scores": self.scores,
            "p_scores": self.p_scores,
            "model": self.model,
            "answer_trial": self.answer_trial,
            "score_trial": self.score_trial,
            "f_submission": self.f_submission,
        }
        

def load_seed(f_seed, r):
    seed = {}
    metadata = json.load(open(f_seed))
    
    for _round in range(r+1):
        _round = str(_round)
        if len(metadata) <= int(_round):
            seed[_round] = {"selected_samples": None, "notes": None, "score_dir": None}
            continue

        #assert _round == metadata[_round]
        if _round == "0":
            assert metadata[_round]["selected_samples"] == None and metadata[_round]["notes"] == None

        seed[_round] = {"selected_samples": metadata[_round]["selected_samples"], 
                        "notes": metadata[_round]["notes"],
                        "score_dir": metadata[_round]["score_dir"]
                        }
    return seed

def load_samples():
    samples = []
    
    for _model_dir in glob(os.path.join(ANSWER_DIR, "*")):
        _model = os.path.basename(_model_dir)
        for answer_trial in range(1,4):
            samples +=  [Sample(None, None, _model, str(answer_trial), "1", "2")] #hardcoded sample num for java 2

    return samples

def load_round(round_dir):
    samples = []
    for f_score in glob(os.path.join(round_dir, "*", "*", f"score_*_1.txt")):
        parts = f_score.split("/")
        model = parts[-3]                                    
        sample_num = parts[-2]                                   

        answer_trial = f_score.split('/')[-1].split('_')[1]
        score_trial = str(1)
        #score_trial = f_score.split('/')[-1].split('_')[2].split('.')[0]

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
       
            #print(f_score, scores)

            score_obj = {}
            for score, ITEM in zip(scores, ITEMS):
                score_obj[ITEM] = list(score.values())[0]
            
            s = Sample(None, score_obj, model, answer_trial, score_trial, sample_num)
            samples.append(s)

            #print(score_obj)
            #break

    return samples

def update_coverage(cov_map, sample):
    if not sample.scores:
        scores = sample.p_scores
    else:
        scores = sample.scores 

    for k, v in scores.items():
        cov_map[k][v] += 1

def marginal_gain(cov_map, candidate):
    if not candidate.scores:
        scores = candidate.p_scores
    else:
        scores = candidate.scores 

    gain = 0
    for k,v in scores.items():
        if cov_map[k][v] == 0:
            gain += 1

    return gain

def update_coverage_2(cov_map, G, sample):
    for a_id in ambiguities:
        if G[candidate][a_id]:
            COV[a_id] += 1   

def marginal_gain_2(cov_map, G, candidate):
    gain = 0
    for a_id in ambiguities:
        if G[candidate][a_id]:
            gain += 1 / COV[a_id] if cov_map[a_id] > 0 else 1

    return gain


def select(k, COV, samples, few_shot, ambiguities):
    #return select_greedy(k, COV, samples, few_shot)
    return select_greedy_2(k, COV, samples, few_shot, ambiguities)

def select_greedy_2(k, COV, samples, few_shot, ambiguities):
    samples = [s for s in samples.copy() if not s in few_shot]
    G = {}
    for sample in samples:
        G[sample.key()] = {}
        for k, v in ambiguities.items():
            G[sample.key()][k] = False

    total = len(ambiguities) * len(samples)
    with tqdm(total=total, desc="scoring") as pbar:
        for k, v in ambiguities.items():
            for sample in samples:
                assert G[sample.key()][k] == False

                r_item = k.split("_")[0]
                #print("RUBRIC ITEM", r_item)
                score_a = utils.score_side_a(sample, v, r_item)
                score_b = utils.score_side_b(sample, v, r_item)
            
                if score_a != score_b:
                    G[sample.key()][k] = True

                pbar.update(1)

    print("=========================================================")
    print("Current G: ")
    print(G)
    print("press enter to continue....")
    input()
    selected = []
    while len(selected) < k:
        greedy_values = [marginal_gain_2(COV, G, sample) for sample in samples]
        best_idx = greedy_values.index(max(greedy_values))      

        max_gain = greedy_values[best_idx]

        print("Selecting sample:", best_sample , "for a gain of", max_gain)

        samples.remove(best_sample)
        best_sample = manually_label(best_sample)
        selected += [best_sample]
        update_coverage_2(COV, best_sample)
        
        print()
        print()

    return selected

def select_greedy(k, COV, samples, few_shot):
    samples = [s for s in samples.copy() if not s in few_shot]
    sample = random.choice(samples)
    print("Selected", sample)
    samples.remove(sample)
    sample = manually_label(sample)
    selected = [sample]
    update_coverage(COV, sample)

    print("updated coverage", COV)

    while len(selected) < k:
        greedy_values = [marginal_gain(COV, sample) for sample in samples]
        best_idx = greedy_values.index(max(greedy_values))      

        best_sample = samples[best_idx]
        max_gain = greedy_values[best_idx]

        #if max_gain == 0:
        #    break

        print("Selecting sample:", best_sample , "for a gain of", max_gain)

        samples.remove(best_sample)
        best_sample = manually_label(best_sample)
        selected += [best_sample]
        update_coverage(COV, best_sample)
        
        print()
        print()
        
        #print(greedy_values, best_idx, greedy_values[best_idx], samples[best_idx])
        #break
    return selected

def manually_label(selected_sample):
    print()
    print()
    print("Query the user for labels.... For this script, we will just read in the manual labels")
    #few_shot = []
    #incor = []
    model = selected_sample.model
    if not "gpt" in model:
        m_norm = model.replace("-"," ")
    else:
        m_norm = model

    key = (m_norm, int(sample.answer_trial))
    manual = manual_deductions[key]
    auto = [k for k,v in sample.p_scores.items() if v]

    #if not auto == manual:
    #    incor += [sample]

    selected_sample.scores = {}
    for ITEM in ITEMS:
        selected_sample.scores[ITEM] = (ITEM in manual)

    print(model, ":", selected_sample.answer_trial)
    print(selected_sample.scores)
    print(manual)
    #few_shot += [sample]

    return selected_sample



ANSWER_DIR = "test/rdb/out/java/"
MANUAL_DIR = "test/apcs/"

#SCORE_DIR = "test/rdb/scores-geval-no-cot/"
#out_dir =  "test/rdb/calibrate-round-1/" #geval no CoT with few shot
#SCORE_DIR = "test/rdb/scores-geval/"

k = 5 #select 6 samples
r = 2 #number of rounds

ITEMS = ["A1", "A2", "A3", "A4"] 

#load manual deductions
#lang = "java"
#sample_num = 2

f_manual = os.path.join(MANUAL_DIR, "labels.csv")
#manual_deductions = load_deductions(f_manual)

args = parse_args()

if args.seed:
    seed = load_seed(args.seed, r)
    print(seed)
else:
    #TODO should this be initialized in any way?
    seed = {"0": {}, "1": {}, "2": {}}

ambiguities = {}

few_shot = []
samples = load_samples()

#print([str(s) for s in samples])
print(len(samples), "samples loaded")

for item in ITEMS:
    a_dir = f"apcs-scratch/{item}.txt"
    if os.path.exists(a_dir):
        a = json.load(open(a_dir))

        for a_i in a:
            ambiguities[a_i["id"]] = a_i
    else:
        a = utils.generate_ambiguities(item, utils.RUBRIC_APCS)
        print(a)
        with open(a_dir, "w") as f:
            f.write(a)

        #for a_i in a:
        #    ambiguities[a_i["id"]] = a_i

sys.exit(1)

COV = {}
for k,v in ambiguities.items():
    COV[k] = 0

print(COV.keys())

few_shot += select(k, COV, samples, few_shot, ambiguities)

seed[0]["selected_samples"] = few_shot

out_dir = "test/rdb/ambg-test1"
print("Saving current seed to ", out_dir)
os.makedirs(os.path.dirname(out_dir), exist_ok=True)

with open(os.path.join(out_dir, "metadata.json"), "w") as f:
    json.dump(seed, f)

sys.exit(1)

samples = load_round(seed["0"]["score_dir"])

print(len(samples))


for _round in range(1, r+1):
    print("CURRENT ROUND", _round)
    print("----"*100)

    if seed[str(_round)]["selected_samples"] == None:
        # pick a random sample
        print("NO SEEDED SELECTED SAMPLES FOR ROUND", _round)
        print("SELECTING.....")
        few_shot += select(k, COV, samples, few_shot)

        seed[str(_round)]["selected_samples"] = [f.to_dict() for f in few_shot]

    else:
        #load the seed
        print("LOADING SEEDED SELECTED SAMPLES")
        for s in seed[str(_round)]["selected_samples"]:
            sample = Sample(s["scores"], s["p_scores"], s["model"], s["answer_trial"], s["score_trial"], str(sample_num))
            if sample in few_shot: continue
            sample = manually_label(sample)
            few_shot += [sample]

        for s in few_shot:
            update_coverage(COV, s)

    print(len(few_shot), "few shot samples selected")
    print("Coverage of", len(few_shot), "samples")
    print(COV)
    

    if seed[str(_round)]["notes"] == None:
        print("NO SEEDED NOTES FOR ROUND: ", _round)

        previous_notes = seed[str(_round-1)]["notes"]
        recon_response = utils.query_scoring_model_reconciliation(few_shot, previous_notes)
        print(recon_response)
        updated_notes = utils.query_scoring_model_consistency(few_shot, recon_response)
        print(updated_notes)

        assert updated_notes.count("FINAL NOTES") == 1
        idx = updated_notes.find("FINAL NOTES")
        notes = updated_notes[idx:]
        input() 

        #seed[str(_round)]["notes"] = recon_response
        seed[str(_round)]["notes"] = notes
        
    else:
        print("LOADING NOTES FROM SEED....")
        recon_response = seed[str(_round)]["notes"]
        print(recon_response)
        notes = recon_response
    
    out_dir = seed[str(_round)]["score_dir"] 
    if out_dir == None:
        out_dir = seed[str(_round-1)]["score_dir"].replace(f"round-{_round-1}", f"round-{_round}")

    print("Saving current seed to ", out_dir)
    os.makedirs(os.path.dirname(out_dir), exist_ok=True)

    with open(os.path.join(out_dir, "metadata.json"), "w") as f:
        json.dump(seed, f)

    print("NOTES OBTAINED... PRESS ENTER TO BEGIN PREDICTION")
    input()

    for sample in samples:
        out_file = os.path.join(out_dir, sample.model, str(sample_num), f"score_{sample.answer_trial}_1.txt")
        if os.path.exists(out_file):
            print("sample already exists for this round... continuing", out_file)
            continue

        '''
        else:
            print("WE ARE ABOUT TO QUERY AND SAVE IN ", out_file)
            print("PRESSS ENTER IF OK ELSE QUIT!")
            input()
        '''

        print("Querying the scoring model to populate", sample)
        response = utils.query_scoring_model_few_shot(sample.f_submission, few_shot, notes)

        print("writing to", out_file)
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        with open(out_file, "w") as f:
                f.write(response) 


#response = utils.kill_forks(few_shot, "2c")
#response = utils.find_missing_fork(few_shot, "2c")
#print(response)

#readings_2c = utils.query_scoring_model_reading_interpretations_rubric_only("2c")
#print(readings_2c)
#sys.exit(1)

#test new notes from the fork killing
notes_1a = '''**Notes on Rubric Item 1a \"singletonMap is immutable\"**\n- Responses should not get the point deducted if they state immutability directly or via clear equivalents (e.g., \"fixed-size,\" \"cannot be changed after creation,\" \"throws UnsupportedOperationException on modification,\" \"static/read-only map\").\n- Responses should get the point deducted if they: only describe singletonMap in terms of efficiency, memory, or single-entry size with no indication that it cannot be modified.\n\n'''

notes_1b = '''**Notes on Rubric Item 1b \"HashMap is mutable\"**\n- Responses should not get the point deducted if they convey mutability in *any* equivalent wording, not just the word \"mutable\" e.g., \"allows modifications,\" \"can be changed/added to later,\" \"intended for dynamic (and potentially larger) collections,\" \"resizable,\" \"can grow,\" \"modifiable map,\" \"allows dynamic additions or removals.\" Implied contrast also counts: describing HashMap as dynamic/resizable while calling singletonMap fixed-size/immutable satisfies this sub-item. Be generous here; the graders credit paraphrase and implication.\n- Responses should get the point deducted if they: only describe HashMap in terms unrelated to mutability (e.g., only performance, memory overhead, copying cost, \"general-purpose implementation\") with no wording that indicates its contents can change.\n\n'''

notes_1c = '''**Notes on Rubric Item 1c \"singletonMap returns only a single key-value mapping\"**\n- Responses should not get the point deducted if they indicate, in any wording, that the singletonMap holds exactly one entry e.g., \"a single, immutable entry,\" \"designed for maps with exactly one entry,\" \"immutable single-entry map,\" \"a map containing only one mapping,\" \"fixed-size map designed for a single entry.\" A count of one stated anywhere in the comparison is enough; no discussion of key/value terminology is required.\n- Responses should get the point deducted if they discuss singletonMap only in terms of immutability, efficiency, or API fit without ever indicating that it contains just one mapping. This is what forced the deduction on the example whose only characterization was \"`singletonMap` is immutable and cannot be changed after creation\" immutability language alone does not satisfy this sub-item, even when the response is otherwise strong on 1a and 1b.\n\n'''

notes_2a = '''**Notes on Rubric Item 2a no_deduct only when the answer grounds the map choice in messageParams' DECLARED parameter type -- i.e. states the method is typed to accept a HashMap, so passing a singletonMap directly would not type-check / would not compile. deduct when the choice is explained only by RUNTIME behavior (mutability, defensive copy, 'needs a modifiable map', 'API requirements') without asserting what type the declaration accepts.\n\n'''

notes_2b = '''**Notes on Rubric Item 2b Credit (no deduction) only when the answer states HashMap is the required parameter type of messageParams and presents the requirement as a hard constraint, that passing a singletonMap directly would not compile / would be rejected, not as a discretionary choice (defensive copy, "in case changes are needed later", efficiency, unspecified "API requirements"). Naming HashMap as merely a parameter mentioned in passing, or implying singletonMap could have been passed directly, does not earn credit.\n\n'''

notes_2c = '''**Notes on Rubric Item 2c Credit (no deduction) only when the answer commits to a definite account of what happens to the map inside messageParams, either that the mutable copy is used or modified there, or that the data is left unmodified. A generic mutable-vs-immutable contrast, a hedged or conditional guess ("likely to allow modifications", "if changes are expected later", "or due to API requirements"), or a pivot to recommending singletonMap on efficiency grounds does not earn credit; naming specific operations (get, containsKey) is not required, but a clear committed determination is. Note that 2c rewards a clear determination, not a correct one: an answer that confidently but wrongly says the map is mutated still satisfies 2c, its error is handled under 2d.\n\n'''

notes_2d = '''**Notes on Rubric Item 2d \"Incorrectly states that usages modify the map\" (2-point deduction)**\n- Responses should not get the points deducted if they merely speculate or hedge about possible mutation e.g., \"likely because the method requires a modifiable map **or the map needs to be changed later**,\" \"perhaps it is changed downstream,\" \"in case modifications are needed,\" \"if changes are expected.\" Hedging words (\"likely,\" \"may,\" \"or,\" \"if,\" \"possibly\") keep this out of 2d territory (it costs 2c instead).\n- Responses should get the points deducted if they: affirmatively and unambiguously assert that `messageParams` (or the command object/code downstream) mutates, writes to, or \"can safely modify internally\" the passed map, i.e., present mutation as fact rather than possibility. Statements like \"passing `singletonMap` directly would restrict future modifications **within `messageParams`**\" also count as asserting internal mutation.'''

notes = notes_1a + notes_1b + notes_1c + notes_2a + notes_2b + notes_2c + notes_2d

out_dir = "test-merged-notes3/"

for sample in samples:
    out_file = os.path.join(out_dir, sample.model, str(sample_num), f"score_{sample.answer_trial}_1.txt")
    if os.path.exists(out_file):
        print("sample already exists for this round... continuing", out_file)
        continue

    print("Querying the scoring model to populate", sample)
    response = utils.query_scoring_model_few_shot(sample.f_submission, few_shot, notes)

    print("writing to", out_file)
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
            f.write(response) 

#response = utils.kill_forks(few_shot)
#print(response)


'''
for sample in samples:
    print(sample.model, sample.answer_trial)

    out_file = os.path.join("gap-test", sample.model, str(sample_num), f"score_{sample.answer_trial}_1.txt")
    if os.path.exists(out_file):
        print("sample already exists for this round... continuing", out_file)
        continue

    label = utils.query_scoring_model_gap_inference(sample, notes)

    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        f.write(label)

    #sys.exit(1)
'''

