# LLM-as-a-Reader

Artifact for "LLM-as-a-Reader: Automated Rubric Application via Active Ambiguity Resolution".

## Layout
- `scripts/`: entry points; run them from the repository root.
- `src/`: all Python code (LLM-as-a-Reader, LLM-as-a-Judge baselines, scoring, analysis).
- `apcs_generation/`: how the APCS responses were built.
- `data/`: APCS responses and labels, RubberDuckBench answers.
- `runs/`: every run output reported in the paper.
- `analysis/`: ambiguity and flagging statistics.

## Contents
- `utils.py`, `selection.py`, `calibrate.py`, `validate.py`, `consts.py`: LLM-as-a-Reader (ambiguity generation, rule application, greedy selection, refinement, grading notes, flagging). Prompts are in `utils.py`.
- `llm_judge_geval*.py`: the LLM-as-a-Judge baseline (G-Eval style), zero-shot and few-shot.
- `run_*.sh`, `compare_all.sh`, `eval.py`, `apcs_eval.sh`: experiment and scoring scripts.
- `src/amb_stats.py`, `src/flag_stats.py`: ambiguity and flagging statistics (no model calls), e.g. `python src/amb_stats.py "ambg-apcs-*-t[0-9]-claude-opus-5"`.
- `runs/rubberduckbench/`, `runs/apcs/`: all run outputs used in the paper (`ambg-*`: LLM-as-a-Reader, `random-*`: random selection, `llm-judge-*`: zero-shot judge, `llm-judge-fs-*`: few-shot judge). Each `ambg-*/round-1/` holds the selected responses (`selected.json`), ambiguities, grading notes (`notes.json`), and predictions.
- `data/apcs/sub/mistakes/<q>/`: the 115 generated APCS responses; `manual.csv` holds the expert labels. `data/apcs/apcs-correct/`: correct answers from 21 LLMs.
- `data/rdb/out/`: RubberDuckBench answers.
- `apcs_generation/`: clustering of correct answers and generation of incorrect responses.

## Data not included
The APCS free-response questions and scoring guidelines are copyrighted by the College Board. Download the 2026 AP Computer Science A free-response questions and scoring guidelines from AP Central and place them in `data/apcs/` (`q1a.txt` ... `q4.txt`, `rubric_1a.json` ... `rubric_4.json`).
RubberDuckBench is publicly available; place its dataset in `../crqbench/artifact/dataset/`.

## Running
Set `ANTHROPIC_API_KEY` (and `OPENAI_API_KEY` for GPT backbones).
- APCS: `Q=2 bash scripts/run_apcs.sh`, then `bash scripts/apcs_eval.sh 2`.
- RubberDuckBench: `bash scripts/compare_all.sh <question> java|py`.

Scripts write new runs to the repository root; to rescore a stored run, copy it from `runs/` to the root first.
