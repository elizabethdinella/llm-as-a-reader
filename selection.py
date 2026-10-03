from enum import Enum
from glob import glob
from consts import K, init_pred_dir
import consts
from models import Status, Sample
from tqdm import tqdm
import utils
import os
import random
import json

class SelectionMethod(str, Enum):
    GREEDY_AUGMENTATION = "greedy-augmentation"
    RANDOM = "random"
    AMBIGUITY = "ambiguity"
    LABEL = "label"
    JOINT = "joint"  # ambiguity + labels

    def __str__(self):
        return self.value

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

def update_coverage_3(cov_a, cov_labels, G, sample):
    update_coverage(cov_labels, sample)
    update_coverage_2(cov_a, G, sample, ambiguities) 


def update_coverage_2(cov_map, G, sample, ambiguities):
    #print(cov_map)
    #print(G)

    untouched = [a for a in ambiguities if a.status == Status.UNTOUCHED]
    for a in untouched:
        if G[sample.key()][a.id]:
            cov_map[a.id] += 1   

def marginal_gain_2(cov_map, G, candidate, ambiguities):
    gain = 0

    untouched = [a for a in ambiguities if a.status == Status.UNTOUCHED]
    for a in untouched:
        if G[candidate.key()][a.id]: #G contains True if the sides are different
            gain += 1 / cov_map[a.id] if cov_map[a.id] > 0 else 1

    return gain

def marginal_gain_3(cov_map_a, cov_map_labels, G, candidate, ambiguities):
    gain = 0
    for a in ambiguities:
        if G[candidate.key()][a.id]:
            gain += 1 / cov_map_a[a.id] if cov_map_a[a.id] > 0 else 1

    gain /= len(ambiguities)

    if not candidate.scores:
        scores = candidate.p_scores
    else:
        scores = candidate.scores 

    for k,v in scores.items():
        if cov_map_labels[k][v] == 0:
            gain += 1

    return gain


def select(selection_method, COV, COV_LABELS, samples, few_shot, ambiguities, backbone_llm):
    if selection_method == SelectionMethod.GREEDY_AUGMENTATION:
        return select_greedy_2(COV, COV_LABELS, samples, few_shot, ambiguities, backbone_llm)
    elif selection_method == SelectionMethod.LABEL:
        return select_greedy_label(init_pred_dir, COV_LABELS, samples, few_shot)
    elif selection_method == SelectionMethod.RANDOM:
        return select_random(samples, few_shot)
    else:
        raise Exception("Not yet implemented")


def load_G(samples, ambiguities, backbone_llm, allow_run=True):
    untouched = [a for a in ambiguities if a.status == Status.UNTOUCHED]

    G = {}
    for sample in samples:
        G[sample.key()] = {}
        for a in untouched:
            G[sample.key()][a.id] = False

    #print(len(untouched), len(samples))
    total = len(untouched) * len(samples)
    #total = len(amiguities) * len(samples)
    with tqdm(total=total, desc="loading G") as pbar:
        for a in untouched:
            for sample in samples:
                assert G[sample.key()][a.id] == False
                cache_path = os.path.join(consts.get_cache_prefix(backbone_llm), a.id, sample.key().replace(" ","-") + ".txt")

                if os.path.exists(cache_path):
                    scores = json.load(open(cache_path))
                else:
                    print(cache_path, "Doesn't exist")
                    if not allow_run: 
                        print(cache_path, "Doesn't exist but not allowed to generate")
                        continue
                        #assert False

                    #scores = utils.score_both_sides(sample, a, a.r_item, backbone_llm)
                    score_a = utils.score_side_a(sample, a, a.r_item, backbone_llm)
                    score_b = utils.score_side_b(sample, a, a.r_item, backbone_llm)
                    scores = [score_a, score_b]
                         
                    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                    with open(cache_path, "w") as f:
                        json.dump(scores, f)
            
                score_a, score_b = scores
                if score_a["decision"] != score_b["decision"]: 
                    G[sample.key()][a.id] = True

                pbar.update(1)

    return G
    

def select_random(samples, few_shot):
    samples = [s for s in samples.copy() if not s in few_shot]
    selected =  random.sample(samples, K)
    return list(map(utils.manually_label, selected))

def select_greedy_2(COV, COV_LABELS, samples, few_shot, ambiguities, backbone_llm):
    samples = [s for s in samples.copy() if not s in few_shot]

    G = load_G(samples, ambiguities, backbone_llm)

    print("G loaded...")
    print("press enter to continue....")
    #input()
    selected = []
    while len(selected) < K:
        greedy_values = [marginal_gain_2(COV, G, sample, ambiguities) for sample in samples]
        #greedy_values = [marginal_gain_3(COV, COV_LABELS, G, sample) for sample in samples]

        best_idx = greedy_values.index(max(greedy_values))      
        best_sample = samples[best_idx]

        max_gain = greedy_values[best_idx]

        print("Selecting sample:", best_sample , "for a gain of", max_gain)

        samples.remove(best_sample)
        best_sample = utils.manually_label(best_sample)

        print("LABEL: ", best_sample)

        for g, s in sorted(zip(greedy_values, samples), key=lambda x: x[0], reverse=True):
            print(g)
            print(s)
        
        untouched = [a for a in ambiguities if a.status == Status.UNTOUCHED]
        utils.calibrate([best_sample], untouched, backbone_llm)

        selected += [best_sample]
        #update_coverage_3(COV, COV_LABELS, G, best_sample)
        update_coverage_2(COV, G, best_sample, ambiguities)
        
        #print(COV_LABELS)
        print(COV)
        print(best_sample.scores)
        print()
        print()

    #input()
    return selected

def select_greedy_label(init_pred_dir, COV, samples, few_shot):
    samples = [s for s in samples.copy() if not s in few_shot]

    for f_score in glob(os.path.join(init_pred_dir, "*", "*", f"score_*_1.txt")):
        parts = f_score.split("/")
        model = parts[-3]                                    
        sample_num = parts[-2]                                   

        answer_trial = f_score.split('/')[-1].split('_')[1]

        scores = utils.load_preds(f_score)

        for s in samples:
            if s.model == model and s.answer_trial == answer_trial:
                s.scores = scores
                break

    #sample = random.choice(samples)
    #print("Selected", sample)
    #samples.remove(sample)
    #sample = utils.manually_label(sample)
    #update_coverage(COV, sample)

    selected = []
    print("updated coverage", COV)

    while len(selected) < K:
        greedy_values = [marginal_gain(COV, sample) for sample in samples]
        best_idx = greedy_values.index(max(greedy_values))      

        best_sample = samples[best_idx]
        max_gain = greedy_values[best_idx]

        print("Selecting sample:", best_sample , "for a gain of", max_gain)

        samples.remove(best_sample)
        best_sample = utils.manually_label(best_sample)
        selected += [best_sample]
        update_coverage(COV, best_sample)
        
        print()
        print()
        
    return selected

def load_or_run_selection(f_selected, selection_method, _round, ambiguities, samples, few_shot, backbone_llm):
    COV = {}
    for a in ambiguities:
        COV[a.id] = 0

    COV_LABELS = {}
    for ITEM in consts.ITEMS:
        COV_LABELS[ITEM] = {True: 0, False: 0}

    #for s in few_shot:
    #    update_coverage(COV_LABELS, s)
    #update_coverage_2(COV_LABELS, few_shot)

    if not os.path.exists(f_selected):
        print("NO SEEDED SELECTED SAMPLES FOR ROUND", _round)
        print("SELECTING.....")

        few_shot += select(selection_method, COV, COV_LABELS, samples, few_shot, ambiguities, backbone_llm)
        print("Saving current selection to ", f_selected)

        with open(f_selected, "w") as f:
            json.dump([s.to_dict() for s in few_shot], f)

    else:
        print("LOADING SELECTED SAMPLES")
        with open(f_selected) as f:
            selected_samples = [Sample.from_dict(s) for s in json.load(f)]


        utils.calibrate(selected_samples, ambiguities, backbone_llm)
 
        G = load_G(selected_samples, ambiguities, backbone_llm)
        for sample in selected_samples:
            m_gain = marginal_gain_2(COV, G, sample, ambiguities)

            print(sample.model, sample.answer_trial, m_gain)
            if sample in few_shot: continue
            sample = utils.manually_label(sample)
            print(sample.scores)
            few_shot += [sample]

        for s in few_shot:
            update_coverage_2(COV, G, s, ambiguities)

    return few_shot


