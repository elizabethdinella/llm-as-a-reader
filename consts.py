from enum import Enum
import os
import csv
import json

class Mode(Enum):
    RDB  = "RDB" 
    APCS = "APCS"

    def __str__(self):
        return self.value

K = 5 #select 6 samples
max_rounds = 3 #TODO: set to 25% of dataset size?

lang = None 
sample_num = None #set via arg
#sample_num = 2

init_pred_dir = "test/rdb/scores-geval-no-cot/"


dataset_dir = None 



def get_initial_ambiguity_dir():
    if _MODE == Mode.APCS:
        return "scratch-apcs/"
    elif _MODE == Mode.RDB:
        return "scratch/"
    else:
       assert False 

def set_mode(mode, _lang, _sample_num):
    global _MODE, manual_deductions, sample_num, lang, dataset_dir
    _MODE = mode
    sample_num = _sample_num
    lang = _lang.lower()
    

    dataset_dir = os.path.join("../crqbench/artifact/dataset/", lang)

    if _MODE == Mode.APCS:
        rubric = json.loads(get_rubric())
        ITEMS[:] = [k.split(":", 1)[0].strip() for k in rubric] 

        f_manual = os.path.join(get_answer_dir(), "manual.csv")
        manual_deductions = load_deductions(f_manual, "attempt")

    elif _MODE == Mode.RDB:
        r_obj = json.loads(get_rubric()) 
        my_items = []
        for i, r_item in enumerate(r_obj):
            for j, sub_item in enumerate(r_item["subitems"]):
                my_items += [str(i+1) + chr((ord('a')+j))]

        ITEMS[:] = my_items
        MANUAL_DIR = "../crqbench/artifact/results/rubric-applications/"
        f_manual = os.path.join(MANUAL_DIR, f"{lang}{sample_num}.csv")
        manual_deductions = load_deductions(f_manual)
    else:
        assert False

def get_manual_deductions():
    return manual_deductions

    
def normalize_model_name(model):
    model = model.strip().lower()
    if model == "deepseek-r1": model = "deepseek r1 70b"
    elif model == "qwen 3 coder": model = "qwen3 coder"
    elif model == "qwen 3": model = "qwen3"
    elif model == "llama 4 scout": model = "llama scout 4"
    elif model == "o3": model = "gpt-o3"
    elif "gpt-oss" in model: model = model.replace("oss", "mini")
    return model

def load_deductions(csv_path, trial_col="trial"):
    table = {}
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            model = normalize_model_name(row["model name"])
            if model == "deepseek-r1": model = "deepseek r1 70b"
            elif model == "qwen 3 coder": model = "qwen3 coder"
            elif model == "qwen 3": model = "qwen3"
            elif model == "llama 4 scout": model = "llama scout 4"
            elif model == "o3": model = "gpt-o3"
            elif "gpt-oss" in model: model = model.replace("oss","mini")

            table[(model, int(row[trial_col]))] = \
                row["rubric items deducted"].split(",")
    return table

def get_cache_prefix(model_name):
    if _MODE == Mode.APCS:
        return os.path.join("cache-apcs-" + model_name, str(sample_num))
    elif _MODE == Mode.RDB:
        return os.path.join("cache-" + model_name, lang, str(sample_num))
        #return "cache"
    else:
        assert False

def get_rubric():
    if _MODE == Mode.APCS:
        f_rubric_apcs = os.path.join("test/apcs/", f"rubric_{str(sample_num)}.json")
        return open(f_rubric_apcs).read()
    elif _MODE == Mode.RDB:
        f_rubric = os.path.join(dataset_dir, "rubrics", str(sample_num) + ".json")
        return open(f_rubric).read()
    else:
        assert False

ITEMS = []
manual_deductions = {}
_MODE = None
    
def get_mode():
    return _MODE

def get_answer_dir():
    if _MODE == Mode.RDB:
        return os.path.join("test/rdb/out", lang)
    elif _MODE == Mode.APCS:
        return f"test/apcs/sub/mistakes/{str(sample_num)}"
    else:
        assert False

def get_max_trials():
    if _MODE == Mode.APCS:
        return 5
    elif _MODE == Mode.RDB:
        return 3
    else:
        assert False

def get_question():
    global sample_num
    if _MODE == Mode.RDB: 
        checkout_dir = "../crqbench/projects/"
        f_sample = os.path.join(dataset_dir, "metadata", str(sample_num) + ".json")

        with open(f_sample, "r") as f:
            metadata  = json.load(f)

        repo_url = metadata["repo_url"]
        pull_id = metadata["pull_id"]
        sample_num = metadata["sample_num"]
        sha = metadata["commit"]
        fname = metadata["loc"]["file"]

        func_start = metadata["loc"]["function"]["start"]
        func_end = metadata["loc"]["function"]["end"]
        comment_line = metadata["loc"]["comment"]

        repo_name = os.path.basename(repo_url).replace(".git", "")
        repo_path = os.path.join(checkout_dir, repo_name)

        f_question = os.path.join(dataset_dir, "questions", str(sample_num) + ".txt")
        QUESTION = open(f_question).read()

        CODE = get_function_with_comment(repo_path, fname, func_start, func_end, comment_line, QUESTION)
        return CODE

    elif _MODE == Mode.APCS:
        f_question = f"test/apcs/q{str(sample_num)}.txt"
        return open(f_question).read() 
        
    else:
        assert False

def get_file(repo_path, fname):
    full_fname = os.path.join(repo_path, fname)

    return open(full_fname).read()




def is_checked_out(repo_path, sample_num):
    checked_out_path = os.path.join(repo_path, ".checked_out")
    if not os.path.exists(checked_out_path):
        return False
    with open(checked_out_path, "r") as f:
        stored = f.read().strip()
    return stored == str(sample_num)



def info_validate(repo_path, sample_num):
    if not os.path.exists(repo_path):
        print(f"[!] Repo not found at {repo_path}. Run clone")
        sys.exit(1)

    if not is_checked_out(repo_path, sample_num):
        print(f"[!] Run checkout on the sample num you want info for")
        sys.exit(1)


def get_function_with_comment(repo_path, fname, func_start, func_end, comment_line, question):
    info_validate(repo_path, sample_num)

    full_fname = os.path.join(repo_path, fname)

    full_src = get_file(repo_path, fname)
    lines = full_src.split("\n")

    before_comment = lines[func_start-1:comment_line] 
    comment = ["[*] [QUESTION]\t" + question]
    func_lines = lines[comment_line:func_end]

    return "\n".join(before_comment + comment + func_lines)

