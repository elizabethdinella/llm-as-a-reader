from models import Status, Ambiguity, Sample
from consts import max_rounds, Mode
import consts
from selection import SelectionMethod
import selection
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
    parser.add_argument("dir")
    parser.add_argument("mode", choices=list(Mode), type=Mode)
    parser.add_argument("sample_num", type=lambda v: int(v) if v.isdigit() else v)
    parser.add_argument("lang", type=str)

    parser.add_argument(
        "--selection-method",
        type=SelectionMethod,
        choices=list(SelectionMethod),
        default=SelectionMethod.GREEDY_AUGMENTATION,
        help=(
            "Example selection strategy: "
            "greedy-augmentation (default), random (truly random), "
            "ambiguity (ambiguity resolution), label (label based), "
            "joint (ambiguity + labels)"
        ),
    )

    parser.add_argument("--model", default="claude-opus-5")

    return parser.parse_args()

def load_round(round_dir):
    samples = []
    for f_score in glob(os.path.join(round_dir, "*", "*", f"score_*_1.txt")):
        print(f_score)
        parts = f_score.split("/")
        model = parts[-3]                                    
        sample_num = parts[-2]                                   

        answer_trial = f_score.split('/')[-1].split('_')[1]
        score_trial = str(1)
        #score_trial = f_score.split('/')[-1].split('_')[2].split('.')[0]

        scores = utils.load_preds()   
        #print(f_score, scores)

        s = Sample(None, scores, model, answer_trial, score_trial, sample_num)
        samples.append(s)

    return samples

args = parse_args()
few_shot = []

consts.set_mode(args.mode, args.lang, args.sample_num)
ambiguities = utils.load_initial_ambiguities(args.mode, args.model)
print(len(ambiguities), "total ambiguities")

_dir = args.dir
samples = utils.load_samples()

print(len(samples), "total samples")
#input()

_round = 1
while _round < max_rounds:
    print("CURRENT ROUND", _round)
    print("----"*100)
    print("Press enter to continue to the next round")
    #input()

    round_dir = os.path.join(_dir, f"round-{_round}")
    os.makedirs(round_dir, exist_ok=True)

    f_selected = os.path.join(round_dir, "selected.json")
    few_shot = selection.load_or_run_selection(f_selected, args.selection_method, _round, ambiguities, samples, few_shot, args.model)

    #sys.exit(1)

    print(len(few_shot), "few shot samples selected")
    print([s for s in few_shot])
    #print("Coverage of", len(few_shot), "samples")
    #print(COV)

    ambiguities = utils.calibrate(few_shot, ambiguities, args.model)

    print("Total ambiguities", len(ambiguities))
    #input()
    count_resolved = 0
    count_conflict = 0
    for a in ambiguities:
        if a.is_resolved(): 
            count_resolved += 1
        if a.status == Status.CONFLICT:
            count_conflict += 1

        print(str(a))

    print("TOTAL RESOLVED:", count_resolved)
    print("TOTAL CONFLICT:", count_conflict)
    #input()

    if count_resolved == 0:
        print("NO NEW RESOLVED AMBIGUITIES AFTER CALIBRATION.")
        print("BREAK?")
        #input() 

    #scratch-refined - list of newly added ambiguities

    f_refined = os.path.join(round_dir, "ambiguities.json")
    print(f_refined)
    new_as = utils.load_or_generate_refined_ambiguities(f_refined, _round, ambiguities, few_shot, args.model)

    ambiguities |= new_as

    print(len(ambiguities), "total ambiguities after refinement")
    #input()

    new_as = utils.calibrate(few_shot, new_as, args.model)
    count_resolved = 0
    count_conflict = 0
    for a in new_as:
        if a.is_resolved(): 
            count_resolved += 1
        if a.status == Status.CONFLICT:
            count_conflict += 1

        print(str(a))

    print("TOTAL NEW RESOLVED:", count_resolved)
    print("TOTAL NEW CONFLICT:", count_conflict)
    #input()

    
    if count_resolved == 0:
        print("NO NEW RESOLVED AMBIGUITIES DURING REFINEMENT.")
        print("BREAK?")
        #input() 


    f_notes = os.path.join(round_dir, "notes.json")

    if not os.path.exists(f_notes):
        NOTES = {}
        for item in consts.ITEMS:
            item_as = [a for a in ambiguities if a.r_item == item and a.is_resolved()]
            if len(item_as) > 0:
                #if _round > 0:
                #    previous_notes = seed[str(_round-1)]["notes"]
                #else:
                #    previous_notes = ""
                #notes = utils.generate_notes(item_as, item, previous_notes)
                item_notes = utils.generate_notes(item_as, item, args.model)
                NOTES[item] = item_notes
            else:
                print("NO AMBIGUITIES RESOLVED FOR ITEM", item)
                print("NOT GENERATING GRADING NOTES")

        print("Saving current notes to ", f_notes)
        with open(f_notes, "w") as f:
            json.dump(NOTES, f, indent=4)
    else:
        print("NOTES ARE LOADED!")

        with open(f_notes) as f:
            NOTES = json.load(f)
         
    notes = ""
    for k,v in NOTES.items():
        notes += "\n" + k +":" "\n"
        notes += v + "\n"

    print(notes)

    print("NOTES OBTAINED... PRESS ENTER TO BEGIN PREDICTION")
    #input()

    pred_dir = os.path.join(round_dir, "preds", args.lang)
    os.makedirs(os.path.dirname(pred_dir), exist_ok=True)

    for sample in tqdm(samples):
        model_dir = os.path.join(pred_dir, sample.model)
        sample_pred_dir = os.path.join(model_dir, str(args.sample_num))

        out_file = os.path.join(sample_pred_dir, f"score_{sample.answer_trial}_1.txt")
        os.makedirs(sample_pred_dir, exist_ok=True)

        if os.path.exists(out_file):
            print("sample already exists for this round... continuing", out_file)
            continue

        '''
        else:
            print("WE ARE ABOUT TO QUERY AND SAVE IN ", out_file)
            print("PRESSS ENTER IF OK ELSE QUIT!")
            input()
        '''

        #print("Querying the scoring model to populate", sample)
        response = utils.query_scoring_model_few_shot(sample.f_submission, few_shot, notes, args.model)

        #print("writing to", out_file)
        with open(out_file, "w") as f:
            f.write(response) 

    sys.exit(1)
    _round += 1

