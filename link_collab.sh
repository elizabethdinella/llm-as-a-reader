#!/bin/bash
# Map the collaborator's Claude llm-judge folders to the names compare_all.sh
# expects, using symlinks so their git-tracked folders are left untouched.
#   llm-judge-java3-claude-2     -> llm-judge-java-3-t2-claude-opus-5
#   llm-judge-java1-claude-fs-3  -> llm-judge-fs-java-1-t3-claude-opus-5
# Folders without a trial number (e.g. llm-judge-java1-claude) are reported
# and skipped, since it's unclear which trial they are.

re='^llm-judge-([a-z]+)([0-9]+)-claude(-fs)?-([0-9]+)$'
for d in llm-judge-*claude*/; do
  d=${d%/}
  [ -L "$d" ] && continue                      # one of our own links
  if [[ $d =~ $re ]]; then
    lang=${BASH_REMATCH[1]}; n=${BASH_REMATCH[2]}; fs=${BASH_REMATCH[3]}; t=${BASH_REMATCH[4]}; [ "$lang" = py ] && lang=python
    if [ -n "$fs" ]; then target="llm-judge-fs-${lang}-${n}-t${t}-claude-opus-5"
    else target="llm-judge-${lang}-${n}-t${t}-claude-opus-5"; fi
    if [ -e "$target" ] && [ ! -L "$target" ]; then
      echo "SKIP $d: $target already exists as a real folder (remove it to use the collaborator's)"
    else
      ln -sfn "$d" "$target"
      echo "linked $target -> $d"
    fi
  elif [[ $d =~ ^llm-judge-[a-z]+[0-9]+-claude ]]; then
    echo "SKIP $d: no trial number in the name"
  fi
done
