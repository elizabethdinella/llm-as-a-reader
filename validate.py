import os
import consts
import selection
from pathlib import Path
from selection import load_G
from models import Status
from utils import load_samples, load_initial_ambiguities, load_or_generate_refined_ambiguities, calibrate

G = None

def load(last_round, eval_dir, backbone_llm):
    global G

    prefix = Path(eval_dir).parent.parent
    samples = load_samples()
    ambiguities = load_initial_ambiguities(consts.get_mode(), None)
    
    for _round in range(1, last_round+1):
        f_refined = os.path.join(prefix, f"round-{_round}", "ambiguities.json")
        ambiguities |= load_or_generate_refined_ambiguities(f_refined, _round,  ambiguities, None, None) 

    round_dir = os.path.join(prefix, f"round-{last_round}")
    f_selected = os.path.join(round_dir, "selected.json")

    few_shot = []


    untouched = [a for a in ambiguities if a.status == Status.UNTOUCHED]
    print(len(untouched), len(samples))

    few_shot = selection.load_or_run_selection(f_selected, None, last_round, untouched, samples, few_shot, backbone_llm)

    calibrate(few_shot, ambiguities, backbone_llm)


    G = load_G(samples, untouched, backbone_llm, False) 

    return samples, ambiguities
    

def validate(sample, samples, ambiguities, backbone_llm):
    assert sample.key() in G

    untouched = [a for a in ambiguities if a.status == Status.UNTOUCHED]
    
    for a in untouched:
        if G[sample.key()][a.id]:
            print(a.id)
            return True

    return False 
