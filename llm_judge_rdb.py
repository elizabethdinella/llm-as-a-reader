import argparse
import anthropic
import os
import json
from glob import glob
import sys

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

def get_file(repo_path, fname):
    full_fname = os.path.join(repo_path, fname)

    return open(full_fname).read()


def get_function_with_comment(repo_path, fname, func_start, func_end, comment_line, question):
    info_validate(repo_path, sample_num)

    full_fname = os.path.join(repo_path, fname)

    full_src = get_file(repo_path, fname)
    lines = full_src.split("\n")

    before_comment = lines[func_start-1:comment_line] 
    comment = ["[*] [QUESTION]\t" + question]
    func_lines = lines[comment_line:func_end]

    return "\n".join(before_comment + comment + func_lines)

def query_cld(prompt, model):
    if model == "claude-opus-5" or model == "claude-fable-5" or model == "claude-sonnet-5":
        endpoint_name = model
    elif model == "claude-opus-4.8":
        endpoint_name = "claude-opus-4-8" #-20250805"
    elif model == "claude-sonnet-4":
        endpoint_name = "claude-sonnet-4-20250514"
    elif model == "claude-sonnet-3.7":
        endpoint_name = "claude-3-7-sonnet-latest"
    else:
        raise Exception(f"MODEL {model} NOT FOUND")

    client = anthropic.Anthropic()

    with client.messages.stream(
            model=endpoint_name,
            max_tokens=64000,
            messages=[
                    {
                        "role": "user",
                        "content":  prompt
                    }
                ]
            ) as stream:
                response = stream.get_final_message()

    message = "".join(b.text for b in response.content if b.type == "text")

    '''
    if model == "claude-opus-5" or model == "claude-opus-4.8":
        message = response.content[0].text
    else:
        message = response.content[1].text
    '''

    return message


def parse_args():
    parser = argparse.ArgumentParser(description="Grade a submission against a rubric.")
    parser.add_argument("sample_num", help="Sample number")
    parser.add_argument("dataset_dir", help="Dataset directory")
    parser.add_argument("checkout_dir", help="Dir of checked out projects")
    parser.add_argument("answer_dir", help="Dir of model answers")
    parser.add_argument("out_dir", help="output directory")
    parser.add_argument("--model", default="claude-opus-5", help="model to use")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()

    f_sample = os.path.join(args.dataset_dir, "metadata", args.sample_num + ".json")

    with open(f_sample, "r") as f:
       metadata  = json.load(f)

    #metadata = obj["metadata"]
    repo_url = metadata["repo_url"]
    pull_id = metadata["pull_id"]
    sample_num = metadata["sample_num"]
    sha = metadata["commit"]
    fname = metadata["loc"]["file"]

    func_start = metadata["loc"]["function"]["start"]
    func_end = metadata["loc"]["function"]["end"]
    comment_line = metadata["loc"]["comment"]

    repo_name = os.path.basename(repo_url).replace(".git", "")
    repo_path = os.path.join(args.checkout_dir, repo_name)

    f_rubric = os.path.join(args.dataset_dir, "rubrics", args.sample_num + ".json")
    f_question = os.path.join(args.dataset_dir, "questions", args.sample_num + ".txt")
    
    QUESTION = open(f_question).read()
    CODE = get_function_with_comment(repo_path, fname, func_start, func_end, comment_line, QUESTION)
    RUBRIC = open(f_rubric).read()
    
    #for f_submission in glob(os.path.join(args.answer_dir, "*", str(sample_num), f"{sample_num}_function*.txt")):
    for f_submission in glob(os.path.join(args.answer_dir, "*", str(sample_num), f"t*.txt")):
        model_name = f_submission.split(os.sep)[-3]  

        #trial = os.path.basename(f_submission).replace("t"
        trial = os.path.splitext(os.path.basename(f_submission))[0].replace("t","")

        if trial == "": 
            trial = 1
        else:
            trial = int(trial)

        out_file = os.path.join(args.out_dir, model_name, str(sample_num), f"score_{trial}.txt")

        print(f_submission)
        print(out_file)
        

        if os.path.exists(out_file):
            continue

        ANSWER = open(f_submission).read()

        prompt = (
            "You are a strict grader evaluating a candidate answer to a contextualized "
            "coding question. You will be provided with the question, the surrounding "
            "function, and the rubric. Evaluate the answer against the rubric exactly. "
            "Do not give credit for claims not supported by the code context.\n\n"
            "The rubric has numbered items (1, 2, ...), each with lettered subitems "
            "(a, b, ...). Each subitem is a DEDUCTION CONDITION. For each subitem, decide "
            "whether that condition is met by the answer:\n"
            "- If the condition describes something the answer FAILS to do (e.g. 'the "
            "answer should state X'), set \"deducted\": true when the answer does not do it.\n"
            "- If the condition describes an ERROR the answer makes (e.g. 'if the answer "
            "incorrectly states Y'), set \"deducted\": true when the answer makes that error.\n"
            "In both cases, \"deducted\": true means the answer LOSES that subitem's points. "
            "There is no partial credit.\n\n"
            "Return ONLY a valid JSON list, one object per subitem, covering every subitem "
            "in the rubric. Identify each subitem by its ID (item number + subitem letter, "
            "e.g. \"1a\", \"2c\"). Required format for each subitem:\n"
            "{ \"item\": \"1a\", \"deducted\": false, \"feedback\": \"Detailed analysis here\" }\n"
            "DO NOT RETURN ANY TEXT OUTSIDE OF THE JSON LIST.\n\n"
            f"Question: {QUESTION}\n"
            f"Code Context: {CODE}\n"
            f"Rubric: {RUBRIC}\n"
            f"CANDIDATE_ANSWER: {ANSWER}"
        )

        g_eval_prompt =  (


        )

        #print(f_submission) 
        print("-"*100)
        print()
        response = query_cld(prompt, args.model)
        print(response)

        print("="*100)
        print()

        
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        with open(out_file, "w") as f:
            f.write(response) 
    
