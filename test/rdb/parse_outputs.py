import re
import os
from glob import glob


sample_num = 5
lang = "py"

answer_dir = "../RubberDuckBench/results/out/"
answer_dir += lang + "/"

for f_submission in glob(os.path.join(answer_dir, "*", str(sample_num), "*_function*.txt")):

    print(f_submission)
    
    with open(f_submission, "r") as file:
        content = file.read()



    model = os.path.basename(os.path.dirname(os.path.dirname(f_submission)))
    OUT_DIR = os.path.join("out", lang, model, str(sample_num))

    pattern = re.compile(r"<answer>(([\S\s]*?))(?:<\/answer>)", flags=re.MULTILINE)

    matches = list(pattern.finditer(content))

    #print(len(matches))
    assert len(matches) == 1

    #continue
    match = matches[0]

    name = os.path.splitext(os.path.basename(f_submission))[0]  
    trial = int(name.split("_t")[-1]) if "_t" in name else 1
    #trial = int(name.split("_t")[-1])
    out_file = os.path.join(OUT_DIR, f"t{trial}.txt")

    #print("writing", match.group(1), "to" ,out_file)
    #print(match_num, match.group())
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as file:
        file.write(match.group(1))
        
