#!/usr/bin/env bash
# Usage: [PREFIX=ambg|random|llm-judge|llm-judge-fs] ./eval.sh <sample_num> <language> [model]
# Example: PREFIX=random ./eval.sh 3 java
# Runs eval.py for trials t1, t2, t3, then prints train/test metrics for each.
#
# llm-judge (G-Eval baseline) runs have no round-1/ or selected.json. They are
# scored against the matching random trial's selected.json (falling back to
# ambg), so every method is evaluated on the same train/test split.

if [ $# -lt 2 ]; then
  echo "Usage: [PREFIX=...] $0 <sample_num> <language> [model]"
  exit 1
fi

N="$1"
LANG_NAME="$2"
MODEL="${3:-gpt-oss-120}"
PREFIX="${PREFIX:-ambg}"

mkdir -p logs
SUMMARY=$(mktemp)
failed=()

# Pull metrics out of one eval.py log. Prints one line per split:
# trial split n score_acc total_acc
parse_log() {
  awk -v trial="$2" '
    /Train accuracy/   { s = "train" }
    /Test accuracy/    { s = "test" }
    /total samples:/   { n[s]  = $NF }
    /Score Accuracy:/  { sa[s] = $NF }
    /Total Accuracy:/  { ta[s] = $NF }
    END {
      split("train test", order, " ")
      for (i = 1; i <= 2; i++) {
        k = order[i]
        if (k in n)
          printf "%s %s %s %.3f %.3f\n", trial, k, n[k], sa[k], ta[k]
      }
    }' "$1"
}

for T in 1 2 3; do
  RUN="${PREFIX}-${LANG_NAME}-${N}-t${T}-${MODEL}"
  LOG="logs/${RUN}-eval.log"

  if [ "$PREFIX" = "llm-judge" ] || [ "$PREFIX" = "llm-judge-fs" ]; then
    PRED_DIR="${RUN}/"
    SEED=""
    # Few-shot judge: its examples came from the ambg selection, so that is
    # its train set. Zero-shot judge: use the random split (then ambg).
    if [ "$PREFIX" = "llm-judge-fs" ]; then order="ambg"; else order="random ambg"; fi
    for p in $order; do
      cand="${p}-${LANG_NAME}-${N}-t${T}-${MODEL}/round-1/selected.json"
      if [ -f "$cand" ]; then SEED="$cand"; break; fi
    done
    if [ -z "$SEED" ]; then
      echo "=== Trial ${T}: ${PRED_DIR} ==="
      echo "Trial ${T} skipped: no random/ambg selected.json to define the split"
      failed+=("$T")
      continue
    fi
  else
    PRED_DIR="${RUN}/round-1/preds/${LANG_NAME}/"
    SEED="${RUN}/round-1/selected.json"
  fi

  echo "=== Trial ${T}: ${PRED_DIR} (split: ${SEED}) ==="
  python eval.py "$PRED_DIR" "$N" RDB "$MODEL" "$LANG_NAME" \
    --seed "$SEED" > "$LOG" 2>&1

  if grep -q "Traceback" "$LOG"; then
    echo "Trial ${T} failed, last lines of ${LOG}:"
    tail -3 "$LOG"
    failed+=("$T")
  else
    parse_log "$LOG" "t${T}" >> "$SUMMARY"
  fi
done

echo
echo "=== Summary: ${PREFIX}, ${LANG_NAME}, sample ${N}, ${MODEL} ==="
FMT="%-6s %-6s %4s %10s %10s\n"
printf "$FMT" trial split n score_acc total_acc
sort -k2,2r -k1,1 "$SUMMARY" | while read -r a b c d e; do
  printf "$FMT" "$a" "$b" "$c" "$d" "$e"
done
# Mean across trials for each split
awk -v fmt="$FMT" '{ c[$2]++; for (i = 4; i <= 5; i++) s[$2, i] += $i }
     END {
       split("train test", order, " ")
       for (j = 1; j <= 2; j++) {
         k = order[j]
         if (c[k]) {
           for (i = 4; i <= 5; i++) m[i] = sprintf("%.3f", s[k, i] / c[k])
           printf fmt, "mean", k, "-", m[4], m[5]
         }
       }
     }' "$SUMMARY"

rm -f "$SUMMARY"

if [ ${#failed[@]} -gt 0 ]; then
  echo "Failed trials: ${failed[*]}"
  exit 1
fi
