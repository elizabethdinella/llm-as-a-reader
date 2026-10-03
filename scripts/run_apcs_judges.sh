#!/bin/bash
# LLM-as-a-judge baselines on APCS: zero-shot and few-shot, 3 trials each.
#   Q=2 bash scripts/run_apcs_judges.sh                      # Claude Opus 5, both modes
#   Q=2 MODES=few-shot TRIALS=1 bash scripts/run_apcs_judges.sh
#
# Outputs (same naming as the ambg/random APCS runs, so eval finds them directly):
#   llm-judge-apcs-<q>-t<t>-<model>/      zero-shot
#   llm-judge-fs-apcs-<q>-t<t>-<model>/   few-shot, examples = the 5 samples in
#                                         ambg-apcs-<q>-t<t>-<model>/round-1/selected.json
# Needs (pull from git first):
#   data/apcs/q<q>.txt, data/apcs/rubric_<q>.json,
#   data/apcs/sub/mistakes/<q>/<model>/answer_<a>.txt and manual.csv,
#   ambg-apcs-<q>-t<t>-<model>/round-1/selected.json (few-shot examples and split),
#   random-apcs-<q>-t<t>-<model>/round-1/selected.json (zero-shot split, for eval)
# Existing score files are skipped, so rerunning only fills gaps.

Q="${Q:-2}"
MODEL="${MODEL:-claude-opus-5}"
MODES="${MODES:-zero-shot few-shot}"
TRIALS="${TRIALS:-1 2 3}"

QUESTION="data/apcs/q${Q}.txt"
RUBRIC="data/apcs/rubric_${Q}.json"
ANSWERS="data/apcs/sub/mistakes/${Q}"
for f in "$QUESTION" "$RUBRIC" "$ANSWERS/manual.csv"; do
  [ -e "$f" ] || { echo "Missing $f (git pull?)"; exit 1; }
done

mkdir -p logs
failed=()

for mode in $MODES; do
  if [ "$mode" = "few-shot" ]; then PREFIX="llm-judge-fs"; else PREFIX="llm-judge"; fi
  for t in $TRIALS; do
    name="${PREFIX}-apcs-${Q}-t${t}-${MODEL}"
    log="logs/${name}-geval.log"
    extra=()
    if [ "$mode" = "few-shot" ]; then
      shots="ambg-apcs-${Q}-t${t}-${MODEL}/round-1/selected.json"
      [ -f "$shots" ] || { echo "Skipping $name: no $shots (git pull?)"; failed+=("$name"); continue; }
      extra=(--seed "$shots")
    fi

    echo "[$(date +%T)] Running $name"
    python src/llm_judge_geval_apcs.py "$QUESTION" "$RUBRIC" "$ANSWERS" "${name}/" \
      --model "$MODEL" --sample-num "$Q" "${extra[@]}" > "$log" 2>&1
    if [ $? -ne 0 ] || grep -q "Traceback" "$log"; then
      echo "  ERROR in $name:"; tail -5 "$log" | sed 's/^/    /'; failed+=("$name"); continue
    fi
    n=$(find "$name" -name 'score_*' | wc -l)
    echo "  $n score files"

    # Evaluate on the matching split if it is here (few-shot: ambg split; zero-shot: random, else ambg)
    if [ "$mode" = "few-shot" ]; then order="ambg"; else order="random ambg"; fi
    split=""
    for p in $order; do
      c="${p}-apcs-${Q}-t${t}-${MODEL}/round-1/selected.json"
      [ -f "$c" ] && { split="$c"; break; }
    done
    if [ -n "$split" ]; then
      python src/eval.py "${name}/" "$Q" APCS "$MODEL" java --seed "$split" > "logs/${name}-eval.log" 2>&1 \
        && echo "  test $(grep -A3 'Test accuracy' "logs/${name}-eval.log" | grep 'Total Accuracy' | head -1 | sed 's/^\s*//')"
    else
      echo "  (no split file for eval yet; outputs are saved)"
    fi
  done
done

[ ${#failed[@]} -gt 0 ] && { echo; echo "Failed: ${failed[*]}"; exit 1; }
echo; echo "Done. Commit and push the llm-judge*-apcs-${Q}-* folders."#!/bin/bash
# LLM-as-a-judge baselines on APCS: zero-shot and few-shot, 3 trials each.
#   Q=2 bash scripts/run_apcs_judges.sh                      # Claude Opus 5, both modes
#   Q=2 MODES=few-shot TRIALS=1 bash scripts/run_apcs_judges.sh
#
# Outputs (same naming as the ambg/random APCS runs, so eval finds them directly):
#   llm-judge-apcs-<q>-t<t>-<model>/      zero-shot
#   llm-judge-fs-apcs-<q>-t<t>-<model>/   few-shot, examples = the 5 samples in
#                                         ambg-apcs-<q>-t<t>-<model>/round-1/selected.json
# Needs (pull from git first):
#   data/apcs/q<q>.txt, data/apcs/rubric_<q>.json,
#   data/apcs/sub/mistakes/<q>/<model>/answer_<a>.txt and manual.csv,
#   ambg-apcs-<q>-t<t>-<model>/round-1/selected.json (few-shot examples and split),
#   random-apcs-<q>-t<t>-<model>/round-1/selected.json (zero-shot split, for eval)
# Existing score files are skipped, so rerunning only fills gaps.

Q="${Q:-2}"
MODEL="${MODEL:-claude-opus-5}"
MODES="${MODES:-zero-shot few-shot}"
TRIALS="${TRIALS:-1 2 3}"

QUESTION="data/apcs/q${Q}.txt"
RUBRIC="data/apcs/rubric_${Q}.json"
ANSWERS="data/apcs/sub/mistakes/${Q}"
for f in "$QUESTION" "$RUBRIC" "$ANSWERS/manual.csv"; do
  [ -e "$f" ] || { echo "Missing $f (git pull?)"; exit 1; }
done

mkdir -p logs
failed=()

for mode in $MODES; do
  if [ "$mode" = "few-shot" ]; then PREFIX="llm-judge-fs"; else PREFIX="llm-judge"; fi
  for t in $TRIALS; do
    name="${PREFIX}-apcs-${Q}-t${t}-${MODEL}"
    log="logs/${name}-geval.log"
    extra=()
    if [ "$mode" = "few-shot" ]; then
      shots="ambg-apcs-${Q}-t${t}-${MODEL}/round-1/selected.json"
      [ -f "$shots" ] || { echo "Skipping $name: no $shots (git pull?)"; failed+=("$name"); continue; }
      extra=(--seed "$shots")
    fi

    echo "[$(date +%T)] Running $name"
    python src/llm_judge_geval_apcs.py "$QUESTION" "$RUBRIC" "$ANSWERS" "${name}/" \
      --model "$MODEL" --sample-num "$Q" "${extra[@]}" > "$log" 2>&1
    if [ $? -ne 0 ] || grep -q "Traceback" "$log"; then
      echo "  ERROR in $name:"; tail -5 "$log" | sed 's/^/    /'; failed+=("$name"); continue
    fi
    n=$(find "$name" -name 'score_*' | wc -l)
    echo "  $n score files"

    # Evaluate on the matching split if it is here (few-shot: ambg split; zero-shot: random, else ambg)
    if [ "$mode" = "few-shot" ]; then order="ambg"; else order="random ambg"; fi
    split=""
    for p in $order; do
      c="${p}-apcs-${Q}-t${t}-${MODEL}/round-1/selected.json"
      [ -f "$c" ] && { split="$c"; break; }
    done
    if [ -n "$split" ]; then
      python src/eval.py "${name}/" "$Q" APCS "$MODEL" java --seed "$split" > "logs/${name}-eval.log" 2>&1 \
        && echo "  test $(grep -A3 'Test accuracy' "logs/${name}-eval.log" | grep 'Total Accuracy' | head -1 | sed 's/^\s*//')"
    else
      echo "  (no split file for eval yet; outputs are saved)"
    fi
  done
done

[ ${#failed[@]} -gt 0 ] && { echo; echo "Failed: ${failed[*]}"; exit 1; }
echo; echo "Done. Commit and push the llm-judge*-apcs-${Q}-* folders."
