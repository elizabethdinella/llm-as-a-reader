import argparse
import anthropic
import os
import json
import ollama
from glob import glob
from tqdm import tqdm
import sys
import openai


def parse_args():
    parser = argparse.ArgumentParser(description="Grade a submission against a rubric.")
    parser.add_argument("f_question", help="File with the question")
    parser.add_argument("f_rubric", help="File with the rubric")
    parser.add_argument("answer_dir", help="Dir of model answers")
    parser.add_argument("out_dir", help="output directory")
    parser.add_argument("--model", default="claude-opus-5", help="model to use")
    parser.add_argument("--sample-num", default="1a",
                        help="question number; used as the output subfolder (default 1a, as before)")
    parser.add_argument("--seed", default=None,
                        help="few-shot: selected.json whose samples (with their manual labels) are shown as graded examples")
    return parser.parse_args()


def query_gpt_mini(prompt):
    model = "gpt-oss:120b"

    messages = [{"role": "user", "content": prompt}]

    resp = ollama.chat(
        model=model,
        messages=messages
        #options={"temperature": temperature},
    )

    return resp["message"]["content"]


def query_gpt(prompt, model):
    client = openai.OpenAI()

    response = client.responses.create(
        model=model,
        input=prompt,
        reasoning={"effort": os.environ.get("GPT_REASONING", "medium")},
    )

    return response.output_text


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
            temperature=1,
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

    return message


def rubric_items(rubric_text):
    """Item IDs in rubric order: the text before ':' in each key."""
    return [k.split(":", 1)[0].strip() for k in json.loads(rubric_text)]


def load_examples(f_seed, answer_dir, items):
    """Graded examples from a selected.json: each sample's answer text plus its
    manual labels (scores[item] is True when the point was deducted)."""
    examples = []
    for s in json.load(open(f_seed)):
        f_answer = os.path.join(answer_dir, s["model"], f"answer_{s['answer_trial']}.txt")
        if not os.path.exists(f_answer):
            sys.exit(f"few-shot example not found: {f_answer}")
        scores = s.get("scores") or {}
        if not all(i in scores for i in items):
            sys.exit(f"selected.json sample {s['model']} {s['answer_trial']} has no manual labels for every item")
        form = "\n".join(json.dumps({"deducted": bool(scores[i])}) for i in items)
        examples.append((s["model"], s["answer_trial"], open(f_answer).read(), form))
    return examples


if __name__ == "__main__":
    args = parse_args()

    QUESTION = open(args.f_question).read()
    RUBRIC = open(args.f_rubric).read()
    ITEMS = rubric_items(RUBRIC)

    sample_num = str(args.sample_num)

    LANG = "Java"
    score_trial = "1"

    examples = load_examples(args.seed, args.answer_dir, ITEMS) if args.seed else []
    if examples:
        shots = ["Graded Examples (scored by expert graders using this rubric):\n\n"]
        for k, (_, _, ans, form) in enumerate(examples, 1):
            shots.append(f"Example {k} Answer:\n{ans}\n")
            shots.append(f"Example {k} Evaluation Form:\n{form}\n\n")
        SHOTS = "".join(shots)
        print(f"few-shot: {len(examples)} examples from {args.seed}")
    else:
        SHOTS = ""

    answers = glob(os.path.join(args.answer_dir, "*", "answer_*.txt"))
    for f_submission in tqdm(answers):
        model_name = f_submission.split(os.sep)[-2]
        trial = os.path.splitext(os.path.basename(f_submission))[0].replace("answer_","")

        if trial == "":
            trial = 1
        else:
            trial = int(trial)

        out_file = os.path.join(args.out_dir, model_name, str(sample_num), f"score_{trial}_{score_trial}.txt")

        if os.path.exists(out_file):
            continue

        ANSWER = open(f_submission).read()

        geval_prompt =  (
           f"You will be given a candidate answer about {LANG} code. ",
            "Your task is to rate the answer based on a rubric. ",
            "Question:\n",
            f"{QUESTION}\n\n",
            "Rubric:\n",
            f"{RUBRIC}\n\n",
            SHOTS,
            "Evaluation Steps:\n\n",
            "1. Read the answer carefully.\n",
            "2. Read the rubric carefully.\n",
            "3. For each rubric-item, decide if the point should be awarded based on the sub-item deduction criteria.\n",
            "4. Output your answer in the following format:\n",
            "{\"deducted\": true/false}\n"
            "There should be one entry for each rubric item.\n",
            "Candidate Answer: \n"
            f"{ANSWER}\n",
            "Evaluation Form:"
        )

        prompt = " ".join(geval_prompt)

        if "claude" in args.model:
            response = query_cld(prompt, args.model)
        elif "gpt-oss" in args.model:
            response = query_gpt_mini(prompt)
        elif "gpt" in args.model:
            response = query_gpt(prompt, args.model)

        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        with open(out_file, "w") as f:
            f.write(response)
