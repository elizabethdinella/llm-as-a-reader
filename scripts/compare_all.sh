#!/usr/bin/env bash
# Usage: ./compare_all.sh <sample_num> <language>
# Example: ./compare_all.sh 3 java
#
# Evaluates every method x backbone for one question and prints one table:
#   methods:   ambg, random, llm-judge (zero-shot G-Eval), llm-judge-fs (few-shot)
#   backbones: claude-opus-5, gpt-oss-120
# Each row is the mean over trials t1-t3. Missing or failed trials are skipped
# and the "trials" column shows how many were averaged.
#
# Splits: ambg/random use their own selected.json. llm-judge uses the random
# split (else ambg), llm-judge-fs uses the ambg split (its few-shot examples),
# so methods are compared on the same test samples where possible.

if [ $# -lt 2 ]; then
  echo "Usage: $0 <sample_num> <language>"
  exit 1
fi

N="$1"
LANG_NAME="$2"
MODELS="${MODELS:-claude-opus-5 gpt-oss-120}"
METHODS="${METHODS:-ambg random llm-judge llm-judge-fs}"

mkdir -p logs
ROWS=$(mktemp)
NOTES=$(mktemp)

# One line per split: split n total_acc
parse_log() {
  awk '
    /Train accuracy/   { s = "train" }
    /Test accuracy/    { s = "test" }
    /total samples:/   { n[s] = $NF }
    /Total Accuracy:/  { a[s] = $NF }
    END {
      split("train test", order, " ")
      for (i = 1; i <= 2; i++) {
        k = order[i]
        if (k in n) printf "%s %s %s\n", k, n[k], a[k]
      }
    }' "$1"
}

find_seed() {  # find_seed <prefix list> <trial> <model>
  for p in $1; do
    cand="${p}-${LANG_NAME}-${N}-t${2}-${3}/round-1/selected.json"
    if [ -f "$cand" ]; then echo "$cand"; return; fi
  done
}

for MODEL in $MODELS; do
  for METHOD in $METHODS; do
    for T in 1 2 3; do
      RUN="${METHOD}-${LANG_NAME}-${N}-t${T}-${MODEL}"
      LOG="logs/${RUN}-eval.log"

      case "$METHOD" in
        llm-judge)    PRED_DIR="${RUN}/"; SEED=$(find_seed "random ambg" "$T" "$MODEL") ;;
        llm-judge-fs) PRED_DIR="${RUN}/"; SEED=$(find_seed "ambg" "$T" "$MODEL") ;;
        *)            PRED_DIR="${RUN}/round-1/preds/${LANG_NAME}/"
                      SEED="${RUN}/round-1/selected.json" ;;
      esac

      if [ ! -d "$PRED_DIR" ]; then
        echo "$MODEL $METHOD t$T: missing (no $PRED_DIR)" >> "$NOTES"
        continue
      fi
      if [ -z "$SEED" ] || [ ! -f "$SEED" ]; then
        echo "$MODEL $METHOD t$T: missing split file" >> "$NOTES"
        continue
      fi

      echo "Evaluating $RUN" >&2
      python src/eval.py "$PRED_DIR" "$N" RDB "$MODEL" "$LANG_NAME" \
        --seed "$SEED" > "$LOG" 2>&1

      if grep -q "Traceback" "$LOG"; then
        echo "$MODEL $METHOD t$T: failed ($(tail -1 "$LOG")) see $LOG" >> "$NOTES"
        continue
      fi

      parse_log "$LOG" | while read -r split n a; do
        echo "$MODEL $METHOD $split $n $a" >> "$ROWS"
      done
    done
  done
done

echo
echo "=== ${LANG_NAME} sample ${N}: mean over trials ==="
FMT="%-14s %-13s %-6s %6s %4s %9s\n"
printf "$FMT" model method split trials n total_acc
for split in test train; do
  awk -v want="$split" -v fmt="$FMT" -v models="$MODELS" -v methods="$METHODS" '
    $3 == want {
      k = $1 SUBSEP $2
      c[k]++; n[k] = $4
      s[k] += $5
    }
    END {
      nm = split(models, M, " "); nt = split(methods, T, " ")
      for (i = 1; i <= nm; i++) for (j = 1; j <= nt; j++) {
        k = M[i] SUBSEP T[j]
        if (!(k in c)) continue
        printf fmt, M[i], T[j], want, c[k], n[k], sprintf("%.3f", s[k]/c[k])
      }
    }' "$ROWS"
done

if [ -s "$NOTES" ]; then
  echo
  echo "Skipped:"
  sed 's/^/  /' "$NOTES"
fi

rm -f "$ROWS" "$NOTES"
