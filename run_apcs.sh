#!/bin/bash
# APCS runs for one backbone: ambg and random calibration (3 trials each), then eval.
#   Q=2 MODEL=claude-opus-5 bash run_apcs.sh
#   Q=2 METHODS=ambg TRIALS=1 bash run_apcs.sh      # quick check first
# Runs are named <method>-apcs-<q>-t<trial>-<model>. Logs in logs/.
# Needs: test/apcs/sub/mistakes/<q>/ (answers + manual.csv), test/apcs/rubric_<q>.json,
#        scratch-apcs/java/<q>/ (ambiguities), cache-apcs-<model>/<q>/ (warmed).
export PATH="$HOME/miniconda3/envs/py39/bin:$PATH"

Q="${Q:-2}"
MODEL="${MODEL:-claude-opus-5}"
METHODS="${METHODS:-ambg random}"
TRIALS="${TRIALS:-1 2 3}"
LANG_ARG=java          # APCS questions are Java; consts.lang is used in paths
mkdir -p logs
failed=()

for method in $METHODS; do
  extra=()
  [ "$method" = "random" ] && extra=(--selection-method random)
  for t in $TRIALS; do
    name="${method}-apcs-${Q}-t${t}-${MODEL}"
    log="logs/${name}-calibrate.log"
    echo "[$(date +%T)] Running $name"
    python calibrate.py "$name/" APCS "$Q" "$LANG_ARG" --model "$MODEL" "${extra[@]}" > "$log" 2>&1
    # calibrate.py exits 1 after one round by design; tracebacks are the real failures
    if grep -q "Traceback" "$log"; then
      echo "  ERROR in $name:"; tail -5 "$log" | sed 's/^/    /'; failed+=("$name"); continue
    fi

    pred=$(find "$name/round-1/preds" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -1)
    elog="logs/${name}-eval.log"
    python eval.py "$pred/" "$Q" APCS "$MODEL" "$LANG_ARG" --seed "$name/round-1/selected.json" > "$elog" 2>&1
    if grep -q "Traceback" "$elog"; then
      echo "  EVAL ERROR in $name:"; tail -5 "$elog" | sed 's/^/    /'; failed+=("$name-eval"); continue
    fi
    echo "  $(grep -A3 'Test accuracy' "$elog" | grep 'Total Accuracy' | head -1 | sed 's/^\s*//')  (test)"
  done
done

echo
echo "=== APCS q${Q} ${MODEL}: mean test total accuracy ==="
for method in $METHODS; do
  grep -h -A3 'Test accuracy' logs/${method}-apcs-${Q}-t*-${MODEL}-eval.log 2>/dev/null \
    | awk -v m="$method" '/Total Accuracy/ {s+=$NF; n++} END {if (n) printf "%-8s %d trials  %.3f\n", m, n, s/n}'
done
[ ${#failed[@]} -gt 0 ] && echo "Failed: ${failed[*]}"
