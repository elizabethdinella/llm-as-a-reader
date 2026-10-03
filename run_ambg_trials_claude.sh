#!/bin/bash
# Run ambiguity calibration with a Claude backbone.
# Defaults: all langs/samples below. Override for a quick check, e.g.:
#   LANGS=java SAMPLES=3 bash run_ambg_trials_claude.sh

MODEL="${MODEL:-claude-opus-5}"
LANGS="${LANGS:-java python}"
SAMPLES="${SAMPLES:-3 4 5}"

mkdir -p logs
failed=()

for lang in $LANGS; do
  for sample in $SAMPLES; do
    for trial in 1 2 3; do
      name="ambg-${lang}-${sample}-t${trial}-${MODEL}"
      log="logs/${name}-calibrate.log"
      echo "Running $name"
      start=$(date +%s)
      python calibrate.py "$name/" RDB "$sample" "$lang" --model "$MODEL" \
        > "$log" 2>&1
      status=$?
      echo "  finished in $(( $(date +%s) - start ))s (exit $status)"

      # calibrate.py ends with sys.exit(1) after one round, so exit 1 is normal.
      # Flag tracebacks instead.
      if grep -q "Traceback" "$log"; then
        echo "  ERROR in $name, last lines of $log:"
        tail -5 "$log" | sed 's/^/    /'
        failed+=("$name")
      fi
    done

    echo
    bash eval.sh "$sample" "$lang" "$MODEL"
    echo
  done
done

if [ ${#failed[@]} -gt 0 ]; then
  echo
  echo "Failed runs: ${failed[*]}"
  exit 1
fi
