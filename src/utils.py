import sys
import anthropic
import openai
import os
import json
import ollama
import re
import csv
from models import Status, Ambiguity, Sample
from consts import dataset_dir, Mode, lang
import consts
from glob import glob
from json_repair import repair_json

def load_or_generate_refined_ambiguities(f_refined, _round, ambiguities, few_shot, backbone_llm):
    new_ambiguities = set()

    if os.path.exists(f_refined):
        with open(f_refined) as f:
            new_as = set([Ambiguity.from_dict(new_a) for new_a in json.load(f)])

        new_ambiguities |= new_as
    else:
        print("MISSING REFINED AMBIGUITIES FOR ROUND ", _round)
        #print("PRESS ENTER TO GENERATE THEM")
        #input()

        new_as = []
        for ITEM in consts.ITEMS:
            try:
                missing_as = refine_ambiguities(few_shot, ambiguities, ITEM, backbone_llm)
            except ValueError as e:
                print("no usable forks for", ITEM, "-", e)
                missing_as = {"forks": []}
            print("adding", missing_as, "for", ITEM)
            #input()

            if isinstance(missing_as, dict) and missing_as.get("forks"):
                for fork in missing_as["forks"]:
                    fork["id"] = ITEM + "_" + fork["id"].split("_", 1)[-1]   # force the item it was generated for
                    new_a = Ambiguity.from_dict(fork)
                    #COV[new_a.id] = 0
                    new_ambiguities.add(new_a)
                    new_as += [new_a]

        with open(f_refined, "w") as f:
            json.dump([a.to_dict() for a in new_as], f, indent=4)

        print("saved current ambiguities to", f_refined)
    
    return new_ambiguities

def load_initial_ambiguities(mode, backbone_llm):
    ambiguities = set()
    print("Generating initial set of ambiguities")
    for item in consts.ITEMS:
        print("For item", item)
        a_dir = f"{consts.get_initial_ambiguity_dir()}/{consts.lang}/{consts.sample_num}/{item}.txt"
        if os.path.exists(a_dir):
            a = json.load(open(a_dir))

            for a_i in a:
                #Serialize from a JSON
                ambiguities.add(Ambiguity.from_dict(a_i))
        else:
            a = generate_ambiguities(item, mode, backbone_llm)
            with open(a_dir, "w") as f:
                json.dump(a, f, indent=4)

            for a_i in a:
                ambiguities.add(Ambiguity.from_dict(a_i))

    return ambiguities


def load_samples():
    samples = []
    
    for _model_dir in glob(os.path.join(consts.get_answer_dir(), "*")):
        if not os.path.isdir(_model_dir): continue
        _model = os.path.basename(_model_dir)
        #for answer_trial in range(1,4):
        for answer_trial in range(1,consts.get_max_trials()+1):
            samples +=  [Sample(None, None, _model, str(answer_trial), "1", str(consts.sample_num))] 

    return samples

def load_preds(f_score):
    try:
        scores = json.load(open(f_score))
    except json.decoder.JSONDecodeError:
        #print("cannot parse entire file.. trying line by line")
        content = open(f_score).read().split("\n")
        scores = []
        for line in content:
            if not line: continue
            try:
                scores += [json.loads(line)]
            except json.decoder.JSONDecodeError:
                continue

        assert len(scores) == len(const.ITEMS) 

    score_obj = {}
    for score, ITEM in zip(scores, consts.ITEMS):
        score_obj[ITEM] = list(score.values())[0]

    return score_obj
    

def manually_label(selected_sample):
    #print()
    #print()
    #print("Query the user for labels.... For this script, we will just read in the manual labels")

    model = selected_sample.model
    if not "gpt" in model:
        m_norm = model.replace("-"," ")
    else:
        m_norm = model

    key = (m_norm, int(selected_sample.answer_trial))
    manual_deductions = consts.get_manual_deductions()
    manual = manual_deductions[key]

    selected_sample.scores = {}
    for ITEM in consts.ITEMS:
        selected_sample.scores[ITEM] = (ITEM in manual)

    #print(model, ":", selected_sample.answer_trial)
    #print(selected_sample.scores)
    #print(manual)

    return selected_sample


def query_gpt_mini(messages):
    model = "gpt-oss:120b"

    resp = ollama.chat(
        model=model,
        messages=messages,
        options={"num_ctx": 65536}
        #options={"temperature": temperature},
    )

    return resp["message"]["content"]

def query_gpt(messages, model):
    client = openai.OpenAI()  # reads OPENAI_API_KEY
    effort = os.environ.get("GPT_REASONING", "medium")

    response = client.responses.create(
        model=model,
        input=messages,
        reasoning={"effort": effort},
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
    elif model == "claude-sonnet-5.5":
        endpoint_name = "claude-sonnet-5-5"
    else:
        raise Exception(f"MODEL {model} NOT FOUND")

    #for message in messages:
    #    print(message)

    #print("QUERYING DISABLED!")
    #sys.exit(1)


    client = anthropic.Anthropic()

    with client.messages.stream(
            model=endpoint_name,
            temperature=1,
            max_tokens=64000,
            messages=messages
            ) as stream:
                response = stream.get_final_message()

    
    message = "".join(b.text for b in response.content if b.type == "text")
    return message





def generate_ambiguities(RUBRIC_ITEM, mode, backbone_llm):
    rubric = consts.get_rubric()
    #print(rubric)
    #input()
    prompt = f'''You are auditing one rubric sub-item for ambiguity, and expressing each ambiguity
        as a SPLIT: a single axis on which a careful grader could go two ways.

        INPUTS
        - Full rubric: {rubric}             # context only, to understand the item in place
        - Target sub-item: {RUBRIC_ITEM}    # the ONE item whose note you are auditing

        Use the full rubric only to understand what the target sub-item means and how it
        relates to the others. Audit the TARGET sub-item only. Do not report ambiguity
        that belongs to a different sub-item.

        TASK
        Find the distinct axes of ambiguity in this sub-item -- the underspecified points
        (vague thresholds, undefined terms, unstated scope, unclear boundaries with other
        sub-items) where two graders could reasonably reach different deduct/no_deduct
        decisions on the SAME answer.

        Express each as a SPLIT with two sides. Each side is a self-contained
        deduct/no_deduct rule a grader could actually follow without seeing the other side.

        Requirements for a valid split:
        - The two sides must DISAGREE on some real answer. If you cannot describe an
          answer they would grade differently, it is not a split -- drop it.
        - Both sides must be genuinely defensible. Do not pair a real reading against a
          strawman no grader would hold.
        - Each side states its own deduct/no_deduct condition in full.
        - Keep splits on DIFFERENT axes. If two splits would divide answers the same way,
          give one. Do not emit near-duplicate axes.
        - If the sub-item is unambiguous, return an empty list.

        OUTPUT
        A JSON list. Each element:
        {{
          "id": "<short_slug>",              # e.g. "2c_granularity"
          "name": "<one line naming the axis: side-a-gist vs side-b-gist>",
          "side_a": "<full deduct/no_deduct rule for one reading>",
          "side_b": "<full deduct/no_deduct rule for the opposing reading>"
        }}
        Nothing else.'''

    messages = [{"role": "user", "content": prompt}]

    if backbone_llm.startswith("claude"):
        response = query_cld(messages, backbone_llm)
    elif backbone_llm.startswith("gpt-oss"):
        response = query_gpt_mini(messages)
    elif backbone_llm.startswith("gpt"):
        response = query_gpt(messages, backbone_llm)
    else:
        print(backbone_llm)
        assert False

    #response = query_cld(messages, "claude-opus-5")
    print(response)
        
    return parse_json(response)

def _score_side(sample, side, rubric_item, backbone_llm):
    ANSWER = open(sample.f_submission).read()
    rubric = consts.get_rubric()
    prompt = f'''You are applying ONE grading rule to a candidate answer.
    INPUTS
    - Full rubric: {rubric}          # context only, to understand the item in place
    - Target sub-item: {rubric_item} # the item this rule is for
    - Rule: {side}                   # the single deduct/no_deduct rule to apply
    - Answer: {ANSWER}               # the candidate answer

    TASK
    Apply the Rule exactly as written to decide deduct or no_deduct for the target
    sub-item on this answer. Use the full rubric only to understand the item; the
    Rule is the sole basis for your decision. Do not apply any standard other than
    the Rule, even if you think the item should be graded differently.

    Quote the span of the answer your decision turns on. If no span is relevant to
    the Rule, say so.

    OUTPUT
    Return only JSON:
    {{
      "decision": "deduct" | "no_deduct",
      "answer_span": "<verbatim span, or null>",
      "why": "<one line: how the Rule applied to that span>"
    }}'''

    #print(prompt)
    #sys.exit(1)
    messages = [{"role": "user", "content": prompt}]

    if backbone_llm.startswith("claude"):
        response = query_cld(messages, backbone_llm)
    elif backbone_llm.startswith("gpt-oss"):
        response = query_gpt_mini(messages)
    elif backbone_llm.startswith("gpt"):
        response = query_gpt(messages, backbone_llm)
    else:
        print(backbone_llm)
        assert False
    #print(response)

    return response


def parse_json(text, want_key=None):
    """Parse JSON from a model response. With want_key, return the first
    object in the response that has that key."""
    if want_key is None:
        return _parse_json_any(text)
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text or ""):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(text[i:])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and want_key in obj:
                return obj
    obj = _parse_json_any(text)
    if isinstance(obj, dict) and want_key in obj:
        return obj
    raise ValueError(f"no JSON object with key {want_key!r} in response: {(text or '')[:300]!r}")

def _parse_json_any(text):
    """Extract and parse a JSON object/array from a model response.
    Tolerates code fences, prose before/after, and trailing commas.
    Raises ValueError if nothing parseable is found."""
    if text is None:
        raise ValueError("empty response")

    # 1. Try ```json fenced blocks first, then the whole response.
    #    Other fences (```java etc.) are left alone.
    candidates = [m.group(1) for m in re.finditer(r"```json\s*(.*?)```", text, re.DOTALL)]
    candidates.append(text)

    for c in candidates:
        c = c.strip()
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            pass

    # 2. Try every { or [ position in the full response; take the first that parses.
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "{[":
            try:
                obj, _ = decoder.raw_decode(text[i:])
                if isinstance(obj, (dict, list)) and obj:
                    return obj
            except json.JSONDecodeError:
                continue

    # 3. Last resort: repair the whole response.
    repaired = repair_json(text, return_objects=True)
    if repaired:
        return repaired
    raise ValueError(f"no JSON found in response: {text[:300]!r}")

    

def _outermost_json_span(s):
    """Return the substring from the first { or [ to its matching close,
    tracking string state so braces inside strings don't miscount."""
    start = None
    for i, ch in enumerate(s):
        if ch in "{[":
            start = i
            open_ch, close_ch = ch, ("}" if ch == "{" else "]")
            break
    if start is None:
        return None

    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
    return None   # unbalanced

def _unwrap(obj):
    # gpt-oss sometimes wraps its answer in a list: [{"decision": ...}]
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return obj[0]
    return obj

def score_side_a(sample, a_i, rubric_item, backbone_llm):
    a = _score_side(sample, a_i.side_a, rubric_item, backbone_llm)
    try:
        obj_a = parse_json(a)
    except json.decoder.JSONDecodeError:
        print("cannot parse json")
        print(a)
        sys.exit(1)

    return _unwrap(obj_a)
def score_side_b(sample, a_i, rubric_item, backbone_llm):
    b = _score_side(sample, a_i.side_b, rubric_item, backbone_llm)
    try:
        obj_b = parse_json(b)
    except json.decoder.JSONDecodeError:
        print("cannot parse json")
        print(b)
        sys.exit(1)

    return _unwrap(obj_b)
def load_or_gen_ambiguity_coverage(sample, a, backbone_llm):
    cache_prefix =  consts.get_cache_prefix(backbone_llm)
    fname = os.path.join(cache_prefix, a.id, sample.key().replace(" ", "-") + ".txt")

    if not os.path.exists(fname):
        #print(fname, "does not exist... ")
        print(fname)
        print("this must be a newly generated ambuigity")
        print("press enter to confirm.....")
        #input() 

        score_a = score_side_a(sample, a, a.r_item, backbone_llm)
        score_b = score_side_b(sample, a, a.r_item, backbone_llm)
        for _s in (score_a, score_b):  # normalize malformed decisions, e.g. 'no_decuct...'
            if isinstance(_s, dict):
                _d = str(_s.get('decision', '')).lower()
                if _d.startswith('no'): _s['decision'] = 'no_deduct'
                elif 'deduct' in _d or 'decuct' in _d: _s['decision'] = 'deduct'

        scores = [score_a, score_b]
        def _norm(o):  # normalize malformed decisions anywhere inside scores
            if isinstance(o, dict):
                if 'decision' in o:
                    _d = str(o['decision']).lower()
                    if _d.startswith('no'): o['decision'] = 'no_deduct'
                    elif 'deduct' in _d or 'decuct' in _d: o['decision'] = 'deduct'
                for v in o.values(): _norm(v)
            elif isinstance(o, (list, tuple)):
                for v in o: _norm(v)
        print('SCORETYPE', type(score_a).__name__, file=open('/tmp/scoretype.txt','a'))
        _norm(scores)

        os.makedirs(os.path.dirname(fname), exist_ok=True)
        with open(fname, "w") as f:
            json.dump(scores, f)

        return scores
    else:
        with open(fname) as f:
            return json.load(f)

def calibrate(few_shot_samples, ambiguities, backbone_llm):
    for a in ambiguities:
        if a.r_item not in consts.ITEMS:  # normalize item names: case, and '3a' -> '3'
            _m = {str(x).lower(): x for x in consts.ITEMS}
            _r = str(a.r_item).lower()
            if _r not in _m and _r[:-1] in _m and _r[-1:].isalpha():
                _r = _r[:-1]
            if _r in _m:
                a.r_item = _m[_r]
        if a.r_item not in consts.ITEMS:   # fork labeled with an item this question doesn't have
            print("skipping", a.id, "- no rubric item", a.r_item)
            a.status = Status.CONFLICT
            continue
        #print("processing ambiguity", repr(a))
        resolved = False
        conflict = False
        for sample in few_shot_samples:
            diff = load_or_gen_ambiguity_coverage(sample, a, backbone_llm)
            true_label = "deduct" if sample.scores[a.r_item] == True else "no_deduct"

            if diff[0]["decision"] != diff[1]["decision"]:
                resolved = True
                a.resolvers += [sample]

                #print(sample.model, sample.answer_trial)
                #print(sample.scores)
                #true_label = "deduct" if sample.scores[a.r_item.upper()] == True else "no_deduct"

                if diff[0]["decision"] == true_label:
                    #print("PICKING SIDE A")

                    if a.status == Status.SIDE_B: 
                        a.status = Status.CONFLICT
                        conflict = True
                    else:
                        a.status = Status.SIDE_A
                else:
                    #print("PICKING SIDE B")
                    if diff[1]["decision"] != true_label: print("ASSERTFAIL", a.id, a.r_item, sample.model, sample.answer_trial, repr(true_label), diff, file=open("/tmp/assertfail.txt","a"))
                    if diff[1]["decision"] != true_label: continue  # garbled side output; skip
                    if a.status == Status.SIDE_A: 
                        a.status = Status.CONFLICT
                        conflict = True
                    else:
                        a.status = Status.SIDE_B

            elif diff[0]["decision"] == diff[1]["decision"] and diff[0]["decision"] != true_label:
                a.status = Status.CONFLICT
                conflict = True
            #else:
            #    print(sample.key(), "does not resolve ambiguity", a.id)

            if conflict: break

    return ambiguities

def generate_notes(ambiguities, RUBRIC_ITEM, backbone_llm):
    resolved_as = " ".join([a.resolved_str() for a in ambiguities if a.r_item == RUBRIC_ITEM and a.is_resolved()])
    rubric = consts.get_rubric()

    prompt = f'''You are writing a grading note for one rubric sub-item, from a set of RESOLVED
        forks that were validated against human labels.

        Each fork is one axis of ambiguity with two sides. A RESOLVED fork has a winning
        side -- the reading the human labels settled on. The note you write must encode
        each resolved fork's WINNING side as a rule; the losing sides are discarded.

        INPUTS
        - Full rubric: {rubric}                # context only
        - Target sub-item: {RUBRIC_ITEM}       # the item this note is for
        - Resolved forks: {resolved_as}     # one or more validated forks for THIS
                                               # sub-item. Each is given as its name plus
                                               # its WINNING side's deduct/no_deduct rule.
                                               # Every winning side is correct; your note
                                               # must honor all of them.

        TASK
        Write a single, coherent grading note for the target sub-item that a grader can
        apply directly to decide deduct / no_deduct.

          from fork's winning sides.
        - The note must be consistent with EVERY resolved fork's winning side. Each one
          fixes how a specific ambiguity is settled; the note has to encode all of them
          at once.
        - Merge the winning sides into one instruction, not a list. Where they address
          different aspects (what counts as a claim, what scope, how hedging is treated),
          fold them into a unified rule.
        - State the deduct condition and the no_deduct condition plainly.
        - Use the winning sides' own concrete language and examples where they sharpen
          the note; do not invent new criteria beyond what the resolved forks establish.
        - If two winning sides genuinely CONFLICT (cannot both hold on some answer), do
          NOT paper over it: write the note for the sides that don't conflict and add a
          final line "CONFLICT: <which forks, and the case that breaks them>".

        Do not mention anything the forks leave unsettled. Say only what the resolved
        forks' winning sides license.

        OUTPUT
        The grading note as plain prose. If a conflict was found, the CONFLICT line last.'''

    messages = [{"role": "user", "content": prompt}]

    if backbone_llm.startswith("claude"):
        response = query_cld(messages, backbone_llm)
    elif backbone_llm.startswith("gpt-oss"):
        response = query_gpt_mini(messages)
    elif backbone_llm.startswith("gpt"):
        response = query_gpt(messages, backbone_llm)
    else:
        print(backbone_llm)
        assert False

    print(response)

    return response

def refine_ambiguities(few_shot_samples, ambiguities, RUBRIC_ITEM, backbone_llm):
    max_forks = 2

    SAMPLES_CREDITED = ""
    SAMPLES_DEDUCTED = ""
    for idx, sample in enumerate(few_shot_samples):
        ANSWER = open(sample.f_submission).read()

        print(sample.scores)
        if sample.scores[RUBRIC_ITEM] == False:
            SAMPLES_CREDITED += f"Sample {idx}\n " + "Candidate Answer: \n" + f"{ANSWER}\n" 
        else:
            SAMPLES_DEDUCTED  += f"Sample {idx}\n " + "Candidate Answer: \n" + f"{ANSWER}\n" 
             
    EXISTING_FORKS = "  ".join([a.resolved_str() for a in ambiguities if a.r_item == RUBRIC_ITEM and a.is_resolved()])

    prompt = f'''You are looking for MISSING distinctions in a grading rubric sub-item.

    Existing forks (axes already known) for this sub-item:
    {EXISTING_FORKS}   # id + name + both sides, so you don't repeat one

    These samples all look similar to the existing forks, yet humans graded them
    differently. The existing forks cannot explain the difference.

    no_deduct (humans gave credit):
    {SAMPLES_CREDITED}

    deduct (humans withheld credit):
    {SAMPLES_DEDUCTED}

    TASK
    Find the distinctions that separate the credited group from the deducted group
    and are NOT already existing forks. State each as a new fork: a single axis with
    two sides, each a deduct/no_deduct rule.

    Requirements:
    - Return at most {max_forks} forks. Return only as many as the answers support;
      fewer is fine, and an empty list is fine.
    - Each fork must be on a DIFFERENT axis from the existing forks and from the other
      forks you return. If two would divide the samples the same way, give one.
    - Each fork must explain at least one sample's label that the existing forks do not.
    - The distinction must be grounded in what the answers actually say, not a feature
      you have to strain to see. Quote the span that carries it.
    - Order forks by how many samples they explain, most first.

    If no principled distinction separates the groups (they genuinely look
    equivalent and the labels may be inconsistent), return an empty list and say why.

    OUTPUT (JSON)
    {{
      "forks": [
        {{
          "id": "{RUBRIC_ITEM}_<short_slug>",
          "name": "<one line naming the axis: side-a-gist vs side-b-gist>",
          "side_a": "...",             # rule; side A should credit the credited group
          "side_b": "...",
          "explains": [<sample ids>],  # samples whose label this fork accounts for
          "evidence": [
            {{"id": <n>, "label": "...", "span": "...", "side_it_supports": "A"|"B"}}
          ],
          "why": "<one line>"
        }}
      ],
      "note_if_none": "<if forks is empty, why the groups look equivalent>"
    }}'''
    
    messages = [{"role": "user", "content": prompt}]

    if backbone_llm.startswith("claude"):
        response = query_cld(messages, backbone_llm)
    elif backbone_llm.startswith("gpt-oss"):
        response = query_gpt_mini(messages)
    elif backbone_llm.startswith("gpt"):
        response = query_gpt(messages, backbone_llm)
    else:
        print(backbone_llm)
        assert False

    #response = query_cld(messages, "claude-opus-5")
    return parse_json(response, want_key="forks")
def refine_ambiguities_single(few_shot_samples, ambiguities, RUBRIC_ITEM):
    SAMPLES_CREDITED = ""
    SAMPLES_DEDUCTED = ""
    for idx, sample in enumerate(few_shot_samples):
        ANSWER = open(sample.f_submission).read()

        print(sample.scores)
        if sample.scores[RUBRIC_ITEM] == False:
            SAMPLES_CREDITED += f"Sample {idx}\n " + "Candidate Answer: \n" + f"{ANSWER}\n" 
        else:
            SAMPLES_DEDUCTED  += f"Sample {idx}\n " + "Candidate Answer: \n" + f"{ANSWER}\n" 
             
    print("SAMPLE MAP: ")
    for idx, sample in enumerate(few_shot_samples):
        print(idx, sample.model, sample.answer_trial)

    print("Samples credited", SAMPLES_CREDITED)
    print("samples deducted", SAMPLES_DEDUCTED)

    EXISTING_FORKS = [str(a) for a in ambiguities if a.r_item == RUBRIC_ITEM]

    prompt = f'''You are looking for a MISSING distinction in a grading rubric sub-item.

    Existing forks (axes already known) for this sub-item:
    {EXISTING_FORKS}   # id + name + both sides, so you don't repeat one

    These samples all look similar to the existing forks, yet humans graded them
    differently. The existing forks cannot explain the difference.

    no_deduct (humans gave credit):
    {SAMPLES_CREDITED}   

    deduct (humans withheld credit):
    {SAMPLES_DEDUCTED}

    TASK
    Find the smallest distinction that separates the credited group from the
    deducted group and is NOT already one of the existing forks. State it as a new
    fork: a single axis with two sides, each a deduct/no_deduct rule.

    The distinction must be grounded in what the answers actually say, not a feature
    you have to strain to see. Quote the span in each group that carries the
    distinction.

    If no principled distinction separates the groups (they genuinely look
    equivalent and the labels may be inconsistent), say so instead of inventing one.

    OUTPUT (JSON)
    {{
      "axis_found": true | false,
      "fork": {{                        # null if axis_found is false
        "id": "<short_slug>",              # e.g. "2c_granularity"
        "name": "<one line naming the axis: side-a-gist vs side-b-gist>",
        "side_a": "...",               # rule; side A should credit the credited group
        "side_b": "..."
      }},
      "evidence": [                    # what in each sample carries the distinction
        {{"id": <n>, "label": "...", "span": "...", "side_it_supports": "A"|"B"}}
      ],
      "why": "<one line>",
      "note_if_no_axis": "<if axis_found false, why they look equivalent>"
    }}'''


    print(prompt)
    messages = [{"role": "user", "content": prompt}]

    response = query_cld(messages, "claude-opus-5")
    print(response)
    return parse_json(response)

def query_scoring_model_reading_interpretations_rubric_only(RUBRIC_ITEM):
    prompt = f'''You are auditing one grading note for ambiguity.

    INPUTS
    - Full rubric: {RUBRIC}             # context only: the whole rubric, so the
                                        # target sub-item can be understood in place
    - Target sub-item: {RUBRIC_ITEM}    # the ONE item whose note you are auditing

    Use the full rubric only to understand what the target sub-item means and how it
    relates to the others. Audit the rubric for the TARGET sub-item only. Do not
    report ambiguity that actually belongs to a different sub-item.

    TASK
    List the distinct, defensible ways a careful grader could read this rubric when
    deciding deduct / no-deduct on the target sub-item. Focus only on the parts that
    are actually underspecified (vague thresholds, undefined terms, unstated scope).
    For each reading:
    - state the reading in one line
    - say what deduct/no-deduct rule it implies

    Rules:
    - Only readings a real grader might genuinely hold. Do not invent strained ones.
    - Keep readings genuinely different. If two collapse to the same rule, give one.
    - If the rubric item is unambiguous, say so and return a single reading.

    OUTPUT
    A numbered list of readings. Nothing else.
    '''

    messages = [{"role": "user", "content": prompt}]

    response = query_cld(messages, "claude-opus-5")
    return response

def get_geval_prompt(notes):
    rubric = consts.get_rubric()
    question = consts.get_question()
    lang = consts.lang
    
    if consts.get_mode() == Mode.RDB:
        geval_instructions =  (
            f"You will be given a candidate answer about {lang} code. ",
            "Your task is to rate the answer based on a rubric. ",
            "Each Rubric Item will have a point value indicated with the \"points\" field. ",
            "Each Rubric Item will have sub-items explaining how points should be deducted.\n",
            "Question:\n",
            f"{question}\n\n",
            "Rubric:\n",
            f"{rubric}\n\n", 
            "Important Rubric Notes:\n", 
            f"{notes}\n\n", 
            "Evaluation Steps:\n\n",
            "1. Read the answer carefully.\n",
            "2. Read the rubric carefully.\n",
            "3. For each sub-item, decide if the point(s) should be deducted based on the sub-item deduction criteria.\n", 
            "4. Output a JSON list with one entry per sub-rubric item, in order:\n",
            '[{"deducted": true/false}, ...]\n\n',
            #"4. Output your answer in the following format:\n",
            #"{\"deducted\": true/false}\n",
        #"{\"justification\": reason for your scoring, \"deducted\": true/false}\n"
            #"There should be one entry for each sub-rubric item.\n",
        )

    elif consts.get_mode() == Mode.APCS:
        geval_instructions =  (
            f"You will be given a candidate answer about {lang} code. ",
            "Your task is to rate the answer based on a rubric. ",
            "Question:\n",
            f"{question}\n\n",
            "Rubric:\n",
            f"{rubric}\n\n", 
            "Important Rubric Notes:\n", 
            f"{notes}\n\n", 
            "Evaluation Steps:\n\n",
            "1. Read the answer carefully.\n",
            "2. Read the rubric carefully.\n",
            "3. For each sub-item, decide if the point(s) should be awarded based on the sub-item deduction criteria.\n", 
            "4. Output a JSON list with one entry per sub-rubric item, in order:\n",
            '[{"deducted": true/false}, ...]\n\n',
        )

    else:
        assert False

    return geval_instructions


def query_scoring_model_few_shot(f_submission, samples, notes, backbone_llm):
    geval_instructions = get_geval_prompt(notes)
    
    ANSWER = open(f_submission).read()
    real_input = "Candidate Answer: \n" + f"{ANSWER}\n" + "Evaluation Form: "

    geval_instructions = " ".join(geval_instructions)

    #print(geval_instructions)
    #sys.exit(1)

    messages = []
    for sample in samples:
        answer = open(sample.f_submission).read()
        content = geval_instructions + "Candidate Answer: \n" + f"{answer}\n" + "Evaluation Form: "
        messages += [{"role": "user", "content": content}]
        
        deductions_json_str = "["
        for idx, (item, deducted) in enumerate(sample.scores.items()):
            deductions_json_str += "{\"deducted\": " + json.dumps(deducted) + "}"

            if not idx == len(sample.scores.items())-1:
                deductions_json_str += ", "

        deductions_json_str += "]"

        messages += [{"role": "assistant", "content": deductions_json_str}]

    messages += [{"role": "user", "content": geval_instructions + real_input}]

    #response = query_cld(messages, "claude-opus-5")
    if backbone_llm.startswith("claude"):
        response = query_cld(messages, backbone_llm)
    elif backbone_llm.startswith("gpt-oss"):
        response = query_gpt_mini(messages)
    elif backbone_llm.startswith("gpt"):
        response = query_gpt(messages, backbone_llm)
    else:
        print(backbone_llm)
        assert False

    return response


def score_both_sides(sample, a_i, rubric_item, backbone_llm):
    ANSWER = open(sample.f_submission).read()
    rubric = consts.get_rubric()
    prompt = f'''You are applying TWO grading rules, independently, to a candidate answer.
    INPUTS
    - Full rubric: {rubric}          # context only, to understand the item in place
    - Target sub-item: {rubric_item} # the item these rules are for
    - Rule A: {a_i.side_a}           # a single deduct/no_deduct rule
    - Rule B: {a_i.side_b}           # a single deduct/no_deduct rule
    - Answer: {ANSWER}               # the candidate answer

    TASK
    For each rule separately, apply that rule exactly as written to decide deduct
    or no_deduct for the target sub-item on this answer. Use the full rubric only to
    understand the item; each rule is the sole basis for its own decision. Do not
    let one rule influence your decision on the other, and do not apply any standard
    other than the rule, even if you think the item should be graded differently.

    For each rule, quote the span of the answer your decision turns on. If no span
    is relevant to that rule, say so.

    OUTPUT
    Return only JSON:
    {{
      "side_a": {{
        "decision": "deduct" | "no_deduct",
        "answer_span": "<verbatim span, or null>",
        "why": "<one line: how Rule A applied to that span>"
      }},
      "side_b": {{
        "decision": "deduct" | "no_deduct",
        "answer_span": "<verbatim span, or null>",
        "why": "<one line: how Rule B applied to that span>"
      }}
    }}'''

    messages = [{"role": "user", "content": prompt}]

    if backbone_llm.startswith("claude"):
        response = query_cld(messages, backbone_llm)
    elif backbone_llm.startswith("gpt-oss"):
        response = query_gpt_mini(messages)
    elif backbone_llm.startswith("gpt"):
        response = query_gpt(messages, backbone_llm)
    else:
        print(backbone_llm)
        assert False

    obj = parse_json(response)
    return [obj["side_a"], obj["side_b"]]
                    




    
