#!/bin/bash
# Run the G-Eval LLM-judge baselines for 3 trials each, then evaluate:
#   llm-judge     zero-shot
#   llm-judge-fs  few-shot, using the samples selected in the matching
#                 ambg-<lang>-<sample>-t<trial>-<model>/round-1/selected.json
# Defaults: all langs/samples/modes below. Override for a quick check, e.g.:
#   LANGS=java SAMPLES=3 bash scripts/run_llm_judge_gpt-oss.sh
#   MODES=few-shot LANGS=java SAMPLES=3 bash scripts/run_llm_judge_gpt-oss.sh

MODEL="${MODEL:-gpt-oss-120}"
LANGS="${LANGS:-java py}"
SAMPLES="${SAMPLES:-3 4 5}"
MODES="${MODES:-zero-shot few-shot}"

DATASET_ROOT="../crqbench/artifact/dataset"
PROJECTS_DIR="../crqbench/projects/"
ANSWER_ROOT="data/rdb/out"

mkdir -p logs
failed=()

for lang in $LANGS; do
  for sample in $SAMPLES; do
    for mode in $MODES; do
      if [ "$mode" = "few-shot" ]; then PREFIX="llm-judge-fs"; else PREFIX="llm-judge"; fi

      for trial in 1 2 3; do
        name="${PREFIX}-${lang}-${sample}-t${trial}-${MODEL}"
        log="logs/${name}-geval.log"
        extra=()

        if [ "$mode" = "few-shot" ]; then
          shots="ambg-${lang}-${sample}-t${trial}-${MODEL}/round-1/selected.json"
          if [ ! -f "$shots" ]; then
            echo "Skipping $name: no few-shot samples at $shots"
            failed+=("$name")
            continue
          fi
          extra=(--seed "$shots")
        fi

        echo "Running $name"
        start=$(date +%s)
        python src/llm_judge_geval.py "$sample" "${DATASET_ROOT}/${lang}/" "$PROJECTS_DIR" \
          "${ANSWER_ROOT}/${lang}/" "${name}/" "$lang" --model "$MODEL" "${extra[@]}" \
          > "$log" 2>&1
        status=$?
        echo "  finished in $(( $(date +%s) - start ))s (exit $status)"

        if [ $status -ne 0 ] || grep -q "Traceback" "$log"; then
          echo "  ERROR in $name, last lines of $log:"
          tail -5 "$log" | sed 's/^/    /'
          failed+=("$name")
        fi
      done

      echo
      PREFIX="$PREFIX" bash scripts/eval.sh "$sample" "$lang" "$MODEL"
      echo
    done
  done
done

if [ ${#failed[@]} -gt 0 ]; then
  echo
  echo "Failed runs: ${failed[*]}"
  exit 1
fi
