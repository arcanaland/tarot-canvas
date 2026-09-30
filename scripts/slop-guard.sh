#!/bin/bash
set -euo pipefail

pattern='(^|[^[:alnum:]_])(RFC|ADR|TASK)-[0-9]+'

if [ $# -eq 0 ]; then
  source=()
  set -- '*.py' '*.sh' '*.just' 'justfile'
else
  source=(--cached)
fi

if git grep -nE ${source[@]+"${source[@]}"} "$pattern" -- "$@"; then
  echo "slop detected"
  exit 1
fi
