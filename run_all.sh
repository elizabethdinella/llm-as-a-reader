#!/bin/bash
# Runs calibrate.py sequentially for Java 3-5, Python 1-5, and C++ 1-5.
# Usage: nohup bash run_all.sh > run_all.log 2>&1 &

MODEL="gpt-oss-120"
CPP="cpp"   # change if calibrate.py expects a different name for C++ (e.g. "c++")

mkdir -p logs

run() {
    local lang=$1
    local n=$2
    local name="ambg-${lang}-${n}"
    echo "[$(date '+%F %T')] starting ${name}"
    python calibrate.py "${name}" RDB "${n}" "${lang}" --model "${MODEL}" \
        > "logs/${name}.log" 2>&1
    echo "[$(date '+%F %T')] finished ${name} (exit $?)"
}

for n in 3 4 5; do run java "$n"; done
for n in 1 2 3 4 5; do run py "$n"; done
for n in 1 2 3 4 5; do run "$CPP" "$n"; done

echo "[$(date '+%F %T')] all done"
