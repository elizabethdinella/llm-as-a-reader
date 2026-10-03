#!/bin/bash
# Exact-match accuracy for APCS runs, parsed from the per-sample eval logs
# (each sample block has "Split:  train|test" and "error?     True|False").
#   bash apcs_summary.sh 2              # q2, all models/methods with logs
#   bash apcs_summary.sh 2 claude-opus-5
Q="${1:-2}"
MODEL="${2:-*}"

printf "%-14s %-13s %-6s %5s %3s %9s\n" model method split trial n acc
for log in logs/*-apcs-${Q}-t*-${MODEL}-eval.log; do
  [ -f "$log" ] || continue
  run=$(basename "$log" -eval.log)                   # e.g. ambg-apcs-2-t1-claude-opus-5
  method=${run%%-apcs-*}
  rest=${run#*-apcs-${Q}-t}; trial=${rest%%-*}; model=${rest#*-}
  awk -v m="$model" -v me="$method" -v t="$trial" '
    /Split:/            { split_ = $NF }
    /^error\?/          { n[split_]++; if ($NF == "False") ok[split_]++ }
    END { for (s in n) printf "%-14s %-13s %-6s %5s %3d %9.3f\n", m, me, s, "t" t, n[s], ok[s] / n[s] }' "$log"
done | sort -k1,1 -k2,2 -k3,3r -k4,4 | tee /tmp/apcs_rows.$$

echo
echo "=== APCS q${Q}: mean over trials ==="
printf "%-14s %-13s %-6s %6s %9s\n" model method split trials acc
awk '{ k = $1 " " $2 " " $3; c[k]++; s[k] += $6 }
     END { for (k in c) { split(k, a, " "); printf "%-14s %-13s %-6s %6d %9.3f\n", a[1], a[2], a[3], c[k], s[k] / c[k] } }' \
  /tmp/apcs_rows.$$ | sort -k1,1 -k3,3r -k5,5nr
rm -f /tmp/apcs_rows.$$
