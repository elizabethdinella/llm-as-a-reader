"""Check whether Ollama truncates the few-shot scoring prompt.

Builds the exact messages query_scoring_model_few_shot sends for one run,
then asks Ollama how many prompt tokens it actually evaluated, first with the
default context and then with a large num_ctx. If the default count is much
lower, the few-shot examples were being dropped.

Usage:
  python check_truncation.py ambg-java-3-t1-gpt-oss-120 3 java
  python check_truncation.py ambg-java-3-t1-gpt-oss-120 3 java --host http://127.0.0.1:11435
"""
import argparse
import json
import os

import ollama

import consts
import utils
from consts import Mode
from models import Sample


def build_messages(f_submission, samples, notes):
    # Mirrors utils.query_scoring_model_few_shot without calling the model.
    geval_instructions = " ".join(utils.get_geval_prompt(notes))
    answer = open(f_submission).read()
    real_input = "Candidate Answer: \n" + f"{answer}\n" + "Evaluation Form: "

    messages = []
    for sample in samples:
        ex = open(sample.f_submission).read()
        content = geval_instructions + "Candidate Answer: \n" + f"{ex}\n" + "Evaluation Form: "
        messages.append({"role": "user", "content": content})
        labels = ", ".join('{"deducted": ' + json.dumps(d) + "}" for d in sample.scores.values())
        messages.append({"role": "assistant", "content": "[" + labels + "]"})
    messages.append({"role": "user", "content": geval_instructions + real_input})
    return messages


def evaluated_tokens(client, messages, num_ctx=None):
    options = {"num_predict": 1}  # only need the prompt count, not an answer
    if num_ctx:
        options["num_ctx"] = num_ctx
    resp = client.chat(model="gpt-oss:120b", messages=messages, options=options)
    
    return resp["prompt_eval_count"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", help="e.g. ambg-java-3-t1-gpt-oss-120")
    ap.add_argument("sample_num", type=int)
    ap.add_argument("lang")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--num-ctx", type=int, default=65536)
    args = ap.parse_args()

    consts.set_mode(Mode.RDB, args.lang, args.sample_num)
    round_dir = os.path.join(args.run_dir, "round-1")

    with open(os.path.join(round_dir, "selected.json")) as f:
        few_shot = [Sample.from_dict(s) for s in json.load(f)]

    notes = ""
    f_notes = os.path.join(round_dir, "notes.json")
    if os.path.exists(f_notes):
        for k, v in json.load(open(f_notes)).items():
            notes += "\n" + k + ":\n" + v + "\n"

    # Any non-few-shot answer works as the target.
    keys = {s.key() for s in few_shot}
    target = next(s for s in utils.load_samples() if s.key() not in keys)

    messages = build_messages(target.f_submission, few_shot, notes)
    chars = sum(len(m["content"]) for m in messages)

    client = ollama.Client(host=args.host)
    default_count = evaluated_tokens(client, messages)
    full_count = evaluated_tokens(client, messages, args.num_ctx)

    print(f"messages:                {len(messages)} ({len(few_shot)} examples + target)")
    print(f"characters:              {chars}  (~{chars // 4} tokens)")
    print(f"evaluated, default ctx:  {default_count}")
    print(f"evaluated, num_ctx={args.num_ctx}: {full_count}")
    if full_count and default_count < 0.9 * full_count:
        print("TRUNCATED: the default context dropped part of the prompt.")
    else:
        print("Not truncated: the full prompt fits in the default context.")

    resp = client.chat(model="gpt-oss:120b", messages=messages)
    print(resp["message"].get("thinking", "")[-3000:])
    print(resp["message"]["content"])


if __name__ == "__main__":
    main()
