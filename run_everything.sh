#!/bin/bash
# Overnight run: every configuration for both backbones, one question at a time.
# Start it so it survives closing the terminal:
#   nohup bash run_everything.sh > run_everything.out 2>&1 &
# Progress:        tail -f run_everything.out   (or results/latest/progress.log)
# In the morning:  cat results/latest/summary.txt
#
# For each question: check out the project, then run in parallel
#   claude-opus-5 (API):    ambg -> random   (Claude llm-judge: collaborator)
#   gpt-oss-120 (GPU 0):    ambg -> random -> llm-judge -> llm-judge-fs
# Everything finishes before the next checkout, so all runs for a question see
# the same checked-out code.

export PATH="$HOME/miniconda3/envs/py39/bin:$PATH"   # same env as manual runs

QUESTIONS="${QUESTIONS:-java:3 java:4 java:5 py:1 py:2 py:3 py:4 py:5}"
RUN_MODELS="${RUN_MODELS:-claude gpt-oss}"     # e.g. RUN_MODELS=claude for Claude only
CLAUDE_WORKERS="${CLAUDE_WORKERS:-16}"          # parallel API calls when filling the cache
GPTOSS_WORKERS="${GPTOSS_WORKERS:-4}"           # parallel Ollama requests (queued if Ollama allows fewer)

# Put ../crqbench/projects/ in the state the question was asked about.
# clone first (it fails harmlessly if the repo is already there), then checkout,
# which must succeed. Dataset path follows crqbench/framework/README.md.
checkout_sample() {  # checkout_sample <lang> <sample_num>
  local dlang="$1"
  [ "$dlang" = "py" ] && dlang="python"     # crqbench's dataset folder is "python", not "py"
  ( cd ../crqbench/framework || exit 1
    python utils.py ../projects/ "$2" "../dataset/$dlang/" clone || true
    python utils.py ../projects/ "$2" "../dataset/$dlang/" checkout )
}

# Commit and push the Claude round-1 selections for one question so the
# collaborator can use them (ambg and random, all trials). Only these files
# are committed; anything else in the working tree is left alone.
push_selected() {  # push_selected <lang> <sample_num>
  files=$(ls ambg-$1-$2-t*-claude-opus-5/round-1/selected.json \
             random-$1-$2-t*-claude-opus-5/round-1/selected.json 2>/dev/null)
  [ -z "$files" ] && { echo "no Claude selected.json files to push"; return 1; }
  git add -f $files &&
  { git diff --cached --quiet -- $files && echo "selected.json already up to date"; } ||
  { git commit -m "Claude opus-5 round-1 selected samples: $1 sample $2" -- $files &&
    git pull --rebase --autostash && git push; }
}

STAMP=$(date +%Y%m%d-%H%M)
OUT="results/${STAMP}"
mkdir -p "$OUT" logs
ln -sfn "$STAMP" results/latest
SUMMARY="$OUT/summary.txt"

# Flag runs that may have been built from the wrong question's answers
# (the old Sample.from_dict bug). Nothing is deleted, only reported.
suspect_check() {
  for d in ambg-*-t[0-9]-*/round-1 random-*-t[0-9]-*/round-1; do
    [ -f "$d/selected.json" ] || continue
    grep -q sample_num "$d/selected.json" && continue   # written after the fix
    sel=$(stat -c %Y "$d/selected.json")
    for f in "$d/ambiguities.json" "$d/notes.json"; do
      [ -f "$f" ] || continue
      t=$(stat -c %Y "$f")
      if [ $((t - sel)) -gt 1800 ]; then
        echo "SUSPECT $d: $(basename "$f") written $(( (t - sel) / 60 )) min after selection"
      fi
    done
    if [ -f "$d/notes.json" ] && [ -d "$d/preds" ]; then
      n=$(stat -c %Y "$d/notes.json")
      p=$(find "$d/preds" -name 'score_*' -printf '%T@\n' | sort -n | tail -1 | cut -d. -f1)
      if [ -n "$p" ] && [ $((p - n)) -gt 1800 ]; then
        echo "SUSPECT $d: last pred written $(( (p - n) / 60 )) min after notes"
      fi
    fi
  done
}

# Progress lines go to the terminal (or run_everything.out under nohup) and to
# progress.log, even from the background jobs whose output goes to log files.
exec 3>&1
progress() { echo "[$(date '+%T')] $*" | tee -a "$OUT/progress.log" >&3; }

# How many of the 3 trials of one configuration already have outputs.
existing() {  # existing <method> <lang> <sample> <model>
  local c=0 t d
  for t in 1 2 3; do
    d="$1-$2-$3-t${t}-$4"
    case "$1" in
      cache) ;;
      llm-judge*) [ -n "$(ls -A "$d" 2>/dev/null)" ] && c=$((c+1)) ;;
      *) [ -n "$(find "$d/round-1/preds" -name 'score_*' 2>/dev/null | head -1)" ] && c=$((c+1)) ;;
    esac
  done
  echo $c
}

# Run one configuration (3 trials) with start/finish progress lines.
step() {  # step <model> <method> <lang> <sample> <command...>
  local model=$1 method=$2 lang=$3 smp=$4; shift 4
  local have; have=$(existing "$method" "$lang" "$smp" "$model")
  local note=""
  [ "$have" -gt 0 ] && note=" ($have/3 trials already have outputs; reusing them)"
  progress "START  ${lang} ${smp}  ${model}  ${method}${note}"
  local t0; t0=$(date +%s)
  "$@"
  progress "DONE   ${lang} ${smp}  ${model}  ${method}  ($(( ($(date +%s) - t0) / 60 )) min)"
}

echo "Started $(date '+%F %T')" | tee "$SUMMARY"
{
  echo
  echo "=== Pre-run check for runs built on the wrong question's answers ==="
  out=$(suspect_check)
  if [ -n "$out" ]; then echo "$out"; echo "(Not deleted. Check these before trusting their rows.)"
  else echo "None found."; fi
} | tee -a "$SUMMARY"


for q in $QUESTIONS; do
  lang=${q%%:*}; s=${q##*:}
  QLOG="$OUT/${lang}-${s}"
  echo | tee -a "$SUMMARY"
  echo "######## ${lang} ${s}: start $(date '+%F %T')" | tee -a "$SUMMARY"
  progress "CHECKOUT ${lang} ${s}"

  if ! checkout_sample "$lang" "$s" > "${QLOG}-checkout.log" 2>&1; then
    echo "CHECKOUT FAILED for ${lang} ${s}, skipping (see ${QLOG}-checkout.log)" | tee -a "$SUMMARY"
    continue
  fi

  # Claude: ambg -> random (Claude llm-judge runs are done by the collaborator)
  if [[ " $RUN_MODELS " == *" claude "* ]]; then
  ( export MODEL=claude-opus-5 LANGS=$lang SAMPLES=$s
    step claude-opus-5 cache  $lang $s python warm_cache.py $s $lang --model claude-opus-5 --workers $CLAUDE_WORKERS
    step claude-opus-5 ambg   $lang $s bash run_ambg_trials.sh
    step claude-opus-5 random $lang $s bash run_random_trials.sh
  ) > "${QLOG}-claude.log" 2>&1 &
  fi

  # gpt-oss on GPU 0 (system Ollama server): ambg -> random -> both judges
  if [[ " $RUN_MODELS " == *" gpt-oss "* ]]; then
  ( export MODEL=gpt-oss-120 LANGS=$lang SAMPLES=$s OLLAMA_HOST=127.0.0.1:11434
    step gpt-oss-120 cache        $lang $s python warm_cache.py $s $lang --model gpt-oss-120 --workers $GPTOSS_WORKERS
    step gpt-oss-120 ambg         $lang $s bash run_ambg_trials.sh
    step gpt-oss-120 random       $lang $s bash run_random_trials.sh
    step gpt-oss-120 llm-judge    $lang $s env MODES=zero-shot bash run_llm_judge_gpt-oss.sh
    step gpt-oss-120 llm-judge-fs $lang $s env MODES=few-shot bash run_llm_judge_gpt-oss.sh
  ) > "${QLOG}-gpt-oss.log" 2>&1 &
  fi

  # Any other API backbone named in RUN_MODELS (e.g. gpt-5): all five steps.
  for M in $RUN_MODELS; do
    case "$M" in claude|gpt-oss) continue ;; esac
    ( export MODEL=$M LANGS=$lang SAMPLES=$s
      step $M cache        $lang $s python warm_cache.py $s $lang --model $M --workers ${API_WORKERS:-16}
      step $M ambg         $lang $s bash run_ambg_trials.sh
      step $M random       $lang $s bash run_random_trials.sh
      step $M llm-judge    $lang $s env MODES=zero-shot bash run_llm_judge_gpt-oss.sh
      step $M llm-judge-fs $lang $s env MODES=few-shot bash run_llm_judge_gpt-oss.sh
    ) > "${QLOG}-${M}.log" 2>&1 &
  done

  wait
  echo "######## ${lang} ${s}: done $(date '+%F %T')" | tee -a "$SUMMARY"
  if push_selected "$lang" "$s" > "${QLOG}-push.log" 2>&1; then
    echo "Pushed Claude selected.json for ${lang} ${s}" | tee -a "$SUMMARY"
  else
    echo "PUSH FAILED for ${lang} ${s} (see ${QLOG}-push.log)" | tee -a "$SUMMARY"
  fi
  [ -f link_collab.sh ] && bash link_collab.sh > "${QLOG}-links.log" 2>&1   # collaborator's Claude judge runs
  bash compare_all.sh "$s" "$lang" 2>/dev/null | tee -a "$SUMMARY"
  grep -h "ERROR in\|Failed runs" "${QLOG}"-*.log | sed 's/^/  /' >> "$SUMMARY"
done

echo | tee -a "$SUMMARY"
echo "All finished $(date '+%F %T')" | tee -a "$SUMMARY"
