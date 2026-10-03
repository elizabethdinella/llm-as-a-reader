import argparse
import anthropic
import os
import json
import ollama
import consts
from glob import glob
from models import Sample
from tqdm import tqdm
import sys
import openai

def parse_args():
    parser = argparse.ArgumentParser(description="Grade a submission against a rubric.")
    parser.add_argument("sample_num", help="Sample number")
    parser.add_argument("dataset_dir", help="Dataset directory")
    parser.add_argument("checkout_dir", help="Dir of checked out projects")
    parser.add_argument("answer_dir", help="Dir of model answers")
    parser.add_argument("out_dir", help="output directory")
    parser.add_argument("lang", help="language")
    parser.add_argument("--model", default="claude-opus-5", help="model to use")
    parser.add_argument("--seed")
    return parser.parse_args()

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


def query_gpt_mini(messages):
    model = "gpt-oss:120b"

    #messages = [{"role": "user", "content": prompt}]

    resp = ollama.chat(
        model=model,
        messages=messages
        #options={"temperature": temperature},
    )

    return resp["message"]["content"]

def query_gpt(messages, model):
    client = openai.OpenAI()

    response = client.responses.create(
        model=model,
        input=messages
    )

    return response.output_text


def query_cld(messages, model):
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
            temperature=1,
            max_tokens=64000,
            messages=messages
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



if __name__ == "__main__":
    args = parse_args()

    f_sample = os.path.join(args.dataset_dir, "metadata", args.sample_num + ".json")

    consts.set_mode(consts.Mode.RDB, args.lang, int(args.sample_num))

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

    score_trial = "1"
    
    #for f_submission in glob(os.path.join(args.answer_dir, "*", str(sample_num), f"{sample_num}_function*.txt")):
    #print(glob(os.path.join(args.answer_dir, "*", str(sample_num), "t*.txt")))
    subs = glob(os.path.join(args.answer_dir, "*", str(sample_num), "t*.txt"))
    for f_submission in tqdm(subs):
        model_name = f_submission.split(os.sep)[-3]  


        #trial = os.path.basename(f_submission).replace("t"
        #trial = os.path.basename(f_submission).replace(f"{sample_num}_function", "").replace(".txt","").replace("_t","")
        trial = os.path.splitext(os.path.basename(f_submission))[0].replace("t","")

        if trial == "": 
            trial = 1
        else:
            trial = int(trial)

        #if not (model_name == "gemini-2.0-flash" and trial == 1): continue

        out_file = os.path.join(args.out_dir, model_name, str(sample_num), f"score_{trial}_{score_trial}.txt")

        #print(f_submission)
        #continue
        #print(out_file)
        

        if os.path.exists(out_file):
            continue

        ANSWER = open(f_submission).read()

        geval_prompt =  (
           f"You will be given a candidate answer about {args.lang} code. ",
            "Your task is to rate the answer based on a rubric. ",
            "Each Rubric Item will have a point value indicated with the \"points\" field. ",
            "Each Rubric Item will have sub-items explaining how points should be deducted.\n",
            "Question:\n",
            f"{CODE}\n\n",
            "Rubric:\n",
            f"{RUBRIC}\n\n", 
            "Evaluation Steps:\n\n",
            "1. Read the answer carefully.\n",
            "2. Read the rubric carefully.\n",
            "3. For each sub-item, decide if the point(s) should be deducted based on the sub-item deduction criteria.\n", 
            "4. Output your answer in the following format:\n",
            "{\"deducted\": true/false}\n"
            #"{\"justification\": reason for your scoring, \"deducted\": true/false}\n"
            "There should be one entry for each sub-rubric item.\n",
            #"Candidate Answer: \n"
            #f"{ANSWER}\n", 
            #"Evaluation Form:"
        )


        prompt = " ".join(geval_prompt)
        messages = []

        if args.seed:
            for s_obj in json.load(open(args.seed)):
                sample = Sample.from_dict(s_obj)
             
                answer = open(sample.f_submission).read()
                content = prompt + "Candidate Answer: \n" + f"{answer}\n" + "Evaluation Form: "
                messages += [{"role": "user", "content": content}]
                
                deductions_json_str = "["
                for idx, (item, deducted) in enumerate(sample.scores.items()):
                    deductions_json_str += "{\"deducted\": " + json.dumps(deducted) + "}"

                    if not idx == len(sample.scores.items())-1:
                        deductions_json_str += ", "

                deductions_json_str += "]"

                messages += [{"role": "assistant", "content": deductions_json_str}]


        real_input = "Candidate Answer: \n" + f"{ANSWER}\n" + "Evaluation Form: "
        
        messages += [{"role": "user", "content": prompt + real_input}]

        #print(prompt + real_input)
        #input()
        #print(messages)
        #input()

        #print(f_submission) 
        #print("-"*100)
        #print()

        if "claude" in args.model:
            response = query_cld(messages, args.model)
        elif "gpt-oss" in args.model:
            response = query_gpt_mini(messages)
        elif "gpt" in args.model:
            response = query_gpt(messages, args.model)
        else:
            assert False

        print(response)
        #input()

        #print("="*100)
        #print()

        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        with open(out_file, "w") as f:
            f.write(response) 

