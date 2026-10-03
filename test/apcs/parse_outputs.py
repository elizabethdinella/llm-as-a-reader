import re
import os

#MODELS = ["gpt-4.1", "gpt-5", "gpt-mini-120", "gpt-mini-20", "gpt-o3", "deepseek-r1-70b", "claude-opus-5", "claude-opus-4.8", "claude-fable-5", "claude-sonnet-5", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-3.6-flash", "grok-4.5", "grok-4", "grok-3", "qwen3-coder", "qwen3", "mistral-large", "llama-scout-4", "llama3.3-70"]

MODELS = ["deepseek-r1-70b"]
LANGS = ["python", "java", "c++"]


for MODEL in MODELS:
    file_path = f"sub/mistakes/{MODEL}/1.txt" 

    
    with open(file_path, "r") as file:
        content = file.read()


    pattern = re.compile(r"<answer>([\S\s]*?)(?:<\/answer>)", flags=re.MULTILINE)
    #pattern = re.compile(r"<answer>([\S\s.][^<]*)<\/answer>", flags=re.MULTILINE)

    matches = pattern.finditer(content)

    print(file_path)
    for match_num, match in enumerate(matches, start=1):
        out_file = os.path.join(os.path.dirname(file_path), f"answer_{match_num}.txt")

        print(match_num, match.group())
        with open(out_file, "w") as file:
            file.write(match.group())
        

    #exit(1)
